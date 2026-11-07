from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import httpx

from amadeus.config import AmadeusSettings, get_default_data_dir


@dataclass(slots=True)
class VoiceSynthesisResult:
    audio_bytes: bytes
    provider: str  # "elevenlabs" | "edge_tts" | "disabled"
    mime_type: str  # "audio/ogg" | "audio/mpeg"
    saved_path: Optional[Path] = None


class AmadeusVoiceEngine:
    """
    Module 9 (Voz):
    Synthesizes Makise Kurisu's voice using ElevenLabs API (primary) and automatically
    falls back to Microsoft Edge-TTS (free, zero local GPU/CPU load) when:
    1. ElevenLabs API key is not configured,
    2. Reply length exceeds `elevenlabs_max_chars_per_reply` (Credit Guard), or
    3. ElevenLabs returns an HTTP/quota error.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        cache_dir: Optional[Path] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        base_dir = cache_dir or (get_default_data_dir() / "voice_cache")
        self.cache_dir = base_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._external_client = http_client is not None
        self._client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=6.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._external_client and not self._client.is_closed:
            await self._client.aclose()

    def should_use_elevenlabs(self, text: str) -> bool:
        """Credit Guard logic: only call ElevenLabs if enabled, key exists, and within char budget."""
        if not self.settings.voice_replies_enabled:
            return False
        if not self.settings.elevenlabs_api_key:
            return False
        if len(text) > self.settings.elevenlabs_max_chars_per_reply:
            return False
        return True

    async def synthesize(
        self,
        text: str,
        for_telegram_opus: bool = False,
        save_to_disk: bool = False,
    ) -> VoiceSynthesisResult:
        clean_text = text.strip()
        if not clean_text or not self.settings.voice_replies_enabled:
            return VoiceSynthesisResult(
                audio_bytes=b"", provider="disabled", mime_type="audio/mpeg"
            )

        # 1. Try ElevenLabs if Credit Guard allows it
        if self.should_use_elevenlabs(clean_text):
            try:
                audio_bytes, mime = await self._call_elevenlabs(
                    clean_text, for_telegram_opus=for_telegram_opus
                )
                saved = self._save_audio(audio_bytes, ".ogg" if for_telegram_opus else ".mp3") if save_to_disk else None
                return VoiceSynthesisResult(
                    audio_bytes=audio_bytes,
                    provider="elevenlabs",
                    mime_type=mime,
                    saved_path=saved,
                )
            except Exception:
                # Graceful fallback to free Edge-TTS per ECC Clean Code Rule 4
                pass

        # 2. Fallback to free Edge-TTS
        audio_bytes = await self._call_edge_tts(clean_text)
        saved = self._save_audio(audio_bytes, ".mp3") if save_to_disk else None
        return VoiceSynthesisResult(
            audio_bytes=audio_bytes,
            provider="edge_tts",
            mime_type="audio/mpeg",
            saved_path=saved,
        )

    async def _call_elevenlabs(
        self, text: str, for_telegram_opus: bool = False
    ) -> tuple[bytes, str]:
        client = await self._get_client()
        output_fmt = "opus_48000_64" if for_telegram_opus else "mp3_44100_128"
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{self.settings.elevenlabs_voice_id}?output_format={output_fmt}"
        )
        headers = {
            "xi-api-key": self.settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.settings.elevenlabs_model_id,
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.80,
                "style": 0.25,
                "use_speaker_boost": True,
            },
        }
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        mime = "audio/ogg" if for_telegram_opus else "audio/mpeg"
        return resp.content, mime

    async def _call_edge_tts(self, text: str) -> bytes:
        """Lazy-import edge_tts per ECC Resource Efficiency Rule 1."""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text=text, voice=self.settings.edge_tts_voice
            )
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.extend(chunk["data"])
            return bytes(chunks)
        except Exception:
            return b""

    def _save_audio(self, data: bytes, ext: str) -> Optional[Path]:
        if not data:
            return None
        out = self.cache_dir / f"last_reply{ext}"
        out.write_bytes(data)
        return out

    async def design_voice_preview(
        self,
        voice_description: str = (
            "Young Japanese anime female scientist, 18 years old, calm, sharp, "
            "intelligent, slightly tsundere tone, clear diction speaking Spanish "
            "with subtle Japanese anime cadence."
        ),
        sample_text: str = (
            "No es que haya organizado tus archivos porque me preocupes, "
            "simplemente detesto el desorden en el laboratorio. El Psy Kongroo."
        ),
    ) -> dict:
        """
        Phase F2 (ElevenLabs Voice Design API + Web Prompt Helper):
        Attempts to generate custom voice previews via ElevenLabs `/v1/text-to-voice/create-previews`.
        If the user's ElevenLabs plan is Free (HTTP 403), returns the exact ready-to-paste
        Voice Design prompt and available account voices.
        """
        if not self.settings.elevenlabs_api_key:
            return {
                "status": "no_api_key",
                "web_prompt": voice_description,
                "sample_text": sample_text,
            }
        client = await self._get_client()
        headers = {
            "xi-api-key": self.settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        resp = await client.post(
            "https://api.elevenlabs.io/v1/text-to-voice/create-previews",
            headers=headers,
            json={"voice_description": voice_description, "text": sample_text},
        )
        if resp.status_code == 200:
            return {"status": "created_previews", "data": resp.json()}
        return {
            "status": "free_tier_web_only",
            "http_status": resp.status_code,
            "web_prompt": voice_description,
            "sample_text": sample_text,
            "instructions": (
                "En el plan gratuito de ElevenLabs, crea la voz desde elevenlabs.io/app/voice-lab "
                "usando esta descripción y pega el Voice ID resultante en el panel."
            ),
        }
