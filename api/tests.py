from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from config.settings import banco_da_url
from quiz.models import Answer, Category, QuizAttempt, Subject, UserResponse

User = get_user_model()


class BaseAPI(TestCase):
    def setUp(self):
        cache.clear()  # zera o controle de limite de requisições entre testes
        call_command("seed_quiz", verbosity=0)
        self.user = User.objects.create_user("ana", password="senha-forte-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.cat = Category.objects.get(nome="Programação")
        self.python = Subject.objects.get(categoria=self.cat, nome="Python")

    def iniciar(self, **dados):
        dados.setdefault("categoria", self.cat.pk)
        return self.client.post("/api/rodadas/", dados, format="json")

    def jogar(self, rodada_id, acertar):
        """Responde todas as perguntas; devolve a última resposta da API."""
        r = self.client.get(f"/api/rodadas/{rodada_id}/")
        while r.data["pergunta"]:
            item = r.data["pergunta"]
            alvo = Answer.objects.filter(pergunta_id=item["pergunta"]["id"], correta=acertar).first()
            r = self.client.post(f"/api/rodadas/{rodada_id}/responder/", {"alternativa": alvo.pk}, format="json")
            self.assertEqual(r.status_code, 200)
            if r.data["finalizada"]:
                return r
            r.data["pergunta"] = r.data["proxima"]
        return r


class AuthTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_registro_login_me_logout(self):
        r = self.client.post("/api/auth/registro/", {"username": "bia", "password": "Xk93!mzqPw"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("token", r.data)
        self.assertNotIn("password", r.data["usuario"])
        r = self.client.post("/api/auth/login/", {"username": "bia", "password": "Xk93!mzqPw"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])
        self.assertEqual(self.client.get("/api/auth/me/").data["username"], "bia")
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)  # token foi apagado

    def test_registro_invalido(self):
        User.objects.create_user("bia", password="x")
        r = self.client.post("/api/auth/registro/", {"username": "BIA", "password": "Xk93!mzqPw"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("username", r.data)
        r = self.client.post("/api/auth/registro/", {"username": "novo", "password": "123"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)

    def test_login_errado_e_rotas_protegidas(self):
        User.objects.create_user("bia", password="Xk93!mzqPw")
        r = self.client.post("/api/auth/login/", {"username": "bia", "password": "errada"}, format="json")
        self.assertEqual(r.status_code, 400)
        for rota in ("/api/categorias/", "/api/dashboard/", "/api/rodadas/"):
            self.assertEqual(self.client.get(rota).status_code, 401)


class RodadasTest(BaseAPI):
    def test_categorias(self):
        r = self.client.get("/api/categorias/")
        self.assertEqual(r.status_code, 200)
        prog = next(c for c in r.data if c["nome"] == "Programação")
        self.assertEqual(prog["icone"], "💻")
        self.assertEqual(prog["total_perguntas"], 8)
        self.assertEqual(prog["revisar"], 0)
        self.assertEqual({a["nome"] for a in prog["assuntos"]}, {"Python", "Java", "JavaScript"})

    def test_fluxo_completo_sem_vazar_gabarito(self):
        r = self.iniciar(quantidade=3)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["total"], 3)
        for alt in r.data["pergunta"]["pergunta"]["alternativas"]:
            self.assertEqual(set(alt), {"id", "texto"})  # sem o campo "correta"
        rid = r.data["id"]
        ultima = self.jogar(rid, acertar=True)
        self.assertTrue(ultima.data["finalizada"])
        self.assertEqual(ultima.data["acertos"], 3)
        res = self.client.get(f"/api/rodadas/{rid}/resultado/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["percentual"], 100.0)
        self.assertEqual(len(res.data["respostas"]), 3)
        self.assertTrue(all(x["acertou"] for x in res.data["respostas"]))
        self.assertIn("diagnostico", res.data["analise"])
        # resultado, histórico e dashboard
        hist = self.client.get("/api/rodadas/")
        self.assertEqual(hist.data["count"], 1)
        self.assertEqual(hist.data["results"][0]["percentual"], 100.0)
        dash = self.client.get("/api/dashboard/").data
        self.assertEqual((dash["total_rodadas"], dash["media"]), (1, 100.0))
        self.assertIsNone(dash["rodada_em_andamento"])

    def test_feedback_da_resposta_errada(self):
        rid = self.iniciar(quantidade=2).data["id"]
        estado = self.client.get(f"/api/rodadas/{rid}/").data
        item = estado["pergunta"]["pergunta"]
        errada = Answer.objects.filter(pergunta_id=item["id"], correta=False).first()
        r = self.client.post(f"/api/rodadas/{rid}/responder/", {"alternativa": errada.pk}, format="json")
        self.assertFalse(r.data["correta"])
        certa = Answer.objects.get(pergunta_id=item["id"], correta=True)
        self.assertEqual(r.data["alternativa_correta"], certa.pk)
        self.assertFalse(r.data["finalizada"])
        self.assertIsNotNone(r.data["proxima"])

    def test_por_assunto_quantidade_e_validacoes(self):
        r = self.iniciar(assunto=self.python.pk, quantidade=20)
        self.assertEqual(r.data["total"], 4)  # Python tem só 4 perguntas
        outra = Subject.objects.exclude(categoria=self.cat).first()
        self.assertEqual(self.iniciar(assunto=outra.pk).status_code, 400)
        self.assertEqual(self.iniciar(quantidade=0).status_code, 400)
        self.assertEqual(self.iniciar(modo="invalido").status_code, 400)
        self.assertEqual(self.client.post("/api/rodadas/", {"categoria": 9999}, format="json").status_code, 400)

    def test_responder_valida_alternativa_e_estado(self):
        rid = self.iniciar(quantidade=2).data["id"]
        r = self.client.post(f"/api/rodadas/{rid}/responder/", {"alternativa": "abc"}, format="json")
        self.assertEqual(r.status_code, 400)
        outra_pergunta = Answer.objects.exclude(pergunta__userresponse__tentativa_id=rid).first()
        r = self.client.post(f"/api/rodadas/{rid}/responder/", {"alternativa": outra_pergunta.pk}, format="json")
        self.assertEqual(r.status_code, 400)  # alternativa de outra pergunta
        self.assertEqual(self.client.get(f"/api/rodadas/{rid}/resultado/").status_code, 409)  # ainda em andamento
        self.assertEqual(self.client.get("/api/dashboard/").data["rodada_em_andamento"], rid)
        self.jogar(rid, True)
        r = self.client.post(f"/api/rodadas/{rid}/responder/", {"alternativa": 1}, format="json")
        self.assertEqual(r.status_code, 409)  # já finalizada

    def test_revisao_de_erros(self):
        self.assertEqual(self.iniciar(modo="revisao").status_code, 409)  # nada para revisar ainda
        rid = self.iniciar(quantidade=4).data["id"]
        self.jogar(rid, acertar=False)
        prog = next(c for c in self.client.get("/api/categorias/").data if c["nome"] == "Programação")
        self.assertEqual(prog["revisar"], 4)
        self.assertEqual(self.client.get("/api/dashboard/").data["revisar_total"], 4)
        r = self.iniciar(modo="revisao", quantidade=10)
        self.assertEqual((r.status_code, r.data["total"], r.data["modo"]), (201, 4, "revisao"))
        self.jogar(r.data["id"], acertar=True)
        self.assertEqual(self.client.get("/api/dashboard/").data["revisar_total"], 0)

    def test_historico_filtro_e_paginacao(self):
        for _ in range(12):
            self.jogar(self.iniciar(quantidade=1).data["id"], True)
        pagina = self.client.get("/api/rodadas/").data
        self.assertEqual((pagina["count"], len(pagina["results"])), (12, 10))
        self.assertEqual(len(self.client.get("/api/rodadas/?page=2").data["results"]), 2)
        outra = Category.objects.exclude(pk=self.cat.pk).first()
        self.assertEqual(self.client.get(f"/api/rodadas/?categoria={outra.pk}").data["count"], 0)

    def test_apagar_rodada_e_isolamento_entre_usuarios(self):
        rid = self.iniciar(quantidade=2).data["id"]
        item_id = UserResponse.objects.filter(tentativa_id=rid).first().pk
        intruso = User.objects.create_user("eve", password="senha-forte-123")
        outro = APIClient()
        outro.force_authenticate(intruso)
        self.assertEqual(outro.get(f"/api/rodadas/{rid}/").status_code, 404)
        self.assertEqual(outro.post(f"/api/rodadas/{rid}/responder/", {"alternativa": 1}, format="json").status_code, 404)
        self.assertEqual(outro.get(f"/api/rodadas/{rid}/resultado/").status_code, 404)
        self.assertEqual(outro.delete(f"/api/rodadas/{rid}/").status_code, 404)
        self.assertEqual(outro.post("/api/ia/explicar/", {"resposta_id": item_id}, format="json").status_code, 404)
        self.assertEqual(outro.get("/api/rodadas/").data["count"], 0)
        self.assertEqual(self.client.delete(f"/api/rodadas/{rid}/").status_code, 204)
        self.assertFalse(QuizAttempt.objects.filter(pk=rid).exists())


def resposta_ia(texto="Porque tuplas são imutáveis."):
    r = MagicMock(status_code=200)
    r.json.return_value = {"content": [{"type": "text", "text": texto}]}
    return r


class IATest(BaseAPI):
    def respondida(self):
        rid = self.iniciar(quantidade=1).data["id"]
        self.jogar(rid, acertar=False)
        return UserResponse.objects.get(tentativa_id=rid)

    @override_settings(AI_API_KEY="")
    def test_sem_chave_devolve_503_e_nao_inventa_resposta(self):
        item = self.respondida()
        r = self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json")
        self.assertEqual(r.status_code, 503)
        item.refresh_from_db()
        self.assertEqual(item.explicacao_ia, "")

    @override_settings(AI_API_KEY="chave-de-teste")
    def test_explicacao_real_e_cache(self):
        item = self.respondida()
        with patch("quiz.ia.requests.post", return_value=resposta_ia()) as post:
            r = self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json")
            self.assertEqual(r.status_code, 200)
            self.assertEqual((r.data["explicacao"], r.data["em_cache"]), ("Porque tuplas são imutáveis.", False))
            self.assertIn("pode errar", r.data["aviso"])
            enviado = post.call_args.kwargs
            self.assertEqual(enviado["headers"]["x-api-key"], "chave-de-teste")
            self.assertIn(item.pergunta.texto, enviado["json"]["messages"][0]["content"])
            r2 = self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json")
            self.assertTrue(r2.data["em_cache"])
            self.assertEqual(post.call_count, 1)  # segunda vez veio do banco
        item.refresh_from_db()
        self.assertEqual(item.explicacao_ia, "Porque tuplas são imutáveis.")

    @override_settings(AI_API_KEY="chave-de-teste")
    def test_falhas_do_provedor_viram_502(self):
        item = self.respondida()
        import requests
        with patch("quiz.ia.requests.post", return_value=MagicMock(status_code=429)):
            self.assertEqual(self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json").status_code, 502)
        with patch("quiz.ia.requests.post", side_effect=requests.Timeout()):
            self.assertEqual(self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json").status_code, 502)
        vazia = MagicMock(status_code=200)
        vazia.json.return_value = {"content": []}
        with patch("quiz.ia.requests.post", return_value=vazia):
            self.assertEqual(self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json").status_code, 502)

    @override_settings(AI_API_KEY="chave-de-teste")
    def test_nao_explica_pergunta_nao_respondida(self):
        rid = self.iniciar(quantidade=2).data["id"]
        item = UserResponse.objects.filter(tentativa_id=rid).first()
        with patch("quiz.ia.requests.post") as post:
            r = self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json")
            self.assertEqual(r.status_code, 400)
            post.assert_not_called()

    @override_settings(AI_API_KEY="chave-de-teste")
    def test_limite_de_chamadas_por_hora(self):
        item = self.respondida()
        with patch("quiz.ia.requests.post", return_value=resposta_ia()):
            codigos = [self.client.post("/api/ia/explicar/", {"resposta_id": item.pk}, format="json").status_code
                       for _ in range(31)]
        self.assertEqual(codigos.count(200), 30)
        self.assertEqual(codigos[-1], 429)


class ConfigTest(SimpleTestCase):
    def test_database_url_do_neon(self):
        cfg = banco_da_url("postgresql://usuario:s%40nha@ep-exemplo.neon.tech:5432/quizdb?sslmode=require")
        self.assertEqual(cfg["NAME"], "quizdb")
        self.assertEqual((cfg["USER"], cfg["PASSWORD"]), ("usuario", "s@nha"))
        self.assertEqual(cfg["HOST"], "ep-exemplo.neon.tech")
        self.assertEqual(cfg["OPTIONS"], {"sslmode": "require"})
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
