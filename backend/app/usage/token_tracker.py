from dataclasses import dataclass, field
from threading import Lock


@dataclass
class AgentTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += max(0, input_tokens)
        self.output_tokens += max(0, output_tokens)


@dataclass
class TokenTracker:
    max_context_tokens: int
    _usage_by_agent: dict[str, AgentTokenUsage] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def record(self, agent_id: str, input_tokens: int, output_tokens: int) -> AgentTokenUsage:
        with self._lock:
            usage = self._usage_by_agent.setdefault(agent_id, AgentTokenUsage())
            usage.add(input_tokens, output_tokens)
            return AgentTokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )

    def get_usage(self, agent_id: str) -> AgentTokenUsage:
        with self._lock:
            usage = self._usage_by_agent.get(agent_id)
            if usage is None:
                return AgentTokenUsage()
            return AgentTokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )

    def get_all_usage(self) -> dict[str, AgentTokenUsage]:
        with self._lock:
            return {
                agent_id: AgentTokenUsage(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
                for agent_id, usage in self._usage_by_agent.items()
            }

    def reset_all(self) -> int:
        with self._lock:
            count = len(self._usage_by_agent)
            self._usage_by_agent.clear()
            return count

    def reset_agent(self, agent_id: str) -> bool:
        with self._lock:
            return self._usage_by_agent.pop(agent_id, None) is not None

    def usage_percent(self, agent_id: str) -> float:
        if self.max_context_tokens <= 0:
            return 0.0
        total = self.get_usage(agent_id).total_tokens
        return min(100.0, (total / self.max_context_tokens) * 100.0)
