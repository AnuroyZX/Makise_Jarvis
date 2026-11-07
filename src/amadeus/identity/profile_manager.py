from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional


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
    Manages 1-click character & audio DSP profiles (`profile.json`) so the user or their
    friend can switch between Amadeus Kurisu, Studio Kurisu, or Fi without editing config files.
    """

    def __init__(self, data_dir: Path) -> None:
        self.profiles_dir = data_dir / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        for pid, prof in BUILTIN_PROFILES.items():
            pfile = self.profiles_dir / f"{pid}.json"
            if not pfile.exists():
                pfile.write_text(
                    json.dumps(asdict(prof), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    def list_profiles(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for pid, prof in BUILTIN_PROFILES.items():
            out.append(
                {
                    "id": pid,
                    "display_name": prof.display_name,
                    "dsp_preset": prof.dsp_preset,
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
        return BUILTIN_PROFILES.get(profile_id, BUILTIN_PROFILES["kurisu_amadeus"])
