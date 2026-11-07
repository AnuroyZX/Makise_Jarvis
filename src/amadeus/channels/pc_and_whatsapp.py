from __future__ import annotations

import asyncio
from typing import Callable, Optional
import httpx

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore, AvatarEvent
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.voice.tts_engine import AmadeusVoiceEngine


class PCInteractionGateway:
    """
    Module 8 (Canales - PC Local Push-to-Talk & Direct Interaction):
    Switches Module 1 (ResourceGovernor) to FOREGROUND_ACTIVE immediately when invoked,
    processes the user's message, synthesizes voice via Module 9, and emits VRoid speech events.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        core: AmadeusAgentCore,
        governor: ResourceGovernor,
        voice: Optional[AmadeusVoiceEngine] = None,
    ) -> None:
        self.settings = settings
        self.core = core
        self.governor = governor
        self.voice = voice
        self._hotkey_registered = False

    async def send_local_prompt(
        self, text: str, synthesize_voice: bool = True
    ) -> tuple[AgentMessage, Optional[str]]:
        """
        Wake Amadeus to FOREGROUND_ACTIVE, process prompt, and optionally synthesize voice.
        Returns (reply_message, saved_audio_path_str).
        """
        self.governor.switch_mode(PowerMode.FOREGROUND_ACTIVE)
        msg = AgentMessage(
            role="user",
            content=text,
            channel="pc",
            user_id=self.settings.user_display_name,
        )
        reply = await self.core.process_user_message(msg)

        audio_path_str: Optional[str] = None
        if synthesize_voice and self.voice is not None and self.settings.voice_replies_enabled:
            synth = await self.voice.synthesize(
                reply.content, for_telegram_opus=False, save_to_disk=True
            )
            if synth.saved_path:
                audio_path_str = str(synth.saved_path)
                await self.core._emit_avatar_event(
                    AvatarEvent(
                        event_type="speech_start",
                        emotion=reply.emotion,
                        text=reply.content,
                        audio_path=audio_path_str,
                    )
                )

        return reply, audio_path_str

    def register_push_to_talk_hotkey(
        self, on_trigger: Callable[[], None]
    ) -> bool:
        """Lazy-load `keyboard` module only if the user activates global Push-to-Talk."""
        try:
            import keyboard

            keyboard.add_hotkey(self.settings.push_to_talk_hotkey, on_trigger)
            self._hotkey_registered = True
            return True
        except Exception:
            return False


class WhatsAppBridgePlugin:
    """
    Module 8 (Canales - Plugin Opcional de WhatsApp):
    Disabled by default (`enable_whatsapp_plugin = False`) so it consumes 0 MB RAM
    unless explicitly enabled by the user.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        core: AmadeusAgentCore,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        self.core = core
        self._client = http_client

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.enable_whatsapp_plugin)

    async def handle_incoming_webhook(
        self, sender_phone: str, text: str, allowed_phones: list[str]
    ) -> str:
        if not self.is_enabled:
            return "Plugin de WhatsApp desactivado por ahorro de recursos."
        if sender_phone not in allowed_phones:
            return "Unauthorized WhatsApp sender."

        msg = AgentMessage(
            role="user",
            content=text,
            channel="whatsapp",
            user_id=sender_phone,
        )
        reply = await self.core.process_user_message(msg)
        return reply.content
