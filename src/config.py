"""
Configuration module for maya-telugu-vlog.
Loads environment variables using Pydantic BaseSettings v2.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # OpenRouter / LLM Configuration
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key")
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL for OpenRouter API"
    )
    STORY_ARCHITECT_MODEL: str = Field(
        default="nousresearch/hermes-3-llama-3.1-70b",
        description="High-chemistry scene plotting and pacing model"
    )
    TELUGU_WRITER_MODEL: str = Field(
        default="google/gemini-2.5-pro",
        description="Model for natural, spoken colloquial Telugu prose"
    )

    # Google Gemini Direct Integration (100% Free at aistudio.google.com for human-grade Telugu)
    GEMINI_API_KEY: str = Field(
        default="",
        description="Optional Google Gemini API Key for flawless, poetic, colloquial Telugu ($0.00 free tier)"
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.0-flash",
        description="Gemini model for Telugu writer and scene architect"
    )

    # Image Generation Configuration
    IMAGE_PROVIDER: str = Field(
        default="auto",
        description="Image generation provider: 'auto', 'together', 'huggingface', 'fal', or 'pollinations'"
    )
    TOGETHER_API_KEY: str = Field(
        default="",
        description="Together AI API key ($5 free credits = 1,600+ Flux.1 images)"
    )
    HF_TOKEN: str = Field(
        default="",
        description="Hugging Face User Access Token for free serverless FLUX.1-schnell inference"
    )
    FAL_KEY: str = Field(default="", description="Fal.ai API key")
    FAL_LORA_URL: str = Field(
        default="https://huggingface.co/XLabs-AI/flux-lora-collection/resolve/main/flux-realism-lora.safetensors",
        description="HuggingFace URL or Fal storage URL for Maya LoRA weights"
    )
    FAL_LORA_SCALE: float = Field(default=0.95, ge=0.0, le=2.0)
    MAYA_TRIGGER_WORD: str = Field(default="maya_south_indian")
    FAL_ENABLE_SAFETY_CHECKER: bool = Field(
        default=False,
        description="Enable/disable Fal NSFW safety checker"
    )

    # Supabase Database Configuration
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_SERVICE_KEY: str = Field(
        default="",
        description="Supabase Service Role Key (bypasses RLS for backend operations)"
    )

    # Telegram Channel & Bot Settings
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram Bot API Token")
    TELEGRAM_CHANNEL_ID: str = Field(
        default="",
        description="Telegram Channel username (@channel) or numeric ID"
    )
    TELEGRAM_SPOILER_BLUR: bool = Field(
        default=True,
        description="If true, image is posted with spoiler blur overlay"
    )

    # Pipeline Execution Flags
    DRY_RUN: bool = Field(
        default=False,
        description="Run pipeline locally without posting to Telegram or writing to live DB"
    )
    MOCK_MODE: bool = Field(
        default=False,
        description="Use internal mock generators for LLM & Image when keys are unavailable"
    )

    @property
    def is_fully_configured_for_live(self) -> bool:
        """Checks if all mandatory keys for live publishing are present."""
        has_llm = bool(
            (self.GEMINI_API_KEY and not self.GEMINI_API_KEY.startswith("your_"))
            or (self.OPENROUTER_API_KEY and not self.OPENROUTER_API_KEY.startswith("your_"))
        )
        mandatory_keys = [
            has_llm,
            bool(self.SUPABASE_URL and not self.SUPABASE_URL.startswith("your_")),
            bool(self.SUPABASE_SERVICE_KEY and not self.SUPABASE_SERVICE_KEY.startswith("your_")),
            bool(self.TELEGRAM_BOT_TOKEN and not self.TELEGRAM_BOT_TOKEN.startswith("your_")),
            bool(self.TELEGRAM_CHANNEL_ID and not self.TELEGRAM_CHANNEL_ID.startswith("your_")),
        ]
        if self.IMAGE_PROVIDER == "fal":
            mandatory_keys.append(bool(self.FAL_KEY and not self.FAL_KEY.startswith("your_")))
        elif self.IMAGE_PROVIDER == "together":
            mandatory_keys.append(bool(self.TOGETHER_API_KEY and not self.TOGETHER_API_KEY.startswith("your_")))
        elif self.IMAGE_PROVIDER == "huggingface":
            mandatory_keys.append(bool(self.HF_TOKEN and not self.HF_TOKEN.startswith("your_")))
        return all(mandatory_keys)


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
