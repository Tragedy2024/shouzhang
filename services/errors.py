"""Public, safe errors shared by journal generation services."""


class GenerationError(Exception):
    """A generation failure that can be shown without exposing provider details."""

    def __init__(self, message: str, stage: str, retryable: bool = True):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.retryable = retryable


def read_generated_text(response) -> str:
    """Validate a chat-completion response before using it as journal content."""
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Missing generated text")
    return content.strip()
