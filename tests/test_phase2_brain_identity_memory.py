from __future__ import annotations

from pathlib import Path
import httpx
import pytest

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore, EmotionState
from amadeus.brain.router import MultiBrainRouter
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.identity.soul_manager import SoulManager
from amadeus.memory.hybrid_memory import HybridMemoryManager


@pytest.mark.asyncio
async def test_multi_brain_smart_routing_and_commands() -> None:
    """Verify Module 3 Smart Routing (Eco vs Full) and /brain runtime switching."""
    settings = AmadeusSettings(
        active_brain="auto",
        gemini_api_key="test-gemini-key",
        anthropic_api_key="test-claude-key",
        openai_api_key="test-openai-key",
    )
    gov = ResourceGovernor(initial_mode=PowerMode.BACKGROUND_ECO)
    router = MultiBrainRouter(settings=settings, governor=gov)
    core = AmadeusAgentCore(governor=gov, brain=router)
    router.bind_commands(core)

    # In BACKGROUND_ECO with 'auto', Smart Router must pick Gemini Flash (eco)
    prov_eco, mod_eco = router.select_provider_and_model(gov.mode)
    assert prov_eco == "gemini"
    assert "flash" in mod_eco

    # In FOREGROUND_ACTIVE with 'auto', Smart Router must pick Claude Sonnet (flagship)
    gov.switch_mode(PowerMode.FOREGROUND_ACTIVE)
    prov_fg, mod_fg = router.select_provider_and_model(gov.mode)
    assert prov_fg == "claude"
    assert "sonnet" in mod_fg

    # Test /brain codex command via Module 2 (Body)
    cmd_reply = await core.process_user_message(
        AgentMessage(role="user", content="/brain codex")
    )
    assert "codex" in cmd_reply.content
    assert settings.active_brain == "codex"
    prov_manual, _ = router.select_provider_and_model(gov.mode)
    assert prov_manual == "codex"


@pytest.mark.asyncio
async def test_soul_and_user_md_persistence(tmp_path: Path) -> None:
    """Verify Module 4 creates USER.md, injects SOUL.md, and handles /remember."""
    gov = ResourceGovernor()
    soul = SoulManager(data_dir=tmp_path, user_display_name="Rintaro")
    core = AmadeusAgentCore(governor=gov, identity=soul)
    soul.bind_commands(core)

    assert (tmp_path / "USER.md").exists()
    profile_text = soul.read_user_profile()
    assert "Rintaro" in profile_text

    # Test /remember command
    rem_reply = await core.process_user_message(
        AgentMessage(role="user", content="/remember Prefiero tomar Dr Pepper frío al programar")
    )
    assert "Dr Pepper" in rem_reply.content
    assert "Dr Pepper" in soul.read_user_profile()

    prompt = soul.build_system_prompt(
        memory_context="El usuario trabaja en el FG Lab", urgent_mode=True
    )
    assert "Amadeus Kurisu" in prompt
    assert "Dr Pepper" in prompt
    assert "FG Lab" in prompt
    assert "MODO EJECUTIVO / URGENTE" in prompt


@pytest.mark.asyncio
async def test_hybrid_memory_honcho_and_sqlite_fts5_integration(tmp_path: Path) -> None:
    """Verify Module 5 (Honcho Cloud + SQLite FTS5) and full connection with Modules 1, 2, 3, 4."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "honcho.dev" in url and request.url.path.endswith("/chat"):
            return httpx.Response(
                200,
                json={"representation": "Al usuario le apasiona la neurociencia y Python."},
            )
        if "honcho.dev" in url and request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"status": "recorded"})
        if "generativelanguage.googleapis.com" in url:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "[EMOTION:smug] Por supuesto que recuerdo tu gusto por el café expreso y la neurociencia, Okabe."
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        settings = AmadeusSettings(
            active_brain="gemini",
            gemini_api_key="mock-gemini-key",
            honcho_api_key="mock-honcho-key",
            use_honcho_cloud=True,
        )
        gov = ResourceGovernor(initial_mode=PowerMode.FOREGROUND_ACTIVE)
        brain = MultiBrainRouter(settings=settings, governor=gov, http_client=mock_client)
        identity = SoulManager(data_dir=tmp_path, user_display_name="Okabe")
        memory = HybridMemoryManager(
            settings=settings,
            db_path=tmp_path / "memory.db",
            http_client=mock_client,
        )
        core = AmadeusAgentCore(
            governor=gov, brain=brain, memory=memory, identity=identity
        )

        # Turn 1: User tells a preference -> stored in SQLite FTS5 + Honcho Cloud
        msg1 = AgentMessage(
            role="user",
            content="Hola Kurisu, recuerda que prefiero el café expreso por las mañanas",
            user_id="okabe_01",
        )
        reply1 = await core.process_user_message(msg1)
        assert reply1.emotion == EmotionState.SMUG
        assert "[EMOTION:" not in reply1.content

        # Verify SQLite FTS5 retrieval and Honcho dialectic retrieval
        ctx = await memory.retrieve_context("okabe_01", "café mañanas")
        assert "Honcho Dialectic Profile" in ctx
        assert "neurociencia" in ctx
        assert "café expreso" in ctx
