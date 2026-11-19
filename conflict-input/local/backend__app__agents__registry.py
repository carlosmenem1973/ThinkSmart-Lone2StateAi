"""Registry for the six ThinkSmart AI agents exposed by the API."""
AGENTS = {
    "property-discovery": {
        "name": "Agente de Descoberta",
        "description": "Identifica oportunidades imobili├írias em fontes p├║blicas autorizadas.",
        "source": "web",
    },
    "market-analyst": {
        "name": "Agente de Mercado",
        "description": "Analisa pre├ºos, zonas, tend├¬ncias e posicionamento.",
        "source": "mixed",
    },
    "lead-qualifier": {
        "name": "Agente de Qualifica├º├úo",
        "description": "Organiza e classifica oportunidades da equipa comercial.",
        "source": "internal",
    },
    "owner-intelligence": {
        "name": "Agente de Informa├º├úo P├║blica",
        "description": "Estrutura informa├º├úo p├║blica e validada sobre an├║ncios.",
        "source": "web",
    },
    "email-intelligence": {
        "name": "Agente de Email",
        "description": "Organiza pedidos, mensagens e oportunidades j├í processadas.",
        "source": "internal",
    },
    "follow-up-assistant": {
        "name": "Agente de Seguimento",
        "description": "Prepara pr├│ximos passos e sugest├Áes de acompanhamento.",
        "source": "internal",
    },
}
