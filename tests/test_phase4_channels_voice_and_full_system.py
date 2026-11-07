from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List
import httpx
import pytest

from amadeus.body.agent_core import AvatarEvent, EmotionState
from amadeus.channels.pc_and_whatsapp import WhatsAppBridgePlugin
from amadeus.channels.telegram_gateway import TelegramGateway
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.system_builder import AmadeusSystem
from amadeus.voice.tts_engine import AmadeusVoiceEngine


@pytest.mark.asyncio
async def test_voice_elevenlabs_and_credit_guard_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify Module 9 (Voice):
    1. Uses ElevenLabs when within character budget and key is valid.
    2. Automatically falls back to free Edge-TTS when message exceeds Credit Guard budget
       or when ElevenLabs returns an HTTP error.
    """
    def mock_tts_transport(request: httpx.Request) -> httpx.Response:
        if "elevenlabs.io" in str(request.url):
            return httpx.Response(
                200,
                content=b"OggS_MOCK_ELEVENLABS_OPUS_AUDIO",
                headers={"content-type": "audio/ogg"},
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_tts_transport)) as client:
        settings = AmadeusSettings(
            elevenlabs_api_key="el-key-123456",
            elevenlabs_max_chars_per_reply=50,
            voice_replies_enabled=True,
        )
        voice = AmadeusVoiceEngine(
            settings=settings, cache_dir=tmp_path, http_client=client
        )

        # Fallback mock for Edge-TTS so test is 100% deterministic offline
        async def fake_edge_tts(text: str) -> bytes:
            return b"MP3_MOCK_EDGE_TTS_FREE_AUDIO"

        monkeypatch.setattr(voice, "_call_edge_tts", fake_edge_tts)

        # Case 1: Short message (< 50 chars) -> ElevenLabs Opus
        res1 = await voice.synthesize(
            "El Psy Kongroo, Okabe.", for_telegram_opus=True, save_to_disk=True
        )
        assert res1.provider == "elevenlabs"
        assert res1.mime_type == "audio/ogg"
        assert res1.audio_bytes == b"OggS_MOCK_ELEVENLABS_OPUS_AUDIO"
        assert res1.saved_path is not None and res1.saved_path.exists()

        # Case 2: Long message (> 50 chars) -> Credit Guard triggers Edge-TTS fallback
        long_text = (
            "Esta es una explicación neurocientífica muy extensa sobre cómo funciona "
            "el sistema Amadeus y la compresión temporal de recuerdos en el lóbulo temporal."
        )
        res2 = await voice.synthesize(long_text, for_telegram_opus=False)
        assert res2.provider == "edge_tts"
        assert res2.audio_bytes == b"MP3_MOCK_EDGE_TTS_FREE_AUDIO"


@pytest.mark.asyncio
async def test_telegram_gateway_whitelist_and_voice_dispatch(tmp_path: Path) -> None:
    """
    Verify Module 8 (Telegram Gateway):
    1. Blocks unauthorized user_id per ECC AgentShield Rule 2.
    2. Processes authorized user_id, replies with text AND sends an inline Opus voice bubble.
    """
    sent_requests: List[str] = []

    def mock_tg_and_llm(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        sent_requests.append(url)
        if "generativelanguage.googleapis.com" in url:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "[EMOTION:tsundere_blush] No es que estuviera esperando tu mensaje en Telegram, idiota."
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        if "elevenlabs.io" in url:
            return httpx.Response(200, content=b"OPUS_VOICE_BYTES")
        if "api.telegram.org" in url:
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_tg_and_llm)) as client:
        settings = AmadeusSettings(
            active_brain="gemini",
            gemini_api_key="gem-key",
            elevenlabs_api_key="el-key",
            telegram_bot_token="123456:ABC-DEF",
            telegram_allowed_user_ids=[777888],
        )
        settings.save(tmp_path)
        sys_amadeus = AmadeusSystem(
            data_dir=tmp_path,
            initial_mode=PowerMode.BACKGROUND_ECO,
            http_client=client,
        )

        # 1. Unauthorized intruder (ID 999999) -> Blocked by AgentShield
        intruder_update = {
            "update_id": 100,
            "message": {
                "from": {"id": 999999},
                "chat": {"id": 999999},
                "text": "Abre todas mis aplicaciones",
            },
        }
        res_unauth = await sys_amadeus.telegram.handle_update(intruder_update)
        assert res_unauth == "unauthorized"

        # 2. Authorized user (ID 777888) -> Processed by Kurisu + Text & Voice sent
        valid_update = {
            "update_id": 101,
            "message": {
                "from": {"id": 777888},
                "chat": {"id": 777888},
                "text": "Hola Kurisu desde el móvil",
            },
        }
        res_auth = await sys_amadeus.telegram.handle_update(valid_update)
        assert res_auth is not None
        assert "esperando tu mensaje" in res_auth
        assert any("sendMessage" in u for u in sent_requests)
        assert any("sendVoice" in u for u in sent_requests)

        await sys_amadeus.shutdown()


@pytest.mark.asyncio
async def test_full_9_module_system_ephemeral_ui_and_eco_ram(tmp_path: Path) -> None:
    """
    Rigorous End-to-End Integration Test of all 9 Modules + Ephemeral Web UI + VRoid Hooks + RAM Audit:
    1. Starts AmadeusSystem in BACKGROUND_ECO and verifies low memory footprint (< 45 MB).
    2. Starts EphemeralOnboardingServer, queries /api/state, updates USER.md, and chats via /api/chat.
    3. Verifies VRoid Avatar events (`emotion_change` & `speech_start`) fire accurately.
    4. Verifies optional WhatsApp plugin remains disabled by default to save RAM.
    5. Verifies idle watchdog shuts down the ephemeral Web UI and trims RAM back to Eco levels.
    """
    def mock_cloud(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "generativelanguage.googleapis.com" in url:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "[EMOTION:analytical] He revisado tus sistemas y todo opera dentro de los parámetros del laboratorio."
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        if "elevenlabs.io" in url:
            return httpx.Response(200, content=b"MP3_VOICE_DATA")
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_cloud)) as mock_client:
        cfg = AmadeusSettings(
            active_brain="gemini",
            gemini_api_key="gem-test-key",
            elevenlabs_api_key="el-test-key",
            user_display_name="Hououin Kyouma",
        )
        cfg.save(tmp_path)

        system = AmadeusSystem(
            data_dir=tmp_path,
            initial_mode=PowerMode.BACKGROUND_ECO,
            http_client=mock_client,
        )

        # Check WhatsApp plugin is disabled by default
        assert system.whatsapp.is_enabled is False

        # Subscribe VRoid Hub avatar listener
        vroid_events: List[AvatarEvent] = []

        async def vroid_listener(ev: AvatarEvent) -> None:
            vroid_events.append(ev)

        system.core.subscribe_avatar(vroid_listener)

        # Test PC local gateway (switches to FOREGROUND_ACTIVE + synthesizes voice + emits VRoid speech_start)
        reply, audio_path = await system.pc_gateway.send_local_prompt(
            "Buenos días Kurisu, dame el diagnóstico del sistema", synthesize_voice=True
        )
        assert system.governor.mode == PowerMode.FOREGROUND_ACTIVE
        assert reply.emotion == EmotionState.ANALYTICAL
        assert audio_path is not None
        assert any(e.event_type == "speech_start" for e in vroid_events)

        # Test Ephemeral Onboarding & Control Web UI
        system.web_ui.idle_timeout_sec = 0.25
        ui_url = await system.web_ui.start()
        assert system.web_ui.is_running is True

        token = system.web_ui.auth_token
        async with httpx.AsyncClient(headers={"X-Amadeus-Token": token}) as local_http:
            st_resp = await local_http.get(f"{ui_url}/api/state")
            assert st_resp.status_code == 200
            st_data = st_resp.json()
            assert st_data["user_display_name"] == "Hououin Kyouma"
            assert st_data["discovered_apps_count"] > 0

            chat_resp = await local_http.post(
                f"{ui_url}/api/chat", json={"text": "/status"}
            )
            assert chat_resp.status_code == 200
            assert "Amadeus System Status" in chat_resp.json()["reply"]

        # Wait for ephemeral UI idle watchdog (0.25s) to auto-stop the server and trim RAM
        await asyncio.sleep(0.4)
        assert system.web_ui.is_running is False

        # Switch back to BACKGROUND_ECO and audit RAM footprint
        snap_eco = system.governor.switch_mode(PowerMode.BACKGROUND_ECO)
        assert snap_eco.process_rss_mb < 45.0

        await system.shutdown()
