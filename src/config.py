import json
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

SUPPORTED_PROVIDERS = {
    "Gemini": [
        "gemini-3.8-flash",
        "gemini-3.8-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro",
        "gemma-4-21b",
        "gemini-2.5-flash",
        "gemini-2.0-flash"
    ],
    "OpenAI": [
        "gpt-4o-mini",
        "gpt-4o"
    ],
    "OpenRouter": [
        "deepseek/deepseek-chat",
        "google/gemini-2.0-flash-001",
        "anthropic/claude-3.5-haiku",
        "meta-llama/llama-3.3-70b-instruct"
    ],
    "Groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ],
    "Ollama": [
        "qwen2.5:14b",
        "llama3.3:70b",
        "mistral:latest"
    ]
}

class ProviderConfig(BaseModel):
    selected_model: str
    api_keys: List[str] = Field(default_factory=list)
    base_url: Optional[str] = None

class LocalizerConfig(BaseModel):
    selected_provider: str = "Gemini"
    chunk_threshold: int = Field(default=5000, description="Max character length before triggering chunking")
    target_chunk_size: int = Field(default=2500, description="Target character size per chunk")
    max_retries: int = Field(default=3, description="Retry attempts for failed chunks")
    source_language: str = "auto"
    target_language: str = "Vietnamese"
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)

    @classmethod
    def get_default(cls) -> "LocalizerConfig":
        return cls(
            selected_provider="Gemini",
            chunk_threshold=5000,
            target_chunk_size=2500,
            max_retries=3,
            source_language="auto",
            target_language="Vietnamese",
            providers={
                "Gemini": ProviderConfig(
                    selected_model="gemini-3.5-flash",
                    api_keys=[]
                ),
                "OpenAI": ProviderConfig(
                    selected_model="gpt-4o-mini",
                    api_keys=[]
                ),
                "OpenRouter": ProviderConfig(
                    selected_model="deepseek/deepseek-chat",
                    api_keys=[],
                    base_url="https://openrouter.ai/api/v1/chat/completions"
                ),
                "Groq": ProviderConfig(
                    selected_model="llama-3.3-70b-versatile",
                    api_keys=[],
                    base_url="https://api.groq.com/openai/v1/chat/completions"
                ),
                "Ollama": ProviderConfig(
                    selected_model="qwen2.5:14b",
                    api_keys=["ollama-local"],
                    base_url="http://localhost:11434/v1/chat/completions"
                )
            }
        )

def load_config(config_path: Path) -> LocalizerConfig:
    """Loads configuration from JSON file. Creates default if not found."""
    if not config_path.exists():
        default_cfg = LocalizerConfig.get_default()
        save_config(default_cfg, config_path)
        return default_cfg

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return LocalizerConfig.model_validate(data)
    except Exception:
        return LocalizerConfig.get_default()

def save_config(config: LocalizerConfig, config_path: Path) -> None:
    """Saves configuration to JSON file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))

