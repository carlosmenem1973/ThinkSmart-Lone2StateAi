# Instruções para criar os serviços ECS Worker e Beat

## 1. Arquitetura

A infraestrutura OpenTofu define três serviços Fargate independentes no cluster `thinksmart-lone2stateai-prod`:

| Serviço | Processo | Desired count |
|---|---|---:|
| API | FastAPI | Configuração da API |
| Worker | Celery Worker | Variável `worker_desired_count` |
| Beat | Celery Beat | **1, sempre** |

O Worker consome tarefas. O Beat publica tarefas agendadas. Nunca executar `celery worker --beat` no Worker e nunca escalar horizontalmente o Beat. A configuração do serviço Beat usa deployment sem sobreposição (`maximum_percent=100`) para evitar duas instâncias de scheduler durante a substituição.

## 2. Task Definitions e imagens

OpenTofu cria as famílias:
- `thinksmart-lone2stateai-prod-api`
- `thinksmart-lone2stateai-prod-worker`
- `thinksmart-lone2stateai-prod-beat`

Worker e Beat usam o mesmo repositório ECR de worker e a mesma tag imutável configurada por `api_image_tag`. Confirmar que o pipeline publica essa imagem no repositório ECR de worker antes de aplicar a infraestrutura.

Comandos definidos:

```bash
celery -A app.workers.celery_app.celery worker --loglevel=INFO --concurrency=2
celery -A app.workers.celery_app.celery beat --loglevel=INFO
```

Os processos Worker e Beat não usam o health check HTTP da API.

## 3. Secrets Manager

A infraestrutura referencia as seguintes chaves no secret JSON da aplicação:
- `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`
- `META_WHATSAPP_ACCESS_TOKEN`
- `META_WHATSAPP_PHONE_NUMBER_ID`
- `META_WHATSAPP_APP_SECRET`
- `META_WHATSAPP_VERIFY_TOKEN`
- `META_GRAPH_API_VERSION`
- `EMAIL_FROM_ADDRESS`
- `SES_SENDER_VERIFIED`

Preencher os valores reais diretamente no AWS Secrets Manager, nunca no repositório, ficheiros de task definition ou variáveis Terraform em texto simples. A infraestrutura cria valores iniciais vazios/placeholders para as chaves novas; isso não configura credenciais reais.

Configuração de email prevista:
- Remetente: `contacto@cbloft2.pt`
- Região SES: `eu-west-1`
- `SES_SENDER_VERIFIED=false` até a identidade estar verificada e validada.

A Task Role tem permissão `ses:SendEmail` limitada à identidade SES `cbloft2.pt`. Confirmar a identidade efetiva, DKIM e estado sandbox/produção no SES. Não substituir o registo SPF existente do Microsoft 365; consolidar os mecanismos SPF num único registo DNS.

Configuração WhatsApp:
- Criar/configurar a aplicação Meta e o WhatsApp Business Phone Number.
- Guardar os tokens e segredos acima no Secrets Manager.
- Configurar o callback HTTPS para o webhook da aplicação e o verify token correspondente.
- Subscrever os eventos necessários no produto WhatsApp.
- Testar primeiro com destinatários de teste autorizados e sem ativar o envio global.

## 4. Redis, RDS e rede

Worker e Beat usam as sub-redes privadas e o Security Group ECS. Precisam de acesso ao Redis na porta 6379, PostgreSQL na porta 5432 e saída HTTPS para Bedrock/AgentCore, Meta Graph API e AWS SES. RDS e Redis não devem ser públicos.

## 5. Migrações

Executar migrações uma única vez, como tarefa ECS pontual, usando a mesma imagem e configuração da release aprovada:

```bash
alembic upgrade head
alembic current
```

A revisão esperada deve ser obtida da release/branch efetivamente implantada; não fixar o procedimento em `0006_property_discovery`, porque a cadeia evoluiu e inclui migrações posteriores, incluindo `0009_communications` e `0010_communications_outbox` neste PR.

Não executar migrações em paralelo em cada réplica da API, Worker ou Beat. Fazer backup e seguir o processo de alteração de schema antes de executar em produção.

## 6. Ordem de rollout

1. Rever o PR e obter CI verde.
2. Construir e publicar a imagem backend aprovada nos repositórios ECR necessários (API e worker).
3. Aplicar OpenTofu apenas após rever o plano e confirmar os recursos que serão criados/alterados.
4. Registar/deployar a API.
5. Executar `alembic upgrade head` uma única vez como tarefa pontual.
6. Confirmar `alembic current`.
7. Iniciar Worker com desired count inicial 1.
8. Iniciar Beat com desired count exatamente 1.
9. Confirmar logs de arranque, registo de tarefas e publicação dos agendamentos.
10. Configurar e testar SES e Meta com envio desativado globalmente.
11. Só depois de validação legal, operacional e humana, ativar os canais de saída.

## 7. Estado do processamento de mensagens

**Importante:** a aprovação grava a mensagem e o registo Outbox na mesma transação PostgreSQL. O Beat agenda o relay; o Worker publica apenas o ID da mensagem numa fila SQS FIFO cifrada e consome essa fila. A fila tem DLQ, redrive após cinco receções e alarme CloudWatch quando há mensagens visíveis na DLQ. Confirmar que o tópico SNS de alertas tem uma subscrição operacional. O consumidor revalida permissões e consentimento antes de enviar. Resultados ambíguos são marcados `delivery_uncertain` e exigem reconciliação humana; não são reenviados automaticamente.

Antes de ativar comunicações em produção, implementar:
- registo Outbox na mesma transação que aprova a mensagem;
- relay/consumer durável com identificador idempotente;
- SQS com DLQ, visibilidade e redrive policy;
- reconciliação para resultados ambíguos do fornecedor, sem reenviar cegamente mensagens em estado `sending`;
- callbacks de entrega/leitura Meta e eventos SES, persistidos com deduplicação.

O estado `sent` atual significa aceitação pelo fornecedor, não confirmação de entrega ao destinatário.

## 8. Monitorização e aceitação

- [ ] Worker inicia e regista as tarefas Celery esperadas.
- [ ] Beat inicia e publica os agendamentos configurados.
- [ ] Existe apenas uma instância Beat ativa.
- [ ] Worker e Beat ligam-se ao Redis e RDS.
- [ ] Logs CloudWatch distinguem API, Worker e Beat.
- [ ] Falhas e reinícios ECS são observáveis.
- [ ] SES identity/DKIM e acesso de envio estão verificados.
- [ ] Webhook Meta é validado e deduplicado.
- [ ] Canais de saída permanecem desativados até aprovação operacional.
- [ ] Nenhuma lead é criada nem qualquer proprietário é contactado automaticamente pela pesquisa automática.

## 9. Limites de segurança

A pesquisa automática recolhe e sintetiza informação pública e cria relatórios internos para revisão. Não cria leads nem contacta proprietários. Qualquer comunicação externa exige consentimento aplicável, verificação do destinatário e aprovação humana explícita.
