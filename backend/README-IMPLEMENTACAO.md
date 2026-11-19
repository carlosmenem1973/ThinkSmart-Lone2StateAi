# ThinkSmart AI — refactor AWS Nova Lite

## O que contém
- `app/services/ai.py`: Amazon Bedrock Converse com Nova Lite e AgentCore Web Search.
- `app/agents/registry.py`: seis agentes.
- `app/api/routes.py`: versão integral baseada no `routes.py` fornecido, preservando as rotas existentes e acrescentando pesquisa `web`/`internal` e `POST /agents/{agent_id}/run`.
- `app/core/config.py`: configuração Bedrock; mantém Cognito e as restantes definições.
- `requirements.txt`: remove OpenAI e `openai-agents`.
- `thinksmart-bedrock-policy.json`: permissões Nova Lite + AgentCore Web Search.

## Importante
1. O perfil `eu.amazon.nova-lite-v1:0` é um perfil de inferência geográfica da UE. O endpoint é chamado em `eu-west-1`, mas a inferência pode ser encaminhada para outras regiões europeias. Não equivale a residência estrita em `eu-west-1`.
2. A pesquisa interna usa apenas tabelas existentes (`leads`, `email_insights`, `followups`). Não cria tabelas nem migrações.
3. Os agentes não alteram leads, follow-ups, emails nem enviam mensagens. Geram relatórios.
4. Para `email_insights`, os utilizadores não-admin ficam limitados a `mailbox == user.email`. Confirma se esse é o identificador de mailbox que a tua integração grava.
5. A rota de drafts existente permanece. A geração de drafts usa Nova Lite e mantém a validação de base legal/autorização existente.
6. A política substitui a política Nova Micro anterior; revê as regiões de destino permitidas pelo inference profile na tua conta antes de anexar.
7. Não executar deploy diretamente em produção antes dos testes locais e do staging.

## Aplicação
Faz cópia de segurança dos ficheiros atuais e substitui os ficheiros pelos correspondentes deste pacote. O `routes.py` foi construído a partir do conteúdo integral que forneceste.

### Configuração local `.env`
Adiciona/atualiza:
```
AWS_REGION=eu-west-1
BEDROCK_MODEL_ID=eu.amazon.nova-lite-v1:0
AGENTCORE_WEB_SEARCH_ID=web-search.v1
AGENTCORE_WEB_SEARCH_MAX_RESULTS=10
```
Remove `OPENAI_API_KEY`, `OPENAI_MODEL` e `OPENAI_WEB_SEARCH_ENABLED` do `.env` e do Secrets Manager quando confirmares que nenhuma outra aplicação os usa. Não coloques segredos em Git.

### Validação local
Na pasta `backend`:
```
python -m compileall app
python -c "from app.services.ai import research_web, research_internal, draft_outreach; from app.agents.registry import AGENTS; print(sorted(AGENTS))"
python -c "import boto3; c=boto3.client('bedrock-agentcore',region_name='eu-west-1'); print(c.meta.service_model.operation_names)"
```
Não executa inferência real no teste de importação.

### Testes HTTP (com token Cognito válido)
```
POST /api/v1/research?query=mercado%20imobiliario%20Portugal&source=web
POST /api/v1/research?query=leads%20por%20municipio&source=internal
POST /api/v1/agents/property-discovery/run
POST /api/v1/agents/market-analyst/run
POST /api/v1/agents/lead-qualifier/run
POST /api/v1/agents/owner-intelligence/run
POST /api/v1/agents/email-intelligence/run
POST /api/v1/agents/follow-up-assistant/run
```
Enviar `{}` como corpo nos endpoints dos agentes. Os pedidos de pesquisa são operações faturáveis.

## Observação de segurança
Os resultados Web Search devem ser apresentados com as respetivas URLs. A API inclui `sources` na pesquisa web; na interface, mantém os links visíveis juntamente com o relatório. Respeita os termos de utilização do AgentCore Web Search e não uses os resultados para construir um índice concorrente.
