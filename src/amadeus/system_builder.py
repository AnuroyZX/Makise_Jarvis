from __future__ import annotations

from pathlib import Path
from typing import Optional
import httpx

from amadeus.body.agent_core import AmadeusAgentCore
from amadeus.brain.router import MultiBrainRouter
from amadeus.channels.pc_and_whatsapp import PCInteractionGateway, WhatsAppBridgePlugin
from amadeus.channels.telegram_gateway import TelegramGateway
from amadeus.config import AmadeusSettings, get_default_data_dir
from amadeus.house.environment_scanner import EnvironmentScanner, HostProfile
from amadeus.house.onboarding_ui import EphemeralOnboardingServer
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.house.ws_bridge import AmadeusWebSocketBridge
from amadeus.identity.soul_manager import SoulManager
from amadeus.memory.habits import HabitTracker
from amadeus.memory.hybrid_memory import HybridMemoryManager
from amadeus.memory.reflection import ReflectionEngine
from amadeus.skills.skill_loader import SkillRegistry
from amadeus.tools.file_ops import SafeFileManager
from amadeus.tools.screen_context import ScreenContextManager
from amadeus.tools.tool_registry import AmadeusToolkit
from amadeus.brain.tool_loop import AmadeusToolDispatcher
from amadeus.voice.listener import WakeWordWhisperListener
from amadeus.voice.tts_engine import AmadeusVoiceEngine


class AmadeusSystem:
    """
    Unified 9-Module Assembler for Amadeus Kurisu:
      1. Casa: ResourceGovernor + EnvironmentScanner + EphemeralOnboardingServer
      2. Cuerpo: AmadeusAgentCore (Event Bus + ReAct + VRoid Hooks)
      3. Cerebro: MultiBrainRouter (Gemini / Claude / Codex / OpenRouter + Smart Routing)
      4. Quién eres: SoulManager (SOUL.md + USER.md)
      5. Memoria: HybridMemoryManager (Honcho Cloud + Local SQLite FTS5)
      6. Habilidades: SkillRegistry (Progressive Disclosure SKILL.md)
      7. Herramientas: AmadeusToolkit (Windows App Auto-Discovery, Mail/Calendar, Ephemeral Browser)
      8. Canales: TelegramGateway + PCInteractionGateway + WhatsAppBridgePlugin
      9. Voz: AmadeusVoiceEngine (ElevenLabs + Credit Guard + Edge-TTS fallback)
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        initial_mode: PowerMode = PowerMode.BACKGROUND_ECO,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.data_dir = data_dir or get_default_data_dir()
        self.settings = AmadeusSettings.load(self.data_dir)

        # Module 1: Casa
        self.host_profile: HostProfile = EnvironmentScanner.scan()
        self.governor = ResourceGovernor(initial_mode=initial_mode)

        # Shared HTTP client pool for cloud modules (ECC Resource Efficiency Rule 2)
        self._shared_http = http_client

        # Module 3: Cerebro
        self.brain = MultiBrainRouter(
            settings=self.settings,
            governor=self.governor,
            http_client=self._shared_http,
        )

        # Module 4: Identidad y Quién eres
        self.identity = SoulManager(
            data_dir=self.data_dir,
            user_display_name=self.settings.user_display_name,
        )

        # Module 5: Memoria Híbrida (Honcho + SQLite FTS5) + Aprendizaje (F5)
        self.memory = HybridMemoryManager(
            settings=self.settings,
            db_path=self.data_dir / "amadeus_memory.db",
            http_client=self._shared_http,
        )
        self.reflection = ReflectionEngine(soul_manager=self.identity)
        self.habits = HabitTracker(db_path=self.data_dir / "amadeus_memory.db")

        # Module 6: Habilidades (Skills)
        self.skills = SkillRegistry(user_skills_dir=self.data_dir / "skills")

        # Module 2: Cuerpo (Amadeus Agent Core)
        self.core = AmadeusAgentCore(
            governor=self.governor,
            brain=self.brain,
            memory=self.memory,
            identity=self.identity,
            skills=self.skills,
        )

        # Module 7: Herramientas + Archivos Seguros (F3) + Contexto de Pantalla (F3)
        self.toolkit = AmadeusToolkit(
            settings=self.settings,
            governor=self.governor,
        )
        self.file_ops = SafeFileManager(
            settings=self.settings,
            data_dir=self.data_dir,
        )
        self.screen = ScreenContextManager(
            settings=self.settings,
            http_client=self._shared_http,
        )
        self.tool_dispatcher = AmadeusToolDispatcher(
            file_ops=self.file_ops,
            screen=self.screen,
            app_launcher=self.toolkit.app_launcher,
        )

        # Bind all cross-module commands into Module 2 (Body)
        self.brain.bind_commands(self.core)
        self.identity.bind_commands(self.core)
        self.toolkit.bind_commands(self.core)
        self.file_ops.bind_commands(self.core)

        # Module 9: Voz (ElevenLabs + Edge-TTS fallback) + Listener "Oye Kurisu" (F2)
        self.voice = AmadeusVoiceEngine(
            settings=self.settings,
            cache_dir=self.data_dir / "voice_cache",
            http_client=self._shared_http,
        )
        self.ws_bridge = AmadeusWebSocketBridge(system=self)
        self.listener = WakeWordWhisperListener(
            settings=self.settings,
            governor=self.governor,
            on_transcription=self.ws_bridge.process_and_stream_turn,
            on_interrupt=self._on_voice_interrupt,
            is_speaker_playing=lambda: self.ws_bridge.speaker_playing,
        )

        # Module 8: Canales (Telegram, PC Local, WhatsApp optional)
        self.telegram = TelegramGateway(
            settings=self.settings,
            core=self.core,
            governor=self.governor,
            voice=self.voice,
            http_client=self._shared_http,
        )
        self.pc_gateway = PCInteractionGateway(
            settings=self.settings,
            core=self.core,
            governor=self.governor,
            voice=self.voice,
        )
        self.whatsapp = WhatsAppBridgePlugin(
            settings=self.settings,
            core=self.core,
            http_client=self._shared_http,
        )

        # Ephemeral Web UI for Onboarding & Control
        self.web_ui = EphemeralOnboardingServer(system=self)

        # Trim initial startup memory footprint if starting in BACKGROUND_ECO
        if initial_mode == PowerMode.BACKGROUND_ECO:
            self.governor.trim_working_set()

    async def _on_voice_interrupt(self) -> None:
        self.ws_bridge.interrupt_current_turn()
        await self.ws_bridge.broadcast({"type": "interrupt", "turn_id": ""})

    async def shutdown(self) -> None:
        self.telegram.stop()
        self.listener.stop()
        self.listener.unload_idle_models(force=True)
        await self.ws_bridge.stop()
        await self.web_ui.stop()
        self.toolkit.browser.close_ephemeral_if_idle(force=True)
        await self.brain.close()
        await self.memory.honcho.close()
        await self.voice.close()
        self.governor.trim_working_set()
