import time
from typing import Optional, Callable, Dict
import json
from pathlib import Path

from ..core.llm_client import BaseLLMClient
from ..core.exceptions import RateLimitExceeded, ServerOverloadedException, EmptyResponseError
from .chunker import SmartChunker

DEFAULT_STYLE_INSTRUCTIONS = """Bạn là một biên tập viên (Editor) chuyên nghiệp cho các ấn phẩm light novel và tiểu thuyết mạng.
Nhiệm vụ của bạn là trau chuốt, sửa văn phong và biên tập lại bản dịch tiếng Việt cho mượt mà, tự nhiên và giàu cảm xúc hơn.

Quy tắc biên tập:
1. Giữ nguyên 100% cấu trúc dòng, số đoạn và thứ tự câu chuyện. Không tóm tắt, không lược bỏ nội dung.
2. Giữ nguyên các hậu tố tôn kính của Nhật Bản (-san, -kun, -chan, -sama, senpai, sensei) hoặc xưng hô Trung Quốc (Huynh, Muội, Tỷ, Đệ).
3. Chỉ xuất ra duy nhất phần nội dung truyện đã được sửa. Không kèm lời chào, lời bình hay giải thích trước/sau văn bản.
"""

class NovelStylePolisher:
    """
    Polishes and edits translated text using targeted LLM style tags.
    """

    def __init__(
        self,
        client: BaseLLMClient,
        chunker: SmartChunker,
        styles_file: Optional[Path] = None,
        max_retries: int = 3
    ):
        self.client = client
        self.chunker = chunker
        self.max_retries = max_retries
        self.styles: Dict[str, str] = self._load_styles(styles_file)

    def _load_styles(self, filepath: Optional[Path]) -> Dict[str, str]:
        if filepath and filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "RomCom": "- Cải thiện hội thoại đáng yêu hơn.\n- Làm câu chữ tự nhiên theo phong cách anime romcom.",
            "Dark Fantasy": "- Giữ văn phong tối tăm, lạnh lẽo, gai góc.",
            "Anime Style": "- Tạo vibe giống light novel hoặc anime Nhật Bản.",
            "Tiểu thuyết xuất bản": "- Dùng câu từ chỉn chu, chuẩn ngữ pháp tiếng Việt."
        }

    def polish_text(
        self,
        text: str,
        style_name: str = "RomCom",
        custom_instructions: str = "",
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        chunks = self.chunker.split(text)
        if not chunks:
            return ""

        style_details = self.styles.get(style_name, "")
        prompt_style_block = f"--- PHONG CÁCH BIÊN TẬP: {style_name} ---\n{style_details}"
        if custom_instructions.strip():
            prompt_style_block += f"\n- Hướng dẫn bổ sung: {custom_instructions.strip()}"

        edited_segments = []
        for chunk in chunks:
            prompt = (
                f"{prompt_style_block}\n\n"
                f"--- NỘI DUNG CẦN BIÊN TẬP ---\n"
                f"{chunk.content}\n"
                f"-----------------------------"
            )

            chunk_result = self._execute_with_retry(prompt, callback=callback)
            edited_segments.append(chunk_result.strip())

        return "\n\n".join(edited_segments)

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
                    system_instruction=DEFAULT_STYLE_INSTRUCTIONS,
                    temperature=0.35,
                    callback=callback
                )
                if not result or not result.strip():
                    raise EmptyResponseError("Empty output returned from style editor.")
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

        raise RuntimeError(f"Style editing failed after {self.max_retries} attempts: {last_exception}")

