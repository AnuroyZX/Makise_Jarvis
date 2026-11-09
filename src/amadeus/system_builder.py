from __future__ import annotations

from pathlib import Path
from typing import Optional
import httpx

from amadeus.body.agent_core import AmadeusAgentCore
from amadeus.brain.router import MultiBrainRouter
from amadeus.channels.pc_and_whatsapp import PCInteractionGateway, WhatsAppBridgePlugin
from amadeus.channels.telegram_gateway import TelegramGateway
from amadeus.config import AmadeusSettings, get_default_data_dir
from amadeus.house.asset_library import AssetLibraryManager
from amadeus.house.environment_scanner import EnvironmentScanner, HostProfile
from amadeus.house.logging_setup import setup_logging
from amadeus.house.onboarding_ui import EphemeralOnboardingServer
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.house.steam_bridge import SteamBridge
from amadeus.house.ws_bridge import AmadeusWebSocketBridge
from amadeus.identity.profile_manager import ProfileManager
from amadeus.identity.soul_manager import SoulManager
from amadeus.memory.habits import HabitTracker
from amadeus.memory.hybrid_memory import HybridMemoryManager
from amadeus.memory.reflection import ReflectionEngine
from amadeus.skills.skill_loader import SkillRegistry
from amadeus.tools.file_ops import SafeFileManager
from amadeus.tools.screen_context import ScreenContextManager
from amadeus.tools.system_control import TimerItem, TimerManager, WindowsSystemController
from amadeus.tools.tool_registry import AmadeusToolkit
from amadeus.tools.calculator import CalculatorTool
from amadeus.tools.weather import WeatherTool
from amadeus.tools.web_search import WebSearchTool
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
        self.logger = setup_logging(self.data_dir)
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

        # Module 4: Identidad y Quién eres + Perfiles y Personajes
        self.profiles = ProfileManager(data_dir=self.data_dir)
        active_pack = self.profiles.get_active_character()
        self.identity = SoulManager(
            data_dir=self.data_dir,
            user_display_name=self.settings.user_display_name,
            active_character=active_pack,
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
        self.core.persona_overlay_provider = lambda: (
            self.profiles.get_profile(self.settings.active_profile).persona_overlay
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
        self.system_control = WindowsSystemController()
        self.timer_manager = TimerManager(
            on_tick=self._on_timer_tick,
            on_expired=self._on_timer_expired,
        )
        self.weather = WeatherTool(
            http_client=self._shared_http,
            default_city=self.settings.default_weather_city,
        )
        self.web_search = WebSearchTool(http_client=self._shared_http)
        self.calculator = CalculatorTool()
        self.tool_dispatcher = AmadeusToolDispatcher(
            file_ops=self.file_ops,
            screen=self.screen,
            app_launcher=self.toolkit.app_launcher,
            system_control=self.system_control,
            timer_manager=self.timer_manager,
            weather=self.weather,
            web_search=self.web_search,
            mail_calendar=self.toolkit.mail_calendar,
            calculator=self.calculator,
        )
        self.core.tool_dispatcher = self.tool_dispatcher

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

        # Free Asset Library & Custom Gesture Manager
        self.library = AssetLibraryManager(data_dir=self.data_dir)

        # Ephemeral Web UI for Onboarding & Control
        self.web_ui = EphemeralOnboardingServer(system=self)

        # Steamworks & Workshop Bridge
        self.steam = SteamBridge(project_root=Path(__file__).resolve().parents[2])

        # Trim initial startup memory footprint if starting in BACKGROUND_ECO
        if initial_mode == PowerMode.BACKGROUND_ECO:
            self.governor.trim_working_set()

    async def _on_voice_interrupt(self) -> None:
        self.ws_bridge.interrupt_current_turn()
        await self.ws_bridge.broadcast({"type": "interrupt", "turn_id": ""})

    async def _on_timer_tick(self, timer: TimerItem) -> None:
        if hasattr(self, "ws_bridge") and self.ws_bridge is not None:
            await self.ws_bridge.broadcast({"type": "timer_tick", "timer": timer.to_dict()})

    async def _on_timer_expired(self, timer: TimerItem) -> None:
        if hasattr(self, "ws_bridge") and self.ws_bridge is not None:
            await self.ws_bridge.broadcast({"type": "timer_expired", "timer": timer.to_dict()})
            # Trigger spoken confirmation
            asyncio.create_task(
                self.ws_bridge.process_and_stream_turn(
                    f"[SYSTEM_EVENT] El temporizador de {timer.label} acaba de finalizar. Avisa alegremente al usuario."
                )
            )

    async def shutdown(self) -> None:
        self.telegram.stop()
        self.listener.stop()
        self.timer_manager.stop()
        self.listener.unload_idle_models(force=True)
        await self.ws_bridge.stop()
        await self.web_ui.stop()
        self.toolkit.browser.close_ephemeral_if_idle(force=True)
        await self.brain.close()
        await self.memory.honcho.close()
        await self.voice.close()
        self.governor.trim_working_set()
