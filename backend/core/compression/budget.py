"""
TokenBudget — tracks token usage and enforces limits for context assembly.
Uses character-based approximation: 1 token ≈ 4 characters (works for English
prose, code, and both OpenAI and Anthropic models within ±20%).
"""

from __future__ import annotations

from dataclasses import dataclass


CHARS_PER_TOKEN = 4


@dataclass
class BudgetSlot:
    name: str
    priority: int          # higher = more important (kept first when truncating)
    max_tokens: int
    content: str = ""
    tokens_used: int = 0


class TokenBudget:
    def __init__(self, total_tokens: int = 8_000):
        self.total = total_tokens
        self._slots: list[BudgetSlot] = []
        self._used: int = 0

    # ------------------------------------------------------------------
    # Estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate(text: str) -> int:
        return len(text) // CHARS_PER_TOKEN

    @staticmethod
    def truncate_to(text: str, max_tokens: int) -> str:
        limit = max_tokens * CHARS_PER_TOKEN
        if len(text) <= limit:
            return text
        return text[:limit].rsplit("\n", 1)[0] + "\n…[truncated]"

    # ------------------------------------------------------------------
    # Slot management
    # ------------------------------------------------------------------

    def add_slot(self, name: str, priority: int, max_tokens: int) -> "TokenBudget":
        self._slots.append(BudgetSlot(name=name, priority=priority, max_tokens=max_tokens))
        return self

    def fill(self, name: str, content: str) -> bool:
        """Fill a named slot. Returns True if the content fit within its budget."""
        slot = next((s for s in self._slots if s.name == name), None)
        if slot is None:
            raise KeyError(f"No slot named '{name}'")

        tokens = self.estimate(content)
        if tokens > slot.max_tokens:
            content = self.truncate_to(content, slot.max_tokens)
            tokens = self.estimate(content)

        slot.content = content
        slot.tokens_used = tokens
        self._used = sum(s.tokens_used for s in self._slots)
        return tokens <= slot.max_tokens

    def assemble(self) -> str:
        """Assemble slots in priority order into a single string."""
        ordered = sorted(self._slots, key=lambda s: s.priority, reverse=True)
        return "\n\n".join(s.content for s in ordered if s.content)

    @property
    def remaining(self) -> int:
        return self.total - self._used

    @property
    def usage_report(self) -> dict:
        return {
            "total_budget": self.total,
            "used": self._used,
            "remaining": self.remaining,
            "utilisation_pct": round(self._used / self.total * 100, 1),
            "slots": [
                {
                    "name": s.name,
                    "tokens_used": s.tokens_used,
                    "max_tokens": s.max_tokens,
                    "filled": bool(s.content),
                }
                for s in sorted(self._slots, key=lambda x: x.priority, reverse=True)
            ],
        }


# ---------------------------------------------------------------------------
# Pre-configured budget profiles
# ---------------------------------------------------------------------------

def coding_agent_budget(total: int = 6_000) -> TokenBudget:
    """Balanced budget for a coding agent working on a feature."""
    return (
        TokenBudget(total_tokens=total)
        .add_slot("task",          priority=100, max_tokens=200)
        .add_slot("stack",         priority=90,  max_tokens=300)
        .add_slot("coding_style",  priority=80,  max_tokens=400)
        .add_slot("decisions",     priority=75,  max_tokens=600)
        .add_slot("known_errors",  priority=70,  max_tokens=500)
        .add_slot("patterns",      priority=65,  max_tokens=400)
        .add_slot("recent_tasks",  priority=60,  max_tokens=300)
        .add_slot("architecture",  priority=50,  max_tokens=600)
        .add_slot("relevant_memories", priority=45, max_tokens=500)
    )


def review_agent_budget(total: int = 4_000) -> TokenBudget:
    """Tighter budget for a code review agent."""
    return (
        TokenBudget(total_tokens=total)
        .add_slot("diff",         priority=100, max_tokens=2_000)
        .add_slot("decisions",    priority=80,  max_tokens=400)
        .add_slot("coding_style", priority=70,  max_tokens=400)
        .add_slot("known_errors", priority=60,  max_tokens=400)
        .add_slot("patterns",     priority=50,  max_tokens=300)
    )
