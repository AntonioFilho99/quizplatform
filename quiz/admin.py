from django.contrib import admin

from .models import (Answer, Category, PerformanceAnalysis, Question, Quiz,
                     QuizAttempt, Subject, UserResponse)


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 4


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("texto", "assunto", "ativa")
    list_filter = ("assunto__categoria", "assunto", "ativa")
    search_fields = ("texto",)
    inlines = [AnswerInline]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria")
    list_filter = ("categoria",)


class UserResponseInline(admin.TabularInline):
    model = UserResponse
    extra = 0
    can_delete = False


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("usuario", "quiz", "assunto", "modo", "iniciado_em", "acertos", "erros", "percentual")
    inlines = [UserResponseInline]


admin.site.register(Category)
admin.site.register(Quiz)
admin.site.register(PerformanceAnalysis)
