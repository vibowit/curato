from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol defining the standardized interface for LLM providers."""

    @property
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'gemini', 'openai')."""
        ...

    @property
    def model_name(self) -> str:
        """Currently active model identifier."""
        ...

    async def generate_structured(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates a structured JSON response matching the prompt requirements."""
        ...
