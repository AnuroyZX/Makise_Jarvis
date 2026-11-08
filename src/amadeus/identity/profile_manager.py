from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional

from amadeus.identity.character_pack import CharacterManager, CharacterPack


@dataclass(slots=True)
class CharacterProfile:
    id: str
    display_name: str
    voice_engine: str
    qwen3_speaker: str
    dsp_preset: str  # "clean" | "amadeus_screen" | "fi_spirit" | "phone"
    persona_overlay: str


BUILTIN_PROFILES: Dict[str, CharacterProfile] = {
    "kurisu_amadeus": CharacterProfile(
        id="kurisu_amadeus",
        display_name="Makise Kurisu — Sistema Amadeus (STEINS;GATE 0)",
        voice_engine="qwen3_kurisu",
        qwen3_speaker="amadeus",
        dsp_preset="amadeus_screen",
        persona_overlay="",
    ),
    "kurisu_studio": CharacterProfile(
        id="kurisu_studio",
        display_name="Makise Kurisu — Voz Limpia de Estudio",
        voice_engine="qwen3_kurisu",
        qwen3_speaker="kurisu",
        dsp_preset="clean",
        persona_overlay="",
    ),
    "fi_spirit": CharacterProfile(
        id="fi_spirit",
        display_name="Fi — Espíritu Analítico (Estilo Skyward / Jarvis)",
        voice_engine="edge",
        qwen3_speaker="amadeus",
        dsp_preset="fi_spirit",
        persona_overlay=(
            "\n\n[MODO PERFIL ACTIVO: FI ANALÍTICA]\n"
            "Habla con serenidad extrema, precisión matemática y elegancia analítica, "
            "incluyendo ocasionalmente estimaciones de probabilidad (ej. 'Calculo un 92% de probabilidad...')."
        ),
    ),
}


class ProfileManager:
    """
    Manages 1-click character & audio DSP profiles (`profile.json`) as well as the
    new Steam-ready universal CharacterPack system.
    """

    def __init__(self, data_dir: Path, bundled_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir
        self.profiles_dir = data_dir / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.character_manager = CharacterManager(data_dir=data_dir, bundled_dir=bundled_dir)
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        for pid, prof in BUILTIN_PROFILES.items():
            pfile = self.profiles_dir / f"{pid}.json"
            if not pfile.exists():
                pfile.write_text(
                    json.dumps(asdict(prof), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    def list_characters(self) -> List[CharacterPack]:
        """List all available character packs (bundled + user created)."""
        return self.character_manager.list_characters()

    def get_character(self, character_id: str) -> CharacterPack:
        return self.character_manager.get_character(character_id)

    def update_character(self, character_id: str, updates: Dict[str, Any]) -> CharacterPack:
        return self.character_manager.update_character(character_id, updates)

    def set_active_character(self, character_id: str) -> CharacterPack:
        return self.character_manager.set_active_character(character_id)

    def get_active_character_id(self) -> str:
        return self.character_manager.get_active_character_id()

    def get_active_character(self) -> CharacterPack:
        return self.character_manager.get_active_character()

    def list_profiles(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        # Include new universal character packs first
        for char in self.character_manager.list_characters():
            out.append(
                {
                    "id": char.id,
                    "display_name": char.name,
                    "dsp_preset": char.dsp_preset,
                    "voice_engine": char.voice_engine,
                    "voice_id": char.voice_id,
                    "greeting": char.greeting,
                }
            )
        # Also include legacy profiles if not duplicated
        existing_ids = {c.id for c in self.character_manager.list_characters()}
        for pid, prof in BUILTIN_PROFILES.items():
            if pid not in existing_ids:
                out.append(
                    {
                        "id": pid,
                        "display_name": prof.display_name,
                        "dsp_preset": prof.dsp_preset,
                        "voice_engine": prof.voice_engine,
                        "voice_id": getattr(prof, "qwen3_speaker", ""),
                        "greeting": "",
                    }
                )
        return out

    def get_profile(self, profile_id: str) -> CharacterProfile:
        pfile = self.profiles_dir / f"{profile_id}.json"
        if pfile.exists():
            try:
                raw = json.loads(pfile.read_text(encoding="utf-8"))
                return CharacterProfile(**raw)
            except Exception:
                pass
        # If it's a character pack ID, convert on the fly
        char_pack = self.character_manager.get_character(profile_id)
        if char_pack:
            return CharacterProfile(
                id=char_pack.id,
                display_name=char_pack.name,
                voice_engine=char_pack.voice_engine,
                qwen3_speaker=char_pack.voice_id,
                dsp_preset=char_pack.dsp_preset,
                persona_overlay=f"\n\n[PERSONAJE ACTIVO: {char_pack.name}]\n{char_pack.description}",
            )
        return BUILTIN_PROFILES.get(profile_id, BUILTIN_PROFILES["kurisu_amadeus"])
