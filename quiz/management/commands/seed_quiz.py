from django.core.management.base import BaseCommand

from quiz.models import Answer, Category, Question, Subject

# (categoria, assunto, pergunta, [alternativas], índice da correta, explicação)
DADOS = [
 ("Programação","Python","Qual estrutura de dados do Python é imutável?",["list","dict","tuple","set"],2,"Tuplas não podem ser alteradas após a criação."),
 ("Programação","Python","O que `len([1,2,3])` retorna?",["2","3","4","Erro"],1,"len conta os elementos da lista."),
 ("Programação","Python","Qual palavra-chave define uma função em Python?",["func","function","def","lambda_def"],2,"Funções são definidas com `def`."),
 ("Programação","Python","Qual é o resultado de `10 // 3`?",["3.33","3","4","1"],1,"`//` é a divisão inteira (piso)."),
 ("Programação","Java","Qual palavra-chave impede a herança de uma classe em Java?",["static","final","private","sealed_off"],1,"`final` em uma classe impede que seja estendida."),
 ("Programação","Java","Qual é o ponto de entrada de um programa Java?",["start()","run()","main()","init()"],2,"`public static void main(String[] args)`."),
 ("Programação","JavaScript","Qual operador compara valor e tipo em JavaScript?",["==","===","=","!="],1,"`===` é a igualdade estrita."),
 ("Programação","JavaScript","Qual método transforma cada item de um array e retorna um novo array?",["forEach","filter","map","reduce"],2,"`map` retorna um novo array com os valores transformados."),
 ("Banco de dados","SQL","Qual comando SQL filtra linhas de uma consulta?",["GROUP BY","WHERE","ORDER BY","JOIN"],1,"`WHERE` filtra as linhas antes do agrupamento."),
 ("Banco de dados","SQL","Qual JOIN retorna apenas linhas com correspondência nas duas tabelas?",["LEFT JOIN","RIGHT JOIN","INNER JOIN","FULL JOIN"],2,"INNER JOIN mantém só as correspondências."),
 ("Banco de dados","SQL","Qual função SQL conta linhas?",["SUM()","COUNT()","AVG()","MAX()"],1,"`COUNT()` conta registros."),
 ("Banco de dados","PostgreSQL","Qual tipo do PostgreSQL armazena dados JSON binários indexáveis?",["JSON","TEXT","JSONB","BLOB"],2,"`JSONB` é binário e permite indexação."),
 ("Banco de dados","PostgreSQL","Qual comando mostra o plano de execução de uma consulta?",["DESCRIBE","EXPLAIN","SHOW PLAN","TRACE"],1,"`EXPLAIN` (ou `EXPLAIN ANALYZE`)."),
 ("Desenvolvimento Web","Django","Qual arquivo do Django define as rotas de URL?",["views.py","urls.py","models.py","admin.py"],1,"`urls.py` mapeia URLs para views."),
 ("Desenvolvimento Web","Django","Qual comando aplica as migrações ao banco?",["makemigrations","migrate","runserver","syncdb"],1,"`makemigrations` cria; `migrate` aplica."),
 ("Desenvolvimento Web","Django","O que o ORM do Django faz?",["Renderiza HTML","Mapeia models para tabelas","Gerencia CSS","Compila Python"],1,"O ORM traduz classes Python em tabelas e consultas."),
 ("Desenvolvimento Web","HTML/CSS","Qual propriedade CSS muda a cor do texto?",["font-color","text-color","color","foreground"],2,"A propriedade é `color`."),
 ("Desenvolvimento Web","HTML/CSS","Qual tag HTML define o maior título?",["<head>","<h1>","<title>","<header>"],1,"`<h1>` é o título de maior nível."),
 ("Inteligência Artificial","Machine Learning","Qual tipo de aprendizado usa dados rotulados?",["Não supervisionado","Supervisionado","Por reforço","Auto-organizado"],1,"No supervisionado, cada exemplo tem um rótulo."),
 ("Inteligência Artificial","Machine Learning","O que é overfitting?",["Modelo simples demais","Modelo que decora o treino e generaliza mal","Falta de dados","Erro de sintaxe"],1,"Bom no treino, ruim em dados novos."),
 ("Inteligência Artificial","Machine Learning","Qual algoritmo é usado para agrupar dados sem rótulos?",["Regressão linear","K-Means","Árvore de decisão","Naive Bayes"],1,"K-Means é um algoritmo de clusterização."),
 ("Inteligência Artificial","Deep Learning","O que é uma função de ativação?",["Define a taxa de aprendizado","Introduz não linearidade no neurônio","Normaliza o dataset","Divide treino e teste"],1,"Sem ela, a rede seria apenas uma transformação linear."),
 ("Inteligência Artificial","Deep Learning","Qual técnica atualiza pesos propagando o erro para trás?",["Dropout","Backpropagation","Pooling","Embedding"],1,"Backpropagation calcula gradientes camada a camada."),
]


class Command(BaseCommand):
    help = "Popula o banco com categorias, assuntos e perguntas de exemplo."

    def handle(self, *args, **opts):
        criadas = 0
        for cat, assunto, texto, alts, correta, expl in DADOS:
            c, _ = Category.objects.get_or_create(nome=cat)
            s, _ = Subject.objects.get_or_create(categoria=c, nome=assunto)
            q, novo = Question.objects.get_or_create(assunto=s, texto=texto, defaults={"explicacao": expl})
            if novo:
                Answer.objects.bulk_create([Answer(pergunta=q, texto=t, correta=(i == correta)) for i, t in enumerate(alts)])
                criadas += 1
        self.stdout.write(self.style.SUCCESS(f"{criadas} perguntas criadas."))
