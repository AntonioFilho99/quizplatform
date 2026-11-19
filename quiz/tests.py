from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .analise import ids_para_revisar
from .models import Answer, Category, Question, QuizAttempt, Subject


class FluxoQuizTest(TestCase):
    def setUp(self):
        call_command("seed_quiz", verbosity=0)
        self.user = get_user_model().objects.create_user("ana", password="senha12345")
        self.client.login(username="ana", password="senha12345")

    def jogar(self, categoria, acertar):
        r = self.client.post(reverse("iniciar", args=[categoria.pk]), {"quantidade": 5}, follow=False)
        tentativa = QuizAttempt.objects.latest("id")
        self.assertRedirects(r, reverse("responder", args=[tentativa.pk]))
        while True:
            r = self.client.get(reverse("responder", args=[tentativa.pk]))
            if r.status_code == 302:
                break
            item = tentativa.respostas.filter(resposta__isnull=True).first()
            alts = Answer.objects.filter(pergunta=item.pergunta, correta=acertar)
            self.client.post(reverse("responder", args=[tentativa.pk]), {"alternativa": alts.first().pk})
        tentativa.refresh_from_db()
        return tentativa

    def test_rodada_completa_e_historico(self):
        cat = Category.objects.get(nome="Programação")
        t1 = self.jogar(cat, acertar=False)
        self.assertEqual((t1.acertos, t1.erros, t1.percentual), (0, 5, 0.0))
        self.assertIn("Dificuldades", t1.analise.diagnostico)
        self.assertIsNone(t1.analise.variacao)
        t2 = self.jogar(cat, acertar=True)
        self.assertEqual(t2.percentual, 100.0)
        self.assertEqual(t2.analise.variacao, 100.0)
        # nova tentativa não sobrescreve a anterior
        t1.refresh_from_db()
        self.assertEqual(t1.percentual, 0.0)
        for nome in ("resultado", ):
            self.assertEqual(self.client.get(reverse(nome, args=[t2.pk])).status_code, 200)
        for nome in ("dashboard", "categorias", "historico"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_feedback_imediato(self):
        cat = Category.objects.get(nome="Programação")
        self.client.post(reverse("iniciar", args=[cat.pk]))
        t = QuizAttempt.objects.latest("id")
        item = t.respostas.first()
        errada = Answer.objects.filter(pergunta=item.pergunta, correta=False).first()
        r = self.client.post(reverse("responder", args=[t.pk]), {"alternativa": errada.pk})
        self.assertRedirects(r, reverse("feedback", args=[t.pk, item.pk]))
        r = self.client.get(reverse("feedback", args=[t.pk, item.pk]))
        self.assertContains(r, "Você errou")
        self.assertContains(r, "Próxima pergunta")

    def test_acesso_exige_login_e_isolamento(self):
        cat = Category.objects.first()
        t = self.jogar(cat, True)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        get_user_model().objects.create_user("bia", password="senha12345")
        self.client.login(username="bia", password="senha12345")
        self.assertEqual(self.client.get(reverse("resultado", args=[t.pk])).status_code, 404)

    def test_registro(self):
        self.client.logout()
        r = self.client.post(reverse("registro"), {"username": "novo", "password1": "Xk93!mzqPw", "password2": "Xk93!mzqPw"})
        self.assertRedirects(r, reverse("dashboard"))


class ImportarCSVTest(TestCase):
    def _rodar(self, conteudo, encoding="utf-8", **kw):
        import tempfile, os
        from io import StringIO
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as f:
            f.write(conteudo.encode(encoding))
        try:
            out, err = StringIO(), StringIO()
            call_command("importar_perguntas", f.name, stdout=out, stderr=err, **kw)
            return out.getvalue(), err.getvalue()
        finally:
            os.unlink(f.name)

    def test_virgula_cp1252_e_duplicatas(self):
        csv_txt = (
            "categoria,assunto,pergunta,alt_a,alt_b,alt_c,correta,explicacao\n"
            'Algoritmos,Lógica,"Quanto é 2+2, em decimal?",3,4,5,B,"Soma simples, sem pegadinha"\n'
        )
        self._rodar(csv_txt, encoding="cp1252")
        q = Question.objects.get(texto="Quanto é 2+2, em decimal?")
        self.assertEqual(q.alternativas.count(), 3)
        self.assertEqual(q.alternativas.get(correta=True).texto, "4")
        out, _ = self._rodar(csv_txt)
        self.assertIn("0 perguntas criadas, 1 já existiam", out)

    def test_erros_e_dry_run(self):
        csv_txt = (
            "categoria;assunto;pergunta;alt_a;alt_b;correta\n"
            "X;Y;Pergunta boa?;sim;não;1\n"
            "X;Y;Sem correta valida?;sim;não;D\n"
        )
        out, err = self._rodar(csv_txt, dry_run=True)
        self.assertIn("[simulação] 1 perguntas criadas", out)
        self.assertIn("linha 3", err)
        self.assertEqual(Question.objects.count(), 0)
        self._rodar(csv_txt)
        self.assertEqual(Question.objects.count(), 1)
        self.assertTrue(Question.objects.get().alternativas.get(correta=True).texto == "sim")

    def test_arquivo_de_exemplo(self):
        from pathlib import Path
        from django.conf import settings
        out, err = self._rodar(Path(settings.BASE_DIR, "dados", "perguntas_exemplo.csv").read_text(encoding="utf-8-sig"))
        self.assertIn("25 perguntas criadas", out)
        self.assertEqual(err, "")


def jogar_tentativa(client, tentativa, acertar):
    while True:
        r = client.get(reverse("responder", args=[tentativa.pk]))
        if r.status_code == 302:
            break
        item = tentativa.respostas.filter(resposta__isnull=True).first()
        alt = Answer.objects.filter(pergunta=item.pergunta, correta=acertar).first()
        client.post(reverse("responder", args=[tentativa.pk]), {"alternativa": alt.pk})
    tentativa.refresh_from_db()
    return tentativa


class AssuntoERevisaoTest(TestCase):
    def setUp(self):
        call_command("seed_quiz", verbosity=0)
        self.user = get_user_model().objects.create_user("lia", password="senha12345")
        self.client.login(username="lia", password="senha12345")
        self.cat = Category.objects.get(nome="Programação")
        self.python = Subject.objects.get(categoria=self.cat, nome="Python")

    def iniciar(self, **dados):
        return self.client.post(reverse("iniciar", args=[self.cat.pk]), dados)

    def test_quiz_por_assunto_e_quantidade(self):
        self.iniciar(assunto=self.python.pk, quantidade=3)
        t = QuizAttempt.objects.latest("id")
        self.assertEqual(t.respostas.count(), 3)
        self.assertTrue(all(r.pergunta.assunto_id == self.python.pk for r in t.respostas.all()))
        self.assertEqual(t.assunto, self.python)
        self.assertIn("Python", t.rotulo)
        # pede mais do que existe: usa só as disponíveis (Python tem 4)
        self.iniciar(assunto=self.python.pk, quantidade=20)
        self.assertEqual(QuizAttempt.objects.latest("id").respostas.count(), 4)

    def test_valores_invalidos_nao_quebram(self):
        r = self.iniciar(assunto="abc", quantidade="xyz")
        self.assertEqual(r.status_code, 302)
        outra = Subject.objects.exclude(categoria=self.cat).first()
        self.assertEqual(self.iniciar(assunto=outra.pk).status_code, 404)

    def test_revisao_de_erros(self):
        self.iniciar(quantidade=8)
        t1 = jogar_tentativa(self.client, QuizAttempt.objects.latest("id"), acertar=False)
        self.assertEqual(len(ids_para_revisar(self.user)), 8)
        self.assertContains(self.client.get(reverse("categorias")), "Revisar erros (8)")
        self.assertContains(self.client.get(reverse("resultado", args=[t1.pk])), "Revisar meus erros")

        self.iniciar(modo="revisao", quantidade=5)
        rev = QuizAttempt.objects.latest("id")
        self.assertEqual(rev.modo, "revisao")
        self.assertEqual(rev.respostas.count(), 5)
        erradas = set(t1.respostas.values_list("pergunta_id", flat=True))
        self.assertTrue(set(rev.respostas.values_list("pergunta_id", flat=True)) <= erradas)
        jogar_tentativa(self.client, rev, acertar=True)
        self.assertIsNone(rev.analise.variacao)  # sem revisão anterior para comparar
        self.assertEqual(len(ids_para_revisar(self.user)), 3)  # acertou 5, restam 3

        self.iniciar(modo="revisao", quantidade=10)
        rev2 = QuizAttempt.objects.latest("id")
        self.assertEqual(rev2.respostas.count(), 3)
        jogar_tentativa(self.client, rev2, acertar=True)
        self.assertEqual(ids_para_revisar(self.user), [])

        antes = QuizAttempt.objects.count()
        r = self.iniciar(modo="revisao")
        self.assertRedirects(r, reverse("categorias"))
        self.assertEqual(QuizAttempt.objects.count(), antes)  # nada para revisar: não cria rodada

    def test_pergunta_acertada_depois_sai_da_revisao(self):
        self.iniciar(assunto=self.python.pk, quantidade=1)
        t = jogar_tentativa(self.client, QuizAttempt.objects.latest("id"), acertar=False)
        pid = t.respostas.first().pergunta_id
        self.assertIn(pid, ids_para_revisar(self.user))
        # nova rodada normal em que ele acerta a mesma pergunta
        self.client.post(reverse("iniciar", args=[self.cat.pk]), {"assunto": self.python.pk, "quantidade": 4})
        t2 = jogar_tentativa(self.client, QuizAttempt.objects.latest("id"), acertar=True)
        self.assertNotIn(pid, ids_para_revisar(self.user))
