from __future__ import annotations

import asyncio
import base64
import json
import secrets
from typing import TYPE_CHECKING, Any, Dict, Optional, Set
import urllib.parse
import uuid

from amadeus.brain.dual_response import parse_dual_layer_output
from amadeus.house.resource_governor import PowerMode

if TYPE_CHECKING:
    from amadeus.system_builder import AmadeusSystem


class AmadeusWebSocketBridge:
    """
    Phase F0/F1 Local WebSocket Bridge (`127.0.0.1` + Random Token Auth) with
    Open-LLM-VTuber patterns:
      1. Sentence Divider & Streaming TTS Queue (`reply_chunk` per sentence).
      2. Real-time Interrupt (`interrupt` signal cancels pending sentence TTS).
      3. Anti-Self-Echo (`audio_playing` state tracking from the Electron renderer).
    """

    def __init__(
        self,
        system: AmadeusSystem,
        host: str = "127.0.0.1",
        port: int = 0,
        auth_token: Optional[str] = None,
    ) -> None:
        self.system = system
        self.host = host
        self.port = port
        self.auth_token = auth_token or secrets.token_urlsafe(24)
        self._server: Any = None
        self._clients: Set[Any] = set()
        self._current_turn_id: Optional[str] = None
        self._cancel_current_turn: bool = False
        self.speaker_playing: bool = False

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws?token={self.auth_token}"

    async def start(self) -> str:
        if self._server is not None:
            return self.ws_url

        import websockets

        self._server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            origins=None,  # Checked explicitly in _handler for token + localhost safety
            max_size=25 * 1024 * 1024,
        )
        sockets = self._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]
        return self.ws_url

    async def stop(self) -> None:
        self.interrupt_current_turn()
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def interrupt_current_turn(self) -> None:
        """Cancel any in-flight sentence TTS synthesis and notify connected UI clients."""
        self._cancel_current_turn = True
        self.speaker_playing = False

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        if not self._clients:
            return
        msg = json.dumps(payload, ensure_ascii=False)
        stale = []
        for ws in list(self._clients):
            try:
                await ws.send(msg)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)

    def _is_authorized(self, ws: Any) -> bool:
        raw_path = getattr(ws, "path", "") or getattr(getattr(ws, "request", None), "path", "")
        parsed = urllib.parse.urlparse(raw_path)
        qs = urllib.parse.parse_qs(parsed.query)
        provided_token = (qs.get("token") or [""])[0]
        if not secrets.compare_digest(provided_token, self.auth_token):
            return False

        # Reject browser origins from external websites (CSRF / Cross-Origin WebSocket hijacking defense)
        headers = getattr(ws, "request_headers", None) or getattr(
            getattr(ws, "request", None), "headers", {}
        )
        origin = str(headers.get("Origin", "") or headers.get("origin", "")).strip()
        if origin and not (
            origin.startswith("http://127.0.0.1")
            or origin.startswith("http://localhost")
            or origin.startswith("file://")
        ):
            return False
        return True

    async def _handler(self, ws: Any) -> None:
        if not self._is_authorized(ws):
            await ws.close(code=4003, reason="Unauthorized token or origin")
            return

        self._clients.add(ws)
        try:
            snap = self.system.governor.snapshot()
            await ws.send(
                json.dumps(
                    {
                        "type": "connected",
                        "power_mode": snap.power_mode.value,
                        "bubbles_mode": self.system.settings.bubbles_mode,
                        "dsp_preset": self.system.settings.dsp_preset,
                        "has_vrm": (self.system.data_dir / "avatar.vrm").exists(),
                    }
                )
            )
            async for raw_msg in ws:
                if isinstance(raw_msg, bytes):
                    raw_msg = raw_msg.decode("utf-8", errors="replace")
                data = json.loads(raw_msg)
                await self._handle_client_message(data)
        except Exception:
            pass
        finally:
            self._clients.discard(ws)

    async def _handle_client_message(self, data: Dict[str, Any]) -> None:
        msg_type = str(data.get("type") or "")

        if msg_type == "audio_playing":
            self.speaker_playing = bool(data.get("playing", False))
            return

        if msg_type == "avatar_pose":
            emo = str(data.get("emotion", "neutral"))
            gest = str(data.get("gesture", "wave"))
            phrase = str(data.get("phrase") or "").strip()
            await self.broadcast(
                {
                    "type": "avatar_pose",
                    "emotion": emo,
                    "gesture": gest,
                    "phrase": phrase,
                }
            )
            return

        if msg_type == "mic_toggle":
            if self.system.listener.is_ptt_recording:
                self.system.listener.stop_ptt_recording()
                return
            asyncio.create_task(self._run_ptt_mic_turn())
            return

        if msg_type == "test_voice":
            asyncio.create_task(self._run_voice_test(str(data.get("mode") or "active")))
            return

        if msg_type == "interrupt":
            turn_id = self._current_turn_id or ""
            self.interrupt_current_turn()
            await self.broadcast({"type": "interrupt", "turn_id": turn_id})
            return

        if msg_type == "mode_change":
            target = str(data.get("mode", "background_eco"))
            mode = (
                PowerMode.FOREGROUND_ACTIVE
                if target == "foreground_active"
                else PowerMode.BACKGROUND_ECO
            )
            snap = self.system.governor.switch_mode(mode)
            await self.broadcast(
                {
                    "type": "mode_changed",
                    "power_mode": snap.power_mode.value,
                    "rss_mb": snap.process_rss_mb,
                }
            )
            return

        if msg_type == "confirm":
            op_id = str(data.get("id") or "")
            approved = bool(data.get("approved", False))
            if hasattr(self.system, "file_ops") and self.system.file_ops is not None:
                res_text = self.system.file_ops.resolve_pending(op_id, approved=approved)
                await self._stream_dual_reply_text(res_text)
            return

        if msg_type == "user_text":
            text = str(data.get("text") or "").strip()
            if not text:
                return
            await self.process_and_stream_turn(text)

    async def _run_ptt_mic_turn(self) -> None:
        """Record user speech from Windows microphone and stream Kurisu's reply."""
        if self._current_turn_id is not None:
            self.interrupt_current_turn()
            await self.broadcast({"type": "interrupt", "turn_id": self._current_turn_id})

        await self.broadcast({"type": "listening", "state": "recording"})
        transcript = await self.system.listener.record_and_transcribe_once(max_seconds=9.0)
        if not transcript:
            await self.broadcast({"type": "listening", "state": "idle"})
            await self.broadcast(
                {
                    "type": "reply_chunk",
                    "turn_id": uuid.uuid4().hex[:8],
                    "index": 0,
                    "total": 1,
                    "sentence": "No logré escuchar tu voz en el micrófono. Habla un poco más cerca e inténtalo de nuevo.",
                    "emotion": "neutral",
                    "gesture": "think",
                    "audio_b64": "",
                    "mime": "audio/mpeg",
                }
            )
            return

        await self.broadcast({"type": "mic_transcript", "text": transcript})
        await self.process_and_stream_turn(transcript)

    async def _run_voice_test(self, mode: str = "active") -> None:
        """Synthesize or play a voice test and broadcast it directly to the 3D Avatar + Panel."""
        turn_id = uuid.uuid4().hex[:8]
        self._current_turn_id = turn_id
        self._cancel_current_turn = False

        if mode == "kikivoice_ref":
            ref_file = self.system.data_dir / "kikivoice_ref.mp3"
            if ref_file.exists():
                audio_bytes = ref_file.read_bytes()
                audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                await self.broadcast(
                    {
                        "type": "reply_chunk",
                        "turn_id": turn_id,
                        "index": 0,
                        "total": 1,
                        "sentence": "Reproduciendo tu muestra de voz subida de KikiVoice en el avatar 3D.",
                        "emotion": "smug",
                        "gesture": "wave",
                        "audio_b64": audio_b64,
                        "mime": "audio/mpeg",
                        "provider": "kikivoice_ref",
                    }
                )
                return

        test_sentence = "Hola Okabe. Sistema Amadeus en línea. Prueba de sincronización vocal completada. El Psy Kongroo."
        synth = await self.system.voice.synthesize(
            test_sentence, for_telegram_opus=False, save_to_disk=False
        )
        audio_b64 = (
            base64.b64encode(synth.audio_bytes).decode("ascii")
            if synth.audio_bytes
            else ""
        )
        await self.broadcast(
            {
                "type": "reply_chunk",
                "turn_id": turn_id,
                "index": 0,
                "total": 1,
                "sentence": test_sentence,
                "emotion": "smug",
                "gesture": "wave",
                "audio_b64": audio_b64,
                "mime": synth.mime_type,
                "provider": synth.provider,
            }
        )

    async def process_and_stream_turn(self, user_text: str) -> None:
        """
        Interrupt any prior speech, run the Amadeus agent turn, split into spoken + detail,
        and stream sentence-by-sentence TTS audio chunks over WebSocket.
        """
        if self._current_turn_id is not None:
            self.interrupt_current_turn()
            await self.broadcast({"type": "interrupt", "turn_id": self._current_turn_id})

        turn_id = uuid.uuid4().hex[:10]
        self._current_turn_id = turn_id
        self._cancel_current_turn = False

        self.system.governor.switch_mode(PowerMode.FOREGROUND_ACTIVE)
        await self.broadcast({"type": "listening", "state": "thinking", "turn_id": turn_id})

        reply_msg, _ = await self.system.pc_gateway.send_local_prompt(
            user_text, synthesize_voice=False
        )
        if reply_msg.metadata and reply_msg.metadata.get("pending_op_id"):
            await self.broadcast(
                {
                    "type": "confirm_request",
                    "id": reply_msg.metadata["pending_op_id"],
                    "summary": reply_msg.metadata.get("pending_summary", ""),
                }
            )
        await self._stream_dual_reply_text(
            reply_msg.content,
            default_emotion=reply_msg.emotion.value,
            turn_id=turn_id,
        )

    async def _stream_dual_reply_text(
        self,
        raw_reply_text: str,
        default_emotion: str = "neutral",
        turn_id: Optional[str] = None,
    ) -> None:
        turn_id = turn_id or uuid.uuid4().hex[:10]
        dual = parse_dual_layer_output(raw_reply_text)
        emotion_str = (
            dual.emotion.value if dual.emotion.value != "neutral" else default_emotion
        )

        # 1. Split spoken response into sentences and synthesize + stream sequentially (Open-LLM-VTuber queue)
        sentences = dual.split_spoken_sentences()
        await self.broadcast({"type": "listening", "state": "speaking", "turn_id": turn_id})

        for idx, sentence in enumerate(sentences):
            if self._cancel_current_turn or self._current_turn_id != turn_id:
                break

            audio_b64 = ""
            mime = "audio/mpeg"
            voice_provider = "disabled"
            if self.system.settings.voice_replies_enabled:
                synth = await self.system.voice.synthesize(
                    sentence, for_telegram_opus=False, save_to_disk=False
                )
                voice_provider = synth.provider
                if synth.audio_bytes:
                    audio_b64 = base64.b64encode(synth.audio_bytes).decode("ascii")
                    mime = synth.mime_type

            if self._cancel_current_turn or self._current_turn_id != turn_id:
                break

            await self.broadcast(
                {
                    "type": "reply_chunk",
                    "turn_id": turn_id,
                    "index": idx,
                    "total": len(sentences),
                    "sentence": sentence,
                    "emotion": emotion_str,
                    "gesture": dual.gesture if idx == 0 else "idle",
                    "audio_b64": audio_b64,
                    "mime": mime,
                    "provider": voice_provider,
                }
            )

        # 2. If there is a detailed written section, push it AFTER spoken chunks so bubbles stay in strict order
        if dual.detail and not self._cancel_current_turn and self._current_turn_id == turn_id:
            await self.broadcast(
                {
                    "type": "reply_detail",
                    "turn_id": turn_id,
                    "detail": dual.detail,
                    "emotion": emotion_str,
                    "gesture": dual.gesture,
                }
            )

        await self.broadcast({"type": "listening", "state": "idle", "turn_id": turn_id})
