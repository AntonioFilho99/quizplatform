"""Análise de desempenho baseada em regras (sem IA na v1)."""
from collections import OrderedDict

from django.conf import settings
from django.utils import timezone

from .models import PerformanceAnalysis, QuizAttempt, UserResponse


def _pct(acertos, total):
    return round(100 * acertos / total, 1) if total else 0.0


def finalizar_tentativa(tentativa):
    """Fecha a rodada, calcula números e grava a análise. Idempotente."""
    if tentativa.finalizada:
        return tentativa.analise

    respostas = list(tentativa.respostas.select_related("pergunta__assunto"))
    total = len(respostas)
    acertos = sum(1 for r in respostas if r.correta)
    tentativa.total = total
    tentativa.acertos = acertos
    tentativa.erros = total - acertos
    tentativa.percentual = _pct(acertos, total)
    tentativa.finalizado_em = timezone.now()
    tentativa.save()

    por_assunto = OrderedDict()
    for r in respostas:
        nome = r.pergunta.assunto.nome
        d = por_assunto.setdefault(nome, {"assunto": nome, "acertos": 0, "erros": 0})
        d["acertos" if r.correta else "erros"] += 1
    linhas = []
    for d in por_assunto.values():
        t = d["acertos"] + d["erros"]
        d["total"] = t
        d["percentual"] = _pct(d["acertos"], t)
        linhas.append(d)

    minimo = settings.MIN_RESPOSTAS_ASSUNTO
    dificuldades = [d for d in linhas if d["total"] >= minimo and d["percentual"] < settings.LIMITE_DIFICULDADE]
    fortes = [d for d in linhas if d["total"] >= minimo and d["percentual"] >= settings.LIMITE_DOMINIO]

    partes = []
    if fortes:
        partes.append("Bom desempenho em " + ", ".join(d["assunto"] for d in fortes) + ".")
    if dificuldades:
        partes.append("Dificuldades em " + ", ".join(d["assunto"] for d in dificuldades) + ".")
    if not fortes and not dificuldades:
        partes.append("Desempenho intermediário ou poucas respostas por assunto para uma conclusão firme.")
    diagnostico = " ".join(partes)

    recomendacoes = ""
    if dificuldades:
        recomendacoes = "Priorize a revisão de: " + ", ".join(d["assunto"] for d in dificuldades) + ". Refaça o quiz após estudar."
    elif fortes and len(fortes) == len(linhas):
        recomendacoes = "Ótimo resultado! Tente uma categoria nova ou aumente a dificuldade."
    else:
        recomendacoes = "Continue praticando para consolidar os assuntos."

    anterior = (
        QuizAttempt.objects.filter(
            usuario=tentativa.usuario, quiz__categoria=tentativa.quiz.categoria, finalizado_em__isnull=False,
            modo=tentativa.modo, assunto=tentativa.assunto,  # compara só rodadas do mesmo tipo
        )
        .exclude(pk=tentativa.pk)
        .order_by("-finalizado_em")
        .first()
    )
    variacao = round(tentativa.percentual - anterior.percentual, 1) if anterior else None

    return PerformanceAnalysis.objects.create(
        tentativa=tentativa,
        por_assunto=linhas,
        diagnostico=diagnostico,
        recomendacoes=recomendacoes,
        variacao=variacao,
    )


def ids_para_revisar(usuario):
    """Perguntas cuja resposta MAIS RECENTE do usuário foi errada (ainda não dominadas)."""
    ultimo = {}
    respostas = (
        UserResponse.objects.filter(tentativa__usuario=usuario, resposta__isnull=False)
        .order_by("tentativa__iniciado_em", "id")
        .values_list("pergunta_id", "correta")
    )
    for pergunta_id, correta in respostas:
        ultimo[pergunta_id] = correta  # a última resposta sobrescreve as anteriores
    return [pid for pid, ok in ultimo.items() if not ok]


def dificuldades_recorrentes(usuario, limite=5):
    """Assuntos com pior desempenho acumulado em todas as rodadas."""
    acumulado = {}
    for a in PerformanceAnalysis.objects.filter(tentativa__usuario=usuario):
        for d in a.por_assunto:
            x = acumulado.setdefault(d["assunto"], {"assunto": d["assunto"], "acertos": 0, "total": 0})
            x["acertos"] += d["acertos"]
            x["total"] += d["total"]
    lista = [
        {**x, "percentual": _pct(x["acertos"], x["total"])}
        for x in acumulado.values()
        if x["total"] >= settings.MIN_RESPOSTAS_ASSUNTO
    ]
    return sorted(lista, key=lambda x: x["percentual"])[:limite]
