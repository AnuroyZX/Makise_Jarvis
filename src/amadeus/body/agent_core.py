from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Protocol

from amadeus.house.resource_governor import PowerMode, ResourceGovernor


class EmotionState(str, Enum):
    """Ready-to-connect emotion states for future VRoid Hub (.vrm) blendshapes."""

    NEUTRAL = "neutral"
    TSUNDERE_BLUSH = "tsundere_blush"
    ANALYTICAL = "analytical"
    SMUG = "smug"
    SERIOUS = "serious"
    SURPRISED = "surprised"


@dataclass(slots=True)
class AgentMessage:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    channel: str = "pc"
    user_id: str = "default_user"
    emotion: EmotionState = EmotionState.NEUTRAL
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AvatarEvent:
    """VRoid Hub bridge event payload so a 3D/2D model can subscribe later without touching Core."""

    event_type: str  # "emotion_change" | "speech_start" | "speech_end" | "mode_change"
    emotion: EmotionState
    text: str = ""
    audio_path: Optional[str] = None


class BrainPort(Protocol):
    async def generate_reply(
        self,
        messages: List[AgentMessage],
        system_prompt: str,
        power_mode: PowerMode,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentMessage: ...


class MemoryPort(Protocol):
    async def retrieve_context(self, user_id: str, query: str) -> str: ...
    async def record_interaction(
        self, user_id: str, user_msg: str, assistant_msg: str
    ) -> None: ...


class IdentityPort(Protocol):
    def build_system_prompt(
        self,
        memory_context: str = "",
        active_skills_summary: str = "",
        urgent_mode: bool = False,
    ) -> str: ...


class SkillsPort(Protocol):
    def build_progressive_context(self, user_query: str) -> str: ...


class AmadeusAgentCore:
    """
    Module 2 (Cuerpo): Hermes-inspired asynchronous orchestrator.
    Connects Module 1 (ResourceGovernor) with Brain (M3), Identity (M4),
    Memory (M5), Skills (M6), Tools (M7), Channels (M8), Voice (M9),
    and exposes an event bus ready for a future VRoid Hub avatar.
    """

    def __init__(
        self,
        governor: ResourceGovernor,
        brain: Optional[BrainPort] = None,
        memory: Optional[MemoryPort] = None,
        identity: Optional[IdentityPort] = None,
        skills: Optional[SkillsPort] = None,
        tool_dispatcher: Optional[Any] = None,
        max_session_history: int = 24,
    ) -> None:
        self.governor = governor
        self.brain = brain
        self.memory = memory
        self.identity = identity
        self.skills = skills
        self.tool_dispatcher = tool_dispatcher
        # Bounded history per ECC Resource Efficiency rules
        self._history: Deque[AgentMessage] = deque(maxlen=max_session_history)
        self._avatar_subscribers: List[Callable[[AvatarEvent], Awaitable[None]]] = []
        self._command_handlers: Dict[
            str, Callable[[str, AgentMessage], Awaitable[str]]
        ] = {}

        # Connect Module 1 -> Module 2 power state listener
        self.governor.register_listener(self._on_power_mode_changed)
        self._register_builtin_commands()

    @property
    def history(self) -> List[AgentMessage]:
        return list(self._history)

    def subscribe_avatar(
        self, handler: Callable[[AvatarEvent], Awaitable[None]]
    ) -> None:
        """Hook for future VRoid Hub model integration."""
        self._avatar_subscribers.append(handler)

    async def _emit_avatar_event(self, event: AvatarEvent) -> None:
        for sub in self._avatar_subscribers:
            await sub(event)

    def _on_power_mode_changed(self, new_mode: PowerMode) -> None:
        """When dropping to BACKGROUND_ECO, prune history to minimum to save RAM."""
        if new_mode == PowerMode.BACKGROUND_ECO and len(self._history) > 10:
            while len(self._history) > 10:
                self._history.popleft()

    def register_command(
        self,
        command: str,
        handler: Callable[[str, AgentMessage], Awaitable[str]],
    ) -> None:
        self._command_handlers[command.lower().lstrip("/")] = handler

    def _register_builtin_commands(self) -> None:
        async def _cmd_status(args: str, msg: AgentMessage) -> str:
            snap = self.governor.snapshot()
            return (
                f"[Amadeus System Status]\n"
                f"• Modo: {snap.power_mode.value}\n"
                f"• RAM Proceso: {snap.process_rss_mb} MB\n"
                f"• Tier LLM: {snap.llm_tier}\n"
                f"• Polling: {snap.polling_interval_sec}s"
            )

        async def _cmd_eco(args: str, msg: AgentMessage) -> str:
            snap = self.governor.switch_mode(PowerMode.BACKGROUND_ECO)
            return f"Modo Eco activado. Memoria recortada a {snap.process_rss_mb} MB."

        async def _cmd_wake(args: str, msg: AgentMessage) -> str:
            snap = self.governor.switch_mode(PowerMode.FOREGROUND_ACTIVE)
            return f"Modo Primer Plano activo ({snap.llm_tier} tier). ¿Qué necesitas?"

        self.register_command("status", _cmd_status)
        self.register_command("eco", _cmd_eco)
        self.register_command("wake", _cmd_wake)

    async def process_user_message(self, incoming: AgentMessage) -> AgentMessage:
        """Main ReAct / message execution pipeline."""
        text = incoming.content.strip()

        # 1. Check fast slash commands (/status, /eco, /wake, /brain, /remember)
        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            cmd_name = parts[0].lower()
            cmd_args = parts[1] if len(parts) > 1 else ""
            if cmd_name in self._command_handlers:
                reply_text = await self._command_handlers[cmd_name](cmd_args, incoming)
                reply = AgentMessage(
                    role="assistant",
                    content=reply_text,
                    channel=incoming.channel,
                    user_id=incoming.user_id,
                    emotion=EmotionState.ANALYTICAL,
                )
                self._history.append(incoming)
                self._history.append(reply)
                return reply

        # 1b. Deterministic Natural-Language Action Dispatcher (Module 7: Files, Apps, Screen)
        if self.tool_dispatcher is not None:
            nl_result = await self.tool_dispatcher.try_natural_language_action(text)
            if nl_result is not None:
                action_text, pending_op = nl_result
                meta: Dict[str, Any] = {}
                if pending_op is not None:
                    meta["pending_op_id"] = pending_op.op_id
                    meta["pending_summary"] = pending_op.summary
                reply = AgentMessage(
                    role="assistant",
                    content=action_text,
                    channel=incoming.channel,
                    user_id=incoming.user_id,
                    emotion=EmotionState.ANALYTICAL,
                    metadata=meta,
                )
                self._history.append(incoming)
                self._history.append(reply)
                if self.memory is not None:
                    await self.memory.record_interaction(
                        incoming.user_id, incoming.content, reply.content
                    )
                await self._emit_avatar_event(
                    AvatarEvent(
                        event_type="emotion_change",
                        emotion=reply.emotion,
                        text=reply.content,
                    )
                )
                return reply

        # 2. Retrieve memory context if Module 5 is connected
        memory_ctx = ""
        if self.memory is not None:
            memory_ctx = await self.memory.retrieve_context(incoming.user_id, text)

        # 3. Build progressive skills summary (Module 6) and system prompt (Module 4)
        skills_ctx = (
            self.skills.build_progressive_context(text)
            if self.skills is not None
            else ""
        )
        if self.tool_dispatcher is not None:
            tools_instr = self.tool_dispatcher.build_tools_prompt_instructions()
            skills_ctx = f"{skills_ctx}\n\n{tools_instr}".strip()

        urgent = any(
            kw in text.lower()
            for kw in ("urgente", "rápido", "error", "bug", "producción")
        )
        system_prompt = (
            self.identity.build_system_prompt(
                memory_context=memory_ctx,
                active_skills_summary=skills_ctx,
                urgent_mode=urgent,
            )
            if self.identity is not None
            else "You are Makise Kurisu (Amadeus System)."
        )

        self._history.append(incoming)

        # 4. Generate reply via Module 3 (Brain)
        if self.brain is not None:
            reply = await self.brain.generate_reply(
                messages=list(self._history),
                system_prompt=system_prompt,
                power_mode=self.governor.mode,
            )
            if self.tool_dispatcher is not None:
                tool_call = self.tool_dispatcher.extract_tool_call(reply.content)
                if tool_call is not None:
                    t_name = str(tool_call.get("tool") or "")
                    t_args = tool_call.get("args") or {}
                    t_res, pending_op = await self.tool_dispatcher.execute_tool_call(
                        t_name, t_args
                    )
                    if pending_op is not None:
                        reply.metadata["pending_op_id"] = pending_op.op_id
                        reply.metadata["pending_summary"] = pending_op.summary
                        reply.content = f"[emotion:serious] {pending_op.summary}"
                    else:
                        reply.content = f"[emotion:smug] [gesture:nod] Listo.\n---DETALLE---\n{t_res}"
        else:
            reply = AgentMessage(
                role="assistant",
                content="El módulo Cerebro aún no está conectado, pero el núcleo Amadeus te escucha.",
                channel=incoming.channel,
                user_id=incoming.user_id,
                emotion=EmotionState.TSUNDERE_BLUSH,
            )

        self._history.append(reply)

        # 5. Persist memory asynchronously in Module 5
        if self.memory is not None:
            await self.memory.record_interaction(
                incoming.user_id, incoming.content, reply.content
            )

        # 6. Emit VRoid-ready avatar event
        await self._emit_avatar_event(
            AvatarEvent(
                event_type="emotion_change",
                emotion=reply.emotion,
                text=reply.content,
            )
        )
        return reply
