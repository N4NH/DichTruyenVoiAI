from pathlib import Path
from typing import Optional
import os
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .config import load_config, save_config, LocalizerConfig
from .core.key_rotator import KeyRotator
from .core.llm_client import create_llm_client
from .processors.chunker import SmartChunker
from .processors.terminology import GlossaryManager, TerminologyExtractor
from .processors.translator import NovelTranslator, DEFAULT_SYSTEM_PROMPT

app = typer.Typer(
    name="novel-localizer",
    help="Production-grade LLM Pipeline for Novel Translation & Terminology Management.",
    add_completion=False
)
console = Console()
CONFIG_FILE = Path("config.json")

def get_configured_translator(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    glossary_path: Optional[Path] = None
) -> NovelTranslator:
    config = load_config(CONFIG_FILE)
    selected_provider = provider or config.selected_provider
    provider_cfg = config.providers.get(selected_provider)

    if not provider_cfg:
        console.print(f"[bold red]Error:[/] Provider '{selected_provider}' not found in configuration.")
        raise typer.Exit(code=1)

    selected_model = model or provider_cfg.selected_model
    keys = list(provider_cfg.api_keys)
    if api_key:
        keys.insert(0, api_key)
    # Check environment variable as fallback
    env_key = os.getenv("GEMINI_API_KEY") if selected_provider == "Gemini" else os.getenv("OPENAI_API_KEY")
    if env_key and env_key not in keys:
        keys.append(env_key)

    if not keys and selected_provider != "Ollama":
        console.print(f"[bold red]Error:[/] No API keys found for provider '{selected_provider}'.")
        console.print("Please set an API key using: [cyan]novel-localizer config set-key <PROVIDER> <KEY>[/]")
        raise typer.Exit(code=1)

    rotator = KeyRotator(api_keys=keys)
    client = create_llm_client(
        provider_name=selected_provider,
        model=selected_model,
        rotator=rotator,
        base_url=provider_cfg.base_url
    )
    chunker = SmartChunker(
        threshold=config.chunk_threshold,
        target_chunk_size=config.target_chunk_size
    )

    glossary = GlossaryManager.load(glossary_path) if glossary_path and glossary_path.exists() else GlossaryManager()

    return NovelTranslator(
        client=client,
        chunker=chunker,
        glossary=glossary,
        max_retries=config.max_retries
    )


@app.command()
def translate(
    input_path: Path = typer.Option(..., "--input", "-i", help="Path to input .txt file or directory containing chapters"),
    output_path: Path = typer.Option(..., "--output", "-o", help="Path to output .txt file or output directory"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="AI Provider (Gemini, OpenRouter, OpenAI, Groq, Ollama)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name"),
    glossary: Optional[Path] = typer.Option(None, "--glossary", "-g", help="Path to glossary file (memory.txt)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Temporary API key to use"),
    lang: str = typer.Option("Vietnamese", "--lang", "-l", help="Target translation language")
):
    """Translates a single chapter or an entire directory of novel chapters."""
    if not input_path.exists():
        console.print(f"[bold red]Error:[/] Input path does not exist: {input_path}")
        raise typer.Exit(code=1)

    translator = get_configured_translator(provider, model, api_key, glossary)

    if input_path.is_file():
        console.print(f"[cyan]Translating file:[/] {input_path.name}")
        with open(input_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        translated = translator.translate_text(raw_text, target_language=lang)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(translated)
        console.print(f"[bold green]Done![/] Saved to: {output_path}")

    elif input_path.is_dir():
        files = sorted([f for f in input_path.iterdir() if f.suffix.lower() == ".txt"])
        if not files:
            console.print("[yellow]No .txt chapter files found in input directory.[/]")
            raise typer.Exit(code=0)

        output_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[cyan]Found {len(files)} chapters to translate...[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Translating chapters...", total=len(files))
            for file in files:
                dest = output_path / file.name
                if dest.exists() and dest.stat().st_size > 0:
                    progress.advance(task)
                    continue

                with open(file, "r", encoding="utf-8") as f:
                    raw_text = f.read()

                try:
                    translated = translator.translate_text(raw_text, target_language=lang)
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(translated)
                except Exception as e:
                    console.print(f"[red]Failed chapter {file.name}: {e}[/]")

                progress.advance(task)

        console.print(f"[bold green]Translation batch complete![/] Output directory: {output_path}")


@app.command()
def extract_terms(
    input_path: Path = typer.Option(..., "--input", "-i", help="Path to directory of chapter files"),
    output_glossary: Path = typer.Option(Path("glossary.txt"), "--output", "-o", help="Output path for glossary"),
    min_freq: int = typer.Option(2, "--min-freq", "-f", help="Minimum frequency for a term candidate"),
    ai_cleanup: bool = typer.Option(False, "--ai-cleanup", help="Run AI refinement and categorization phase"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider for AI cleanup")
):
    """Scans chapter files for named entities, locations, and special terms."""
    if not input_path.exists():
        console.print(f"[bold red]Error:[/] Input directory not found: {input_path}")
        raise typer.Exit(code=1)

    files = [f for f in input_path.iterdir() if f.suffix.lower() == ".txt"] if input_path.is_dir() else [input_path]
    console.print(f"[cyan]Scanning {len(files)} files for candidate terminology...[/]")

    texts = []
    for f in files:
        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
            texts.append(fp.read())

    extractor = TerminologyExtractor()
    candidates = extractor.extract_candidates(texts, min_frequency=min_freq)
    console.print(f"[green]Extracted {len(candidates)} candidates matching frequency >= {min_freq}.[/]")

    if ai_cleanup and candidates:
        console.print("[yellow]Running AI classification and romanization phase...[/]")
        translator = get_configured_translator(provider=provider)
        entries = extractor.refine_with_llm(translator.client, list(candidates.keys()))
        manager = GlossaryManager(entries)
    else:
        # Convert candidate dictionary directly
        from .processors.terminology import GlossaryEntry
        entries = [GlossaryEntry(term=k, category="CHARACTERS") for k in sorted(candidates.keys())]
        manager = GlossaryManager(entries)

    manager.save(output_glossary)
    console.print(f"[bold green]Glossary saved successfully to:[/] {output_glossary}")


@app.command()
def show_config():
    """Displays current configuration and available providers."""
    config = load_config(CONFIG_FILE)
    table = Table(title="LLM Novel Localizer - Configuration")
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Keys Configured", style="magenta")
    table.add_column("Base URL", style="blue")

    for name, p_cfg in config.providers.items():
        is_selected = " [bold green](Active)[/]" if name == config.selected_provider else ""
        table.add_row(
            f"{name}{is_selected}",
            p_cfg.selected_model,
            str(len(p_cfg.api_keys)),
            p_cfg.base_url or "Default"
        )

    console.print(table)


if __name__ == "__main__":
    app()

