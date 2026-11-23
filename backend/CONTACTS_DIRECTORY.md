# Diretório de Proprietários e Clientes

Esta funcionalidade acrescenta uma base de contactos independente dos leads imobiliários.

## Tipos
- owner: proprietário ou potencial vendedor/senhorio.
- client: comprador, investidor ou cliente à procura de imóvel.

## Funcionalidades
- Criar e atualizar contactos.
- Arquivar contactos sem apagar o histórico.
- Filtrar por tipo e pesquisar por nome, email, telefone ou município.
- Importar CSV; registos duplicados por tipo/nome ou tipo/email são ignorados.
- Selecionar contactos e executar o Agente de Descoberta com critérios imobiliários agregados.

## API
Todos os endpoints exigem autenticação Cognito:
- GET /api/v1/contacts?contact_type=owner|client&q=Lisboa
- POST /api/v1/contacts
- PATCH /api/v1/contacts/{id}
- DELETE /api/v1/contacts/{id} (arquivo lógico)
- POST /api/v1/contacts/import com {"csv":"..."}
- POST /api/v1/contacts/agent-audience com {"contact_ids":[1,2]}

A audiência devolve apenas tipo de contacto, localização, preferências e orçamento. Nome, email e telefone não são enviados ao modelo. O frontend usa estes critérios agregados para executar POST /api/v1/agents/property-discovery/run. A pesquisa não envia mensagens.

## CSV
Obrigatórias: contact_type,full_name.
Opcionais: email,phone,municipality,district,property_preferences,source,lawful_basis,contact_permission,do_not_contact.
Tipos: owner ou client. Booleanos: 1,true,yes,sim.

## Segurança e privacidade
- Acesso autenticado; viewers só consultam.
- Vendedores veem apenas os contactos atribuídos à sua conta.
- Administradores e gestores têm visibilidade global.
- A lista do-not-contact prevalece sobre a permissão.
- A audiência exclui contactos inativos e contactos em supressão.
- Permissão de contacto e referência de base legal são campos separados e não são inferidos automaticamente.
- O envio de email/SMS/voz continua desligado. O agente apenas pesquisa oportunidades; qualquer pedido de contacto exige processo separado, revisão humana e validação de base legal e permissão do canal.
- Não importar dados pessoais sem origem e fundamento documentados.

## Migração
A revisão Alembic 0006_contacts_directory depende de 0005_contact_ai. Aplicar a migração antes de executar a nova API.
