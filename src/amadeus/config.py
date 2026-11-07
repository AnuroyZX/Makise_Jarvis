from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List


def classify_api_key(raw_key: str) -> str:
    """
    Detect which provider an API key belongs to from its prefix, so the user can paste
    any key into a single field. Returns the AmadeusSettings field name, or "" if unknown.
    """
    key = raw_key.strip()
    if key.startswith("sk-ant-"):
        return "anthropic_api_key"
    if key.startswith("sk-or-"):
        return "openrouter_api_key"
    if key.startswith("sk-"):
        return "openai_api_key"
    if key.startswith("AIza") or key.startswith("AQ."):
        return "gemini_api_key"
    return ""


def get_default_data_dir() -> Path:
    """Resolve portable data directory dynamically across any Windows PC."""
    custom_dir = os.environ.get("AMADEUS_DATA_DIR")
    if custom_dir:
        path = Path(custom_dir)
    else:
        # If a local 'portable_data' folder exists next to the executable/project, use it (100% USB/folder portable)
        local_portable = Path.cwd() / "data"
        if local_portable.exists() or not os.environ.get("APPDATA"):
            path = local_portable
        else:
            path = Path(os.environ["APPDATA"]) / "AmadeusKurisu"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(slots=True)
class AmadeusSettings:
    """Validated, portable settings for all 9 modules without hardcoded paths."""

    # Module 3: Brain settings
    active_brain: str = "auto"  # auto | free | gemini | claude | codex | openrouter
    foreground_model_gemini: str = "gemini-3-flash-preview"
    background_model_gemini: str = "gemini-3.1-flash-lite-preview"
    foreground_model_claude: str = "claude-3-7-sonnet-latest"
    foreground_model_codex: str = "gpt-4o"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""

    # Module 5: Memory (Honcho + Local SQLite)
    honcho_api_key: str = ""
    honcho_base_url: str = "https://api.honcho.dev/v1"
    honcho_app_id: str = "amadeus-kurisu"
    use_honcho_cloud: bool = True

    # Module 7: Tools (Email / Calendar / Browser)
    imap_host: str = ""
    imap_user: str = ""
    imap_password: str = ""
    smtp_host: str = ""
    caldav_url: str = ""
    browser_idle_timeout_sec: int = 120

    # Module 8: Channels (Telegram / PC Hotkey / WhatsApp)
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: List[int] = field(default_factory=list)
    push_to_talk_hotkey: str = "ctrl+alt+k"
    enable_whatsapp_plugin: bool = False
    whatsapp_bridge_url: str = "http://127.0.0.1:3001"

    # Module 9: Voice (ElevenLabs + Edge-TTS fallback)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "FGY2WhTYpPnrIDTdsKH5"  # Young expressive female voice (or custom Voice Design ID)
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_max_chars_per_reply: int = 380  # Credit Guard threshold
    edge_tts_voice: str = "es-MX-DaliaNeural"
    voice_replies_enabled: bool = True

    # Desktop Companion (Electron Overlay & Bubbles)
    bubbles_mode: str = "detail_only"  # "off" | "detail_only" | "all"
    wake_word_enabled: bool = True
    wake_word_phrase: str = "oye kurisu"
    allowed_fs_roots: List[str] = field(default_factory=list)
    excluded_screen_apps: List[str] = field(
        default_factory=lambda: ["keepass", "1password", "bitwarden", "authy", "banco", "bank"]
    )
    habit_suggestions_enabled: bool = True

    # General & Onboarding
    user_display_name: str = "Okabe"
    onboarding_completed: bool = False

    @classmethod
    def load(cls, data_dir: Path | None = None) -> AmadeusSettings:
        target_dir = data_dir or get_default_data_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        config_file = target_dir / "settings.json"
        data: dict = {}
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}

        # Allow environment variable overrides
        env_map = {
            "gemini_api_key": "GEMINI_API_KEY",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "openrouter_api_key": "OPENROUTER_API_KEY",
            "honcho_api_key": "HONCHO_API_KEY",
            "elevenlabs_api_key": "ELEVENLABS_API_KEY",
            "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        }
        for field_name, env_var in env_map.items():
            env_val = os.environ.get(env_var)
            if env_val:
                data[field_name] = env_val

        valid_keys = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        # Migrate legacy deprecated Gemini 2.5 model names to active Gemini 3 Flash models
        if filtered.get("foreground_model_gemini") in ("gemini-2.5-pro", "gemini-2.5-flash"):
            filtered["foreground_model_gemini"] = "gemini-3-flash-preview"
        if filtered.get("background_model_gemini") in ("gemini-2.5-flash", "gemini-2.0-flash"):
            filtered["background_model_gemini"] = "gemini-3.1-flash-lite-preview"
        return cls(**filtered)

    def save(self, data_dir: Path | None = None) -> Path:
        target_dir = data_dir or get_default_data_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        config_file = target_dir / "settings.json"
        config_file.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return config_file

    def masked_summary(self) -> dict[str, str]:
        """Return safe summary with masked secrets per ECC AgentShield rules."""
        def _mask(secret: str) -> str:
            if not secret:
                return "(not configured)"
            if len(secret) <= 6:
                return "***"
            return f"{secret[:3]}***{secret[-3:]}"

        return {
            "active_brain": self.active_brain,
            "gemini_api_key": _mask(self.gemini_api_key),
            "anthropic_api_key": _mask(self.anthropic_api_key),
            "openai_api_key": _mask(self.openai_api_key),
            "openrouter_api_key": _mask(self.openrouter_api_key),
            "honcho_api_key": _mask(self.honcho_api_key),
            "elevenlabs_api_key": _mask(self.elevenlabs_api_key),
            "telegram_bot_token": _mask(self.telegram_bot_token),
        }
