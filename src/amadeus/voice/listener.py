from __future__ import annotations

import asyncio
from enum import Enum
import json
import math
import struct
import time
from typing import Any, Awaitable, Callable, List, Optional

from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor


class ListenerState(str, Enum):
    STOPPED = "stopped"
    IDLE_WAKE = "idle_wake"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class WakeWordWhisperListener:
    """
    Phase F2 (Palabra de Activación "Oye Kurisu" + VAD + Faster-Whisper Local):
    - Uses grammar-restricted Vosk (`["oye kurisu", "kurisu", "[unk]"]`) for ultra-low CPU wake detection.
    - Open-LLM-VTuber Anti-Self-Echo: raises energy threshold while Kurisu is speaking (`is_speaker_playing`),
      and triggers `on_interrupt()` immediately if the user says "Kurisu" over her speech.
    - Lazy-loads `faster-whisper` (`small`, CUDA `int8_float32` on GTX 1660 with CPU `int8` fallback)
      ONLY when speech is recorded, and unloads it after `whisper_idle_timeout_sec` (120s) to free VRAM/RAM.
    - Automatically stops listening when `PowerMode.BACKGROUND_ECO` is active.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        governor: ResourceGovernor,
        on_transcription: Optional[Callable[[str], Awaitable[None]]] = None,
        on_interrupt: Optional[Callable[[], Awaitable[None]]] = None,
        is_speaker_playing: Optional[Callable[[], bool]] = None,
        whisper_idle_timeout_sec: float = 120.0,
    ) -> None:
        self.settings = settings
        self.governor = governor
        self.on_transcription = on_transcription
        self.on_interrupt = on_interrupt
        self.is_speaker_playing = is_speaker_playing or (lambda: False)
        self.whisper_idle_timeout_sec = whisper_idle_timeout_sec

        self.state: ListenerState = ListenerState.STOPPED
        self.muted: bool = False
        self.is_ptt_recording: bool = False
        self._stop_ptt_flag: bool = False
        self._vosk_recognizer: Any = None
        self._whisper_model: Any = None
        self._last_whisper_use_ts: float = 0.0
        self._audio_buffer: bytearray = bytearray()
        self._silence_duration_sec: float = 0.0
        self._recording_duration_sec: float = 0.0

        self.governor.register_listener(self._on_power_mode_changed)

    def _on_power_mode_changed(self, mode: PowerMode) -> None:
        if mode == PowerMode.BACKGROUND_ECO:
            self.stop()
            self.unload_idle_models(force=True)

    def start(self) -> None:
        if not self.settings.wake_word_enabled or self.muted:
            self.state = ListenerState.STOPPED
            return
        self.state = ListenerState.IDLE_WAKE
        self._audio_buffer.clear()

    def stop(self) -> None:
        self.state = ListenerState.STOPPED
        self._audio_buffer.clear()

    @staticmethod
    def compute_rms_energy(pcm16_bytes: bytes) -> float:
        """Compute root-mean-square energy of 16-bit mono PCM audio frame."""
        if len(pcm16_bytes) < 2:
            return 0.0
        count = len(pcm16_bytes) // 2
        samples = struct.unpack(f"<{count}h", pcm16_bytes[: count * 2])
        mean_sq = sum(s * s for s in samples) / float(count)
        return math.sqrt(mean_sq)

    def check_wake_phrase(self, text_transcript: str) -> bool:
        norm = text_transcript.strip().lower()
        if not norm:
            return False
        wake = self.settings.wake_word_phrase.lower().strip()
        return wake in norm or "kurisu" in norm

    async def process_pcm_frame(
        self,
        pcm16_bytes: bytes,
        frame_duration_sec: float = 0.1,
        simulated_wake_text: Optional[str] = None,
    ) -> Optional[str]:
        """
        Process a 16kHz 16-bit mono PCM audio chunk through the state machine:
        IDLE_WAKE -> RECORDING -> TRANSCRIBING -> IDLE_WAKE.
        """
        if self.state == ListenerState.STOPPED or self.muted:
            return None

        rms = self.compute_rms_energy(pcm16_bytes)
        playing = self.is_speaker_playing()
        # Anti-self-echo: require higher voice energy when speaker is playing
        speech_energy_threshold = 950.0 if playing else 350.0

        if self.state == ListenerState.IDLE_WAKE:
            detected_text = simulated_wake_text or self._feed_vosk(pcm16_bytes)
            if detected_text and self.check_wake_phrase(detected_text):
                if playing and rms < speech_energy_threshold:
                    # Ignore low-energy speaker bleed
                    return None
                if playing and self.on_interrupt is not None:
                    await self.on_interrupt()
                self.state = ListenerState.RECORDING
                self._audio_buffer.clear()
                self._silence_duration_sec = 0.0
                self._recording_duration_sec = 0.0
            return None

        if self.state == ListenerState.RECORDING:
            self._audio_buffer.extend(pcm16_bytes)
            self._recording_duration_sec += frame_duration_sec
            if rms < speech_energy_threshold:
                self._silence_duration_sec += frame_duration_sec
            else:
                self._silence_duration_sec = 0.0

            # Finish recording after 1.2s of silence or max 30s duration
            if self._silence_duration_sec >= 1.2 or self._recording_duration_sec >= 30.0:
                self.state = ListenerState.TRANSCRIBING
                recorded = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                transcript = await self.transcribe_pcm_bytes(recorded)
                self.state = ListenerState.IDLE_WAKE
                if transcript and self.on_transcription is not None:
                    await self.on_transcription(transcript)
                return transcript

        return None

    def _feed_vosk(self, pcm16_bytes: bytes) -> str:
        if self._vosk_recognizer is None:
            return ""
        try:
            if self._vosk_recognizer.AcceptWaveform(pcm16_bytes):
                res = json.loads(self._vosk_recognizer.Result())
                return str(res.get("text") or "")
            partial = json.loads(self._vosk_recognizer.PartialResult())
            return str(partial.get("partial") or "")
        except Exception:
            return ""

    async def transcribe_pcm_bytes(self, pcm16_bytes: bytes) -> str:
        """Transcribe recorded 16kHz PCM16 audio via lazy-loaded faster-whisper."""
        if not pcm16_bytes:
            return ""
        self._last_whisper_use_ts = time.monotonic()
        if self._whisper_model is None:
            self._whisper_model = await asyncio.to_thread(self._load_whisper_model)
        if self._whisper_model is None:
            return ""

        def _run_transcribe() -> str:
            import numpy as np

            samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self._whisper_model.transcribe(
                samples, language="es", beam_size=2, vad_filter=True
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

        return await asyncio.to_thread(_run_transcribe)

    @staticmethod
    def _load_whisper_model() -> Any:
        try:
            from faster_whisper import WhisperModel

            try:
                return WhisperModel("small", device="cuda", compute_type="int8_float32")
            except Exception:
                return WhisperModel("small", device="cpu", compute_type="int8")
        except Exception:
            return None

    def stop_ptt_recording(self) -> None:
        """Signal an active Push-to-Talk microphone capture to finish immediately."""
        self._stop_ptt_flag = True

    async def record_and_transcribe_once(self, max_seconds: float = 9.0) -> str:
        """
        Capture microphone audio directly via `sounddevice` (16kHz 16-bit mono) with automatic
        voice activity & silence detection, then transcribe via Zero-Key Google Speech (`es-ES`)
        with local `faster-whisper` fallback. Costs 0 MB VRAM in default mode.
        """
        if self.is_ptt_recording:
            self._stop_ptt_flag = True
            return ""

        self.is_ptt_recording = True
        self._stop_ptt_flag = False

        def _capture_pcm() -> bytes:
            import sounddevice as sd

            sample_rate = 16000
            block_size = 1600  # 100ms per block
            buf = bytearray()
            spoke = False
            silence_blocks = 0
            max_blocks = int(max_seconds * 10)

            try:
                with sd.RawInputStream(
                    samplerate=sample_rate,
                    blocksize=block_size,
                    dtype="int16",
                    channels=1,
                ) as stream:
                    for idx in range(max_blocks):
                        if self._stop_ptt_flag:
                            break
                        data, _ = stream.read(block_size)
                        chunk = bytes(data)
                        buf.extend(chunk)
                        rms = self.compute_rms_energy(chunk)
                        if rms >= 240.0:
                            spoke = True
                            silence_blocks = 0
                        elif spoke:
                            silence_blocks += 1
                            # Stop automatically after 1.3s of silence once user finishes speaking
                            if silence_blocks >= 13:
                                break
                        elif idx >= 45 and not spoke:
                            # 4.5s of total silence with no speech
                            break
            except Exception:
                return b""
            return bytes(buf) if spoke or len(buf) > 6400 else b""

        try:
            pcm_bytes = await asyncio.to_thread(_capture_pcm)
        finally:
            self.is_ptt_recording = False
            self._stop_ptt_flag = False

        if not pcm_bytes:
            return ""

        # 1. Cloud STT via Google Speech (requires user consent per ECC AgentShield)
        if self.settings.cloud_stt_consent:
            def _google_stt() -> str:
                try:
                    import speech_recognition as sr

                    rec = sr.Recognizer()
                    audio_data = sr.AudioData(pcm_bytes, 16000, 2)
                    return str(rec.recognize_google(audio_data, language="es-ES")).strip()
                except Exception:
                    return ""

            text = await asyncio.to_thread(_google_stt)
            if text:
                return text

        # 2. Local offline STT via faster-whisper (private, no audio sent to cloud)
        return await self.transcribe_pcm_bytes(pcm_bytes)

    def unload_idle_models(self, force: bool = False) -> bool:
        """Unload faster-whisper from VRAM/RAM after idle timeout and trim Working Set."""
        if self._whisper_model is None:
            return False
        elapsed = time.monotonic() - self._last_whisper_use_ts
        if force or elapsed >= self.whisper_idle_timeout_sec:
            self._whisper_model = None
            self.governor.trim_working_set()
            return True
        return False
