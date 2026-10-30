import json
from abc import ABC, abstractmethod
from typing import Optional, Callable
import requests

from .exceptions import (
    RateLimitExceeded,
    ServerOverloadedException,
    AuthenticationError,
    EmptyResponseError,
    ProviderError
)
from .key_rotator import KeyRotator

class BaseLLMClient(ABC):
    """Abstract interface for LLM providers."""

    def __init__(self, model: str, rotator: KeyRotator, base_url: Optional[str] = None):
        self.model = model
        self.rotator = rotator
        self.base_url = base_url

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.3,
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Generates completion for a given prompt, optionally with stream callback."""
        pass


class GeminiClient(BaseLLMClient):
    """Google Gemini API implementation using official google-genai SDK."""

    def generate(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.3,
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        from google import genai
        from google.genai import types

        api_key = self.rotator.get_key()
        if not api_key:
            raise AuthenticationError("No available Gemini API keys (all are cooling down or none provided).")

        try:
            client = genai.Client(api_key=api_key)
            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction if system_instruction else None
            )

            if callback:
                full_text = []
                response = client.models.generate_content_stream(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                for chunk in response:
                    if chunk.text:
                        full_text.append(chunk.text)
                        callback(chunk.text)
                res = "".join(full_text)
                if not res.strip():
                    raise EmptyResponseError("Gemini returned empty streaming response (possibly filtered).")
                return res
            else:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if not response.text or not response.text.strip():
                    raise EmptyResponseError("Gemini returned an empty response.")
                return response.text

        except Exception as e:
            err_str = str(e).lower()
            if "resource_exhausted" in err_str or "429" in err_str or "quota" in err_str:
                self.rotator.mark_rate_limited(api_key)
                raise RateLimitExceeded(f"Gemini quota/rate limit exceeded: {e}")
            elif "503" in err_str or "overloaded" in err_str or "unavailable" in err_str:
                raise ServerOverloadedException(f"Gemini model overloaded: {e}")
            elif "api_key" in err_str or "unauthenticated" in err_str:
                self.rotator.mark_rate_limited(api_key, custom_cooldown=3600)
                raise AuthenticationError(f"Invalid API key: {e}")
            raise ProviderError(f"Gemini error: {e}")


class OpenAILikeClient(BaseLLMClient):
    """OpenAI-compatible client for OpenRouter, Groq, OpenAI, and Ollama."""

    def generate(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.3,
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        if not self.base_url:
            raise ProviderError("OpenAILike client requires a valid base_url.")

        api_key = self.rotator.get_key()
        if not api_key:
            raise AuthenticationError("No available API key for provider.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": bool(callback)
        }

        try:
            if callback:
                resp = requests.post(self.base_url, headers=headers, json=payload, stream=True, timeout=120)
                self._check_status_code(resp, api_key)

                full_text = []
                for line in resp.iter_lines():
                    if line:
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith("data: "):
                            data_content = line_str[6:]
                            if data_content == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_content)
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_text.append(delta)
                                    callback(delta)
                            except Exception:
                                continue
                res = "".join(full_text)
                if not res.strip():
                    raise EmptyResponseError("Empty stream returned from provider.")
                return res
            else:
                resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
                self._check_status_code(resp, api_key)
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise EmptyResponseError("Provider returned empty response content.")
                return content

        except requests.RequestException as e:
            raise ProviderError(f"Network error calling {self.base_url}: {e}")

    def _check_status_code(self, resp: requests.Response, api_key: str):
        if resp.status_code == 429:
            self.rotator.mark_rate_limited(api_key)
            raise RateLimitExceeded(f"Rate limited by {self.base_url} (HTTP 429)")
        elif resp.status_code in [502, 503, 529]:
            raise ServerOverloadedException(f"Server overloaded (HTTP {resp.status_code})")
        elif resp.status_code in [401, 403]:
            self.rotator.mark_rate_limited(api_key, custom_cooldown=3600)
            raise AuthenticationError(f"Authentication failed (HTTP {resp.status_code}): {resp.text}")
        elif resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code} error: {resp.text}")


def create_llm_client(
    provider_name: str,
    model: str,
    rotator: KeyRotator,
    base_url: Optional[str] = None
) -> BaseLLMClient:
    """Factory helper to instantiate provider client."""
    if provider_name.lower() == "gemini":
        return GeminiClient(model=model, rotator=rotator)
    else:
        return OpenAILikeClient(model=model, rotator=rotator, base_url=base_url)

