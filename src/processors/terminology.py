import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter
from pydantic import BaseModel, Field

class GlossaryEntry(BaseModel):
    term: str
    translation: str = ""
    category: str = "OTHER"
    note: str = ""

DEFAULT_BLACKLIST = {
    # English common stopwords
    "the", "is", "are", "and", "you", "that", "this", "to", "of", "it", "in", "for",
    "on", "with", "as", "he", "she", "they", "we", "i", "a", "an", "but", "so",
    "because", "when", "where", "how", "why", "who", "what", "which", "there", "then",
    # Vietnamese common stopwords
    "tôi", "bạn", "anh", "em", "hắn", "y", "thị", "và", "là", "của", "có", "không",
    "thì", "mà", "đã", "đang", "sẽ", "với", "nhưng", "vào", "ra", "từ", "lên", "xuống",
    "lại", "rồi", "để", "khi", "người", "một", "này", "kia", "đó", "đây", "mình", "gì"
}

class GlossaryManager:
    """Manages loading, formatting, and persisting glossary/terminology files."""

    CATEGORIES = ["CHARACTERS", "LOCATIONS", "ORGANIZATIONS", "HONORIFICS", "FANTASY TERMS", "OTHER"]

    def __init__(self, entries: Optional[List[GlossaryEntry]] = None):
        self.entries: List[GlossaryEntry] = entries or []

    @classmethod
    def load(cls, filepath: Path) -> "GlossaryManager":
        if not filepath.exists():
            return cls([])

        entries = []
        current_cat = "OTHER"
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str or line_str.startswith("#"):
                    continue

                if line_str.startswith("[") and line_str.endswith("]"):
                    cat_name = line_str[1:-1].strip().upper()
                    if cat_name in cls.CATEGORIES:
                        current_cat = cat_name
                    continue

                if "=" in line_str:
                    parts = line_str.split("=", 1)
                    term = parts[0].strip()
                    rest = parts[1].strip()
                    note = ""
                    if "#" in rest:
                        subparts = rest.split("#", 1)
                        trans = subparts[0].strip()
                        note = subparts[1].strip()
                    else:
                        trans = rest

                    entries.append(GlossaryEntry(
                        term=term,
                        translation=trans,
                        category=current_cat,
                        note=note
                    ))

        return cls(entries)

    def save(self, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        categorized: Dict[str, List[GlossaryEntry]] = {cat: [] for cat in self.CATEGORIES}
        for entry in self.entries:
            cat = entry.category.upper() if entry.category.upper() in self.CATEGORIES else "OTHER"
            categorized[cat].append(entry)

        lines = []
        for cat in self.CATEGORIES:
            items = categorized[cat]
            if items:
                lines.append(f"[{cat}]")
                for it in items:
                    if it.note:
                        lines.append(f"{it.term} = {it.translation} # {it.note}")
                    else:
                        lines.append(f"{it.term} = {it.translation}")
                lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip())

    def format_for_prompt(self) -> str:
        """Formats the glossary entries into a clean prompt block for LLM conditioning."""
        if not self.entries:
            return ""

        lines = ["--- GLOSSARY & TERMINOLOGY CONSTRAINTS ---"]
        for entry in self.entries:
            if entry.translation:
                desc = f" -> {entry.translation}"
                if entry.note:
                    desc += f" ({entry.note})"
                lines.append(f"- [{entry.category}] {entry.term}{desc}")
            else:
                lines.append(f"- [{entry.category}] {entry.term}")
        lines.append("------------------------------------------")
        return "\n".join(lines)


class TerminologyExtractor:
    """Extracts entity and term candidates using regex heuristics and optional AI refinement."""

    def __init__(self, blacklist: Optional[set] = None):
        self.blacklist = blacklist if blacklist is not None else DEFAULT_BLACKLIST

    def extract_candidates(self, texts: List[str], min_frequency: int = 2) -> Dict[str, int]:
        counter: Counter = Counter()

        # Regex patterns:
        # 1. Katakana phrases (Japanese names/terms)
        katakana_pattern = re.compile(r'[\u30a0-\u30ff]{2,}')
        # 2. Capitalized Western names/phrases (e.g. John Doe, Excalibur)
        capitalized_pattern = re.compile(r'\b[A-Z][a-zA-Z]{1,}(?:\s+[A-Z][a-zA-Z]{1,})*\b')

        for text in texts:
            # Match katakana
            for match in katakana_pattern.findall(text):
                counter[match] += 1

            # Match capitalized phrases
            for match in capitalized_pattern.findall(text):
                word_lower = match.lower()
                if word_lower not in self.blacklist and len(match) > 1:
                    counter[match] += 1

        return {term: count for term, count in counter.items() if count >= min_frequency}

    def refine_with_llm(self, client, candidate_terms: List[str], batch_size: int = 50) -> List[GlossaryEntry]:
        """
        Uses LLM with structured output to classify candidates, filter garbage/stopwords,
        and provide standard romanizations.
        """
        if not candidate_terms:
            return []

        entries = []
        prompt_template = """
You are an expert novel translator and Named Entity Recognition (NER) specialist.
Classify each provided term and discard any common stopwords, noise, or particles.

Allowed Categories:
- Character, Location, Organization, Honorific, Fantasy Term, Skill, Item, Other, Ignore

Rules:
1. Return a JSON array of objects: [{"term": "...", "category": "...", "romanized": "...", "note": "..."}]
2. For terms that are generic noise, pronouns, or common adjectives, mark category as "Ignore".
3. Provide standard romanization if the term is in Japanese/Chinese/Korean.

Terms to classify:
"""
        total_batches = (len(candidate_terms) + batch_size - 1) // batch_size
        for i in range(total_batches):
            batch = candidate_terms[i * batch_size : (i + 1) * batch_size]
            prompt = prompt_template + json.dumps(batch, ensure_ascii=False)

            try:
                raw_resp = client.generate(
                    prompt=prompt,
                    system_instruction="You are a strict JSON data extractor. Output valid JSON array only.",
                    temperature=0.1
                )
                clean_json = raw_resp.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]

                data = json.loads(clean_json.strip())
                for item in data:
                    cat = item.get("category", "Other")
                    if cat != "Ignore":
                        entries.append(GlossaryEntry(
                            term=item.get("term", ""),
                            translation=item.get("romanized", ""),
                            category=cat.upper(),
                            note=item.get("note", "")
                        ))
            except Exception:
                continue

        return entries

