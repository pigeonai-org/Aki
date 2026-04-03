"""
Token Budget

Tracks token allocation and remaining capacity for an agent's conversation.
"""

from pydantic import BaseModel, Field


class TokenBudget(BaseModel):
    """
    Token budget for a single agent conversation.

    Tracks how much context space is available after accounting for
    system prompt, tool schemas, and a reserve buffer.
    """

    max_context_tokens: int = Field(default=128_000, description="Model's context window size")
    system_prompt_tokens: int = Field(default=0, description="Tokens used by system prompt")
    tool_schemas_tokens: int = Field(default=0, description="Tokens used by tool definitions")
    reserve_tokens: int = Field(default=4_000, description="Buffer reserved for model output")
    used_message_tokens: int = Field(default=0, description="Tokens currently used by messages")

    @property
    def available_tokens(self) -> int:
        """Tokens available for conversation messages."""
        return max(
            0,
            self.max_context_tokens
            - self.system_prompt_tokens
            - self.tool_schemas_tokens
            - self.reserve_tokens
            - self.used_message_tokens,
        )

    @property
    def total_used(self) -> int:
        """Total tokens consumed across all categories."""
        return self.system_prompt_tokens + self.tool_schemas_tokens + self.used_message_tokens

    @property
    def utilization(self) -> float:
        """Fraction of context window used (0.0 to 1.0)."""
        if self.max_context_tokens == 0:
            return 0.0
        return self.total_used / self.max_context_tokens

    def has_capacity(self) -> bool:
        """Check if there is remaining capacity for more messages."""
        return self.available_tokens > 0

    def update_message_tokens(self, tokens: int) -> None:
        """Set the current message token count."""
        self.used_message_tokens = tokens

    @property
    def compaction_threshold(self) -> int:
        """Token count at which compaction should trigger (75% of message budget)."""
        message_budget = self.max_context_tokens - self.system_prompt_tokens - self.tool_schemas_tokens - self.reserve_tokens
        return int(message_budget * 0.75)
