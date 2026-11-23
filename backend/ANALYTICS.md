# Analytics de utilização (admin)

A funcionalidade regista eventos autenticados no PostgreSQL, usando o utilizador resolvido a partir do token Cognito. Não altera User Pool, App Client, grupos, Amplify nem recursos AWS.

## Eventos
- `session_start`: sessão da aplicação iniciada/recuperada.
- `page_view`: navegação entre áreas.
- `feature_action`: operação funcional concluída com sucesso.

A API aceita apenas tipos de evento e áreas pré-definidos. Não recolhe IP, user-agent, tokens, palavras-passe, conteúdo de pesquisas, emails de contactos ou texto dos prompts.

## Endpoints
- `POST /api/v1/analytics/events` — utilizador autenticado.
- `GET /api/v1/analytics/overview?days=30` — apenas SUPER_ADMIN/ADMIN.

## Métricas
Utilizadores ativos no período, utilizadores ativos nas últimas 24 horas, utilizadores inativos no período, sessões iniciadas, eventos por funcionalidade e última atividade por utilizador. Um utilizador é considerado ativo se gerar pelo menos um evento registado pela aplicação; isto não representa prova de pessoa única nem mede tempo exato de permanência.

## Migração e testes
Executar `alembic upgrade head` antes de atualizar o serviço API. A partir de `backend/`: `python -m pip install -r requirements-dev.txt` e `python -m pytest tests/`.
