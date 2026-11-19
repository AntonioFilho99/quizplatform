# QuizTI — Plataforma de Quiz Inteligente (MVP)

Django + SQLite (padrão) ou PostgreSQL. Análise de desempenho baseada em regras (sem IA na v1).

## Rodando
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_quiz          # categorias e perguntas de exemplo
python manage.py createsuperuser    # acesso ao /admin/
python manage.py runserver
```
Acesse http://127.0.0.1:8000/

## PostgreSQL
Defina `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` e instale `psycopg[binary]`.

## Ajustes (config/settings.py)
`PERGUNTAS_POR_RODADA`, `MIN_RESPOSTAS_ASSUNTO`, `LIMITE_DIFICULDADE`, `LIMITE_DOMINIO`.

## Estrutura
- `contas/` — registro/login
- `quiz/models.py` — Category, Subject, Question, Answer, Quiz, QuizAttempt, UserResponse, PerformanceAnalysis
- `quiz/analise.py` — cálculo de resultado, diagnóstico, recomendação e comparação com rodada anterior
- `quiz/views.py` — dashboard, categorias, rodada, resultado, histórico
