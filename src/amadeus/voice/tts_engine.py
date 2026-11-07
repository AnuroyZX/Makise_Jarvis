from __future__ import annotations

import base64
from dataclasses import dataclass
import io
from pathlib import Path
from typing import Optional
import wave
import httpx

from amadeus.config import AmadeusSettings, get_default_data_dir
from amadeus.voice.qwen3_kurisu_tts import Qwen3KurisuTTSModule


@dataclass(slots=True)
class VoiceSynthesisResult:
    audio_bytes: bytes
    provider: str  # "qwen3_kurisu" | "fish_audio" | "gemini_kurisu" | "elevenlabs" | "edge_tts" | "disabled"
    mime_type: str  # "audio/ogg" | "audio/mpeg" | "audio/wav"
    saved_path: Optional[Path] = None


class AmadeusVoiceEngine:
    """
    Module 9 (Voz):
    Synthesizes Makise Kurisu's voice with a 4-tier cascade:
      1. Fish Audio (`8750a78673b44b568c08e23eebcea67e` — 牧濑红莉栖 / Makise Kurisu) when `fish_audio_api_key` is set.
      2. Gemini 2.5 Flash TTS (`Leda` + Makise Kurisu / Asami Imai acoustic profile) when `voice_engine == "gemini_kurisu"`.
      3. ElevenLabs (`eleven_multilingual_v2`) when within Credit Guard character budget.
      4. Microsoft Edge-TTS (free fallback with young anime pitch/rate tuning).
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
        self.qwen3 = Qwen3KurisuTTSModule(
            speaker=settings.qwen3_speaker,
            http_client=http_client,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(22.0, connect=6.0))
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

        engine = (self.settings.voice_engine or "auto").lower()

        # 0. Independent Qwen3-TTS Makise Kurisu Module (`starrydark/Makise_Kurisu_Qwen3_TTS`)
        if engine == "qwen3_kurisu" and not for_telegram_opus:
            try:
                q_out = await self.qwen3.synthesize(
                    clean_text, speaker=self.settings.qwen3_speaker
                )
                if q_out.audio_bytes:
                    saved = self._save_audio(q_out.audio_bytes, ".wav") if save_to_disk else None
                    return VoiceSynthesisResult(
                        audio_bytes=q_out.audio_bytes,
                        provider="qwen3_kurisu",
                        mime_type=q_out.mime_type,
                        saved_path=saved,
                    )
            except Exception:
                # If Space is busy/offline, fall back gracefully to Gemini Kurisu TTS
                if self.settings.gemini_api_key:
                    try:
                        audio_bytes, mime = await self._call_gemini_kurisu_tts(clean_text)
                        saved = self._save_audio(audio_bytes, ".wav") if save_to_disk else None
                        return VoiceSynthesisResult(
                            audio_bytes=audio_bytes,
                            provider="gemini_kurisu",
                            mime_type=mime,
                            saved_path=saved,
                        )
                    except Exception:
                        pass

        # 1. Fish Audio (Model 8750a78673b44b568c08e23eebcea67e — Makise Kurisu)
        if engine in ("auto", "fish") and self.settings.fish_audio_api_key:
            try:
                audio_bytes, mime = await self._call_fish_audio(clean_text)
                saved = self._save_audio(audio_bytes, ".mp3") if save_to_disk else None
                return VoiceSynthesisResult(
                    audio_bytes=audio_bytes,
                    provider="fish_audio",
                    mime_type=mime,
                    saved_path=saved,
                )
            except Exception:
                pass

        # 2. Gemini 2.5 Flash TTS ('Leda' with Makise Kurisu / Asami Imai acoustic profile)
        if engine == "gemini_kurisu" and self.settings.gemini_api_key and not for_telegram_opus:
            try:
                audio_bytes, mime = await self._call_gemini_kurisu_tts(clean_text)
                saved = self._save_audio(audio_bytes, ".wav") if save_to_disk else None
                return VoiceSynthesisResult(
                    audio_bytes=audio_bytes,
                    provider="gemini_kurisu",
                    mime_type=mime,
                    saved_path=saved,
                )
            except Exception:
                pass

        # 3. ElevenLabs if Credit Guard allows it
        if engine in ("auto", "elevenlabs") and self.should_use_elevenlabs(clean_text):
            try:
                audio_bytes, mime = await self._call_elevenlabs(
                    clean_text, for_telegram_opus=for_telegram_opus
                )
                saved = (
                    self._save_audio(audio_bytes, ".ogg" if for_telegram_opus else ".mp3")
                    if save_to_disk
                    else None
                )
                return VoiceSynthesisResult(
                    audio_bytes=audio_bytes,
                    provider="elevenlabs",
                    mime_type=mime,
                    saved_path=saved,
                )
            except Exception:
                pass

        # 4. Fallback to free Edge-TTS with young pitch tuning
        audio_bytes = await self._call_edge_tts(clean_text)
        saved = self._save_audio(audio_bytes, ".mp3") if save_to_disk else None
        return VoiceSynthesisResult(
            audio_bytes=audio_bytes,
            provider="edge_tts",
            mime_type="audio/mpeg",
            saved_path=saved,
        )

    async def _call_fish_audio(self, text: str) -> tuple[bytes, str]:
        """
        Calls Fish Audio TTS (`https://api.fish.audio/v1/tts`) using either:
        1. An uploaded KikiVoice reference audio (`kikivoice_ref.mp3`) for zero-shot cloning, or
        2. Makise Kurisu's trained model ID (`8750a78673b44b568c08e23eebcea67e`).
        """
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.settings.fish_audio_api_key}",
            "Content-Type": "application/json",
            "model": "s1",
        }
        kiki_ref = self.cache_dir.parent / "kikivoice_ref.mp3"
        payload: dict = {
            "text": text,
            "format": "mp3",
            "mp3_bitrate": 128,
            "latency": "balanced",
        }
        if kiki_ref.exists() and not self.settings.fish_model_id:
            payload["references"] = [
                {
                    "audio": base64.b64encode(kiki_ref.read_bytes()).decode("ascii"),
                    "text": "",
                }
            ]
        else:
            payload["reference_id"] = (
                self.settings.fish_model_id or "8750a78673b44b568c08e23eebcea67e"
            )
        resp = await client.post("https://api.fish.audio/v1/tts", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.content, "audio/mpeg"

    async def _call_gemini_kurisu_tts(self, text: str) -> tuple[bytes, str]:
        """
        Uses Gemini 2.5 Flash Preview TTS (`Leda` voice) directed to imitate the young,
        calm, smooth, slightly breathy Japanese anime voice of Makise Kurisu (`8750a78673b44b568c08e23eebcea67e`).
        """
        client = await self._get_client()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash-preview-tts:generateContent?key={self.settings.gemini_api_key}"
        )
        style_prompt = (
            "Speak in a young 18-year-old Japanese anime female voice actress tone "
            "(like Makise Kurisu / Asami Imai: calm, smooth, slightly breathy, intelligent, "
            f"youthful, speaking natural Spanish): {text}"
        )
        payload = {
            "contents": [{"parts": [{"text": style_prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": self.settings.gemini_tts_voice or "Leda"
                        }
                    }
                },
            },
        }
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        inline = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm_bytes = base64.b64decode(inline["data"])

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_bytes)
        return buf.getvalue(), "audio/wav"

    async def _call_elevenlabs(
        self, text: str, for_telegram_opus: bool = False
    ) -> tuple[bytes, str]:
        client = await self._get_client()
        output_fmt = "opus_48000_64" if for_telegram_opus else "mp3_44100_128"
        voice_id = self.settings.elevenlabs_voice_id
        if voice_id == "EXAVITQu4vr4xnSDxMaL":
            voice_id = "cgSgspJ2msm6clMCkdW9"
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{voice_id}?output_format={output_fmt}"
        )
        headers = {
            "xi-api-key": self.settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.settings.elevenlabs_model_id,
            "voice_settings": {
                "stability": 0.50,
                "similarity_boost": 0.80,
                "style": 0.30,
                "use_speaker_boost": True,
            },
        }
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        mime = "audio/ogg" if for_telegram_opus else "audio/mpeg"
        return resp.content, mime

    async def _call_edge_tts(self, text: str) -> bytes:
        """Lazy-import edge_tts per ECC Resource Efficiency Rule 1, with young anime pitch."""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text=text,
                voice=self.settings.edge_tts_voice,
                rate="+6%",
                pitch="+10Hz",
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
            "fish_model_id": self.settings.fish_model_id,
        }
