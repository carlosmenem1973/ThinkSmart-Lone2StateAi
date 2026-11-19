# Procura IA — experiência visual

Preserva React/Amplify, Cognito, FastAPI/ECS, RDS e AgentCore. Não cria tabelas nem migrações.

- A pesquisa mantém text, sources e result_count e acrescenta properties[].
- As imagens vêm exclusivamente de Open Graph, Twitter Card ou JSON-LD do anúncio original. Se não houver imagem, o cartão mostra esse facto; nunca usa stock ou imagens geradas.
- A análise visual usa Bedrock Converse com BEDROCK_VISION_MODEL_ID, por defeito eu.amazon.nova-2-lite-v1:0, e descreve apenas elementos observáveis. Não faz avaliação financeira, inspeção estrutural nem identificação de pessoas.
- O mapa usa OpenStreetMap embed e só cria marcadores para coordenadas publicadas em JSON-LD. Sem coordenadas, apresenta pesquisa por endereço; não inventa pins.
- A extração limita tempo, tamanho e redirects e rejeita DNS/IP não públicos. Isto não substitui egress firewall; bloquear RFC1918, loopback, link-local, metadata endpoints e IPv6 privados na rede.
- Antes de armazenar/caching imagens, obter autorização/licença e definir retenção, atribuição e takedown. Esta implementação não copia imagens para S3.

## IAM necessário antes de ativar Vision

A Task Role thinksmart-ecs-task-role precisa de bedrock:InvokeModel e bedrock:InvokeModelWithResponseStream para o inference profile Nova 2 Lite EU, modelos de destino autorizados e bedrock:GetInferenceProfile. Validar os ARNs reais e a condição bedrock:InferenceProfileArn na conta antes de aplicar. Manter a política atual Nova Lite e AgentCore Web Search.

## Rollout

1. Validar IAM e disponibilidade do perfil EU Nova 2 Lite.
2. Executar testes backend e npm run build.
3. Publicar backend por commit SHA e nova Task Definition.
4. Publicar frontend no Amplify.
5. Validar Cognito, pesquisa, fontes, fotografias, análise visual e mapa.
6. Manter rollback ECS e Amplify para as versões anteriores.
