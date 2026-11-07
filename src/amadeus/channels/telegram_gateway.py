from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import httpx

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import ResourceGovernor
from amadeus.voice.tts_engine import AmadeusVoiceEngine


class TelegramGateway:
    """
    Module 8 (Canales - Telegram):
    Lightweight async Telegram Bot gateway with:
    1. ECC AgentShield strict `telegram_allowed_user_ids` whitelist.
    2. Adaptive polling synced with Module 1 (`ResourceGovernor.polling_interval_sec`).
    3. Inline Opus voice note replies synthesized via Module 9 (`AmadeusVoiceEngine`).
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        core: AmadeusAgentCore,
        governor: ResourceGovernor,
        voice: Optional[AmadeusVoiceEngine] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        self.core = core
        self.governor = governor
        self.voice = voice
        self._external_client = http_client is not None
        self._client = http_client
        self._offset: int = 0
        self._running: bool = False

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.telegram_bot_token)

    def is_user_authorized(self, user_id: int) -> bool:
        """
        ECC AgentShield Rule 2: Enforce explicit allowed_user_ids whitelist.
        If whitelist is empty, deny external execution until the user registers their ID.
        """
        if not self.settings.telegram_allowed_user_ids:
            return False
        return user_id in self.settings.telegram_allowed_user_ids

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0))
        return self._client

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/{method}"

    async def handle_update(self, update: Dict[str, Any]) -> Optional[str]:
        """Process a single Telegram update dictionary and dispatch text + voice reply."""
        update_id = int(update.get("update_id", 0))
        if update_id >= self._offset:
            self._offset = update_id + 1

        msg = update.get("message")
        if not msg:
            return None

        sender = msg.get("from", {})
        user_id = int(sender.get("id", 0))
        chat_id = int(msg.get("chat", {}).get("id", user_id))
        text = str(msg.get("text") or msg.get("caption") or "").strip()

        if not text:
            return None

        # AgentShield Whitelist check
        if not self.is_user_authorized(user_id):
            await self.send_text_message(
                chat_id,
                f"⛔ Acceso denegado por Amadeus AgentShield. Tu ID de Telegram ({user_id}) "
                "no está en la lista blanca (`telegram_allowed_user_ids`).",
            )
            return "unauthorized"

        agent_msg = AgentMessage(
            role="user",
            content=text,
            channel="telegram",
            user_id=str(user_id),
        )
        reply = await self.core.process_user_message(agent_msg)
        await self.send_text_message(chat_id, reply.content)

        # Send voice note if voice engine is enabled
        if self.voice is not None and self.settings.voice_replies_enabled:
            synth = await self.voice.synthesize(
                reply.content, for_telegram_opus=True
            )
            if synth.audio_bytes:
                await self.send_voice_note(chat_id, synth.audio_bytes, synth.mime_type)

        return reply.content

    async def send_text_message(self, chat_id: int, text: str) -> None:
        client = await self._get_client()
        await client.post(
            self._api_url("sendMessage"),
            json={"chat_id": chat_id, "text": text},
        )

    async def send_voice_note(
        self, chat_id: int, audio_bytes: bytes, mime_type: str = "audio/ogg"
    ) -> None:
        client = await self._get_client()
        ext = "ogg" if "ogg" in mime_type else "mp3"
        files = {"voice": (f"kurisu_reply.{ext}", audio_bytes, mime_type)}
        await client.post(
            self._api_url("sendVoice"),
            data={"chat_id": str(chat_id)},
            files=files,
        )

    async def poll_once(self) -> List[str]:
        if not self.is_configured:
            return []
        client = await self._get_client()
        resp = await client.get(
            self._api_url("getUpdates"),
            params={"offset": self._offset, "timeout": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        results: List[str] = []
        for upd in data.get("result", []):
            res = await self.handle_update(upd)
            if res:
                results.append(res)
        return results

    async def run_forever(self) -> None:
        """Adaptive background polling loop scaled by ResourceGovernor."""
        self._running = True
        while self._running:
            if self.is_configured:
                try:
                    await self.poll_once()
                except Exception:
                    pass
            await asyncio.sleep(self.governor.polling_interval_sec)

    def stop(self) -> None:
        self._running = False
