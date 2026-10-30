import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import load_config, save_config, SUPPORTED_PROVIDERS
from src.core.key_rotator import KeyRotator
from src.core.llm_client import create_llm_client
from src.processors.chunker import SmartChunker
from src.processors.terminology import GlossaryManager, TerminologyExtractor, GlossaryEntry
from src.processors.translator import NovelTranslator, DEFAULT_SYSTEM_PROMPT
from src.processors.style_polisher import NovelStylePolisher
from src.processors.splitter import NovelSplitter
from src.processors.epub_builder import EpubBuilder
from src.processors.pipeline import LocalizationPipeline

CONFIG_FILE = BASE_DIR / "config.json"
PROMPT_FILE = BASE_DIR / "prompt.txt"
MEMORY_FILE = BASE_DIR / "memory.txt"
STYLES_FILE = BASE_DIR / "styles.json"

class ModernLocalizerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("📚 LLM Novel Localizer - Hệ Sinh Thái Dịch Truyện")
        self.root.geometry("900x720")
        self.root.minsize(800, 600)

        self.config = load_config(CONFIG_FILE)
        self.setup_ui()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[12, 6])
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=6)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Build tabs
        self.create_tab_translate()
        self.create_tab_style()
        self.create_tab_terminology()
        self.create_tab_splitter()
        self.create_tab_epub()
        self.create_tab_pipeline()
        self.create_tab_settings()

    # -------------------------------------------------------------
    # TAB 1: DỊCH TRUYỆN AI
    # -------------------------------------------------------------
    def create_tab_translate(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="🌐 Dịch Truyện AI")

        # Top IO Frame
        io_frame = ttk.LabelFrame(tab, text="Thư Mục Làm Việc", padding=10)
        io_frame.pack(fill=tk.X, pady=(0, 8))

        self.trans_raw_var = tk.StringVar(value=str(BASE_DIR / "data" / "raw"))
        self.trans_out_var = tk.StringVar(value=str(BASE_DIR / "data" / "translated"))

        r1 = ttk.Frame(io_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Thư mục Raw:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.trans_raw_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="Chọn...", command=lambda: self.browse_dir(self.trans_raw_var)).pack(side=tk.RIGHT)

        r2 = ttk.Frame(io_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="Thư mục Đích:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.trans_out_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r2, text="Chọn...", command=lambda: self.browse_dir(self.trans_out_var)).pack(side=tk.RIGHT)

        # Provider and Options
        opt_frame = ttk.LabelFrame(tab, text="Cấu Hình AI & Prompt", padding=10)
        opt_frame.pack(fill=tk.X, pady=(0, 8))

        r3 = ttk.Frame(opt_frame)
        r3.pack(fill=tk.X, pady=2)
        ttk.Label(r3, text="AI Provider:", width=15).pack(side=tk.LEFT)
        self.trans_prov_combo = ttk.Combobox(r3, values=list(SUPPORTED_PROVIDERS.keys()), state="readonly", width=18)
        self.trans_prov_combo.set(self.config.selected_provider)
        self.trans_prov_combo.pack(side=tk.LEFT, padx=5)
        self.trans_prov_combo.bind("<<ComboboxSelected>>", self.on_trans_provider_change)

        ttk.Label(r3, text="Model:").pack(side=tk.LEFT, padx=(10, 5))
        self.trans_model_combo = ttk.Combobox(r3, values=SUPPORTED_PROVIDERS.get(self.config.selected_provider, []), state="readonly", width=25)
        current_model = self.config.providers.get(self.config.selected_provider, None)
        self.trans_model_combo.set(current_model.selected_model if current_model else "")
        self.trans_model_combo.pack(side=tk.LEFT, padx=5)

        ttk.Button(r3, text="📝 Sửa Prompt", command=lambda: self.open_text_editor(PROMPT_FILE, "Tùy Chỉnh Prompt")).pack(side=tk.RIGHT, padx=2)
        ttk.Button(r3, text="📖 Sửa Memory", command=lambda: self.open_text_editor(MEMORY_FILE, "Từ Điển Thuật Ngữ")).pack(side=tk.RIGHT, padx=2)

        # Action Buttons & Progress
        act_frame = ttk.Frame(tab)
        act_frame.pack(fill=tk.X, pady=4)
        self.btn_trans_start = tk.Button(act_frame, text="▶ BẮT ĐẦU DỊCH TRUYỆN", bg="#4CAF50", fg="white", font=("Segoe UI", 11, "bold"),
                                         command=self.start_translation, height=2)
        self.btn_trans_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.trans_prog = ttk.Progressbar(tab, orient=tk.HORIZONTAL, mode='determinate')
        self.trans_prog.pack(fill=tk.X, pady=4)

        # Log
        self.trans_log = scrolledtext.ScrolledText(tab, height=12, font=("Consolas", 9))
        self.trans_log.pack(fill=tk.BOTH, expand=True)

    def on_trans_provider_change(self, event=None):
        prov = self.trans_prov_combo.get()
        models = SUPPORTED_PROVIDERS.get(prov, [])
        self.trans_model_combo['values'] = models
        if models:
            self.trans_model_combo.set(models[0])

    def start_translation(self):
        raw_p = Path(self.trans_raw_var.get())
        out_p = Path(self.trans_out_var.get())
        if not raw_p.exists():
            messagebox.showerror("Lỗi", "Thư mục Raw không tồn tại!")
            return

        self.btn_trans_start.config(state=tk.DISABLED)
        self.trans_log.delete("1.0", tk.END)

        def worker():
            try:
                prov = self.trans_prov_combo.get()
                model = self.trans_model_combo.get()
                p_cfg = self.config.providers.get(prov)
                keys = p_cfg.api_keys if p_cfg else []

                rotator = KeyRotator(keys)
                client = create_llm_client(prov, model, rotator, p_cfg.base_url if p_cfg else None)
                chunker = SmartChunker(self.config.chunk_threshold, self.config.target_chunk_size)
                glossary = GlossaryManager.load(MEMORY_FILE) if MEMORY_FILE.exists() else GlossaryManager()

                prompt_text = DEFAULT_SYSTEM_PROMPT
                if PROMPT_FILE.exists():
                    prompt_text = PROMPT_FILE.read_text(encoding="utf-8")

                translator = NovelTranslator(client, chunker, glossary, system_prompt=prompt_text)

                files = sorted([f for f in raw_p.iterdir() if f.suffix.lower() == ".txt"])
                out_p.mkdir(parents=True, exist_ok=True)

                self.trans_prog['maximum'] = len(files) if files else 1
                self.trans_prog['value'] = 0

                self.append_log(self.trans_log, f"=== Bắt đầu dịch {len(files)} chương với {prov} ({model}) ===\n")

                for idx, file in enumerate(files, 1):
                    dest = out_p / file.name
                    if dest.exists() and dest.stat().st_size > 0:
                        self.append_log(self.trans_log, f"[{idx}/{len(files)}] Bỏ qua đã có: {file.name}\n")
                        self.trans_prog['value'] = idx
                        continue

                    self.append_log(self.trans_log, f"[{idx}/{len(files)}] Đang dịch: {file.name}...")
                    raw_text = file.read_text(encoding="utf-8", errors="ignore")
                    trans_text = translator.translate_text(raw_text)

                    dest.write_text(trans_text, encoding="utf-8")
                    self.append_log(self.trans_log, " [OK]\n")
                    self.trans_prog['value'] = idx

                self.append_log(self.trans_log, "\n🎉 HOÀN THÀNH DỊCH TOÀN BỘ!\n")
            except Exception as e:
                self.append_log(self.trans_log, f"\n❌ LỖI: {e}\n")
            finally:
                self.btn_trans_start.config(state=tk.NORMAL)

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------
    # TAB 2: TUỐT VĂN PHONG
    # -------------------------------------------------------------
    def create_tab_style(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="✨ Tuốt Văn Phong")

        io_frame = ttk.LabelFrame(tab, text="Thư Mục Làm Việc", padding=10)
        io_frame.pack(fill=tk.X, pady=(0, 8))

        self.style_in_var = tk.StringVar(value=str(BASE_DIR / "data" / "translated"))
        self.style_out_var = tk.StringVar(value=str(BASE_DIR / "data" / "edited"))

        r1 = ttk.Frame(io_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Thư mục Nguồn:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.style_in_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="Chọn...", command=lambda: self.browse_dir(self.style_in_var)).pack(side=tk.RIGHT)

        r2 = ttk.Frame(io_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="Thư mục Đích:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.style_out_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r2, text="Chọn...", command=lambda: self.browse_dir(self.style_out_var)).pack(side=tk.RIGHT)

        opt_frame = ttk.LabelFrame(tab, text="Tùy Chọn Style Tag", padding=10)
        opt_frame.pack(fill=tk.X, pady=(0, 8))

        r3 = ttk.Frame(opt_frame)
        r3.pack(fill=tk.X, pady=2)
        ttk.Label(r3, text="Chọn Phong Cách:", width=15).pack(side=tk.LEFT)

        style_tags = ["RomCom", "Dark Fantasy", "Anime Style", "Slice of Life", "Trầm nội tâm", "Văn nhẹ nhàng", "Tiểu thuyết xuất bản", "Hài hước tự nhiên"]
        self.style_tag_combo = ttk.Combobox(r3, values=style_tags, state="readonly", width=22)
        self.style_tag_combo.set("RomCom")
        self.style_tag_combo.pack(side=tk.LEFT, padx=5)

        ttk.Button(r3, text="🎨 Sửa Styles JSON", command=lambda: self.open_text_editor(STYLES_FILE, "Quản Lý Style Tags")).pack(side=tk.RIGHT)

        r4 = ttk.Frame(opt_frame)
        r4.pack(fill=tk.X, pady=4)
        ttk.Label(r4, text="Yêu cầu bổ sung:", width=15).pack(side=tk.LEFT)
        self.style_custom_entry = ttk.Entry(r4)
        self.style_custom_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        act_frame = ttk.Frame(tab)
        act_frame.pack(fill=tk.X, pady=4)
        self.btn_style_start = tk.Button(act_frame, text="✨ BẮT ĐẦU TUỐT VĂN PHONG", bg="#9C27B0", fg="white", font=("Segoe UI", 11, "bold"),
                                         command=self.start_styling, height=2)
        self.btn_style_start.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.style_prog = ttk.Progressbar(tab, orient=tk.HORIZONTAL, mode='determinate')
        self.style_prog.pack(fill=tk.X, pady=4)

        self.style_log = scrolledtext.ScrolledText(tab, height=12, font=("Consolas", 9))
        self.style_log.pack(fill=tk.BOTH, expand=True)

    def start_styling(self):
        in_p = Path(self.style_in_var.get())
        out_p = Path(self.style_out_var.get())
        if not in_p.exists():
            messagebox.showerror("Lỗi", "Thư mục Nguồn không tồn tại!")
            return

        self.btn_style_start.config(state=tk.DISABLED)
        self.style_log.delete("1.0", tk.END)

        def worker():
            try:
                prov = self.config.selected_provider
                p_cfg = self.config.providers.get(prov)
                keys = p_cfg.api_keys if p_cfg else []
                model = p_cfg.selected_model if p_cfg else "gemini-3.5-flash"

                rotator = KeyRotator(keys)
                client = create_llm_client(prov, model, rotator, p_cfg.base_url if p_cfg else None)
                chunker = SmartChunker(self.config.chunk_threshold, self.config.target_chunk_size)
                polisher = NovelStylePolisher(client, chunker, styles_file=STYLES_FILE)

                files = sorted([f for f in in_p.iterdir() if f.suffix.lower() == ".txt"])
                out_p.mkdir(parents=True, exist_ok=True)

                self.style_prog['maximum'] = len(files) if files else 1
                self.style_prog['value'] = 0

                tag = self.style_tag_combo.get()
                extra = self.style_custom_entry.get()
                self.append_log(self.style_log, f"=== Bắt đầu tuốt văn phong '{tag}' cho {len(files)} chương ===\n")

                for idx, file in enumerate(files, 1):
                    dest = out_p / file.name
                    if dest.exists() and dest.stat().st_size > 0:
                        self.append_log(self.style_log, f"[{idx}/{len(files)}] Bỏ qua đã sửa: {file.name}\n")
                        self.style_prog['value'] = idx
                        continue

                    self.append_log(self.style_log, f"[{idx}/{len(files)}] Đang sửa: {file.name}...")
                    raw_text = file.read_text(encoding="utf-8", errors="ignore")
                    res = polisher.polish_text(raw_text, style_name=tag, custom_instructions=extra)

                    dest.write_text(res, encoding="utf-8")
                    self.append_log(self.style_log, " [OK]\n")
                    self.style_prog['value'] = idx

                self.append_log(self.style_log, "\n🎉 HOÀN THÀNH TUỐT VĂN PHONG!\n")
            except Exception as e:
                self.append_log(self.style_log, f"\n❌ LỖI: {e}\n")
            finally:
                self.btn_style_start.config(state=tk.NORMAL)

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------
    # TAB 3: QUÉT TÊN RIÊNG & THUẬT NGỮ
    # -------------------------------------------------------------
    def create_tab_terminology(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="🔍 Quét Tên Riêng (NER)")

        top = ttk.Frame(tab)
        top.pack(fill=tk.X, pady=(0, 6))

        self.ner_in_var = tk.StringVar(value=str(BASE_DIR / "data" / "raw"))
        ttk.Label(top, text="Thư mục quét:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.ner_in_var, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(top, text="Chọn...", command=lambda: self.browse_dir(self.ner_in_var)).pack(side=tk.LEFT)

        ttk.Label(top, text="Tần suất tối thiểu:").pack(side=tk.LEFT, padx=(10, 2))
        self.ner_freq_var = tk.IntVar(value=2)
        ttk.Spinbox(top, from_=1, to=100, textvariable=self.ner_freq_var, width=5).pack(side=tk.LEFT)

        btn_bar = ttk.Frame(tab)
        btn_bar.pack(fill=tk.X, pady=4)
        ttk.Button(btn_bar, text="⚡ Quét Nhanh Heuristics", command=self.scan_ner_fast).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="🤖 AI Xác Thực & Phiên Âm", command=self.scan_ner_ai).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="💾 Lưu Vào memory.txt", command=self.save_ner_to_memory).pack(side=tk.RIGHT, padx=2)

        # Treeview
        columns = ("term", "category", "translation", "count")
        self.ner_tree = ttk.Treeview(tab, columns=columns, show="headings", height=15)
        self.ner_tree.heading("term", text="Thuật Ngữ / Tên")
        self.ner_tree.heading("category", text="Phân Loại")
        self.ner_tree.heading("translation", text="Phiên Âm / Dịch")
        self.ner_tree.heading("count", text="Số Lần Gặp")

        self.ner_tree.column("term", width=220)
        self.ner_tree.column("category", width=120)
        self.ner_tree.column("translation", width=200)
        self.ner_tree.column("count", width=90, anchor=tk.CENTER)

        scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.ner_tree.yview)
        self.ner_tree.configure(yscrollcommand=scroll.set)
        self.ner_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def scan_ner_fast(self):
        folder = Path(self.ner_in_var.get())
        if not folder.exists():
            messagebox.showerror("Lỗi", "Thư mục không tồn tại!")
            return

        files = [f for f in folder.iterdir() if f.suffix.lower() == ".txt"]
        texts = [f.read_text(encoding="utf-8", errors="ignore") for f in files]

        extractor = TerminologyExtractor()
        candidates = extractor.extract_candidates(texts, min_frequency=self.ner_freq_var.get())

        for row in self.ner_tree.get_children():
            self.ner_tree.delete(row)

        for term, count in sorted(candidates.items(), key=lambda x: x[1], reverse=True):
            self.ner_tree.insert("", tk.END, values=(term, "CHARACTERS", "", count))

        messagebox.showinfo("Thành công", f"Tìm thấy {len(candidates)} thuật ngữ!")

    def scan_ner_ai(self):
        items = self.ner_tree.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Hãy bấm 'Quét Nhanh Heuristics' trước!")
            return

        terms = [self.ner_tree.item(it)['values'][0] for it in items]

        def worker():
            try:
                prov = self.config.selected_provider
                p_cfg = self.config.providers.get(prov)
                keys = p_cfg.api_keys if p_cfg else []
                model = p_cfg.selected_model if p_cfg else "gemini-3.5-flash"

                rotator = KeyRotator(keys)
                client = create_llm_client(prov, model, rotator, p_cfg.base_url if p_cfg else None)
                extractor = TerminologyExtractor()

                entries = extractor.refine_with_llm(client, terms)

                self.root.after(0, lambda: self._update_ner_tree_with_ai(entries))
            except Exception as e:
                messagebox.showerror("Lỗi AI", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _update_ner_tree_with_ai(self, entries):
        for row in self.ner_tree.get_children():
            self.ner_tree.delete(row)

        for e in entries:
            self.ner_tree.insert("", tk.END, values=(e.term, e.category, e.translation, "-"))
        messagebox.showinfo("Hoàn tất", f"AI đã phân loại và phiên âm {len(entries)} từ!")

    def save_ner_to_memory(self):
        items = self.ner_tree.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Danh sách đang trống!")
            return

        manager = GlossaryManager.load(MEMORY_FILE) if MEMORY_FILE.exists() else GlossaryManager()
        existing = {e.term for e in manager.entries}

        count = 0
        for it in items:
            val = self.ner_tree.item(it)['values']
            term = str(val[0])
            cat = str(val[1])
            trans = str(val[2]) if len(val) > 2 else ""
            if term not in existing:
                manager.entries.append(GlossaryEntry(term=term, translation=trans, category=cat))
                count += 1

        manager.save(MEMORY_FILE)
        messagebox.showinfo("Lưu Thành Công", f"Đã thêm {count} thuật ngữ mới vào {MEMORY_FILE.name}!")

    # -------------------------------------------------------------
    # TAB 4: TÁCH FILE TRUYỆN (SPLITTER)
    # -------------------------------------------------------------
    def create_tab_splitter(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="✂️ Tách File Truyện")

        box = ttk.LabelFrame(tab, text="Cắt File Gộp Nhiều Chương", padding=15)
        box.pack(fill=tk.X, pady=10)

        self.split_in_file = tk.StringVar()
        self.split_out_dir = tk.StringVar(value=str(BASE_DIR / "data" / "raw"))

        r1 = ttk.Frame(box)
        r1.pack(fill=tk.X, pady=4)
        ttk.Label(r1, text="File gộp (.txt):", width=15).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.split_in_file).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="Chọn File...", command=self.browse_split_file).pack(side=tk.RIGHT)

        r2 = ttk.Frame(box)
        r2.pack(fill=tk.X, pady=4)
        ttk.Label(r2, text="Thư mục xuất:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.split_out_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r2, text="Chọn...", command=lambda: self.browse_dir(self.split_out_dir)).pack(side=tk.RIGHT)

        btn = tk.Button(tab, text="✂️ TIẾN HÀNH TÁCH CHƯƠNG", bg="#3F51B5", fg="white", font=("Segoe UI", 11, "bold"),
                        command=self.run_splitter, height=2)
        btn.pack(fill=tk.X, pady=10)

        self.split_log = scrolledtext.ScrolledText(tab, height=12, font=("Consolas", 9))
        self.split_log.pack(fill=tk.BOTH, expand=True)

    def browse_split_file(self):
        f = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if f:
            self.split_in_file.set(f)

    def run_splitter(self):
        inp = Path(self.split_in_file.get())
        out = Path(self.split_out_dir.get())
        if not inp.exists():
            messagebox.showerror("Lỗi", "Vui lòng chọn file .txt hợp lệ!")
            return

        self.split_log.delete("1.0", tk.END)
        self.append_log(self.split_log, f"Đang quét tiêu đề chương trong {inp.name}...\n")

        def worker():
            try:
                splitter = NovelSplitter()
                out_files = splitter.split_txt_file(
                    inp, out,
                    progress_cb=lambda c, t, title: self.append_log(self.split_log, f"  -> Tạo chương [{c}/{t}]: {title}\n")
                )
                self.append_log(self.split_log, f"\n🎉 Tách thành công {len(out_files)} chương vào thư mục:\n{out}\n")
            except Exception as e:
                self.append_log(self.split_log, f"❌ Lỗi: {e}\n")

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------
    # TAB 5: ĐÓNG GÓI EPUB
    # -------------------------------------------------------------
    def create_tab_epub(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="📚 Đóng Gói EPUB")

        box = ttk.LabelFrame(tab, text="Cấu Hình Ebook", padding=15)
        box.pack(fill=tk.X, pady=10)

        self.epub_in_dir = tk.StringVar(value=str(BASE_DIR / "data" / "edited"))
        self.epub_out_file = tk.StringVar(value=str(BASE_DIR / "data" / "output" / "MyNovel.epub"))
        self.epub_title = tk.StringVar(value="Tên Truyện")
        self.epub_author = tk.StringVar(value="Tác Giả")
        self.epub_cover_file = tk.StringVar()

        r1 = ttk.Frame(box)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Thư mục .txt:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.epub_in_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="Chọn...", command=lambda: self.browse_dir(self.epub_in_dir)).pack(side=tk.RIGHT)

        r2 = ttk.Frame(box)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="File EPUB xuất:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.epub_out_file).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r2, text="Chọn...", command=self.browse_epub_save).pack(side=tk.RIGHT)

        r3 = ttk.Frame(box)
        r3.pack(fill=tk.X, pady=2)
        ttk.Label(r3, text="Tên Sách:", width=15).pack(side=tk.LEFT)
        ttk.Entry(r3, textvariable=self.epub_title).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Label(r3, text="Tác Giả:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(r3, textvariable=self.epub_author).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        r4 = ttk.Frame(box)
        r4.pack(fill=tk.X, pady=2)
        ttk.Label(r4, text="Ảnh Bìa (Cover):", width=15).pack(side=tk.LEFT)
        ttk.Entry(r4, textvariable=self.epub_cover_file).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r4, text="Chọn Bìa...", command=self.browse_cover_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(r4, text="🎨 AI Vẽ Bìa", command=self.generate_ai_cover).pack(side=tk.LEFT, padx=2)

        btn = tk.Button(tab, text="📚 TẠO FILE EPUB", bg="#FF9800", fg="white", font=("Segoe UI", 11, "bold"),
                        command=self.run_epub_builder, height=2)
        btn.pack(fill=tk.X, pady=10)

        self.epub_log = scrolledtext.ScrolledText(tab, height=10, font=("Consolas", 9))
        self.epub_log.pack(fill=tk.BOTH, expand=True)

    def browse_epub_save(self):
        f = filedialog.asksaveasfilename(defaultextension=".epub", filetypes=[("EPUB Ebook", "*.epub")])
        if f:
            self.epub_out_file.set(f)

    def browse_cover_image(self):
        f = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.png;*.jpeg")])
        if f:
            self.epub_cover_file.set(f)

    def generate_ai_cover(self):
        title = self.epub_title.get().strip() or "Light Novel"
        out_cover = BASE_DIR / "data" / "output" / "cover_ai.jpg"
        self.append_log(self.epub_log, f"🎨 Đang nhờ AI vẽ bìa cho truyện '{title}'...\n")

        def worker():
            try:
                EpubBuilder.generate_ai_cover(title, out_cover)
                self.epub_cover_file.set(str(out_cover))
                self.append_log(self.epub_log, f"🎉 Đã tạo bìa AI thành công: {out_cover.name}\n")
            except Exception as e:
                self.append_log(self.epub_log, f"❌ Lỗi vẽ bìa: {e}\n")

        threading.Thread(target=worker, daemon=True).start()

    def run_epub_builder(self):
        inp = Path(self.epub_in_dir.get())
        out = Path(self.epub_out_file.get())
        if not inp.exists():
            messagebox.showerror("Lỗi", "Thư mục chứa file .txt không tồn tại!")
            return

        self.epub_log.delete("1.0", tk.END)
        cover_path = Path(self.epub_cover_file.get()) if self.epub_cover_file.get() else None

        def worker():
            try:
                builder = EpubBuilder()
                builder.build_epub(
                    inp, out,
                    title=self.epub_title.get(),
                    author=self.epub_author.get(),
                    cover_image=cover_path,
                    progress_cb=lambda c, t, name: self.append_log(self.epub_log, f"  -> Thêm chương [{c}/{t}]: {name}\n")
                )
                self.append_log(self.epub_log, f"\n🎉 ĐÓNG GÓI THÀNH CÔNG: {out}\n")
            except Exception as e:
                self.append_log(self.epub_log, f"❌ Lỗi: {e}\n")

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------
    # TAB 6: AUTO PIPELINE (LIÊN HOÀN 1 CHẠM)
    # -------------------------------------------------------------
    def create_tab_pipeline(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="⚡ Auto Pipeline")

        box = ttk.LabelFrame(tab, text="Quy Trình Tự Động Hóa Trọn Vẹn", padding=15)
        box.pack(fill=tk.X, pady=5)

        self.pipe_step1 = tk.BooleanVar(value=True)
        self.pipe_step2 = tk.BooleanVar(value=True)
        self.pipe_step3 = tk.BooleanVar(value=True)
        self.pipe_step4 = tk.BooleanVar(value=True)

        ttk.Checkbutton(box, text="Step 1: Quét và cập nhật thuật ngữ vào Glossary", variable=self.pipe_step1).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(box, text="Step 2: Dịch toàn bộ chương qua AI LLM", variable=self.pipe_step2).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(box, text="Step 3: Tuốt văn phong tự nhiên (RomCom/Anime...)", variable=self.pipe_step3).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(box, text="Step 4: Đóng gói thành file EPUB hoàn chỉnh", variable=self.pipe_step4).pack(anchor=tk.W, pady=2)

        btn = tk.Button(tab, text="▶ BẮT ĐẦU CHẠY CHUỖI TỰ ĐỘNG (1-CLICK)", bg="#009688", fg="white", font=("Segoe UI", 12, "bold"),
                        command=self.run_auto_pipeline, height=2)
        btn.pack(fill=tk.X, pady=8)

        self.pipe_log = scrolledtext.ScrolledText(tab, height=14, font=("Consolas", 9))
        self.pipe_log.pack(fill=tk.BOTH, expand=True)

    def run_auto_pipeline(self):
        raw_dir = BASE_DIR / "data" / "raw"
        trans_dir = BASE_DIR / "data" / "translated"
        edited_dir = BASE_DIR / "data" / "edited"
        epub_out = BASE_DIR / "data" / "output" / "FullNovel.epub"

        self.pipe_log.delete("1.0", tk.END)

        def worker():
            try:
                prov = self.config.selected_provider
                p_cfg = self.config.providers.get(prov)
                keys = p_cfg.api_keys if p_cfg else []
                model = p_cfg.selected_model if p_cfg else "gemini-3.5-flash"

                rotator = KeyRotator(keys)
                client = create_llm_client(prov, model, rotator, p_cfg.base_url if p_cfg else None)
                chunker = SmartChunker(self.config.chunk_threshold, self.config.target_chunk_size)
                glossary = GlossaryManager.load(MEMORY_FILE) if MEMORY_FILE.exists() else GlossaryManager()

                prompt_text = DEFAULT_SYSTEM_PROMPT
                if PROMPT_FILE.exists():
                    prompt_text = PROMPT_FILE.read_text(encoding="utf-8")

                translator = NovelTranslator(client, chunker, glossary, system_prompt=prompt_text)
                polisher = NovelStylePolisher(client, chunker, styles_file=STYLES_FILE)
                builder = EpubBuilder()

                pipeline = LocalizationPipeline(translator, polisher, builder)
                pipeline.run_pipeline(
                    raw_dir=raw_dir,
                    translated_dir=trans_dir,
                    edited_dir=edited_dir,
                    epub_file=epub_out,
                    glossary_file=MEMORY_FILE,
                    do_extract_terms=self.pipe_step1.get(),
                    do_translate=self.pipe_step2.get(),
                    do_polish_style=self.pipe_step3.get(),
                    do_package_epub=self.pipe_step4.get(),
                    log_callback=lambda msg: self.append_log(self.pipe_log, msg + "\n")
                )
            except Exception as e:
                self.append_log(self.pipe_log, f"❌ Lỗi Pipeline: {e}\n")

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------
    # TAB 7: CẤU HÌNH & API KEYS
    # -------------------------------------------------------------
    def create_tab_settings(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="🔑 Cấu Hình & Keys")

        box = ttk.LabelFrame(tab, text="Quản Lý API Key & Provider Mặc Định", padding=15)
        box.pack(fill=tk.BOTH, expand=True)

        r1 = ttk.Frame(box)
        r1.pack(fill=tk.X, pady=4)
        ttk.Label(r1, text="Provider Đang Chọn:", width=20).pack(side=tk.LEFT)
        self.sett_prov_combo = ttk.Combobox(r1, values=list(SUPPORTED_PROVIDERS.keys()), state="readonly", width=20)
        self.sett_prov_combo.set(self.config.selected_provider)
        self.sett_prov_combo.pack(side=tk.LEFT, padx=5)
        self.sett_prov_combo.bind("<<ComboboxSelected>>", self.on_settings_prov_change)

        ttk.Label(box, text="Danh sách API Keys (Mỗi key 1 dòng - Hệ thống sẽ tự động xoay tua):").pack(anchor=tk.W, pady=(10, 4))
        self.key_box = scrolledtext.ScrolledText(box, height=10, font=("Consolas", 10))
        self.key_box.pack(fill=tk.BOTH, expand=True, pady=4)

        self.load_keys_to_box()

        btn = tk.Button(box, text="💾 LƯU CẤU HÌNH", bg="#4CAF50", fg="white", font=("Segoe UI", 11, "bold"),
                        command=self.save_settings, height=2)
        btn.pack(fill=tk.X, pady=8)

    def on_settings_prov_change(self, event=None):
        self.load_keys_to_box()

    def load_keys_to_box(self):
        prov = self.sett_prov_combo.get()
        p_cfg = self.config.providers.get(prov)
        keys = p_cfg.api_keys if p_cfg else []
        self.key_box.delete("1.0", tk.END)
        self.key_box.insert(tk.END, "\n".join(keys))

    def save_settings(self):
        prov = self.sett_prov_combo.get()
        raw_keys = self.key_box.get("1.0", tk.END).splitlines()
        clean_keys = [k.strip() for k in raw_keys if k.strip()]

        self.config.selected_provider = prov
        if prov in self.config.providers:
            self.config.providers[prov].api_keys = clean_keys

        save_config(self.config, CONFIG_FILE)
        messagebox.showinfo("Thành Công", f"Đã lưu {len(clean_keys)} keys cho provider '{prov}'!")

    # -------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------
    def browse_dir(self, string_var: tk.StringVar):
        d = filedialog.askdirectory()
        if d:
            string_var.set(d)

    def append_log(self, text_widget, msg: str):
        self.root.after(0, lambda: self._do_append(text_widget, msg))

    def _do_append(self, text_widget, msg: str):
        text_widget.insert(tk.END, msg)
        text_widget.see(tk.END)

    def open_text_editor(self, file_path: Path, title: str):
        if not file_path.exists():
            file_path.write_text("", encoding="utf-8")

        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("650x500")

        txt = scrolledtext.ScrolledText(win, font=("Segoe UI", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        txt.insert(tk.END, file_path.read_text(encoding="utf-8"))

        def save():
            file_path.write_text(txt.get("1.0", tk.END).strip(), encoding="utf-8")
            messagebox.showinfo("Lưu thành công", f"Đã lưu nội dung vào: {file_path.name}", parent=win)
            win.destroy()

        btn = ttk.Button(win, text="💾 Lưu và Đóng", command=save)
        btn.pack(pady=5)

def main():
    root = tk.Tk()
    app = ModernLocalizerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

