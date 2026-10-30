import time
from typing import Optional, Callable, List
from pathlib import Path

from ..core.llm_client import BaseLLMClient
from ..core.exceptions import RateLimitExceeded, ServerOverloadedException, EmptyResponseError
from .chunker import SmartChunker
from .terminology import GlossaryManager

DEFAULT_SYSTEM_PROMPT = """You are a master literary translator specializing in Japanese, Korean, and Chinese light novels and web novels.
Translate the text into natural, fluent Vietnamese.

Key Instructions:
1. Preserve the tone, emotions, and pacing of the original author.
2. Adhere strictly to the provided Glossary and Terminology constraints.
3. Keep Japanese/Chinese honorifics when appropriate (-san, -kun, -sama, Huynh, Muội) to maintain flavor.
4. Output ONLY the translated story text. Do not add conversational remarks, disclaimers, or notes before or after the translation.
"""

class NovelTranslator:
    """
    Coordinates chunking, terminology injection, rate-limit recovery, and LLM translation.
    """

    def __init__(
        self,
        client: BaseLLMClient,
        chunker: SmartChunker,
        glossary: Optional[GlossaryManager] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_retries: int = 3
    ):
        self.client = client
        self.chunker = chunker
        self.glossary = glossary or GlossaryManager()
        self.system_prompt = system_prompt
        self.max_retries = max_retries

    def translate_text(
        self,
        raw_text: str,
        target_language: str = "Vietnamese",
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        chunks = self.chunker.split(raw_text)
        if not chunks:
            return ""

        glossary_context = self.glossary.format_for_prompt()
        translated_segments = []

        for chunk in chunks:
            prompt_parts = []
            if glossary_context:
                prompt_parts.append(glossary_context)
                prompt_parts.append("")

            prompt_parts.append(f"Target Language: {target_language}")
            prompt_parts.append("--- SOURCE CHAPTER TEXT ---")
            prompt_parts.append(chunk.content)
            prompt_parts.append("---------------------------")

            prompt = "\n".join(prompt_parts)

            chunk_translation = self._execute_with_retry(prompt, callback=callback)
            translated_segments.append(chunk_translation.strip())

        return "\n\n".join(translated_segments)

    def _execute_with_retry(
        self,
        prompt: str,
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.client.generate(
                    prompt=prompt,
                    system_instruction=self.system_prompt,
                    temperature=0.3,
                    callback=callback
                )
                if not result or not result.strip():
                    raise EmptyResponseError("Empty output returned from LLM.")
                return result
            except RateLimitExceeded as e:
                last_exception = e
                wait_time = e.retry_after if hasattr(e, 'retry_after') else 10 * attempt
                time.sleep(wait_time)
            except ServerOverloadedException as e:
                last_exception = e
                time.sleep(5 * attempt)
            except Exception as e:
                last_exception = e
                time.sleep(2 * attempt)

        raise RuntimeError(f"Translation failed after {self.max_retries} attempts. Last error: {last_exception}")

