from pathlib import Path
from typing import Optional, Callable, Dict, Any

from .terminology import TerminologyExtractor, GlossaryManager
from .translator import NovelTranslator
from .style_polisher import NovelStylePolisher
from .epub_builder import EpubBuilder

class LocalizationPipeline:
    """
    Executes a seamless end-to-end automation pipeline:
    Extract Terms -> Translate -> Polish Style -> Package EPUB
    """

    def __init__(
        self,
        translator: NovelTranslator,
        polisher: Optional[NovelStylePolisher] = None,
        epub_builder: Optional[EpubBuilder] = None
    ):
        self.translator = translator
        self.polisher = polisher
        self.epub_builder = epub_builder or EpubBuilder()

    def run_pipeline(
        self,
        raw_dir: Path,
        translated_dir: Path,
        edited_dir: Optional[Path] = None,
        epub_file: Optional[Path] = None,
        glossary_file: Optional[Path] = None,
        do_extract_terms: bool = True,
        do_translate: bool = True,
        do_polish_style: bool = True,
        do_package_epub: bool = True,
        style_name: str = "RomCom",
        book_title: str = "Translated Novel",
        book_author: str = "Unknown Author",
        cover_image: Optional[Path] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        log("🚀 BẮT ĐẦU CHUỖI TỰ ĐỘNG HÓA PIPELINE")
        raw_files = sorted([f for f in raw_dir.iterdir() if f.suffix.lower() == ".txt"]) if raw_dir.exists() else []
        if not raw_files:
            log(f"❌ Không tìm thấy file .txt nào trong thư mục raw: {raw_dir}")
            return

        # Step 1: Extract terms if requested
        if do_extract_terms:
            log(f"\n[Step 1/4] 🔍 Quét và trích xuất thuật ngữ từ {len(raw_files)} chương...")
            texts = []
            for f in raw_files:
                with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                    texts.append(fp.read())

            extractor = TerminologyExtractor()
            candidates = extractor.extract_candidates(texts, min_frequency=2)
            log(f"  -> Tìm thấy {len(candidates)} thuật ngữ xuất hiện >= 2 lần.")

            if glossary_file:
                # Merge with existing
                manager = GlossaryManager.load(glossary_file)
                existing_terms = {e.term for e in manager.entries}
                from .terminology import GlossaryEntry
                new_entries = [GlossaryEntry(term=k, category="CHARACTERS") for k in candidates if k not in existing_terms]
                manager.entries.extend(new_entries)
                manager.save(glossary_file)
                self.translator.glossary = manager
                log(f"  -> Đã cập nhật bộ nhớ glossary tại: {glossary_file.name}")

        # Step 2: Translate
        if do_translate:
            translated_dir.mkdir(parents=True, exist_ok=True)
            log(f"\n[Step 2/4] 🌐 Bắt đầu Dịch AI {len(raw_files)} chương...")
            for idx, file in enumerate(raw_files, 1):
                dest = translated_dir / file.name
                if dest.exists() and dest.stat().st_size > 0:
                    log(f"  [{idx}/{len(raw_files)}] Bỏ qua đã dịch: {file.name}")
                    continue

                log(f"  [{idx}/{len(raw_files)}] Đang dịch: {file.name}...")
                with open(file, "r", encoding="utf-8") as fp:
                    content = fp.read()

                try:
                    res = self.translator.translate_text(content)
                    with open(dest, "w", encoding="utf-8") as fp:
                        fp.write(res)
                    log(f"  -> Xong {file.name}")
                except Exception as e:
                    log(f"  ❌ Lỗi khi dịch {file.name}: {e}")

        # Step 3: Polish Style
        source_for_epub = translated_dir
        if do_polish_style and self.polisher and edited_dir:
            edited_dir.mkdir(parents=True, exist_ok=True)
            trans_files = sorted([f for f in translated_dir.iterdir() if f.suffix.lower() == ".txt"])
            log(f"\n[Step 3/4] ✨ Tuốt văn phong ({style_name}) cho {len(trans_files)} chương...")
            for idx, file in enumerate(trans_files, 1):
                dest = edited_dir / file.name
                if dest.exists() and dest.stat().st_size > 0:
                    log(f"  [{idx}/{len(trans_files)}] Bỏ qua đã sửa: {file.name}")
                    continue

                log(f"  [{idx}/{len(trans_files)}] Đang sửa văn phong: {file.name}...")
                with open(file, "r", encoding="utf-8") as fp:
                    content = fp.read()

                try:
                    res = self.polisher.polish_text(content, style_name=style_name)
                    with open(dest, "w", encoding="utf-8") as fp:
                        fp.write(res)
                    log(f"  -> Xong {file.name}")
                except Exception as e:
                    log(f"  ❌ Lỗi khi sửa {file.name}: {e}")
            source_for_epub = edited_dir

        # Step 4: Package EPUB
        if do_package_epub and epub_file:
            log(f"\n[Step 4/4] 📚 Đóng gói thành file EPUB: {epub_file.name}...")
            try:
                self.epub_builder.build_epub(
                    input_dir=source_for_epub,
                    output_file=epub_file,
                    title=book_title,
                    author=book_author,
                    cover_image=cover_image,
                    progress_cb=lambda cur, tot, name: log(f"  -> Đóng gói chương [{cur}/{tot}]: {name}")
                )
                log(f"🎉 Xuất bản thành công: {epub_file}")
            except Exception as e:
                log(f"❌ Lỗi đóng gói EPUB: {e}")

        log("\n" + "="*50)
        log("🎉 HOÀN THÀNH TOÀN BỘ CHUỖI PIPELINE TỰ ĐỘNG!")
        log("="*50)

