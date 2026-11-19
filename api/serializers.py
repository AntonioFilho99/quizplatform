from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from quiz.models import Category, QuizAttempt, Subject

User = get_user_model()


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]


class RegistroSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_username(self, valor):
        if User.objects.filter(username__iexact=valor).exists():
            raise serializers.ValidationError("Este nome de usuário já está em uso.")
        return valor

    def validate(self, attrs):
        try:
            password_validation.validate_password(attrs["password"], User(username=attrs["username"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, dados):
        return User.objects.create_user(**dados)


class AssuntoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "nome"]


class CategoriaSerializer(serializers.ModelSerializer):
    assuntos = AssuntoSerializer(many=True, read_only=True)
    revisar = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "nome", "descricao", "icone", "total_perguntas", "assuntos", "revisar"]

    def get_revisar(self, categoria):
        """Perguntas dessa categoria que o usuário ainda precisa revisar."""
        return self.context.get("revisar", {}).get(categoria.pk, 0)


class IniciarRodadaSerializer(serializers.Serializer):
    categoria = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    assunto = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    modo = serializers.ChoiceField(choices=["normal", "revisao"], default="normal")
    quantidade = serializers.IntegerField(min_value=1, max_value=50, required=False)

    def validate(self, attrs):
        assunto = attrs.get("assunto")
        if assunto and assunto.categoria_id != attrs["categoria"].pk:
            raise serializers.ValidationError({"assunto": "Esse assunto não pertence à categoria escolhida."})
        return attrs


class ResponderSerializer(serializers.Serializer):
    alternativa = serializers.IntegerField()


class ExplicarSerializer(serializers.Serializer):
    resposta_id = serializers.IntegerField()


class RodadaResumoSerializer(serializers.ModelSerializer):
    """Linha do histórico."""
    categoria = serializers.CharField(source="quiz.categoria.nome", read_only=True)
    categoria_id = serializers.IntegerField(source="quiz.categoria_id", read_only=True)
    assunto = serializers.SerializerMethodField()
    finalizada = serializers.BooleanField(read_only=True)

    class Meta:
        model = QuizAttempt
        fields = ["id", "rotulo", "categoria", "categoria_id", "assunto", "modo", "iniciado_em",
                  "finalizado_em", "finalizada", "total", "acertos", "erros", "percentual"]

    def get_assunto(self, tentativa):
        return tentativa.assunto.nome if tentativa.assunto_id else None
