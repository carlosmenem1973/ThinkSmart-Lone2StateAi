import boto3

region = "eu-west-1"
model_id = "eu.amazon.nova-lite-v1:0"

client = boto3.client("bedrock-runtime", region_name=region)

response = client.converse(
    modelId=model_id,
    messages=[
        {
            "role": "user",
            "content": [{"text": "Responde em português: escreve apenas 'Nova Lite operacional'."}]
        }
    ],
    inferenceConfig={
        "maxTokens": 100,
        "temperature": 0.2
    }
)

print(response["output"]["message"]["content"][0]["text"])
print("Nova Lite: OK")
