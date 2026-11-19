from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("rodadas", views.RodadaViewSet, basename="rodada")

urlpatterns = [
    path("auth/registro/", views.RegistroView.as_view(), name="api-registro"),
    path("auth/login/", views.LoginView.as_view(), name="api-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="api-logout"),
    path("auth/me/", views.MeView.as_view(), name="api-me"),
    path("categorias/", views.CategoriaListView.as_view(), name="api-categorias"),
    path("dashboard/", views.DashboardView.as_view(), name="api-dashboard"),
    path("ia/explicar/", views.ExplicarIAView.as_view(), name="api-ia-explicar"),
    path("", include(router.urls)),
]
