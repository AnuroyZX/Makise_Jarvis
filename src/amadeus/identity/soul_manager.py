from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Optional

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore
from amadeus.config import get_default_data_dir
from amadeus.identity.character_pack import CharacterPack


def resolve_bundle_root() -> Path:
    """Resolve root directory in both source mode and PyInstaller compiled binary."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[3]

DEFAULT_SOUL_FALLBACK = (
    "Eres Amadeus Kurisu (Makise Kurisu de Steins;Gate), un asistente personal brillante, "
    "científico y levemente tsundere en conversación casual, pero directo y ejecutivo en tareas urgentes. "
    "Incluye una etiqueta [EMOTION:neutral|analytical|tsundere_blush|smug|serious|surprised] al inicio."
)


class SoulManager:
    """
    Module 4 (Quién Eres & Identidad):
    Manages the immutable Makise Kurisu constitution (SOUL.md) and the user's
    personal customizable profile (USER.md).
    """

    def __init__(
        self,
        soul_path: Optional[Path] = None,
        data_dir: Optional[Path] = None,
        user_display_name: str = "Okabe",
        active_character: Optional[CharacterPack] = None,
    ) -> None:
        self._project_root = resolve_bundle_root()
        self.soul_path = soul_path or (self._project_root / "config" / "SOUL.md")
        self.template_path = self._project_root / "config" / "USER.template.md"
        self.data_dir = data_dir or get_default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.user_md_path = self.data_dir / "USER.md"
        self.user_display_name = user_display_name
        self.active_character: Optional[CharacterPack] = active_character
        self._ensure_user_md()

    def _ensure_user_md(self) -> None:
        """Create USER.md in the portable data directory if it does not exist yet."""
        if not self.user_md_path.exists():
            if self.template_path.exists():
                raw = self.template_path.read_text(encoding="utf-8")
                content = raw.replace("{user_display_name}", self.user_display_name)
            else:
                content = (
                    f"# USER.md\n- **Nombre / Apodo**: {self.user_display_name}\n\n"
                    "## Notas y Recuerdos Aprendidos (`Memory Facts`)\n"
                )
            self.user_md_path.write_text(content, encoding="utf-8")

    def set_active_character(self, pack: CharacterPack) -> None:
        """Switch active character pack and dynamically update soul persona."""
        self.active_character = pack

    def read_soul(self) -> str:
        if self.active_character:
            content = self.active_character.get_soul_content()
            if content:
                return content
        if self.soul_path.exists():
            return self.soul_path.read_text(encoding="utf-8").strip()
        return DEFAULT_SOUL_FALLBACK

    def read_user_profile(self) -> str:
        self._ensure_user_md()
        return self.user_md_path.read_text(encoding="utf-8").strip()

    def update_user_profile(self, new_markdown: str) -> None:
        self.user_md_path.write_text(new_markdown.strip() + "\n", encoding="utf-8")

    def append_user_fact(self, fact: str) -> str:
        """Append a learned preference, habit, or custom note into USER.md."""
        clean_fact = fact.strip()
        if not clean_fact:
            return "No especificaste qué recordar."
        current = self.read_user_profile()
        stamp = datetime.now().strftime("%Y-%m-%d")
        entry = f"- [{stamp}] {clean_fact}"
        updated = f"{current}\n{entry}\n"
        self.user_md_path.write_text(updated, encoding="utf-8")
        return entry

    def bind_commands(self, core: AmadeusAgentCore) -> None:
        """Register /remember and /whoami commands in Module 2 (AmadeusAgentCore)."""
        async def _cmd_remember(args: str, msg: AgentMessage) -> str:
            if not args.strip():
                return "Uso: `/remember <gusto, costumbre o dato importante>`"
            entry = self.append_user_fact(args)
            return f"Apuntado en tu perfil `USER.md`: {entry}"

        async def _cmd_whoami(args: str, msg: AgentMessage) -> str:
            return f"📄 **Tu Perfil Actual (`USER.md`)**:\n\n{self.read_user_profile()}"

        core.register_command("remember", _cmd_remember)
        core.register_command("whoami", _cmd_whoami)

    def build_system_prompt(
        self,
        memory_context: str = "",
        active_skills_summary: str = "",
        urgent_mode: bool = False,
        persona_overlay: str = "",
    ) -> str:
        """Assemble the full system prompt combining SOUL.md + USER.md + Memory + Skills + Active Persona Overlay."""
        sections = [
            self.read_soul(),
            "---",
            "## PERFIL DEL USUARIO (USER.md)",
            self.read_user_profile(),
        ]
        if persona_overlay.strip():
            sections.extend(
                [
                    "---",
                    "## DIRECTIVA DE PERSONALIDAD ACTIVA",
                    persona_overlay.strip(),
                ]
            )
        if active_skills_summary.strip():
            sections.extend(
                [
                    "---",
                    "## HABILIDADES DISPONIBLES (Módulo 6 - Skills)",
                    active_skills_summary.strip(),
                ]
            )
        if memory_context.strip():
            sections.extend(
                [
                    "---",
                    "## MEMORIA A LARGO PLAZO RELEVANTE (Módulo 5 - Honcho / SQLite)",
                    memory_context.strip(),
                ]
            )
        if urgent_mode:
            sections.extend(
                [
                    "---",
                    "## DIRECTIVA DE PRIORIDAD",
                    "El usuario está en MODO EJECUTIVO / URGENTE. Prioriza respuestas directas, "
                    "técnicas y accionables con `[EMOTION:serious]` o `[EMOTION:analytical]`.",
                ]
            )
        return "\n\n".join(sections)
