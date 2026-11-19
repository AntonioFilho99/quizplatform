from django.conf import settings
from django.db import models


ICONES = [
    ("matem", "📐"), ("program", "💻"), ("banco", "🗄️"), ("web", "🌐"), ("intelig", "🤖"),
    ("ciênc", "📊"), ("engenharia", "🛠️"), ("infra", "🖧"), ("algor", "🧮"),
]


class Category(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)

    class Meta:
        verbose_name = "categoria"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def icone(self):
        nome = self.nome.lower()
        for chave, emoji in ICONES:
            if chave in nome:
                return emoji
        return "📚"

    @property
    def total_perguntas(self):
        return Question.objects.filter(assunto__categoria=self, ativa=True).count()


class Subject(models.Model):
    categoria = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="assuntos")
    nome = models.CharField(max_length=100)

    class Meta:
        verbose_name = "assunto"
        ordering = ["categoria__nome", "nome"]
        unique_together = ("categoria", "nome")

    def __str__(self):
        return f"{self.categoria} / {self.nome}"


class Question(models.Model):
    assunto = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="perguntas")
    texto = models.TextField()
    explicacao = models.TextField(blank=True, help_text="Explicação exibida após a rodada.")
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "pergunta"

    def __str__(self):
        return self.texto[:80]


class Answer(models.Model):
    pergunta = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="alternativas")
    texto = models.CharField(max_length=300)
    correta = models.BooleanField(default=False)

    class Meta:
        verbose_name = "alternativa"

    def __str__(self):
        return self.texto


class Quiz(models.Model):
    """Configuração de uma rodada: categoria + quantidade de perguntas."""
    titulo = models.CharField(max_length=150)
    categoria = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="quizzes")
    num_perguntas = models.PositiveSmallIntegerField(default=5)

    def __str__(self):
        return self.titulo


class QuizAttempt(models.Model):
    MODOS = [("normal", "Quiz"), ("revisao", "Revisão de erros")]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tentativas")
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name="tentativas")
    iniciado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    total = models.PositiveSmallIntegerField(default=0)
    acertos = models.PositiveSmallIntegerField(default=0)
    erros = models.PositiveSmallIntegerField(default=0)
    percentual = models.FloatField(default=0)
    assunto = models.ForeignKey(Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name="tentativas")
    modo = models.CharField(max_length=10, choices=MODOS, default="normal")

    class Meta:
        ordering = ["-iniciado_em"]

    @property
    def rotulo(self):
        texto = str(self.quiz.categoria)
        if self.assunto_id:
            texto += f" · {self.assunto.nome}"
        if self.modo == "revisao":
            texto += " · Revisão de erros"
        return texto

    @property
    def finalizada(self):
        return self.finalizado_em is not None

    def __str__(self):
        return f"{self.usuario} - {self.quiz} ({self.iniciado_em:%d/%m/%Y %H:%M})"


class UserResponse(models.Model):
    """Uma linha por pergunta sorteada; resposta fica nula até o usuário responder."""
    tentativa = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="respostas")
    pergunta = models.ForeignKey(Question, on_delete=models.PROTECT)
    resposta = models.ForeignKey(Answer, null=True, blank=True, on_delete=models.PROTECT)
    correta = models.BooleanField(default=False)
    ordem = models.PositiveSmallIntegerField(default=0)
    explicacao_ia = models.TextField(blank=True, default="", help_text="Explicação gerada pela IA (guardada para não repetir a chamada).")

    class Meta:
        ordering = ["ordem"]

    @property
    def respondida(self):
        return self.resposta_id is not None


class PerformanceAnalysis(models.Model):
    """Snapshot da análise: não muda mesmo que perguntas sejam editadas depois."""
    tentativa = models.OneToOneField(QuizAttempt, on_delete=models.CASCADE, related_name="analise")
    por_assunto = models.JSONField(default=list)
    diagnostico = models.TextField()
    recomendacoes = models.TextField(blank=True)
    variacao = models.FloatField(null=True, blank=True, help_text="Diferença em pontos percentuais vs. rodada anterior da categoria.")
    criado_em = models.DateTimeField(auto_now_add=True)
