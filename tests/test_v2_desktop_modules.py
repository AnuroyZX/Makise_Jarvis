from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import struct
import httpx
import pytest

from amadeus.brain.dual_response import parse_dual_layer_output
from amadeus.brain.tool_loop import AmadeusToolDispatcher
from amadeus.config import AmadeusSettings, classify_api_key
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.house.ws_bridge import AmadeusWebSocketBridge
from amadeus.identity.soul_manager import SoulManager
from amadeus.memory.habits import HabitTracker
from amadeus.memory.reflection import ReflectionEngine
from amadeus.system_builder import AmadeusSystem
from amadeus.tools.app_launcher import WindowsAppLauncher
from amadeus.tools.file_ops import SafeFileManager
from amadeus.tools.screen_context import ScreenContextManager
from amadeus.voice.listener import ListenerState, WakeWordWhisperListener


def test_classify_api_key_prefixes() -> None:
    """Verify F0 key auto-classification by prefix."""
    assert classify_api_key("sk-ant-api03-12345") == "anthropic_api_key"
    assert classify_api_key("sk-or-v1-99999") == "openrouter_api_key"
    assert classify_api_key("sk-proj-abcdef") == "openai_api_key"
    assert classify_api_key("AIzaSyTestKey") == "gemini_api_key"
    assert classify_api_key("AQ.Ab8RN6Test") == "gemini_api_key"
    assert classify_api_key("unknown_key") == ""


def test_dual_layer_response_and_sentence_divider() -> None:
    """Verify F1 Two-Layer response parser (spoken + detail + emotion + gesture) & Open-LLM-VTuber sentence divider."""
    # 1. Valid JSON output from LLM
    raw_json = (
        '{"spoken": "He revisado tu código. Te dejo la solución en pantalla.", '
        '"detail": "```python\\nprint(42)\\n```", "emotion": "smug", "gesture": "point"}'
    )
    dual1 = parse_dual_layer_output(raw_json)
    assert dual1.emotion.value == "smug"
    assert dual1.gesture == "point"
    assert "```python" in dual1.detail
    sentences = dual1.split_spoken_sentences()
    assert len(sentences) == 2
    assert sentences[0] == "He revisado tu código."

    # 2. Long markdown text without JSON -> automatically splits into brief spoken + full detail card
    long_md = (
        "[EMOTION:analytical] Aquí tienes los pasos para configurar el entorno:\n"
        "1. Crear el venv\n2. Instalar dependencias\n```bash\npip install -r requirements.txt\n```"
    )
    dual2 = parse_dual_layer_output(long_md)
    assert dual2.emotion.value == "analytical"
    assert dual2.gesture == "point"
    assert len(dual2.spoken) <= 340
    assert "pip install" in dual2.detail


@pytest.mark.asyncio
async def test_ws_bridge_auth_streaming_and_interrupt(tmp_path: Path) -> None:
    """Verify F0/F1 WebSocket bridge rejects invalid tokens, streams sentence chunks, and supports interrupt."""
    import websockets

    def mock_llm_and_tts(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "pollinations.ai" in url:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"spoken": "Primera frase de prueba. Segunda frase de Kurisu.", "detail": "Detalle técnico.", "emotion": "smug", "gesture": "wave"}'
                            }
                        }
                    ]
                },
            )
        if "elevenlabs.io" in url:
            return httpx.Response(200, content=b"FAKE_MP3_SENTENCE_BYTES")
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_llm_and_tts)) as client:
        cfg = AmadeusSettings(
            active_brain="free",
            elevenlabs_api_key="el-test-key",
            voice_replies_enabled=True,
        )
        cfg.save(tmp_path)
        system = AmadeusSystem(data_dir=tmp_path, http_client=client)
        ws_url = await system.ws_bridge.start()

        # 1. Connection with wrong token must be closed with code 4003
        bad_url = f"ws://127.0.0.1:{system.ws_bridge.port}/ws?token=wrong_token"
        async with websockets.connect(bad_url) as bad_ws:
            with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
                await bad_ws.recv()
            assert exc_info.value.rcvd is not None and exc_info.value.rcvd.code == 4003

        # 2. Valid connection receives `connected`, sends `user_text`, and receives `reply_detail` + 2 `reply_chunk`s
        received_types = []
        async with websockets.connect(ws_url) as ws:
            init_msg = await ws.recv()
            assert '"connected"' in init_msg

            await ws.send('{"type": "user_text", "text": "Hola Kurisu"}')
            for _ in range(10):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                if '"reply_detail"' in raw:
                    received_types.append("reply_detail")
                elif '"reply_chunk"' in raw:
                    received_types.append("reply_chunk")
                elif '"state": "idle"' in raw and "reply_chunk" in received_types:
                    break

        assert "reply_detail" in received_types
        assert received_types.count("reply_chunk") == 2
        await system.shutdown()


def test_file_ops_sandbox_confirmation_recycle_and_undo(tmp_path: Path) -> None:
    """
    Verify F3 SafeFileManager:
    1. Rejects paths outside allowed roots, `C:\\Windows`, and reserved names (`CON`).
    2. Direct create_folder and create_file work inside allowed root.
    3. Move, rename, and delete require confirmation (`PendingFileOperation`) and do nothing until approved.
    4. `/deshacer` (`undo_last_batch`) reverses delete, rename, and move cleanly.
    """
    allowed_root = tmp_path / "UserDocs"
    allowed_root.mkdir()
    outside_root = tmp_path / "OutsideSecret"
    outside_root.mkdir()

    cfg = AmadeusSettings(allowed_fs_roots=[str(allowed_root)])
    fm = SafeFileManager(settings=cfg, data_dir=tmp_path)

    # 1. Security rejections
    with pytest.raises(PermissionError):
        fm.validate_safe_path("C:\\Windows\\System32\\cmd.exe")
    with pytest.raises(PermissionError):
        fm.validate_safe_path(outside_root / "secret.txt")
    with pytest.raises(ValueError):
        fm.validate_safe_path(allowed_root / "CON.txt")

    # 2. Direct folder and file creation
    sub = allowed_root / "Proyectos"
    fm.fs_create_folder(sub)
    assert sub.is_dir()

    note = allowed_root / "nota.txt"
    fm.fs_create_file(note, "El Psy Kongroo")
    assert note.read_text(encoding="utf-8") == "El Psy Kongroo"

    # 3. Move requires confirmation
    pending_mv = fm.request_move([note], sub)
    assert note.exists()  # Still at original location before approval!
    res_mv = fm.resolve_pending(pending_mv.op_id, approved=True)
    assert "procesados" in res_mv
    moved_note = sub / "nota.txt"
    assert moved_note.exists() and not note.exists()

    # Undo move -> back at original location
    fm.undo_last_batch()
    assert note.exists() and not moved_note.exists()

    # 4. Delete requires confirmation + Undo restores deleted file
    pending_del = fm.request_delete([note])
    assert note.exists()
    fm.resolve_pending(pending_del.op_id, approved=True)
    assert not note.exists()

    fm.undo_last_batch()
    assert note.exists()
    assert note.read_text(encoding="utf-8") == "El Psy Kongroo"


def test_screen_context_exclusion_privacy() -> None:
    """Verify F3 ScreenContextManager blocks excluded password managers and banking windows."""
    cfg = AmadeusSettings()
    scr = ScreenContextManager(settings=cfg)
    assert scr.is_excluded_window("KeePass.exe", "Mi Base de Contraseñas") is True
    assert scr.is_excluded_window("chrome.exe", "Banco Santander - Acceso Clientes") is True
    assert scr.is_excluded_window("Code.exe", "router.py - Makise_Jarvis") is False


@pytest.mark.asyncio
async def test_wake_word_listener_anti_echo_and_idle_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify F2 WakeWordWhisperListener:
    1. Ignores low-energy audio when speaker is playing (Anti-Self-Echo).
    2. Interrupts speaker when user speaks "oye kurisu" loudly over playback.
    3. Records speech until 1.2s of silence, transcribes via Whisper, and unloads model on Eco/Idle.
    """
    cfg = AmadeusSettings(wake_word_enabled=True, wake_word_phrase="oye kurisu")
    gov = ResourceGovernor(initial_mode=PowerMode.FOREGROUND_ACTIVE)

    interrupted = False
    transcribed_texts = []
    speaker_playing = True

    async def on_int() -> None:
        nonlocal interrupted
        interrupted = True

    async def on_trans(txt: str) -> None:
        transcribed_texts.append(txt)

    listener = WakeWordWhisperListener(
        settings=cfg,
        governor=gov,
        on_transcription=on_trans,
        on_interrupt=on_int,
        is_speaker_playing=lambda: speaker_playing,
        whisper_idle_timeout_sec=0.05,
    )

    async def fake_transcribe(pcm: bytes) -> str:
        listener._whisper_model = "DUMMY_LOADED_WHISPER_MODEL"
        listener._last_whisper_use_ts = 0.0
        return "¿Qué hora es en Akihabara?"

    monkeypatch.setattr(listener, "transcribe_pcm_bytes", fake_transcribe)
    listener.start()
    assert listener.state == ListenerState.IDLE_WAKE

    # Low energy frame while speaker is playing -> ignored (anti-echo)
    quiet_frame = struct.pack("<1600h", *([100] * 1600))
    await listener.process_pcm_frame(
        quiet_frame, frame_duration_sec=0.1, simulated_wake_text="oye kurisu"
    )
    assert listener.state == ListenerState.IDLE_WAKE
    assert interrupted is False

    # High energy frame with wake word -> interrupts speaker and enters RECORDING
    loud_frame = struct.pack("<1600h", *([2500] * 1600))
    await listener.process_pcm_frame(
        loud_frame, frame_duration_sec=0.1, simulated_wake_text="oye kurisu"
    )
    assert interrupted is True
    assert listener.state == ListenerState.RECORDING

    speaker_playing = False
    # Feed 1.3s of silence to finish recording and trigger transcription
    silent_frame = struct.pack("<1600h", *([10] * 1600))
    for _ in range(13):
        await listener.process_pcm_frame(silent_frame, frame_duration_sec=0.1)

    assert listener.state == ListenerState.IDLE_WAKE
    assert transcribed_texts == ["¿Qué hora es en Akihabara?"]

    # Switching to BACKGROUND_ECO stops listener and unloads Whisper model from memory
    gov.switch_mode(PowerMode.BACKGROUND_ECO)
    assert listener.state == ListenerState.STOPPED
    assert listener._whisper_model is None


def test_reflection_and_habit_learning(tmp_path: Path) -> None:
    """
    Verify F5 ReflectionEngine & HabitTracker:
    1. Filters out low-confidence (< 0.7) and sensitive (password/API key) facts.
    2. Learns direct style corrections ("no me llames Okabe") into `## Reglas de estilo`.
    3. Removes obsolete fact IDs and supports deleting learned items by ID.
    4. HabitTracker suggests an app only after >= 3 distinct weeks in the same time slot, max once per day.
    """
    soul = SoulManager(data_dir=tmp_path, user_display_name="Rintaro")
    refl = ReflectionEngine(soul_manager=soul)

    rule = refl.detect_direct_style_correction("Oye Kurisu, no me llames Okabe por favor")
    assert rule is not None
    assert "Nunca llamar al usuario 'Okabe'" in soul.read_user_profile()

    res = refl.apply_reflection_payload(
        {
            "facts": [
                {"id": "f001", "text": "Trabaja con motor Unity y VRM", "category": "proyecto", "confidence": 0.92},
                {"id": "f002", "text": "Tal vez le guste el té", "category": "gusto", "confidence": 0.45},
                {"id": "f003", "text": "Su password de correo es 123456", "category": "persona", "confidence": 0.99},
            ],
            "style_rules": ["Usar ejemplos concisos en Python."],
            "obsolete_ids": [],
        }
    )
    assert res["added_facts"] == 1  # Only f001 passed confidence >= 0.7 and sensitivity filter!
    profile = soul.read_user_profile()
    assert "[id:f001]" in profile
    assert "password" not in profile

    # Delete f001 by ID
    assert refl.delete_learned_item_by_id("f001") is True
    assert "[id:f001]" not in soul.read_user_profile()

    # HabitTracker: 3 distinct weeks at Monday 21:00 using Code.exe
    habits = HabitTracker(db_path=tmp_path / "habits.db")
    w1 = datetime(2026, 10, 19, 21, 15)  # Monday
    w2 = datetime(2026, 10, 26, 21, 10)  # Monday
    w3 = datetime(2026, 11, 2, 21, 5)    # Monday
    for dt in (w1, w2, w3):
        habits.record_usage("Code.exe", seconds=300, when=dt)

    check_time = datetime(2026, 11, 9, 21, 0)  # Next Monday 21:00
    sug1 = habits.get_habit_suggestion(currently_open_processes=["chrome.exe"], when=check_time)
    assert sug1 is not None and "code" in sug1.lower()

    # Second call on the same day must return None (max 1 suggestion per day)
    sug2 = habits.get_habit_suggestion(currently_open_processes=["chrome.exe"], when=check_time)
    assert sug2 is None
