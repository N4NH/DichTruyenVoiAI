import re
import html
import uuid
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Optional, Callable

class EpubBuilder:
    """
    Builds clean EPUB eBooks from a directory of .txt chapter files with natural sorting.
    """

    @staticmethod
    def natural_sort_key(filename: str):
        """Natural sort key supporting chapter decimals like 1, 2, 2.1, 2.10, 3"""
        base = Path(filename).stem
        parts = re.split(r'(\d+(?:\.\d+)?)', base)
        result = []
        for p in parts:
            try:
                result.append(float(p))
            except ValueError:
                result.append(p.lower())
        return result

    @classmethod
    def generate_ai_cover(cls, title: str, output_path: Path, prompt_override: str = "") -> Path:
        """Generates a free AI book cover via Pollinations AI."""
        prompt = prompt_override or f"Anime light novel book cover art, high fantasy illustration, masterpiece, title {title}"
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=800&height=1200&nologo=true"

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(data)

        return output_path

    def build_epub(
        self,
        input_dir: Path,
        output_file: Path,
        title: str = "My Novel",
        author: str = "Unknown Author",
        cover_image: Optional[Path] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> Path:
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(title)
        book.set_language('vi')
        book.add_author(author)

        # Set cover if provided
        if cover_image and cover_image.exists():
            with open(cover_image, 'rb') as f:
                book.set_cover("cover.jpg", f.read())

        files = sorted([f for f in input_dir.iterdir() if f.suffix.lower() == '.txt'], key=lambda x: self.natural_sort_key(x.name))
        if not files:
            raise ValueError(f"Không tìm thấy file .txt nào trong thư mục: {input_dir}")

        chapters = []
        total = len(files)

        for i, file_path in enumerate(files):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_content = f.read()

            lines = raw_content.splitlines()
            first_line = lines[0].strip() if lines else ""
            chap_title = first_line if first_line else file_path.stem

            # Format HTML content
            paragraphs = []
            for line in lines:
                escaped = html.escape(line.strip())
                if escaped:
                    paragraphs.append(f"<p>{escaped}</p>")

            html_body = f"<h2>{html.escape(chap_title)}</h2>\n" + "\n".join(paragraphs)

            c = epub.EpubHtml(
                title=chap_title,
                file_name=f"chap_{i + 1:04d}.xhtml",
                lang='vi'
            )
            c.content = f"<html><body>{html_body}</body></html>"
            book.add_item(c)
            chapters.append(c)

            if progress_cb:
                progress_cb(i + 1, total, chap_title)

        book.toc = tuple(chapters)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        book.spine = ['nav'] + chapters

        output_file.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(output_file), book, {})
        return output_file

