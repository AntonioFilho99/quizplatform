# QuizTI — Plataforma de Quiz com análise de desempenho

Quiz de estudos (TI, IA e Matemática) que registra cada resposta, mostra seus pontos fortes e dificuldades por assunto,
guarda o histórico de rodadas e monta quizzes de revisão dos erros. Tem uma explicação por **IA** para cada resposta.

**Arquitetura:** React (front-end) → API REST (Django REST Framework) → PostgreSQL / SQLite  ·  IA chamada só no servidor.

> O front-end em React fica em `frontend/` (próxima etapa). O site antigo em templates Django continua funcionando em `/`.

## Rodando o back-end
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                    # Windows: Copy-Item .env.example .env
python manage.py migrate
python manage.py importar_perguntas dados/perguntas_matematica_ti.csv
python manage.py createsuperuser
python manage.py runserver
```
- Site (templates): http://127.0.0.1:8000/  ·  Admin: `/admin/`  ·  API: `/api/`
- Testes: `python manage.py test`

## Variáveis de ambiente (`.env`, nunca vai ao Git — veja `.env.example`)
| Variável | Para quê |
|---|---|
| `DEBUG` | `1` em desenvolvimento; **`0` em produção** |
| `SECRET_KEY` | obrigatória quando `DEBUG=0` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | domínios do servidor |
| `CORS_ALLOWED_ORIGINS` | endereços do front React autorizados (padrão: Vite em `localhost:5173`) |
| `DATABASE_URL` | PostgreSQL (ex.: Neon). Vazio = SQLite local. Requer `psycopg[binary]` |
| `AI_API_KEY`, `AI_API_URL`, `AI_MODEL` | provedor de IA (padrão: API Messages da Anthropic) |
| `PERGUNTAS_POR_RODADA` | padrão de perguntas por rodada (10) |

## API REST
Autenticação por token: envie `Authorization: Token <token>` (obtido em registro/login).

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/auth/registro/` | cria conta `{username, password}` → `{token, usuario}` |
| POST | `/api/auth/login/` | login → `{token, usuario}` |
| POST | `/api/auth/logout/` | apaga o token |
| GET | `/api/auth/me/` | usuário logado |
| GET | `/api/categorias/` | categorias, assuntos, total de perguntas e quantas há para revisar |
| POST | `/api/rodadas/` | inicia rodada `{categoria, assunto?, modo?: "normal"\|"revisao", quantidade?}` |
| GET | `/api/rodadas/` | histórico paginado (`?categoria=ID&page=N`) |
| GET | `/api/rodadas/{id}/` | estado da rodada e pergunta atual (sem o gabarito) |
| POST | `/api/rodadas/{id}/responder/` | `{alternativa}` → acerto/erro na hora, explicação e próxima pergunta |
| GET | `/api/rodadas/{id}/resultado/` | acertos, erros, análise por assunto, diagnóstico e revisão |
| DELETE | `/api/rodadas/{id}/` | apaga uma rodada sua |
| GET | `/api/dashboard/` | média, evolução, dificuldades recorrentes, rodada em andamento |
| POST | `/api/ia/explicar/` | `{resposta_id}` → explicação gerada por IA (guardada no banco) |

Segurança: cada usuário só acessa as próprias rodadas (404 para as dos outros); o gabarito só é revelado depois da
resposta; login/registro e IA têm limite de requisições; a chave da IA fica só no servidor.

## Estrutura
- `api/` — serializers, views e rotas da API REST
- `quiz/models.py` — Category, Subject, Question, Answer, Quiz, QuizAttempt, UserResponse, PerformanceAnalysis
- `quiz/servicos.py` — regras de negócio compartilhadas (iniciar rodada, responder, revisão)
- `quiz/analise.py` — resultado, diagnóstico por assunto e comparação com a rodada anterior
- `quiz/ia.py` — chamada ao provedor de IA
- `dados/` — CSVs de perguntas (`importar_perguntas`)

## IA: limitações
A explicação pode conter erros e sempre vem com esse aviso. Só são enviados à IA o texto da pergunta, as alternativas e a
escolha do aluno (dados fictícios). Sem `AI_API_KEY` o endpoint responde 503; nada é simulado.
