import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Callable

SPECIAL_KEYWORDS = [
    r'序章', r'楔子', r'引子', r'前言', r'尾声', r'终章', r'后记', r'番外[0-9一二三四五六七八九十]*',
    r'外传[0-9一二三四五六七八九十]*', r'特别篇', r'附录', r'幕间', r'閑話', r'闲话',
    r'第[0-9一二三四五六七八九十]+話', r'プロローグ', r'エピローグ', r'프롤로그', r'에필로그', r'외전',
    r'Prologue', r'Epilogue', r'Interlude', r'Extra\s*[0-9]*', r'Side\s*Story\s*[0-9]*',
    r'Lời\s+mở\s+đầu', r'Lời\s+bạt', r'Ngoại\s+truyện\s*[0-9]*', r'Phiên\s+ngoại\s*[0-9]*'
]
SPECIAL_REGEX = r'^\s*(?:' + '|'.join(SPECIAL_KEYWORDS) + r')(?:\s*[:：\-\_]?\s*.*)?$'

CHAPTER_REGEX_PATTERNS = [
    # Chinese / Japanese: 第123章 Title / 第123話
    r'^\s*第\s*[0-9一二三四五六七八九十百千万]+[章話回节集卷]\s*.*$',
    # Korean: 제1화 / 제 1 장
    r'^\s*제\s*[0-9]+\s*[화장]\s*.*$',
    # English / Vietnamese / Spanish / French / Russian: Chapter 1 / Chương 1 / Глава 1
    r'^\s*(?:Chapter|Chương|Capítulo|Cap|Глава|Chapitre|Kapitel)\s+[0-9]+\s*.*$',
    # Numeric prefix: 1. Title / 123: Title
    r'^\s*[0-9]{1,5}\s*[\.\:\：\-\_]\s*.*$',
    # Markdown headers: # Chapter
    r'^\s*#{1,3}\s+.*$',
    # Special chapter keywords
    SPECIAL_REGEX
]

COMPILED_CHAPTER_REGEX = re.compile('|'.join(CHAPTER_REGEX_PATTERNS), re.IGNORECASE | re.MULTILINE)

class NovelSplitter:
    """
    Splits large aggregated novel files into clean individual chapter files.
    """

    def __init__(self, custom_regex: Optional[str] = None):
        if custom_regex:
            try:
                self.regex = re.compile(custom_regex, re.IGNORECASE | re.MULTILINE)
            except Exception:
                self.regex = COMPILED_CHAPTER_REGEX
        else:
            self.regex = COMPILED_CHAPTER_REGEX

    @staticmethod
    def clean_filename(name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|\r\n\t]', '_', name).strip()
        if len(name) > 100:
            name = name[:100]
        return name or "Untitled"

    def split_txt_file(
        self,
        txt_path: Path,
        output_dir: Path,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)

        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'utf-16']
        content = None
        for enc in encodings:
            try:
                with open(txt_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except Exception:
                continue

        if content is None:
            raise ValueError(f"Không thể đọc file {txt_path.name}. Lỗi encoding!")

        lines = content.splitlines()
        chapters = []

        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue
            if self.regex.match(line_str):
                chapters.append({
                    'index': len(chapters) + 1,
                    'title': line_str,
                    'line_start': idx
                })

        if not chapters:
            # No chapters detected: write whole file as chapter 1
            out_file = output_dir / f"1. {self.clean_filename(txt_path.stem)}.txt"
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return [out_file]

        saved_files = []
        total = len(chapters)

        for i, chap in enumerate(chapters):
            start = chap['line_start']
            end = chapters[i + 1]['line_start'] if i + 1 < total else len(lines)
            chap_body = "\n".join(lines[start:end]).strip()

            clean_title = self.clean_filename(chap['title'])
            filename = f"{chap['index']}. {clean_title}.txt"
            file_path = output_dir / filename

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(chap_body)

            saved_files.append(file_path)
            if progress_cb:
                progress_cb(i + 1, total, chap['title'])

        return saved_files

