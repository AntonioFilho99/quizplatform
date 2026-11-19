import csv
import io
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Answer, Category, Question, Subject

LETRAS = "abcdef"


def _norm(texto):
    """minúsculas, sem acento e sem espaços nas pontas (cabeçalhos tolerantes)."""
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


class Command(BaseCommand):
    help = "Importa perguntas de um CSV. Colunas: categoria, assunto, pergunta, alt_a..alt_f, correta, explicacao."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho do arquivo .csv")
        parser.add_argument("--dry-run", action="store_true", help="Só valida, não grava nada.")

    def handle(self, *args, **opts):
        caminho = Path(opts["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")

        bruto = caminho.read_bytes()
        try:
            texto = bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = bruto.decode("cp1252")  # CSV salvo pelo Excel no Windows

        primeira = texto.splitlines()[0] if texto.strip() else ""
        delimitador = ";" if primeira.count(";") > primeira.count(",") else ","
        leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
        linhas = list(leitor)
        if not linhas:
            raise CommandError("O arquivo está vazio.")

        cab = [_norm(c) for c in linhas[0]]
        obrigatorias = {"categoria", "assunto", "pergunta", "alt_a", "alt_b", "correta"}
        faltando = obrigatorias - set(cab)
        if faltando:
            raise CommandError("Colunas obrigatórias ausentes: " + ", ".join(sorted(faltando)))

        criadas, duplicadas, erros = 0, 0, []
        with transaction.atomic():
            for n, valores in enumerate(linhas[1:], start=2):
                if not any(v.strip() for v in valores):
                    continue
                d = {cab[i]: v.strip() for i, v in enumerate(valores) if i < len(cab)}
                alts = {l: d.get(f"alt_{l}", "") for l in LETRAS if d.get(f"alt_{l}", "")}
                correta = _norm(d.get("correta", ""))
                if correta.isdigit() and 1 <= int(correta) <= len(LETRAS):
                    correta = LETRAS[int(correta) - 1]  # aceita 1..6 além de A..F

                if not (d.get("categoria") and d.get("assunto") and d.get("pergunta")):
                    erros.append(f"linha {n}: categoria, assunto e pergunta são obrigatórios")
                elif len(alts) < 2:
                    erros.append(f"linha {n}: informe pelo menos 2 alternativas")
                elif correta not in alts:
                    erros.append(f"linha {n}: 'correta' deve ser uma letra de alternativa preenchida (A-F)")
                else:
                    cat, _ = Category.objects.get_or_create(nome=d["categoria"])
                    sub, _ = Subject.objects.get_or_create(categoria=cat, nome=d["assunto"])
                    q, nova = Question.objects.get_or_create(
                        assunto=sub, texto=d["pergunta"], defaults={"explicacao": d.get("explicacao", "")}
                    )
                    if nova:
                        Answer.objects.bulk_create(
                            [Answer(pergunta=q, texto=t, correta=(l == correta)) for l, t in alts.items()]
                        )
                        criadas += 1
                    else:
                        duplicadas += 1
            if opts["dry_run"]:
                transaction.set_rollback(True)

        prefixo = "[simulação] " if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefixo}{criadas} perguntas criadas, {duplicadas} já existiam."))
        for e in erros:
            self.stderr.write(self.style.ERROR(e))
        if erros:
            self.stderr.write(self.style.WARNING(f"{len(erros)} linha(s) ignorada(s) por erro."))
