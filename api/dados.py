"""Monta os dicionários de resposta da API (nunca expõe qual alternativa é a correta antes da hora)."""
from quiz.models import Answer
from quiz.servicos import alternativas_embaralhadas, pergunta_atual


def pergunta_dict(item):
    return {
        "item_id": item.pk,  # id da resposta dentro da rodada; usado também no endpoint de IA
        "numero": item.ordem + 1,
        "pergunta": {
            "id": item.pergunta_id,
            "texto": item.pergunta.texto,
            "assunto": item.pergunta.assunto.nome,
            "alternativas": [{"id": a.pk, "texto": a.texto} for a in alternativas_embaralhadas(item)],
        },
    }


def contagens(tentativa):
    respondidas = tentativa.respostas.filter(resposta__isnull=False)
    return {
        "respondidas": respondidas.count(),
        "acertos": respondidas.filter(correta=True).count(),
        "erros": respondidas.filter(correta=False).count(),
    }


def estado_rodada(tentativa):
    atual = None if tentativa.finalizada else pergunta_atual(tentativa)
    return {
        "id": tentativa.pk,
        "rotulo": tentativa.rotulo,
        "categoria": {"id": tentativa.quiz.categoria_id, "nome": tentativa.quiz.categoria.nome},
        "assunto": tentativa.assunto.nome if tentativa.assunto_id else None,
        "modo": tentativa.modo,
        "total": tentativa.total,
        **contagens(tentativa),
        "finalizada": tentativa.finalizada,
        "pergunta": pergunta_dict(atual) if atual else None,
    }


def resultado_rodada(tentativa):
    respostas = list(tentativa.respostas.select_related("pergunta__assunto", "resposta"))
    corretas = {
        a.pergunta_id: a.texto
        for a in Answer.objects.filter(pergunta_id__in=[r.pergunta_id for r in respostas], correta=True)
    }
    analise = tentativa.analise
    return {
        "id": tentativa.pk,
        "rotulo": tentativa.rotulo,
        "categoria": {"id": tentativa.quiz.categoria_id, "nome": tentativa.quiz.categoria.nome},
        "assunto": tentativa.assunto.nome if tentativa.assunto_id else None,
        "modo": tentativa.modo,
        "iniciado_em": tentativa.iniciado_em,
        "finalizado_em": tentativa.finalizado_em,
        "total": tentativa.total,
        "acertos": tentativa.acertos,
        "erros": tentativa.erros,
        "percentual": tentativa.percentual,
        "analise": {
            "por_assunto": analise.por_assunto,
            "diagnostico": analise.diagnostico,
            "recomendacoes": analise.recomendacoes,
            "variacao": analise.variacao,
        },
        "respostas": [
            {
                "item_id": r.pk,
                "numero": r.ordem + 1,
                "pergunta": r.pergunta.texto,
                "assunto": r.pergunta.assunto.nome,
                "escolhida": r.resposta.texto if r.resposta_id else None,
                "correta": corretas.get(r.pergunta_id, ""),
                "acertou": r.correta,
                "explicacao": r.pergunta.explicacao,
                "explicacao_ia": r.explicacao_ia,
            }
            for r in respostas
        ],
    }
