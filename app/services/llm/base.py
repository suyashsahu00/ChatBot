"""
Shared LLM types, exceptions, and constants.
Provides error boundaries for the LLM providers and the orchestrator.
"""

class LLMGenerationError(Exception):
    """Custom exception raised when an LLM provider fails to generate content."""
    pass
