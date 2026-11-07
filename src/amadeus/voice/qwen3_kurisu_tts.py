from __future__ import annotations

from dataclasses import dataclass
import io
import json
import re
from typing import Literal, Optional
import wave
import httpx

Qwen3KurisuSpeaker = Literal["kurisu", "amadeus", "phone"]
Qwen3KurisuLanguage = Literal["Auto", "Detect", "Japanese", "Chinese", "English"]

MAX_QWEN3_CHARS = 195
DEFAULT_HF_REPO = "starrydark/Makise_Kurisu_Qwen3_TTS"
DEFAULT_SPACE_URL = "https://starrydark-kurisu-qwen3-tts.hf.space"


@dataclass(slots=True)
class Qwen3SynthesisOutput:
    audio_bytes: bytes
    mime_type: str
    speaker: str
    language: str
    backend: str  # "space_api" | "local_checkpoint"


class Qwen3KurisuTTSModule:
    """
    Independent Module for `starrydark/Makise_Kurisu_Qwen3_TTS` (Qwen3-TTS 1.7B v3):
    Supports Makise Kurisu's authentic trained voice across 3 recording personas:
      - `kurisu`: Studio default voice of Makise Kurisu
      - `amadeus`: The Amadeus AI device voice from STEINS;GATE 0
      - `phone`: Phone call EQ voice

    Operates in two modes:
      1. `space_api` (default, 0 MB local VRAM): Calls the official ZeroGPU Gradio Space
         (`https://starrydark-kurisu-qwen3-tts.hf.space/gradio_api/call/generate_speech`).
      2. `local_checkpoint`: Lazy-loads `qwen_tts.Qwen3TTSModel` locally when installed.
    """

    def __init__(
        self,
        speaker: str = "amadeus",
        language: str = "Auto",
        space_url: str = DEFAULT_SPACE_URL,
        model_id: str = DEFAULT_HF_REPO,
        use_local_checkpoint: bool = False,
        hf_token: str = "",
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.speaker: str = speaker if speaker in ("kurisu", "amadeus", "phone") else "amadeus"
        self.language: str = language
        self.space_url = space_url.rstrip("/")
        self.model_id = model_id
        self.use_local_checkpoint = use_local_checkpoint
        self.hf_token = hf_token.strip()
        self._external_client = http_client is not None
        self._client = http_client
        self._local_model = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._external_client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalizes text per `starrydark/Makise_Kurisu_Qwen3_TTS` rules:
        - Strips markdown symbols that shouldn't be spoken
        - Removes spaces adjacent to expressive tags (`[sigh]`, `[nv]`)
        - Truncates cleanly at `MAX_QWEN3_CHARS` (200 char limit on the v3 checkpoint)
        """
        cleaned = re.sub(r"[*_`#~]+", "", text).strip()
        cleaned = re.sub(r"\s*(\[[a-z_]+\])\s*", r"\1", cleaned)
        if len(cleaned) <= MAX_QWEN3_CHARS:
            return cleaned
        # Cut at last punctuation or space within 195 chars
        cut = cleaned[:MAX_QWEN3_CHARS]
        last_space = cut.rfind(" ")
        if last_space > 80:
            return cut[:last_space].strip()
        return cut.strip()

    async def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Qwen3SynthesisOutput:
        norm_text = self.normalize_text(text)
        if not norm_text:
            return Qwen3SynthesisOutput(
                audio_bytes=b"",
                mime_type="audio/wav",
                speaker=self.speaker,
                language=self.language,
                backend="none",
            )

        active_speaker = (speaker or self.speaker).lower().strip()
        if active_speaker not in ("kurisu", "amadeus", "phone"):
            active_speaker = "amadeus"
        active_lang = language or self.language or "Auto"

        if self.use_local_checkpoint:
            wav_bytes = await self._synthesize_local(norm_text, active_speaker, active_lang)
            return Qwen3SynthesisOutput(
                audio_bytes=wav_bytes,
                mime_type="audio/wav",
                speaker=active_speaker,
                language=active_lang,
                backend="local_checkpoint",
            )

        wav_bytes = await self._synthesize_space_api(norm_text, active_speaker, active_lang)
        return Qwen3SynthesisOutput(
            audio_bytes=wav_bytes,
            mime_type="audio/wav",
            speaker=active_speaker,
            language=active_lang,
            backend="space_api",
        )

    async def _synthesize_space_api(
        self, text: str, speaker: str, language: str
    ) -> bytes:
        """
        Calls `starrydark/Kurisu_Qwen3_TTS` Space via `gradio_client` (which handles
        HuggingFace ZeroGPU `X-IP-Token` headers and optional `hf_token`), or pure async
        `httpx` when an external mock transport client is injected.
        """
        if not self._external_client:
            import asyncio
            from pathlib import Path

            def _call_gradio_space() -> bytes:
                from gradio_client import Client

                kwargs = {"token": self.hf_token} if self.hf_token else {}
                g_client = Client("starrydark/Kurisu_Qwen3_TTS", **kwargs)
                res = g_client.predict(
                    text,
                    speaker,
                    language,
                    api_name="/generate_speech",
                )
                wav_path = res[0] if isinstance(res, (list, tuple)) else res
                if isinstance(wav_path, dict) and wav_path.get("path"):
                    wav_path = wav_path["path"]
                p = Path(str(wav_path))
                if p.is_file():
                    return p.read_bytes()
                raise RuntimeError("Qwen3-TTS Space did not return a local audio file.")

            return await asyncio.to_thread(_call_gradio_space)

        client = await self._get_client()
        call_url = f"{self.space_url}/gradio_api/call/generate_speech"
        resp = await client.post(
            call_url,
            json={"data": [text, speaker, language]},
        )
        resp.raise_for_status()
        event_id = resp.json().get("event_id")
        if not event_id:
            raise RuntimeError("Qwen3-TTS Space did not return an event_id.")

        stream_url = f"{call_url}/{event_id}"
        wav_url: Optional[str] = None
        async with client.stream("GET", stream_url) as sse:
            sse.raise_for_status()
            async for line in sse.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw_json = line[6:].strip()
                if raw_json == "null":
                    continue
                payload = json.loads(raw_json)
                if (
                    isinstance(payload, list)
                    and payload
                    and isinstance(payload[0], dict)
                    and payload[0].get("url")
                ):
                    wav_url = str(payload[0]["url"])
                    break

        if not wav_url:
            raise RuntimeError("Qwen3-TTS Space stream finished without audio URL.")

        audio_resp = await client.get(wav_url)
        audio_resp.raise_for_status()
        return audio_resp.content

    async def _synthesize_local(
        self, text: str, speaker: str, language: str
    ) -> bytes:
        """
        Lazy-loads `qwen_tts.Qwen3TTSModel` locally per ECC Resource Efficiency Rule 1.
        Requires `pip install qwen-tts soundfile torch`.
        """
        import asyncio

        def _run_sync() -> bytes:
            import numpy as np
            import torch
            from qwen_tts import Qwen3TTSModel

            if self._local_model is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                dtype = torch.bfloat16 if device == "cuda" else torch.float32
                self._local_model = Qwen3TTSModel.from_pretrained(
                    self.model_id,
                    device_map=device,
                    dtype=dtype,
                )
            wavs, sr = self._local_model.generate_custom_voice(
                text=text,
                speaker=speaker,
                language=language if language != "Detect" else "Auto",
            )
            samples = np.asarray(wavs[0], dtype=np.float32)
            pcm16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(int(sr))
                wf.writeframes(pcm16.tobytes())
            return buf.getvalue()

        return await asyncio.to_thread(_run_sync)
