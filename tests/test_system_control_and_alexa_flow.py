from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from amadeus.tools.system_control import (
    WindowsSystemController,
    TimerManager,
    TimerItem,
    VK_VOLUME_UP,
    VK_VOLUME_DOWN,
    VK_VOLUME_MUTE,
    VK_MEDIA_PLAY_PAUSE,
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PREV_TRACK,
    VK_MEDIA_STOP,
)
from amadeus.brain.tool_loop import AmadeusToolDispatcher
from amadeus.house.resource_governor import ResourceGovernor


def test_windows_system_controller_volume_and_media():
    ctrl = WindowsSystemController()

    with patch("amadeus.tools.system_control._send_vk") as mock_send_vk:
        mock_send_vk.return_value = True

        # Volume controls
        msg_up = ctrl.volume_up(steps=2)
        assert "aumentado" in msg_up
        assert mock_send_vk.call_count == 2
        mock_send_vk.assert_called_with(VK_VOLUME_UP)

        mock_send_vk.reset_mock()
        msg_down = ctrl.volume_down(steps=3)
        assert "reducido" in msg_down
        assert mock_send_vk.call_count == 3
        mock_send_vk.assert_called_with(VK_VOLUME_DOWN)

        mock_send_vk.reset_mock()
        msg_mute = ctrl.toggle_mute()
        assert "Mute" in msg_mute
        mock_send_vk.assert_called_once_with(VK_VOLUME_MUTE)

        # Media controls
        mock_send_vk.reset_mock()
        ctrl.media_play_pause()
        mock_send_vk.assert_called_once_with(VK_MEDIA_PLAY_PAUSE)

        mock_send_vk.reset_mock()
        ctrl.media_next()
        mock_send_vk.assert_called_once_with(VK_MEDIA_NEXT_TRACK)

        mock_send_vk.reset_mock()
        ctrl.media_prev()
        mock_send_vk.assert_called_once_with(VK_MEDIA_PREV_TRACK)

        mock_send_vk.reset_mock()
        ctrl.media_stop()
        mock_send_vk.assert_called_once_with(VK_MEDIA_STOP)


def test_windows_system_controller_telemetry():
    ctrl = WindowsSystemController()
    data = ctrl.get_telemetry()

    assert "cpu_percent" in data
    assert "ram_used_mb" in data
    assert "ram_free_mb" in data
    assert "ram_percent" in data
    assert "time_str" in data
    assert "date_str" in data
    assert isinstance(data["cpu_percent"], (int, float))
    assert isinstance(data["ram_used_mb"], (int, float))


@pytest.mark.asyncio
async def test_timer_manager_lifecycle_and_expiration():
    expired_calls = []
    tick_calls = []

    async def on_tick(t: TimerItem):
        tick_calls.append(t.remaining_seconds)

    async def on_expired(t: TimerItem):
        expired_calls.append(t.id)

    mgr = TimerManager(on_tick=on_tick, on_expired=on_expired)
    try:
        timer = mgr.create_timer(seconds=1, label="Test Timer")
        assert timer.is_active is True
        assert timer.label == "Test Timer"
        assert len(mgr.list_active_timers()) == 1

        # Wait for the tick loop to expire the 1s timer
        await asyncio.sleep(1.4)

        assert len(expired_calls) == 1
        assert expired_calls[0] == timer.id
        assert len(mgr.list_active_timers()) == 0
    finally:
        mgr.stop()


def test_timer_manager_cancellation():
    mgr = TimerManager()
    try:
        t1 = mgr.create_timer(seconds=60, label="Hervir café")
        t2 = mgr.create_timer(seconds=120, label="Té verde")
        assert len(mgr.list_active_timers()) == 2

        # Cancel by partial label match
        cancelled = mgr.cancel_timer("café")
        assert cancelled is not None
        assert cancelled.id == t1.id
        assert cancelled.is_active is False
        assert len(mgr.list_active_timers()) == 1

        # Cancel remaining by default
        cancelled_last = mgr.cancel_timer("")
        assert cancelled_last is not None
        assert cancelled_last.id == t2.id
        assert len(mgr.list_active_timers()) == 0
    finally:
        mgr.stop()


@pytest.mark.asyncio
async def test_tool_dispatcher_alexa_style_intents():
    mock_file_ops = MagicMock()
    mock_screen = MagicMock()
    mock_launcher = MagicMock()
    mock_sys_ctrl = MagicMock()
    mock_sys_ctrl.volume_up.return_value = "Volumen subido."
    mock_sys_ctrl.volume_down.return_value = "Volumen bajado."
    mock_sys_ctrl.toggle_mute.return_value = "Silenciado."
    mock_sys_ctrl.media_play_pause.return_value = "Pausa aplicada."
    mock_sys_ctrl.media_next.return_value = "Siguiente pista."
    mock_sys_ctrl.media_prev.return_value = "Pista anterior."
    mock_sys_ctrl.get_telemetry.return_value = {
        "ram_free_mb": 8192,
        "ram_used_mb": 4096,
        "ram_percent": 33.3,
        "cpu_percent": 12.0,
        "time_str": "14:30",
        "date_str": "Lunes, 09 de Noviembre de 2026",
        "battery": {"percent": 90, "power_plugged": True},
    }

    mock_timer_mgr = MagicMock()
    mock_timer_mgr.create_timer.return_value = TimerItem(
        id="t1",
        label="3 minutos para el café",
        total_seconds=180,
        remaining_seconds=180,
        created_at=0.0,
    )
    mock_timer_mgr.cancel_timer.return_value = TimerItem(
        id="t1",
        label="3 minutos para el café",
        total_seconds=180,
        remaining_seconds=100,
        created_at=0.0,
    )
    mock_timer_mgr.list_active_timers.return_value = [
        TimerItem(id="t1", label="3 minutos para el café", total_seconds=180, remaining_seconds=120, created_at=0.0)
    ]

    dispatcher = AmadeusToolDispatcher(
        file_ops=mock_file_ops,
        screen=mock_screen,
        app_launcher=mock_launcher,
        system_control=mock_sys_ctrl,
        timer_manager=mock_timer_mgr,
    )

    # 1. Natural language Volume Up
    res, _ = await dispatcher.try_natural_language_action("oye kurisu sube el volumen por favor")
    assert res is not None
    assert "subido el volumen" in res
    mock_sys_ctrl.volume_up.assert_called()

    # 2. Volume Down
    res, _ = await dispatcher.try_natural_language_action("baja el volumen")
    assert res is not None
    assert "bajado el volumen" in res
    mock_sys_ctrl.volume_down.assert_called()

    # 3. Mute
    res, _ = await dispatcher.try_natural_language_action("pon en silencio")
    assert res is not None
    mock_sys_ctrl.toggle_mute.assert_called()

    # 4. Media Play/Pause
    res, _ = await dispatcher.try_natural_language_action("pausa la música")
    assert res is not None
    mock_sys_ctrl.media_play_pause.assert_called()

    # 5. Media Next
    res, _ = await dispatcher.try_natural_language_action("siguiente canción")
    assert res is not None
    mock_sys_ctrl.media_next.assert_called()

    # 6. Timer Creation (3 minutes -> 180s)
    res, _ = await dispatcher.try_natural_language_action("pon un temporizador de 3 minutos para el café")
    assert res is not None
    assert "temporizador" in res.lower()
    mock_timer_mgr.create_timer.assert_called_with(180, "3 minutos para el café")

    # 7. Timer Cancellation
    res, _ = await dispatcher.try_natural_language_action("cancela el temporizador")
    assert res is not None
    assert "cancelado tu temporizador" in res
    mock_timer_mgr.cancel_timer.assert_called()

    # 8. Hardware Telemetry
    res, _ = await dispatcher.try_natural_language_action("cuánta memoria ram tengo libre?")
    assert res is not None
    assert "memoria ram" in res.lower()
    mock_sys_ctrl.get_telemetry.assert_called()

    # 9. LLM Tool Execution dispatch
    vol_call_res, _ = await dispatcher.execute_tool_call("volume_control", {"action": "up", "steps": 2})
    assert vol_call_res is not None
    assert "Volumen subido" in vol_call_res

    med_call_res, _ = await dispatcher.execute_tool_call("media_control", {"action": "play_pause"})
    assert med_call_res is not None
    assert "Pausa aplicada" in med_call_res

    time_call_res, _ = await dispatcher.execute_tool_call("timer_control", {"action": "create", "seconds": 60, "label": "test"})
    assert time_call_res is not None
    assert "iniciado" in time_call_res

    tel_call_res, _ = await dispatcher.execute_tool_call("get_telemetry", {})
    assert tel_call_res is not None
    assert "ram_free_mb" in tel_call_res


def test_resource_governor_1gb_working_set():
    gov = ResourceGovernor()
    assert gov.MAX_WORKING_SET_MB == 1024.0

    # Under 1024 MB, trim_working_set with force=False skips kernel call
    with patch("amadeus.house.resource_governor.os.name", "nt"):
        with patch.object(gov, "get_process_memory_mb", side_effect=[500.0, 500.0]):
            with patch("ctypes.windll.kernel32.SetProcessWorkingSetSize") as mock_set_size:
                gov.trim_working_set(force=False)
                mock_set_size.assert_not_called()

        with patch.object(gov, "get_process_memory_mb", side_effect=[1200.0, 800.0]):
            with patch("ctypes.windll.kernel32.SetProcessWorkingSetSize") as mock_set_size:
                mock_set_size.return_value = 1
                gov.trim_working_set(force=False)
                mock_set_size.assert_called_once()


@pytest.mark.asyncio
async def test_webspeech_engine_zero_latency_dispatch(tmp_path):
    from amadeus.config import AmadeusSettings
    from amadeus.house.ws_bridge import AmadeusWebSocketBridge

    settings = AmadeusSettings(
        voice_engine="webspeech",
        webspeech_voice_name="Microsoft Sabina - Spanish (Mexico)",
        webspeech_rate=1.1,
    )
    assert settings.voice_engine == "webspeech"
    assert settings.webspeech_voice_name == "Microsoft Sabina - Spanish (Mexico)"

    mock_system = MagicMock()
    mock_system.settings = settings
    mock_system.voice.synthesize = AsyncMock()

    bridge = AmadeusWebSocketBridge(mock_system, host="127.0.0.1", port=0)
    bridge._current_turn_id = "turn_test_1"
    bridge._cancel_current_turn = False
    sent_broadcasts = []

    async def mock_broadcast(payload):
        sent_broadcasts.append(payload)

    bridge.broadcast = mock_broadcast

    # Stream a dual reply text in webspeech mode
    await bridge._stream_dual_reply_text(
        "Hola Okabe. Amadeus con voz nativa lista.",
        default_emotion="happy",
        turn_id="turn_test_1",
    )

    # In webspeech mode, zero backend synthesis calls should occur
    mock_system.voice.synthesize.assert_not_called()

    # The broadcast should immediately contain webspeech chunks with 0ms latency
    reply_chunks = [m for m in sent_broadcasts if m.get("type") == "reply_chunk"]
    assert len(reply_chunks) >= 1
    chunk = reply_chunks[0]
    assert chunk["type"] == "reply_chunk"
    assert chunk["provider"] == "webspeech"
    assert chunk["audio_b64"] == ""
    assert "Hola Okabe" in chunk["sentence"]

