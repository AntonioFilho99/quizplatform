git from django.contrib.auth import get_user_model
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from quiz import ia
from quiz.analise import dificuldades_recorrentes, finalizar_tentativa, ids_para_revisar
from quiz.models import Category, Question, QuizAttempt, UserResponse
from quiz.servicos import (RodadaVazia, contagem_revisao_por_categoria, iniciar_rodada, pergunta_atual,
                           registrar_resposta)

from .dados import contagens, estado_rodada, pergunta_dict, resultado_rodada
from .serializers import (CategoriaSerializer, ExplicarSerializer, IniciarRodadaSerializer,
                          RegistroSerializer, ResponderSerializer, RodadaResumoSerializer,
                          UsuarioSerializer)

User = get_user_model()


def sessao(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {"token": token.key, "usuario": UsuarioSerializer(user).data}


# ---------- autenticação ----------
class RegistroView(generics.CreateAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(sessao(serializer.save()), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = AuthTokenSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(sessao(serializer.validated_data["user"]))


class LogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)


# ---------- categorias ----------
class CategoriaListView(generics.ListAPIView):
    serializer_class = CategoriaSerializer
    pagination_class = None

    def get_queryset(self):
        return Category.objects.prefetch_related("assuntos")

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        contexto["revisar"] = contagem_revisao_por_categoria(self.request.user)
        return contexto


# ---------- rodadas ----------
class RodadaViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    list      GET    /api/rodadas/               histórico (rodadas concluídas, paginado; ?categoria=ID)
    create    POST   /api/rodadas/               inicia rodada {categoria, assunto?, modo?, quantidade?}
    retrieve  GET    /api/rodadas/{id}/          estado da rodada e pergunta atual
    destroy   DELETE /api/rodadas/{id}/          apaga (abandona) uma rodada sua
    responder POST   /api/rodadas/{id}/responder/   {alternativa}
    resultado GET    /api/rodadas/{id}/resultado/
    """
    serializer_class = RodadaResumoSerializer

    def get_queryset(self):
        qs = QuizAttempt.objects.filter(usuario=self.request.user).select_related("quiz__categoria", "assunto")
        if self.action == "list":
            qs = qs.filter(finalizado_em__isnull=False)
            categoria = self.request.query_params.get("categoria", "")
            if categoria.isdigit():
                qs = qs.filter(quiz__categoria_id=categoria)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = IniciarRodadaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        try:
            tentativa = iniciar_rodada(
                request.user, dados["categoria"], dados.get("assunto"), dados["modo"], dados.get("quantidade")
            )
        except RodadaVazia as exc:
            motivo = "Você não tem erros pendentes para revisar aqui." if exc.args[0] == "revisao" \
                else "Não há perguntas cadastradas para essa seleção."
            return Response({"detail": motivo, "codigo": "sem_perguntas"}, status=status.HTTP_409_CONFLICT)
        return Response(estado_rodada(tentativa), status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return Response(estado_rodada(self.get_object()))

    @action(detail=True, methods=["post"])
    def responder(self, request, pk=None):
        tentativa = self.get_object()
        if tentativa.finalizada:
            return Response({"detail": "Esta rodada já foi finalizada."}, status=status.HTTP_409_CONFLICT)
        item = pergunta_atual(tentativa)
        if item is None:
            finalizar_tentativa(tentativa)
            return Response({"detail": "Todas as perguntas já foram respondidas."}, status=status.HTTP_409_CONFLICT)

        serializer = ResponderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alternativa = item.pergunta.alternativas.filter(pk=serializer.validated_data["alternativa"]).first()
        if alternativa is None:
            return Response({"alternativa": ["Alternativa inválida para esta pergunta."]},
                            status=status.HTTP_400_BAD_REQUEST)

        registrar_resposta(item, alternativa)
        correta = item.pergunta.alternativas.filter(correta=True).first()
        proxima = pergunta_atual(tentativa)
        if proxima is None:
            finalizar_tentativa(tentativa)
        return Response({
            "correta": item.correta,
            "alternativa_correta": correta.pk if correta else None,
            "explicacao": item.pergunta.explicacao,
            "item_id": item.pk,
            "total": tentativa.total,
            **contagens(tentativa),
            "finalizada": proxima is None,
            "proxima": pergunta_dict(proxima) if proxima else None,
        })

    @action(detail=True, methods=["get"])
    def resultado(self, request, pk=None):
        tentativa = self.get_object()
        if not tentativa.finalizada:
            if pergunta_atual(tentativa) is not None:
                return Response({"detail": "Esta rodada ainda está em andamento."}, status=status.HTTP_409_CONFLICT)
            finalizar_tentativa(tentativa)
        return Response(resultado_rodada(tentativa))


# ---------- dashboard ----------
class DashboardView(APIView):
    def get(self, request):
        usuario = request.user
        concluidas = QuizAttempt.objects.filter(usuario=usuario, finalizado_em__isnull=False) \
            .select_related("quiz__categoria", "assunto")
        media = concluidas.aggregate(m=Avg("percentual"))["m"]
        em_andamento = QuizAttempt.objects.filter(usuario=usuario, finalizado_em__isnull=True) \
            .order_by("-iniciado_em").first()
        return Response({
            "total_rodadas": concluidas.count(),
            "media": round(media, 1) if media is not None else 0,
            "revisar_total": Question.objects.filter(pk__in=ids_para_revisar(usuario), ativa=True).count(),
            "rodada_em_andamento": em_andamento.pk if em_andamento else None,
            "ultimas": RodadaResumoSerializer(concluidas[:5], many=True).data,
            "dificuldades": dificuldades_recorrentes(usuario),
            "evolucao": [
                {"data": t.finalizado_em, "percentual": t.percentual}
                for t in concluidas.order_by("finalizado_em")[:20]
            ],
        })


# ---------- IA ----------
class ExplicarIAView(APIView):
    """POST /api/ia/explicar/ {resposta_id}: a IA explica uma resposta que o próprio usuário já deu."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ia"

    def post(self, request):
        serializer = ExplicarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = get_object_or_404(
            UserResponse.objects.select_related("pergunta__assunto", "resposta"),
            pk=serializer.validated_data["resposta_id"], tentativa__usuario=request.user,
        )
        if not item.respondida:  # evita entregar o gabarito antes de responder
            return Response({"detail": "Responda a pergunta antes de pedir a explicação."},
                            status=status.HTTP_400_BAD_REQUEST)
        if item.explicacao_ia:
            return Response({"explicacao": item.explicacao_ia, "em_cache": True, "aviso": ia.AVISO})
        try:
            texto = ia.explicar_resposta(item)
        except ia.IANaoConfigurada:
            return Response({"detail": "A IA não está configurada neste servidor."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ia.IAErro:
            return Response({"detail": "Não foi possível obter a explicação agora. Tente novamente em instantes."},
                            status=status.HTTP_502_BAD_GATEWAY)
        item.explicacao_ia = texto
        item.save(update_fields=["explicacao_ia"])
        return Response({"explicacao": texto, "em_cache": False, "aviso": ia.AVISO})
