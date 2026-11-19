"""Chamada real a um modelo de IA, feita somente no servidor.

Por padrão usa a API Messages da Anthropic. Para trocar de provedor, ajuste
`explicar_resposta` (URL, cabeçalhos e formato do corpo/resposta).
"""
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)

AVISO = "Explicação gerada por IA, que pode errar. Confira em fontes confiáveis."

SISTEMA = (
    "Você é um tutor de estudos. Responda sempre em português do Brasil, de forma clara e didática, "
    "em no máximo 120 palavras. Não invente fatos: se não tiver certeza de algo, diga."
)


class IAErro(Exception):
    """Falha ao consultar o provedor de IA."""


class IANaoConfigurada(IAErro):
    """AI_API_KEY não foi definida."""


def montar_prompt(item):
    pergunta = item.pergunta
    letras = "ABCDEFGH"
    alternativas = list(pergunta.alternativas.all())
    linhas = [f"{letras[i]}) {a.texto}" for i, a in enumerate(alternativas)]
    correta = next((a for a in alternativas if a.correta), None)
    veredito = "correta" if item.correta else "incorreta"
    partes = [
        f"Assunto: {pergunta.assunto.nome}",
        f"Pergunta: {pergunta.texto}",
        "Alternativas:\n" + "\n".join(linhas),
        f"Alternativa escolhida pelo aluno: {item.resposta.texto} ({veredito})",
        f"Alternativa correta: {correta.texto if correta else 'não informada'}",
    ]
    if pergunta.explicacao:
        partes.append(f"Nota do professor: {pergunta.explicacao}")
    partes.append(
        "Tarefa: explique por que a alternativa correta está certa. Se o aluno errou, explique o erro mais "
        "provável e dê uma dica curta para não esquecer. Se acertou, reforce o conceito em uma ou duas frases."
    )
    return "\n\n".join(partes)


def explicar_resposta(item, timeout=25):
    chave = settings.AI_API_KEY
    if not chave:
        raise IANaoConfigurada("AI_API_KEY não configurada")
    try:
        resp = requests.post(
            settings.AI_API_URL,
            headers={"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": settings.AI_MODEL,
                "max_tokens": 400,
                "system": SISTEMA,
                "messages": [{"role": "user", "content": montar_prompt(item)}],
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        log.warning("Falha de rede ao chamar a IA: %s", exc.__class__.__name__)
        raise IAErro("Não foi possível falar com o provedor de IA") from exc
    if resp.status_code != 200:
        log.warning("Provedor de IA respondeu %s", resp.status_code)  # nunca registrar a chave
        raise IAErro(f"Provedor de IA respondeu {resp.status_code}")
    try:
        blocos = resp.json()["content"]
        texto = "".join(b.get("text", "") for b in blocos if b.get("type") == "text").strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise IAErro("Resposta inesperada do provedor de IA") from exc
    if not texto:
        raise IAErro("O provedor de IA devolveu uma resposta vazia")
    return texto
