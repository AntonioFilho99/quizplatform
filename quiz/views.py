from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .analise import dificuldades_recorrentes, finalizar_tentativa, ids_para_revisar
from .servicos import (RodadaVazia, alternativas_embaralhadas, contagem_revisao_por_categoria,
                       iniciar_rodada, pergunta_atual, registrar_resposta)
from .models import Answer, Category, Question, QuizAttempt, Subject, UserResponse


@login_required
def dashboard(request):
    tentativas = QuizAttempt.objects.filter(usuario=request.user, finalizado_em__isnull=False)
    ultimas = list(tentativas.select_related("quiz__categoria", "assunto")[:5])
    total = tentativas.count()
    media = round(sum(t.percentual for t in tentativas) / total, 1) if total else 0
    evolucao = list(tentativas.order_by("finalizado_em")[:20])
    return render(request, "quiz/dashboard.html", {
        "ultimas": ultimas,
        "revisar_total": Question.objects.filter(pk__in=ids_para_revisar(request.user), ativa=True).count(),
        "total_rodadas": total,
        "media": media,
        "dificuldades": dificuldades_recorrentes(request.user),
        "grafico_labels": [t.finalizado_em.strftime("%d/%m %H:%M") for t in evolucao],
        "grafico_valores": [t.percentual for t in evolucao],
    })


@login_required
def categorias(request):
    cats = list(Category.objects.prefetch_related("assuntos"))
    contagem = contagem_revisao_por_categoria(request.user)
    for c in cats:
        c.revisar = contagem.get(c.pk, 0)
    return render(request, "quiz/categorias.html", {
        "categorias": cats,
        "opcoes_qtd": [5, 10, 15, 20],
        "qtd_padrao": settings.PERGUNTAS_POR_RODADA,
    })


@login_required
def iniciar(request, categoria_id):
    if request.method != "POST":
        return redirect("categorias")
    categoria = get_object_or_404(Category, pk=categoria_id)
    modo = "revisao" if request.POST.get("modo") == "revisao" else "normal"

    assunto = None
    assunto_id = request.POST.get("assunto", "")
    if assunto_id.isdigit():
        assunto = get_object_or_404(Subject, pk=assunto_id, categoria=categoria)
    qtd = request.POST.get("quantidade", "")
    quantidade = min(max(int(qtd), 1), 50) if qtd.isdigit() else None

    try:
        tentativa = iniciar_rodada(request.user, categoria, assunto, modo, quantidade)
    except RodadaVazia:
        if modo == "revisao":
            messages.info(request, "Nada para revisar aqui: você não tem erros pendentes. 🎉")
        else:
            messages.error(request, "Não há perguntas cadastradas para essa seleção.")
        return redirect("categorias")
    return redirect("responder", tentativa_id=tentativa.pk)


@login_required
def responder(request, tentativa_id):
    tentativa = get_object_or_404(QuizAttempt, pk=tentativa_id, usuario=request.user)
    if tentativa.finalizada:
        return redirect("resultado", tentativa_id=tentativa.pk)

    atual = pergunta_atual(tentativa)
    if atual is None:
        finalizar_tentativa(tentativa)
        return redirect("resultado", tentativa_id=tentativa.pk)

    if request.method == "POST":
        alt = Answer.objects.filter(pk=request.POST.get("alternativa"), pergunta=atual.pergunta).first()
        if alt is None:
            messages.error(request, "Selecione uma alternativa.")
        else:
            registrar_resposta(atual, alt)
            return redirect("feedback", tentativa_id=tentativa.pk, resposta_id=atual.pk)

    alternativas = alternativas_embaralhadas(atual)
    respondidas = tentativa.respostas.filter(resposta__isnull=False).count()
    return render(request, "quiz/pergunta.html", {
        "tentativa": tentativa,
        "item": atual,
        "alternativas": alternativas,
        "numero": respondidas + 1,
        "total": tentativa.total,
        "progresso": int(100 * respondidas / tentativa.total),
    })


@login_required
def feedback(request, tentativa_id, resposta_id):
    """Mostra na hora se a resposta estava certa, a correta e a explicação."""
    tentativa = get_object_or_404(QuizAttempt, pk=tentativa_id, usuario=request.user)
    item = get_object_or_404(
        UserResponse.objects.select_related("pergunta", "resposta"), pk=resposta_id, tentativa=tentativa
    )
    if not item.respondida:
        return redirect("responder", tentativa_id=tentativa.pk)
    respondidas = tentativa.respostas.filter(resposta__isnull=False)
    return render(request, "quiz/feedback.html", {
        "tentativa": tentativa,
        "item": item,
        "correta": item.pergunta.alternativas.filter(correta=True).first(),
        "numero": item.ordem + 1,
        "total": tentativa.total,
        "acertos": respondidas.filter(correta=True).count(),
        "erros": respondidas.filter(correta=False).count(),
        "progresso": int(100 * respondidas.count() / tentativa.total),
        "ultima": not tentativa.respostas.filter(resposta__isnull=True).exists(),
    })


@login_required
def resultado(request, tentativa_id):
    tentativa = get_object_or_404(
        QuizAttempt.objects.select_related("quiz__categoria", "assunto"), pk=tentativa_id, usuario=request.user
    )
    if not tentativa.finalizada:
        return redirect("responder", tentativa_id=tentativa.pk)
    respostas = tentativa.respostas.select_related("pergunta__assunto", "resposta")
    corretas = {a.pergunta_id: a.texto for a in Answer.objects.filter(pergunta__in=[r.pergunta for r in respostas], correta=True)}
    for r in respostas:
        r.texto_correto = corretas.get(r.pergunta_id, "")
    return render(request, "quiz/resultado.html", {
        "tentativa": tentativa, "analise": tentativa.analise, "respostas": respostas,
    })


@login_required
def historico(request):
    tentativas = QuizAttempt.objects.filter(usuario=request.user, finalizado_em__isnull=False).select_related("quiz__categoria", "assunto")
    categoria_id = request.GET.get("categoria")
    if categoria_id:
        tentativas = tentativas.filter(quiz__categoria_id=categoria_id)
    ordenadas = list(tentativas.order_by("finalizado_em"))
    return render(request, "quiz/historico.html", {
        "tentativas": tentativas,
        "categorias": Category.objects.all(),
        "categoria_id": categoria_id or "",
        "grafico_labels": [t.finalizado_em.strftime("%d/%m %H:%M") for t in ordenadas],
        "grafico_valores": [t.percentual for t in ordenadas],
        "dificuldades": dificuldades_recorrentes(request.user),
    })
