from dataclasses import dataclass
from typing import List
import re

@dataclass
class TextChunk:
    index: int
    total: int
    content: str
    char_count: int

class SmartChunker:
    """
    Intelligent text splitter designed for light novels and literary works.
    Splits text across natural paragraph and sentence boundaries, avoiding awkward mid-sentence cuts.
    """

    def __init__(self, threshold: int = 5000, target_chunk_size: int = 2500):
        self.threshold = threshold
        self.target_chunk_size = target_chunk_size

    def split(self, text: str) -> List[TextChunk]:
        clean_text = text.strip()
        if not clean_text:
            return []

        total_len = len(clean_text)
        if total_len <= self.threshold:
            return [TextChunk(index=1, total=1, content=clean_text, char_count=total_len)]

        # Determine target number of chunks
        num_chunks = max(2, round(total_len / self.target_chunk_size))
        ideal_chunk_len = total_len // num_chunks

        split_indices = [0]
        current_pos = 0

        for i in range(1, num_chunks):
            target_pos = i * ideal_chunk_len
            split_pos = self._find_best_break_point(clean_text, target_pos, window=ideal_chunk_len // 2)
            if split_pos > current_pos and split_pos < total_len:
                split_indices.append(split_pos)
                current_pos = split_pos

        split_indices.append(total_len)
        # Deduplicate and sort
        split_indices = sorted(list(set(split_indices)))

        raw_chunks = []
        for i in range(len(split_indices) - 1):
            start = split_indices[i]
            end = split_indices[i + 1]
            segment = clean_text[start:end].strip()
            if segment:
                raw_chunks.append(segment)

        total_chunks = len(raw_chunks)
        return [
            TextChunk(
                index=idx + 1,
                total=total_chunks,
                content=chunk,
                char_count=len(chunk)
            )
            for idx, chunk in enumerate(raw_chunks)
        ]

    def _find_best_break_point(self, text: str, target_pos: int, window: int) -> int:
        """Searches around target_pos for natural breaks in order of priority:
        1. Paragraph break (\n\n)
        2. Line break (\n)
        3. Sentence end (. ! ? 。 ！)
        """
        start_search = max(0, target_pos - window)
        end_search = min(len(text), target_pos + window)
        sub = text[start_search:end_search]

        # 1. Paragraph breaks
        para_breaks = [m.end() for m in re.finditer(r'\n\s*\n', sub)]
        if para_breaks:
            best_local = min(para_breaks, key=lambda pos: abs((start_search + pos) - target_pos))
            return start_search + best_local

        # 2. Line breaks
        line_breaks = [m.end() for m in re.finditer(r'\n', sub)]
        if line_breaks:
            best_local = min(line_breaks, key=lambda pos: abs((start_search + pos) - target_pos))
            return start_search + best_local

        # 3. Sentence boundaries (including CJK punctuation)
        sent_breaks = [m.end() for m in re.finditer(r'([.!?。！？…])\s*', sub)]
        if sent_breaks:
            best_local = min(sent_breaks, key=lambda pos: abs((start_search + pos) - target_pos))
            return start_search + best_local

        # Fallback to nearest whitespace
        space_breaks = [m.end() for m in re.finditer(r'\s+', sub)]
        if space_breaks:
            best_local = min(space_breaks, key=lambda pos: abs((start_search + pos) - target_pos))
            return start_search + best_local

        return target_pos

