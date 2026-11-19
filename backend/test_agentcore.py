import boto3

client = boto3.client("bedrock-agentcore", region_name="eu-west-1")

response = client.invoke_web_search(
    webSearchId="web-search.v1",
    searchQuery="mercado imobiliário Portugal 2026",
    maxResults=3
)

print("AgentCore Web Search: OK")
for item in response.get("results", []):
    print("Título:", item.get("title"))
    print("URL:", item.get("url"))
    print("---")
