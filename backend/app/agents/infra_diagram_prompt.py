"""Shared system-prompt snippet for infra agents that may produce architecture diagrams."""

INFRA_ARCHITECTURE_D2_INSTRUCTION = (
    "When the user requests an architecture diagram, structure diagram, topology, or visualization "
    "(including requests routed from archi-analysis), query the relevant infrastructure resources first, "
    "then provide a brief explanation in Korean and MUST include a fenced ```d2 code block with a "
    "complete D2 diagram that uses real resource names and relationships from the query results. "
    "Use this structure as a guide:\n"
    "```d2\n"
    "direction: down\n"
    "\n"
    "ingress: Ingress\n"
    "service: Service\n"
    "pod: Pod\n"
    "\n"
    "ingress -> service -> pod\n"
    "```\n"
    "Never say that you cannot generate diagrams."
)
