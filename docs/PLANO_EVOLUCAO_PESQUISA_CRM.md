# Plano de evolução da pesquisa até à criação de oportunidades no CRM

## 1. Estado atual

A funcionalidade atual permite pesquisa manual/agendada através do AgentCore Web Search, síntese dos resultados com Amazon Nova Lite e registo do relatório e das fontes no histórico/audit log.

Este resultado é informação de pesquisa, não uma oportunidade CRM validada. Um anúncio, excerto de pesquisa ou página pública não prova, por si só, que uma pessoa é proprietária do imóvel nem que pode ser contactada.

## 2. Princípios de desenho

- Reutilizar as entidades, permissões e fluxos CRM existentes.
- Preservar origem, URL, data de recolha e evidência de cada campo.
- Separar imóvel, anúncio, pessoa/contacto e oportunidade comercial.
- Distinguir informação declarada, inferida e verificada.
- Não transformar automaticamente resultados de pesquisa em leads.
- Aplicar sempre isolamento por organização/equipa/utilizador e as regras de visibilidade de vendedores.
- Registar decisões e alterações relevantes em auditoria.
- Não enviar comunicações externas automaticamente.

## 3. Fases de evolução

### Fase 1 — Relatório de pesquisa (implementação atual)

**Objetivo:** encontrar informação pública relevante e apresentar um relatório.

Resultado:
- consulta de pesquisa;
- síntese produzida pelo modelo;
- URLs e fontes disponíveis;
- data da pesquisa;
- estado e histórico da execução.

Critério de conclusão: relatório consultável por utilizador autorizado, com fontes preservadas e sem criação de leads.

### Fase 2 — Extração de candidatos

**Objetivo:** converter resultados em candidatos estruturados a imóveis/oportunidades, sem os inserir ainda como leads aceites.

Campos possíveis:
- tipo de imóvel;
- endereço e localidade;
- preço/moeda, se publicado;
- área, tipologia e características, se publicadas;
- referência do anúncio/portal;
- URL canónico;
- data de publicação, quando disponível;
- data de recolha;
- fonte por campo;
- confiança e estado de verificação.

Regras:
- não inventar campos ausentes;
- não inferir proprietário a partir do anunciante;
- preservar o texto original e a evidência;
- marcar dados contraditórios como conflito para revisão.

### Fase 3 — Deduplicação e correspondência

**Objetivo:** comparar candidatos com anúncios, imóveis e leads existentes.

Comparar, por ordem de robustez:
1. identificador/referência única do portal, dentro do respetivo portal;
2. URL canónico normalizado;
3. endereço normalizado e localidade;
4. combinação de características do imóvel, apenas como sinal auxiliar.

Resultado possível:
- duplicado confirmado;
- provável duplicado;
- candidato distinto;
- insuficiência de dados.

Não fundir automaticamente registos com identidade ambígua. A regra detalhada está em `REGRAS_DEDUPLICACAO_PROPRIETARIOS_APROVACAO.md`.

### Fase 4 — Fila de qualificação humana

**Objetivo:** permitir que um utilizador autorizado decida o destino do candidato.

Ações:
- aceitar para avaliação CRM;
- rejeitar e indicar motivo;
- pedir pesquisa adicional;
- marcar como duplicado de um registo existente;
- colocar em espera por falta de evidência.

Apenas candidatos aceites podem avançar para a criação de oportunidade, após as validações e permissões necessárias. A decisão deve guardar utilizador, data, motivo e evidência consultada.

### Fase 5 — Verificação de proprietário e elegibilidade

**Objetivo:** avaliar separadamente se a identidade do proprietário está comprovada e se existe base legal para o contacto.

Não assumir que:
- anunciante = proprietário;
- agente imobiliário = proprietário;
- contacto publicado = autorização para qualquer campanha;
- presença de dados na Internet = consentimento.

Registar:
- identidade e papel alegado;
- fonte e evidência;
- estado de verificação;
- data e responsável pela verificação;
- finalidade e base legal documentada;
- canal permitido e eventuais restrições;
- origem e data dos dados;
- prazo/regras de retenção aplicáveis.

A verificação deve usar fontes fiáveis e procedimentos legalmente adequados. Dados não confirmados permanecem explicitamente não verificados.

### Fase 6 — Criação da oportunidade no CRM

**Objetivo:** criar uma oportunidade apenas depois da qualificação humana.

Pré-condições:
- candidato não é duplicado de oportunidade existente;
- campos obrigatórios estão completos e rastreáveis;
- utilizador tem permissão para criar/associar o registo;
- decisão humana de aceitação está registada;
- associação entre imóvel, contacto e oportunidade não contém conflitos por resolver.

A criação deve ser transacional e idempotente, com referência ao candidato de origem, evitando oportunidades repetidas em retries.

### Fase 7 — Preparação e aprovação de contacto

O sistema pode preparar um rascunho interno. Antes de qualquer envio, um utilizador deve aprovar:
- destinatário exato;
- canal;
- finalidade;
- base legal e permissões;
- texto final;
- momento do envio.

O envio automático está fora do âmbito destas fases. Não realizar chamadas, emails, SMS ou WhatsApp sem aprovação humana e validação de conformidade.

## 4. Modelo de estados sugerido

```text
DISCOVERED
  -> EXTRACTED
  -> NEEDS_REVIEW
  -> ACCEPTED | REJECTED | NEEDS_MORE_RESEARCH
  -> DEDUPLICATED | DISTINCT | POSSIBLE_DUPLICATE
  -> OWNER_UNVERIFIED | OWNER_VERIFIED | OWNER_CONFLICT
  -> CONTACT_ELIGIBILITY_PENDING | ELIGIBLE | NOT_ELIGIBLE
  -> CRM_OPPORTUNITY_CREATED
  -> OUTREACH_DRAFTED
  -> OUTREACH_APPROVED
```

Os estados devem ser transições auditáveis; não saltar diretamente de `DISCOVERED` para `CRM_OPPORTUNITY_CREATED`.

## 5. Componentes técnicos a implementar

1. Serviço de extração estruturada com validação de schema.
2. Repositório/tabela de candidatos, após revisão do modelo de dados atual.
3. Serviço determinístico de normalização e deduplicação.
4. Fila/API de revisão humana com RBAC.
5. Serviço de verificação de identidade/elegibilidade com evidência.
6. Serviço de criação idempotente de oportunidade, reutilizando entidades CRM existentes.
7. Auditoria, retenção e métricas por fase.

Antes de criar tabelas ou migrations, inspecionar o schema e as regras atuais de Lead, FollowUp, User, AuditLog e respetivos acessos. Não duplicar entidades existentes sem necessidade.

## 6. Critérios de aceitação para produção

- Cada campo extraído tem origem e data de recolha.
- Dados desconhecidos permanecem nulos/desconhecidos, não são inventados.
- Duplicados confirmados não criam novas oportunidades.
- Casos ambíguos seguem para revisão humana.
- Testes demonstram isolamento de dados e permissões por vendedor/equipa.
- Apenas aceitação humana cria oportunidade.
- Retries não duplicam registos.
- Proprietário e elegibilidade de contacto têm estados independentes.
- Nenhuma comunicação externa é enviada automaticamente.
- Decisões, alterações e aprovações são auditáveis.

## 7. Sequência recomendada

Implementar por incrementos: extração e schema -> deduplicação -> fila de revisão -> verificação de proprietário/elegibilidade -> criação idempotente de oportunidade -> rascunho de contacto e aprovação. Não avançar para a fase seguinte enquanto os critérios de aceitação da anterior não estiverem testados.
