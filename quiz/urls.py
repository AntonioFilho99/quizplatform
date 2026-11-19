from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("categorias/", views.categorias, name="categorias"),
    path("iniciar/<int:categoria_id>/", views.iniciar, name="iniciar"),
    path("rodada/<int:tentativa_id>/", views.responder, name="responder"),
    path("rodada/<int:tentativa_id>/feedback/<int:resposta_id>/", views.feedback, name="feedback"),
    path("resultado/<int:tentativa_id>/", views.resultado, name="resultado"),
    path("historico/", views.historico, name="historico"),
]
