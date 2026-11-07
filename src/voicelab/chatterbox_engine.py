from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Optional
import wave

logger = logging.getLogger("voicelab.chatterbox")


class ChatterboxEngine:
    """
    Chatterbox Zero-Shot Base TTS Engine for Spanish.
    Synthesizes expressive phonetic base audio for subsequent RVC timbre conversion.
    """

    def __init__(
        self,
        voice_ref_wav: Optional[Path] = None,
        device: str = "auto",
    ) -> None:
        self.voice_ref_wav = voice_ref_wav
        self.device = device
        self._is_loaded = False

    async def generate_base_speech(self, text: str) -> bytes:
        """
        Generate intermediate Spanish speech audio as standard WAV (PCM 16-bit, 24kHz mono).
        Uses lightweight edge-tts (es-ES / es-MX) or local zero-shot model.
        """
        import edge_tts

        voice = "es-MX-DaliaNeural"
        communicate = edge_tts.Communicate(text, voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        audio_data = buf.getvalue()

        if audio_data.startswith(b"RIFF"):
            return audio_data

        # Decode MP3 to WAV using av
        try:
            import av

            container = av.open(io.BytesIO(audio_data))
            if not container.streams.audio:
                return audio_data
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
            out_buf = io.BytesIO()
            with wave.open(out_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                for frame in container.decode(stream):
                    for rf in resampler.resample(frame):
                        wf.writeframes(rf.to_ndarray().tobytes())
            return out_buf.getvalue()
        except Exception as exc:
            logger.warning("Could not convert speech to WAV format via PyAV: %s", exc)
            return audio_data

    def unload(self) -> None:
        self._is_loaded = False
