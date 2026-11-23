# Instruções para criar os serviços ECS Worker e Beat

## 1. Objetivo e arquitetura

A API FastAPI existente continua no serviço `thinksmart-api`. A execução de tarefas assíncronas e a agenda de pesquisa automática devem correr em serviços ECS Fargate separados:

| Serviço ECS | Processo | Desired count |
|---|---|---:|
| `thinksmart-api` | API FastAPI | Manter configuração atual |
| `thinksmart-worker` | Celery Worker | 1 inicialmente; pode escalar |
| `thinksmart-beat` | Celery Beat | **Exatamente 1** |

O Worker consome tarefas da fila. O Beat publica tarefas agendadas. Não executar Beat em cada réplica do Worker: isso pode originar agendamentos duplicados. A proteção por lock na base de dados é uma salvaguarda adicional, não substitui a regra de manter um único Beat ativo.

## 2. Pré-requisitos

Antes de criar os serviços, confirmar:

- Cluster ECS: `thinksmart-cluster`, região `eu-west-1`.
- Imagem ECR da mesma versão imutável utilizada pela API (preferir digest SHA256, não uma tag mutável).
- Task Role e Execution Role atuais, sem alargar permissões desnecessariamente.
- Secrets Manager: reutilizar referências existentes, incluindo `DATABASE_URL` e `SECRET_KEY`; nunca copiar valores secretos para texto simples.
- Configuração do broker Celery/Redis e respetivo acesso de rede.
- Variáveis existentes para AWS Region, Bedrock e AgentCore Web Search.
- Sub-redes privadas, Security Group e configuração de logs CloudWatch já utilizados pela API.
- Dependências instaladas na imagem: Celery, driver PostgreSQL e dependências do projeto.

Não criar uma nova base de dados nem alterar Cognito, utilizadores, leads ou dados existentes para implementar estes serviços.

## 3. Criar as Task Definitions

Criar duas novas famílias a partir da Task Definition atualmente utilizada por `thinksmart-api`:

- `thinksmart-worker`
- `thinksmart-beat`

Clonar a configuração funcional da API e preservar, após revisão:

- `requiresCompatibilities: [FARGATE]`
- `networkMode: awsvpc`
- CPU e memória adequadas ao processo
- Execution Role e Task Role
- imagem ECR pelo mesmo digest da release da API
- environment variables não secretas necessárias
- referências Secrets Manager/SSM já existentes
- configuração de rede e logging

Não copiar cegamente o health check HTTP da API: os processos Worker e Beat não servem o endpoint HTTP da API. Remover esse health check ou substituí-lo por uma verificação adequada ao processo.

### 3.1 Comando do Worker

No container principal da Task Definition `thinksmart-worker`, configurar o comando:

```json
["celery", "-A", "app.workers.celery_app.celery", "worker", "--loglevel=INFO", "--concurrency=2"]
```

Começar com concorrência 2 e uma réplica. Ajustar CPU, memória e concorrência após observar utilização, latência e backlog.

### 3.2 Comando do Beat

No container principal da Task Definition `thinksmart-beat`, configurar:

```json
["celery", "-A", "app.workers.celery_app.celery", "beat", "--loglevel=INFO"]
```

O serviço deve manter `desiredCount=1`. Não configurar autoscaling horizontal para Beat.

## 4. Rede e permissões

Usar as sub-redes privadas e o Security Group dos workloads atuais, ou uma regra equivalente devidamente revista.

Os serviços precisam de:

- acesso ao Redis/broker e backend Celery;
- acesso ao RDS PostgreSQL;
- saída HTTPS para Bedrock Runtime e AgentCore Web Search;
- acesso a CloudWatch Logs;
- acesso aos recursos AWS necessários através de NAT Gateway ou VPC Endpoints adequados.

As regras de entrada do Redis e RDS devem permitir apenas o Security Group dos serviços ECS, nas portas efetivamente configuradas. Não tornar RDS ou Redis públicos.

Validar as permissões IAM para invocação do modelo Nova Lite e da ferramenta AgentCore Web Search. Manter o princípio do menor privilégio. Não atribuir permissões administrativas genéricas.

## 5. Migração da base de dados

A migração da funcionalidade de pesquisa automática deve ser executada uma única vez, como tarefa ECS pontual, usando a mesma imagem e configuração de produção:

```bash
alembic upgrade head
alembic current
```

Confirmar que a revisão atual é `0006_property_discovery` (ou a revisão equivalente que estiver efetivamente no branch/release).

**Não** executar migrações em paralelo em cada réplica da API, Worker ou Beat. Fazer backup e seguir o procedimento normal de alterações de schema antes da migração de produção.

## 6. Ordem de implementação

1. Rever e aprovar o código e os testes da release.
2. Construir e publicar a imagem backend no ECR.
3. Registar a Task Definition da API com a imagem aprovada e publicar a API, se necessário.
4. Executar a migração Alembic uma única vez como tarefa pontual.
5. Confirmar a revisão Alembic e a conectividade com RDS/Redis.
6. Registar a Task Definition `thinksmart-worker`.
7. Criar o serviço `thinksmart-worker` com desired count 1.
8. Registar a Task Definition `thinksmart-beat`.
9. Criar o serviço `thinksmart-beat` com desired count exatamente 1.
10. Verificar logs, registo de tarefas, scheduler e execução controlada.
11. Só depois ativar a pesquisa automática na configuração administrativa.

Não ativar a pesquisa automática enquanto Worker, Beat, Redis, RDS e migração não estiverem validados.

## 7. Logs e monitorização

Pode reutilizar o grupo `/ecs/thinksmart-api`, desde que os stream prefixes distingam claramente `worker` e `beat`; em alternativa, criar grupos dedicados com retenção definida.

Monitorizar:

- Worker: arranque, tarefas recebidas, duração, falhas e retries.
- Beat: arranque e publicação do agendamento `property-discovery-scheduler` (configurado no código para cada 300 segundos).
- ECS: desired/running/pending count, reinícios e deployments falhados.
- Redis: disponibilidade, ligações e tamanho da fila.
- RDS: ligações, erros e capacidade.
- Bedrock/AgentCore: throttling, timeouts e erros de invocação.

Criar alarmes para Worker/Beat sem tarefas em execução, falhas repetidas e serviço indisponível. Garantir que só existe uma instância Beat ativa durante substituições e deployments.

## 8. Teste de aceitação

- [ ] Worker inicia e regista as tarefas Celery esperadas.
- [ ] Beat inicia e publica o agendamento esperado.
- [ ] Existe apenas uma instância Beat ativa.
- [ ] Worker liga-se ao Redis e à base de dados.
- [ ] Uma execução manual controlada cria apenas um relatório de pesquisa/auditoria.
- [ ] Configuração desativada não invoca Bedrock.
- [ ] Falhas ficam registadas e são observáveis.
- [ ] Nenhuma lead é criada nem qualquer proprietário é contactado automaticamente.

## 9. Limites de segurança

A pesquisa automática recolhe e sintetiza informação pública e cria relatórios internos para revisão. Não cria leads, não envia email/SMS/WhatsApp e não realiza chamadas telefónicas. A identificação de proprietário, elegibilidade de contacto e qualquer comunicação externa exigem fluxo próprio, validação legal e aprovação humana explícita.
