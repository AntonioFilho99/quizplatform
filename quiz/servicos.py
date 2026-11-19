"""Regras de negócio compartilhadas pelo site (templates) e pela API REST."""
import random

from django.conf import settings
from django.db import transaction
from django.db.models import Count

from .analise import ids_para_revisar
from .models import Question, Quiz, QuizAttempt, UserResponse


class RodadaVazia(Exception):
    """Não há perguntas disponíveis para a seleção pedida. args[0] = modo da rodada."""


def iniciar_rodada(usuario, categoria, assunto=None, modo="normal", quantidade=None):
    base = Question.objects.filter(assunto__categoria=categoria, ativa=True, alternativas__correta=True)
    if assunto:
        base = base.filter(assunto=assunto)
    if modo == "revisao":
        base = base.filter(pk__in=ids_para_revisar(usuario))
    ids = list(base.distinct().values_list("id", flat=True))
    if not ids:
        raise RodadaVazia(modo)

    quiz = Quiz.objects.filter(categoria=categoria).first() or Quiz.objects.create(
        categoria=categoria, titulo=f"Quiz de {categoria.nome}", num_perguntas=settings.PERGUNTAS_POR_RODADA
    )
    sorteadas = random.sample(ids, min(quantidade or quiz.num_perguntas, len(ids)))
    with transaction.atomic():
        tentativa = QuizAttempt.objects.create(
            usuario=usuario, quiz=quiz, total=len(sorteadas), assunto=assunto, modo=modo
        )
        UserResponse.objects.bulk_create(
            [UserResponse(tentativa=tentativa, pergunta_id=q, ordem=i) for i, q in enumerate(sorteadas)]
        )
    return tentativa


def pergunta_atual(tentativa):
    """Próximo item ainda sem resposta (ou None se todas foram respondidas)."""
    return tentativa.respostas.filter(resposta__isnull=True).select_related("pergunta__assunto").first()


def alternativas_embaralhadas(item):
    """Ordem das alternativas embaralhada, mas estável para o mesmo item."""
    alternativas = list(item.pergunta.alternativas.all())
    random.Random(item.pk).shuffle(alternativas)
    return alternativas


def registrar_resposta(item, alternativa):
    item.resposta = alternativa
    item.correta = alternativa.correta
    item.save(update_fields=["resposta", "correta"])
    return item


def contagem_revisao_por_categoria(usuario):
    """{categoria_id: quantas perguntas ainda precisam de revisão}."""
    pendentes = (
        Question.objects.filter(pk__in=ids_para_revisar(usuario), ativa=True)
        .values("assunto__categoria").annotate(n=Count("id"))
    )
    return {r["assunto__categoria"]: r["n"] for r in pendentes}
