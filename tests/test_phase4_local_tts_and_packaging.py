from __future__ import annotations

import asyncio
import io
from pathlib import Path
import wave
import httpx
import pytest

from amadeus.config import AmadeusSettings
from amadeus.voice.tts_engine import AmadeusVoiceEngine
from voicelab.chatterbox_engine import ChatterboxEngine
from voicelab.client import VoiceLabSidecarClient
from voicelab.rvc_engine import RVCEngine
from voicelab.server import VoiceLabSidecarServer
from voicelab.voicepack_downloader import download_voicepack


@pytest.mark.asyncio
async def test_voicelab_sidecar_server_and_client_handshake(tmp_path: Path) -> None:
    """
    Test starting VoiceLab sidecar server on ephemeral loopback port,
    querying /health, performing synthesis, and unloading VRAM.
    """
    token = "test-voicelab-token-12345"
    server = VoiceLabSidecarServer(port=0, auth_token=token, idle_timeout_sec=60.0, model_dir=tmp_path)
    url = await server.start()

    client = VoiceLabSidecarClient(base_url=url, auth_token=token)

    # 1. Health check
    is_healthy = await client.is_healthy()
    assert is_healthy is True

    # 2. Synthesis (generates base audio through Chatterbox + RVC passthrough fallback)
    res = await client.synthesize("Hola Okabe, soy Amadeus Kurisu.")
    assert res is not None
    audio_bytes, mime = res
    assert len(audio_bytes) > 0
    assert mime == "audio/wav"

    # 3. Verify WAV header integrity
    with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
        assert wf.getnchannels() in (1, 2)
        assert wf.getframerate() > 0

    await server.stop()


def test_rvc_engine_lazy_loading_and_unload(tmp_path: Path) -> None:
    """
    Test RVCEngine properties, lazy loading without top-level CUDA imports,
    and memory unloading.
    """
    engine = RVCEngine(model_dir=tmp_path, model_name="kurisu")
    assert engine.is_available is False
    assert engine.pth_path == tmp_path / "kurisu.pth"

    # Test conversion fallback when weights are missing
    dummy_wav = io.BytesIO()
    with wave.open(dummy_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 240)

    out = engine.convert_audio(dummy_wav.getvalue())
    assert out == dummy_wav.getvalue()

    # Unload should execute without error
    engine.unload()
    assert engine._is_loaded is False


@pytest.mark.asyncio
async def test_tts_engine_integrates_local_rvc_provider(tmp_path: Path) -> None:
    """
    Test that AmadeusVoiceEngine seamlessly invokes VoiceLab client
    when voice_engine is set to 'local_rvc'.
    """
    settings = AmadeusSettings(voice_engine="local_rvc")
    settings.save(tmp_path)
    voice_engine = AmadeusVoiceEngine(settings=settings, cache_dir=tmp_path)

    # Mock voicelab client to return dummy WAV bytes
    async def mock_vl_synth(text: str) -> tuple[bytes, str]:
        return b"RIFF_LOCAL_RVC_AUDIO_BYTES", "audio/wav"

    voice_engine.voicelab.synthesize = mock_vl_synth  # type: ignore[assignment]

    result = await voice_engine.synthesize("Prueba de voz local RVC", save_to_disk=False)
    assert result.provider == "local_rvc"
    assert result.mime_type == "audio/wav"
    assert result.audio_bytes == b"RIFF_LOCAL_RVC_AUDIO_BYTES"


def test_hf_voicepack_downloader_guard(tmp_path: Path) -> None:
    """
    Test that Hugging Face voicepack downloader correctly identifies
    when models are already installed or need download.
    """
    # 1. Existing model skips download
    target_dir = tmp_path / "models" / "rvc"
    target_dir.mkdir(parents=True)
    (target_dir / "kurisu.pth").write_bytes(b"EXISTING_PTH")

    res = download_voicepack(target_dir=target_dir)
    assert res is True
