# ThinkSmart AI — preparação de rollout Omnichannel com AWS CLI

Este documento substitui os passos OpenTofu do guia de rollout para a infraestrutura Production existente. É um runbook de preparação: **não executar comandos de escrita em Production sem autorização explícita e revisão do impacto**.

## 1. Recursos Production existentes

- Região: `eu-west-1`
- Cluster ECS: `thinksmart-cluster`
- Serviço API: `thinksmart-api`
- Task Definition API atual: família `thinksmart-api`, revisão 18 (a confirmar antes de qualquer rollout)
- Imagem atualmente em uso: repositório ECR `thinksmart-api`
- Secret da aplicação: `thinksmart/production`
- Log group API: `/ecs/thinksmart-api`

Não criar um segundo cluster, VPC, ALB, RDS, Cognito, CloudFront ou bucket para esta funcionalidade. Não assumir os nomes de recursos da infraestrutura OpenTofu deste PR.

## 2. Email híbrido

O worker aplica esta regra de encaminhamento:
- `purpose=transactional` → Amazon SES.
- `purpose=service`, `property_enquiry` ou `marketing` → Microsoft Graph.

O canal escolhido tem de estar registado, ativo e com outbound ativado. A aprovação humana e a validação de consentimento continuam obrigatórias.

### Microsoft Graph — pré-requisitos externos

O adaptador usa client credentials (app-only) e o endpoint `/users/{sender}/sendMail`. Antes de o ativar:
1. Configurar um tenant ID Microsoft Entra específico (não usar `common`).
2. Conceder à aplicação Microsoft Graph a permissão **Application** `Mail.Send`.
3. Conceder admin consent no tenant.
4. Restringir a aplicação à mailbox remetente autorizada através de Exchange Online Application RBAC ou mecanismo equivalente.
5. Configurar `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID` e `MICROSOFT_GRAPH_SENDER` no secret da aplicação.
6. Testar numa mailbox controlada antes de habilitar o canal.

A integração Microsoft 365 existente de leitura de mensagens usa permissões delegadas; não implica que a permissão app-only `Mail.Send` já exista. Não presumir que o envio está autorizado.

### Amazon SES

- Remetente configurado: `EMAIL_FROM_ADDRESS` (por omissão `contacto@cbloft2.pt`).
- Região: `eu-west-1`.
- `SES_SENDER_VERIFIED=true` apenas depois da identidade, DKIM e estado de produção estarem confirmados.
- Preservar o SPF Microsoft 365 existente e manter um único registo SPF consolidado.

## 3. Atualização segura do Secrets Manager

Usar o novo helper `scripts/aws/merge-runtime-secrets.sh` apenas depois de revisão. O helper:
- lê o JSON atual do secret;
- altera apenas chaves explicitamente fornecidas no ambiente;
- preserva as restantes chaves existentes;
- não imprime valores secretos.

Exemplo de preparação local (não executar até haver autorização):
```bash
export AWS_REGION=eu-west-1
export APP_SECRET_ID=thinksmart/production
# Definir apenas as variáveis aprovadas, num ambiente seguro.
bash scripts/aws/merge-runtime-secrets.sh
```

Não usar o antigo `scripts/aws/set-runtime-secrets.sh`: constrói um JSON novo e pode substituir configurações existentes. Não colocar segredos em argumentos CLI, commits, logs ou mensagens.

## 4. Inventário AWS CLI — apenas leitura

Antes de preparar Task Definitions ou serviços, recolher novamente o estado real:
```powershell
aws sts get-caller-identity --profile default

aws ecs describe-clusters --clusters thinksmart-cluster --region eu-west-1 --profile default

aws ecs describe-services --cluster thinksmart-cluster --services thinksmart-api --region eu-west-1 --profile default

aws ecs describe-task-definition --task-definition thinksmart-api:18 --region eu-west-1 --profile default

aws secretsmanager describe-secret --secret-id thinksmart/production --region eu-west-1 --profile default

aws sqs list-queues --region eu-west-1 --profile default

aws iam list-role-policies --role-name thinksmart-ecs-task-role --region eu-west-1 --profile default
```

Guardar os resultados de configuração em ficheiros locais protegidos; nunca guardar `SecretString` em relatórios, commits ou tickets.

## 5. Infraestrutura ainda necessária

O inventário anterior identificou que ainda não existem filas SQS no ambiente e que o Task Role atual não apresenta permissões SQS. Também não foram identificados serviços ECS Worker/Beat nem um Redis ElastiCache. Antes de lançar o worker:
- decidir onde ficará o Redis e confirmar conectividade privada;
- provisionar SQS FIFO cifrada e DLQ FIFO, com redrive após cinco receções;
- adicionar política SQS de privilégio mínimo ao Task Role existente, sem substituir permissões Bedrock/Cognito;
- criar Task Definitions separadas para Worker e Beat usando a imagem aprovada;
- criar serviços ECS separados no cluster existente;
- garantir Beat com desired count exatamente 1 e deployment sem sobreposição;
- verificar rotas privadas/NAT e regras de segurança para Redis 6379 e PostgreSQL 5432.

Não executar `create-queue`, `put-role-policy`, `register-task-definition`, `create-service` ou `update-service` até haver plano aprovado, nomes finais, imagem e configuração de rede confirmados.

## 6. Migração e rollout

A migração `alembic upgrade head` deve correr exatamente uma vez como tarefa ECS one-off, com a imagem aprovada e as mesmas configurações de rede/secret da API. Verificar exit code e `alembic current`. Se falhar, não iniciar API/Worker/Beat com o novo código.

A ordem final será:
1. Aprovar PR e CI.
2. Publicar imagem imutável.
3. Rever inventário e alterações AWS.
4. Preparar filas, permissões, Redis e Task Definitions.
5. Executar migração uma única vez e validar.
6. Atualizar API e iniciar Worker; iniciar Beat apenas com uma réplica.
7. Confirmar logs, conectividade, relay Outbox, DLQ e recuperação.
8. Registar canais com envio desativado.
9. Testar Meta, Graph e SES com destinatários de teste.
10. Ativar outbound apenas após aprovação legal, operacional e humana.

## 7. Limites de segurança

- Nenhuma mensagem sai sem aprovação humana.
- O worker revalida contacto ativo, `contact_permission`, `do_not_contact` e consentimento por canal/finalidade.
- WhatsApp livre continua limitado à janela de atendimento de 24 horas; templates não estão implementados.
- `sent` significa aceitação pelo fornecedor, não confirmação de entrega.
- Resultado ambíguo fica em `delivery_uncertain` e requer reconciliação manual; nunca reenviar cegamente.
- Não fazer alterações na Production como parte deste PR.
