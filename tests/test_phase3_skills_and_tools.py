from __future__ import annotations

import asyncio
from pathlib import Path
import httpx
import pytest

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.identity.soul_manager import SoulManager
from amadeus.skills.skill_loader import SkillRegistry
from amadeus.tools.app_launcher import WindowsAppLauncher
from amadeus.tools.browser_tool import EphemeralBrowserTool
from amadeus.tools.mail_calendar import MailCalendarTool
from amadeus.tools.tool_registry import AmadeusToolkit


def test_progressive_disclosure_skills_loader() -> None:
    """Verify Module 6 loads skill metadata lightly and only expands matching SKILL.md."""
    registry = SkillRegistry()
    assert "morning_briefing" in registry.skills
    assert "focus_pomodoro" in registry.skills
    assert "pc_cleanup_status" in registry.skills
    assert "quick_research" in registry.skills

    # Query unrelated to any skill -> only catalog is returned, no full SKILL ACTIVA block
    ctx_idle = registry.build_progressive_context("Hola Kurisu, ¿qué tal estás?")
    assert "Catálogo de Habilidades" in ctx_idle
    assert "[SKILL ACTIVA:" not in ctx_idle

    # Query matching morning_briefing trigger -> full SKILL.md injected progressively
    ctx_active = registry.build_progressive_context("Buenos días Kurisu, dame mi resumen del día")
    assert "[SKILL ACTIVA: morning_briefing]" in ctx_active
    assert "Agenda Cronológica" in ctx_active


def test_windows_app_launcher_auto_discovery_and_dry_run() -> None:
    """Verify Module 7 auto-discovers Windows apps without hardcoded user paths."""
    launcher = WindowsAppLauncher()
    assert len(launcher.catalog) > 0

    # Notepad / terminal / explorer are universally present on Windows
    found = (
        launcher.find_app("notepad")
        or launcher.find_app("explorer")
        or launcher.find_app("terminal")
    )
    assert found is not None
    res = launcher.launch(found.name, dry_run=True)
    assert "[Dry-Run]" in res


@pytest.mark.asyncio
async def test_ephemeral_browser_clean_fetch_and_auto_kill_watchdog() -> None:
    """Verify Module 7 Browser Level 1 (<untrusted_data>) and Level 2 idle watchdog."""
    def mock_web(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><head><script>evil()</script></head><body><h1>Steins;Gate Lab</h1><p>Divergence 1.048596%</p></body></html>",
        )

    gov = ResourceGovernor(initial_mode=PowerMode.FOREGROUND_ACTIVE)
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_web)) as client:
        browser = EphemeralBrowserTool(
            governor=gov, idle_timeout_sec=0.05, http_client=client
        )
        page_text = await browser.fetch_clean_page("https://futuregadgetlab.org")
        assert "<untrusted_data" in page_text
        assert "Steins;Gate Lab" in page_text
        assert "evil()" not in page_text

        # Simulate an ephemeral browser process via a dummy mock object
        class DummyProc:
            def __init__(self) -> None:
                self.terminated = False

            def poll(self):
                return None if not self.terminated else 0

            def terminate(self) -> None:
                self.terminated = True

        dummy = DummyProc()
        browser.attach_ephemeral_process(dummy)  # type: ignore[arg-type]
        await asyncio.sleep(0.12)
        assert dummy.terminated is True


@pytest.mark.asyncio
async def test_phase3_connection_with_body_and_identity(tmp_path: Path) -> None:
    """Verify Modules 6 & 7 connect cleanly with Modules 1, 2, and 4."""
    settings = AmadeusSettings()
    gov = ResourceGovernor(initial_mode=PowerMode.FOREGROUND_ACTIVE)
    soul = SoulManager(data_dir=tmp_path)
    skills = SkillRegistry()
    mail_cal = MailCalendarTool(settings=settings, data_dir=tmp_path)
    toolkit = AmadeusToolkit(
        settings=settings, governor=gov, mail_calendar=mail_cal
    )

    core = AmadeusAgentCore(governor=gov, identity=soul, skills=skills)
    toolkit.bind_commands(core)

    # Test /event and /agenda commands with <untrusted_data> protection
    ev_reply = await core.process_user_message(
        AgentMessage(role="user", content="/event 2026-11-07 09:00 | Experimento D-Mail")
    )
    assert "Experimento D-Mail" in ev_reply.content

    ag_reply = await core.process_user_message(
        AgentMessage(role="user", content="/agenda")
    )
    assert "<untrusted_data source=\"calendar\">" in ag_reply.content
    assert "Experimento D-Mail" in ag_reply.content
