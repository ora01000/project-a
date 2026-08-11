"""Infrastructure generation gap-analysis agent (static-config, AXIT/mock-catalog independent)."""

from backend.app.infra_gap_analysis.agent import InfraGapAnalysisService, infra_gap_analysis_service
from backend.app.infra_gap_analysis.settings import AGENT_ID, STATIC_CONFIG

__all__ = [
    "AGENT_ID",
    "STATIC_CONFIG",
    "InfraGapAnalysisService",
    "infra_gap_analysis_service",
]
