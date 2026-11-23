# Regras para deduplicação, verificação de proprietários e aprovação humana

## 1. Objetivo e âmbito

Este documento define as regras de integridade para transformar resultados de pesquisa imobiliária em candidatos e, posteriormente, em oportunidades CRM.

Aplica-se à pesquisa manual e automática, extração de anúncios, comparação com dados CRM, verificação de identidade e preparação de contactos.

**Regra fundamental:** resultados públicos são pistas de pesquisa. Não são prova automática de propriedade, identidade, autorização de contacto ou oportunidade comercial qualificada.

## 2. Deduplicação de imóveis e anúncios

### 2.1 Normalização

Antes de comparar registos, normalizar sem destruir o valor original:

- URL: remover parâmetros de tracking conhecidos, normalizar host e caminho, remover fragmentos não relevantes; não remover parâmetros que identifiquem o anúncio.
- Referência do portal: normalizar espaços e capitalização; manter o portal como parte da chave.
- Endereço: normalizar espaços, pontuação, abreviaturas e capitalização; preservar número, fração, código postal e localidade.
- Localidade: normalizar acentos e variantes apenas para comparação; manter a forma original para apresentação.
- Características: normalizar unidades (por exemplo, m²) e tipos, sem preencher valores ausentes.

Guardar sempre o valor original e o valor normalizado, quando aplicável.

### 2.2 Hierarquia de correspondência

| Sinal | Interpretação | Ação |
|---|---|---|
| Mesmo portal + mesma referência única | Correspondência forte | Duplicado confirmado, salvo conflito material |
| Mesmo URL canónico | Correspondência forte | Duplicado confirmado |
| Mesmo endereço completo e mesma fração | Correspondência forte | Provável duplicado; confirmar conflitos |
| Mesmo endereço incompleto + características semelhantes | Correspondência média/fraca | Revisão humana |
| Mesma zona, preço ou tipologia | Insuficiente isoladamente | Não deduplicar |

Não usar nome do anunciante, telefone ou email como prova de que dois imóveis são o mesmo imóvel.

### 2.3 Decisão e fusão

Estados:
- `DISTINCT`: evidência suficiente de que são registos diferentes.
- `DUPLICATE_CONFIRMED`: correspondência inequívoca.
- `POSSIBLE_DUPLICATE`: semelhança que exige revisão.
- `INSUFFICIENT_DATA`: dados insuficientes para decidir.
- `CONFLICT`: fontes contraditórias.

A fusão automática só é permitida para anúncios tecnicamente idênticos pela mesma chave única e sem conflito nos dados essenciais. Nos restantes casos, exigir decisão humana.

Ao fundir:
- escolher um registo principal e preservar os IDs de origem;
- manter todas as fontes e datas de recolha;
- não apagar histórico, notas, auditoria ou relações;
- não substituir campos verificados por dados de menor confiança;
- registar quem/que processo fez a fusão e porquê;
- permitir rastrear e corrigir a decisão.

Uma nova publicação do mesmo imóvel pode ser um anúncio diferente e deve manter-se ligada ao mesmo imóvel, não ser descartada como se fosse a mesma publicação.

## 3. Deduplicação de contactos e proprietários

Imóvel, anúncio, pessoa e oportunidade são entidades distintas.

- Não fundir pessoas apenas porque têm o mesmo nome.
- Não fundir contactos apenas porque partilham endereço.
- Email/telefone coincidente pode ser sinal de correspondência, não prova suficiente de identidade ou titularidade.
- Não assumir que o anunciante, mediador, representante ou ocupante é o proprietário.
- Se houver homónimos, coproprietários ou papéis contraditórios, manter registos separados e marcar conflito.
- Não associar automaticamente uma pessoa a todos os imóveis de uma morada.

Qualquer associação de pessoa a imóvel deve guardar o papel alegado (por exemplo, proprietário, representante, mediador, anunciante), a fonte e o estado de verificação.

## 4. Verificação de proprietário

### 4.1 Estados permitidos

- `UNVERIFIED`: identidade/papel não comprovados.
- `PENDING_REVIEW`: existe evidência, aguarda validação.
- `VERIFIED`: verificação concluída por pessoa/processo autorizado, com evidência adequada.
- `CONFLICT`: fontes contraditórias ou identidade incerta.
- `REJECTED`: alegação não sustentada ou incorreta.

Nunca atribuir `VERIFIED` com base apenas em:
- snippet de motor de pesquisa;
- anúncio sem confirmação independente;
- nome de anunciante;
- perfil de rede social;
- coincidência de email/telefone;
- inferência do modelo de IA.

### 4.2 Evidência e auditoria

Para cada verificação, guardar apenas os dados necessários:
- pessoa/contacto e papel que se pretende confirmar;
- tipo de fonte e referência/documento;
- URL ou identificador da evidência, quando legalmente permitido;
- data de consulta;
- responsável pela revisão;
- decisão, fundamento e nível de confiança;
- conflitos e limitações encontrados.

O modelo de IA pode resumir evidência e apontar inconsistências, mas não pode declarar autonomamente um proprietário como verificado. O acesso a documentos oficiais ou dados sujeitos a restrições deve respeitar a autorização e a finalidade legal aplicável.

## 5. Elegibilidade para contacto

A verificação do proprietário não equivale a autorização para contacto. Manter estados independentes:

- `CONTACT_ELIGIBILITY_PENDING`
- `ELIGIBLE`
- `NOT_ELIGIBLE`
- `RESTRICTED`

Antes de preparar ou aprovar contacto, registar e validar:
- finalidade específica;
- base legal aplicável e respetiva justificação;
- origem dos dados e data de recolha;
- canal pretendido e regras aplicáveis a esse canal;
- consentimento, quando exigido;
- oposição/opt-out e listas de supressão;
- prazo de retenção e necessidade de conservação.

A presença de um email ou telefone numa página pública não significa consentimento para marketing. Em caso de dúvida, bloquear o contacto e encaminhar para revisão de conformidade. A implementação deve ser revista face ao RGPD e às regras portuguesas/europeias aplicáveis, incluindo regras específicas de comunicações eletrónicas.

## 6. Aprovação humana obrigatória

### 6.1 Criação de oportunidade CRM

Antes da criação:
1. candidato extraído com fontes por campo;
2. deduplicação concluída;
3. conflitos resolvidos ou explicitamente aceites com justificação;
4. permissões e âmbito de visibilidade verificados;
5. utilizador autorizado seleciona **Aceitar e criar oportunidade**.

A ação deve guardar utilizador, timestamp, candidato de origem, decisão, motivo e ID da oportunidade criada. A criação deve ser idempotente para impedir duplicados em retries.

### 6.2 Comunicação externa

Cada comunicação requer aprovação humana separada, mesmo que a oportunidade já exista.

A aprovação deve mostrar:
- destinatário e identidade/estado de verificação;
- imóvel e contexto;
- finalidade e base legal registada;
- canal;
- mensagem integral;
- anexos, se existirem;
- opt-out/restrições;
- utilizador aprovador e data.

Qualquer alteração ao destinatário, canal, finalidade ou conteúdo após aprovação invalida a aprovação e exige nova revisão.

O sistema pode gerar rascunhos, mas não pode enviar automaticamente emails, SMS, WhatsApp nem iniciar chamadas. Não contactar proprietários a partir de tarefas de pesquisa ou extração.

## 7. Permissões e segregação de dados

- Aplicar RBAC do CRM existente.
- Respeitar o âmbito de vendedor/equipa/organização em todas as pesquisas, listas, APIs e tarefas de fundo.
- Não expor dados de outro vendedor/tenant em resultados de deduplicação.
- Operações administrativas devem ser auditadas.
- A conta técnica do Worker deve ter apenas as permissões necessárias para executar pesquisa e persistir resultados autorizados.
- Não permitir que o modelo de IA contorne controlos de acesso ou execute ações privilegiadas.

## 8. Auditoria, retenção e correção

Registar eventos para:
- candidato criado/atualizado;
- correspondência encontrada e decisão de deduplicação;
- fusão ou separação de registos;
- verificação de proprietário;
- decisão de elegibilidade de contacto;
- aceitação/rejeição humana;
- criação de oportunidade;
- aprovação/revogação de contacto.

Guardar fonte, autor/processo, timestamp e motivo. Definir prazos de retenção e mecanismos de correção/eliminação de acordo com a política aplicável. Não conservar dados pessoais sem finalidade e fundamento documentados.

## 9. Critérios mínimos de teste

- Variações de acentos, abreviaturas e espaços no endereço.
- Mesmo imóvel em URLs com parâmetros de tracking.
- Referências iguais em portais diferentes.
- Endereço incompleto e anúncios sem referência.
- Imóveis diferentes no mesmo edifício.
- Homónimos e contactos partilhados.
- Anunciante que não é proprietário.
- Evidência contraditória.
- Tentativa de acesso entre vendedores/tenants.
- Retry de criação de oportunidade.
- Tentativa de envio sem aprovação ou após alteração da mensagem.
- Opt-out e contacto não elegível.

Todos os casos ambíguos devem terminar em revisão humana, nunca numa fusão, verificação ou comunicação automática.
