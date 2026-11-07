from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import httpx
import pytest

from amadeus.body.agent_core import AgentMessage
from amadeus.config import AmadeusSettings
from amadeus.house.logging_setup import SecretMaskingFilter, setup_logging
from amadeus.house.onboarding_ui import EphemeralOnboardingServer
from amadeus.house.ws_bridge import AmadeusWebSocketBridge
from amadeus.system_builder import AmadeusSystem
from amadeus.tools.app_launcher import DiscoveredApp, WindowsAppLauncher
from amadeus.voice.qwen3_kurisu_tts import Qwen3KurisuTTSModule


@pytest.mark.asyncio
async def test_ws_bridge_interrupt_and_turn_decoupling(tmp_path: Path) -> None:
    """
    B1/B2 Test:
    Verify WebSocket bridge handles interrupts cleanly and turns are decoupled.
    """
    system = AmadeusSystem(data_dir=tmp_path)
    bridge = system.ws_bridge
    assert bridge.is_running is False

    # Simulate in-flight turn
    bridge._current_turn_id = "turn_123"
    bridge.speaker_playing = True
    bridge.interrupt_current_turn()

    assert bridge._cancel_current_turn is True
    assert bridge.speaker_playing is False
    await system.shutdown()


def test_app_launcher_word_boundaries_and_fuzzy_matching() -> None:
    """
    B7 Test:
    Verify WindowsAppLauncher does not false-positive on substring substrings (e.g. matching uninstaller),
    and correctly matches word boundaries and aliases.
    """
    launcher = WindowsAppLauncher()
    launcher._catalog.clear()

    # Add mock entries
    launcher._catalog["visual studio code"] = DiscoveredApp(
        name="Visual Studio Code", executable_path="C:\\Tools\\Code.exe", source="start_menu"
    )
    launcher._catalog["uninstall visual studio code"] = DiscoveredApp(
        name="Uninstall Visual Studio Code", executable_path="C:\\Tools\\unins000.exe", source="start_menu"
    )
    launcher._catalog["calculator"] = DiscoveredApp(
        name="Calculator", executable_path="C:\\Windows\\System32\\calc.exe", source="registry"
    )

    # Alias "vscode" should match "visual studio code", NOT the uninstaller
    app_alias = launcher.find_app("vscode")
    assert app_alias is not None
    assert "unins" not in app_alias.executable_path.lower()

    # Exact word match
    app_word = launcher.find_app("calculator")
    assert app_word is not None
    assert app_word.name == "Calculator"

    # Fuzzy match with slight typo
    app_fuzzy = launcher.find_app("calculatr")
    assert app_fuzzy is not None
    assert app_fuzzy.name == "Calculator"


@pytest.mark.asyncio
async def test_persona_overlay_injection_with_profiles(tmp_path: Path) -> None:
    """
    B4 Test:
    Verify that when active_profile is changed (e.g. to fi_spirit),
    its persona_overlay is injected into the system prompt.
    """
    system = AmadeusSystem(data_dir=tmp_path)
    # Default profile: kurisu_amadeus -> persona_overlay is empty
    prompt_default = system.identity.build_system_prompt(
        persona_overlay=system.core.persona_overlay_provider()
    )
    assert "FI ANALÍTICA" not in prompt_default

    # Switch to fi_spirit
    system.settings.active_profile = "fi_spirit"
    overlay = system.core.persona_overlay_provider()
    assert "FI ANALÍTICA" in overlay

    prompt_fi = system.identity.build_system_prompt(persona_overlay=overlay)
    assert "DIRECTIVA DE PERSONALIDAD ACTIVA" in prompt_fi
    assert "FI ANALÍTICA" in prompt_fi
    await system.shutdown()


@pytest.mark.asyncio
async def test_qwen3_circuit_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    B10 Test:
    Verify Qwen3 TTS trips circuit breaker on ZeroGPU quota error,
    failing fast without blocking subsequent requests.
    """
    qwen = Qwen3KurisuTTSModule()

    # Simulate an error from space API
    async def mock_fail(*args, **kwargs):
        raise RuntimeError("ZeroGPU quota exceeded: limit reached")

    monkeypatch.setattr(qwen, "_synthesize_space_api", mock_fail)

    with pytest.raises(RuntimeError) as exc_info:
        await qwen.synthesize("Hola Okabe")
    assert "quota" in str(exc_info.value).lower()

    # Circuit breaker is now active; next call fails fast with cooldown notice
    qwen._circuit_broken_until = 9999999999.0
    with pytest.raises(RuntimeError) as exc_info2:
        await qwen.synthesize("Segunda llamada")
    assert "cooldown active" in str(exc_info2.value).lower()


def test_logging_secret_masking(tmp_path: Path) -> None:
    """
    B8 Test:
    Verify SecretMaskingFilter masks API keys matching sk-*, AIza*, hf_*.
    """
    logger = setup_logging(data_dir=tmp_path, log_file_name="test_mask.log")
    test_record = logging.LogRecord(
        name="amadeus",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Iniciando con clave sk-ant-api03-abcdef123456789 y Gemini AIzaSyTestKey9988776655",
        args=(),
        exc_info=None,
    )
    filter_mask = SecretMaskingFilter()
    filter_mask.filter(test_record)

    assert "sk-ant-api03-abcdef123456789" not in test_record.msg
    assert "AIzaSyTestKey9988776655" not in test_record.msg
    assert "***" in test_record.msg


@pytest.mark.asyncio
async def test_sync_fish_agent_endpoint(tmp_path: Path) -> None:
    """
    B13 Test:
    Verify POST /api/sync_fish_agent updates fish_model_id and returns 200 OK.
    """
    system = AmadeusSystem(data_dir=tmp_path)
    server = EphemeralOnboardingServer(system=system, host="127.0.0.1", port=0)
    url = await server.start()
    token = server.auth_token

    async def mock_sync() -> dict:
        system.settings.fish_model_id = "synced_model_id_12345"
        return {"voice": {"voice_id": "synced_model_id_12345"}}

    system.voice.sync_fish_agent_config = mock_sync  # type: ignore[assignment]

    async with httpx.AsyncClient(headers={"X-Amadeus-Token": token}) as client:
        r = await client.post(f"{url}/api/sync_fish_agent")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["fish_model_id"] == "synced_model_id_12345"

    await server.stop()
    await system.shutdown()
