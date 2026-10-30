"""Custom exceptions for LLM Novel Localizer."""

class LocalizerException(Exception):
    """Base exception for the localization system."""
    pass

class RateLimitExceeded(LocalizerException):
    """Raised when an LLM provider hits rate limits (HTTP 429 / RESOURCE_EXHAUSTED)."""
    def __init__(self, message: str, retry_after: int = 30):
        super().__init__(message)
        self.retry_after = retry_after

class ServerOverloadedException(LocalizerException):
    """Raised when upstream AI servers are overloaded (HTTP 502/503/529)."""
    pass

class ContextWindowExceeded(LocalizerException):
    """Raised when input text exceeds the maximum allowed prompt/token threshold."""
    pass

class AuthenticationError(LocalizerException):
    """Raised when the API key is missing or rejected."""
    pass

class EmptyResponseError(LocalizerException):
    """Raised when LLM returns an empty response (often due to safety content filters)."""
    pass

class ProviderError(LocalizerException):
    """General provider-side error."""
    pass

