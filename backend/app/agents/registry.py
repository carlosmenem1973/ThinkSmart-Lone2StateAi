"""Logical specialist-agent definitions; execution is handled by the FastAPI agent router."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    mode: str
    instruction: str


AGENTS = (
    AgentDefinition(
        id="property-discovery",
        name="Agente de Descoberta",
        mode="web",
        instruction="Descobrir oportunidades imobiliárias em fontes públicas autorizadas em Portugal.",
    ),
    AgentDefinition(
        id="market-analyst",
        name="Agente de Mercado",
        mode="web",
        instruction="Analisar preços anunciados, oferta e tendências com fontes e datas.",
    ),
    AgentDefinition(
        id="lead-qualifier",
        name="Agente de Qualificação",
        mode="database",
        instruction="Qualificar leads com base apenas nos dados existentes e na evidência disponível.",
    ),
    AgentDefinition(
        id="owner-intelligence",
        name="Agente de Proprietários",
        mode="web",
        instruction="Organizar informação pública verificável sem inferir identidade ou propriedade.",
    ),
    AgentDefinition(
        id="email-intelligence",
        name="Agente de Email",
        mode="unavailable",
        instruction="Aguarda integração Microsoft 365 delegada e isolada por utilizador.",
    ),
    AgentDefinition(
        id="follow-up-assistant",
        name="Agente de Seguimento",
        mode="database",
        instruction="Analisar seguimentos pendentes e sugerir próximos passos sem enviar mensagens.",
    ),
)
