from __future__ import annotations

from pathlib import Path
from typing import List
import pytest

from amadeus.body.agent_core import (
    AgentMessage,
    AmadeusAgentCore,
    AvatarEvent,
    EmotionState,
)
from amadeus.config import AmadeusSettings
from amadeus.house.environment_scanner import EnvironmentScanner
from amadeus.house.resource_governor import PowerMode, ResourceGovernor


def test_portable_settings_and_secret_masking(tmp_path: Path) -> None:
    """Verify settings save/load portably and mask secrets per ECC AgentShield rules."""
    settings = AmadeusSettings(
        active_brain="gemini",
        gemini_api_key="AIzaSySuperSecretKey12345",
        user_display_name="Okabe Rintaro",
    )
    saved_file = settings.save(tmp_path)
    assert saved_file.exists()

    loaded = AmadeusSettings.load(tmp_path)
    assert loaded.active_brain == "gemini"
    assert loaded.user_display_name == "Okabe Rintaro"
    assert loaded.gemini_api_key == "AIzaSySuperSecretKey12345"

    masked = loaded.masked_summary()
    assert "SuperSecret" not in masked["gemini_api_key"]
    assert masked["gemini_api_key"] == "AIz***345"
    assert masked["anthropic_api_key"] == "(not configured)"


def test_environment_scanner_auto_discovery() -> None:
    """Verify Module 1 EnvironmentScanner detects host capabilities without hardcoded paths."""
    profile = EnvironmentScanner.scan()
    assert profile.cpu_cores_logical >= 1
    assert profile.total_ram_gb > 0
    assert profile.os_name != ""
    assert profile.appdata_dir != ""


def test_resource_governor_mode_transitions_and_ram_trim() -> None:
    """Verify Module 1 ResourceGovernor switches modes, trims working set, and notifies listeners."""
    gov = ResourceGovernor(initial_mode=PowerMode.BACKGROUND_ECO)
    assert gov.mode == PowerMode.BACKGROUND_ECO
    assert gov.recommended_llm_tier == "eco"
    assert gov.polling_interval_sec > 2.0

    notified_modes: List[PowerMode] = []
    gov.register_listener(lambda mode: notified_modes.append(mode))

    snap_fg = gov.switch_mode(PowerMode.FOREGROUND_ACTIVE)
    assert snap_fg.power_mode == PowerMode.FOREGROUND_ACTIVE
    assert snap_fg.llm_tier == "full"
    assert snap_fg.polling_interval_sec < 1.0
    assert notified_modes == [PowerMode.FOREGROUND_ACTIVE]

    snap_bg = gov.switch_mode(PowerMode.BACKGROUND_ECO)
    assert snap_bg.power_mode == PowerMode.BACKGROUND_ECO
    assert snap_bg.process_rss_mb < 120.0  # Lightweight RSS check


@pytest.mark.asyncio
async def test_house_and_body_connection_and_vroid_hooks() -> None:
    """Verify Module 1 <-> Module 2 connection, history pruning in Eco mode, and VRoid avatar events."""
    gov = ResourceGovernor(initial_mode=PowerMode.FOREGROUND_ACTIVE)
    core = AmadeusAgentCore(governor=gov, max_session_history=20)

    avatar_events: List[AvatarEvent] = []

    async def on_avatar_event(ev: AvatarEvent) -> None:
        avatar_events.append(ev)

    core.subscribe_avatar(on_avatar_event)

    # Send normal messages to populate history
    for i in range(8):
        msg = AgentMessage(role="user", content=f"Mensaje de prueba {i}")
        reply = await core.process_user_message(msg)
        assert reply.role == "assistant"

    assert len(core.history) == 16  # 8 user + 8 assistant
    assert len(avatar_events) == 8
    assert avatar_events[-1].emotion == EmotionState.TSUNDERE_BLUSH

    # Test built-in slash command /eco which bridges Module 2 -> Module 1 -> Module 2 listener
    eco_reply = await core.process_user_message(
        AgentMessage(role="user", content="/eco")
    )
    assert "Modo Eco activado" in eco_reply.content
    assert gov.mode == PowerMode.BACKGROUND_ECO
    # Listener pruned history to 10 before appending the 2 command messages -> 12 total
    assert len(core.history) <= 12
