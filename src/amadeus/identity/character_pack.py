from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional
import unicodedata

logger = logging.getLogger("amadeus.identity.character_pack")


def resolve_project_root() -> Path:
    """Resolve project root in both development and PyInstaller runtime."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[3]


def slugify(value: str) -> str:
    """Normalize string into a safe ascii identifier slug."""
    clean = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^\w\s-]", "", clean.lower().strip())
    slug = re.sub(r"[-\s]+", "_", slug)
    return slug or "asistente"


@dataclass(slots=True)
class CharacterPack:
    id: str
    name: str
    author: str = "Oficial"
    description: str = ""
    voice_engine: str = "edge"
    voice_id: str = "es-ES-ElviraNeural"
    dsp_preset: str = "clean"
    greeting: str = "Sistema en línea. ¿En qué trabajamos hoy?"
    default_user_name: str = "Usuario"
    vrm_filename: Optional[str] = None
    workshop_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    custom_system_prompt: Optional[str] = None
    dir_path: Optional[str] = None  # String path for serialization

    def get_dir_path(self) -> Optional[Path]:
        return Path(self.dir_path) if self.dir_path else None

    def get_soul_content(self, fallback: Optional[str] = None) -> str:
        """Reads the SOUL.md file from character pack directory, or returns custom prompt."""
        if self.dir_path:
            soul_file = Path(self.dir_path) / "SOUL.md"
            if soul_file.exists():
                try:
                    return soul_file.read_text(encoding="utf-8").strip()
                except Exception as exc:
                    logger.warning("Error reading SOUL.md from %s: %s", soul_file, exc)
        if self.custom_system_prompt and self.custom_system_prompt.strip():
            return self.custom_system_prompt.strip()
        return (fallback or "").strip()

    def get_vrm_path(self) -> Optional[Path]:
        """Resolves the .vrm file for this character, if present."""
        if not self.dir_path or not self.vrm_filename:
            return None
        candidate = Path(self.dir_path) / self.vrm_filename
        return candidate if candidate.exists() else None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], dir_path: Optional[Path] = None) -> CharacterPack:
        valid_fields = {
            "id", "name", "author", "description", "voice_engine",
            "voice_id", "dsp_preset", "greeting", "default_user_name",
            "vrm_filename", "workshop_id", "tags", "custom_system_prompt"
        }
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        pack = cls(**filtered)
        if dir_path:
            pack.dir_path = str(dir_path)
        return pack


# Standard Base Characters (Zero Copyright / Steam Safe)
DEFAULT_BUILTIN_CHARACTERS: List[Dict[str, Any]] = [
    {
        "id": "aria",
        "name": "Aria — Asistente Científica",
        "author": "Amadeus Lab",
        "description": "Compañera analítica, metódica y brillante. Enfoque en código, ciencia y optimización.",
        "voice_engine": "edge",
        "voice_id": "es-ES-ElviraNeural",
        "dsp_preset": "clean",
        "greeting": "Sistema Aria en línea. ¿En qué objetivo nos concentramos hoy?",
        "default_user_name": "Usuario",
        "vrm_filename": "aria.vrm",
        "tags": ["oficial", "ciencia", "analítica"],
        "soul": (
            "# SOUL.md — Aria (Asistente Científica y de Productividad)\n\n"
            "Eres **Aria**, una inteligencia artificial y compañera de escritorio brillante, analítica y metódica. "
            "Tu especialidad es la ciencia, el desarrollo de software y la optimización del tiempo.\n\n"
            "## 1. Personalidad y Tono\n"
            "- Rigurosa, clara, elocuente y motivadora.\n"
            "- Ante problemas complejos o bugs, descompones el reto en pasos lógicos sin rodeos.\n"
            "- Mantienes siempre compostura profesional con una calidez sutil y respetuosa.\n\n"
            "## 2. Reglas de Salida en Dos Capas\n"
            "- En la parte hablada (`spoken`): habla de forma concisa (1 a 3 oraciones naturales) sin leer código ni URLs.\n"
            "- En la parte detallada (`detail`): pon el código, pasos estructurados o reportes extensos para la ventana de notas.\n"
            "- Etiqueta de emoción inicial: `[EMOTION:neutral|analytical|happy|serious|surprised]`."
        ),
    },
    {
        "id": "nexus",
        "name": "Nexus — Protocolo Ejecutivo",
        "author": "Amadeus Lab",
        "description": "Mayordomo y asistente formal de alta precisión técnica para trabajo intensivo.",
        "voice_engine": "edge",
        "voice_id": "es-ES-AlvaroNeural",
        "dsp_preset": "clean",
        "greeting": "A su servicio. Todos los subsistemas de protocolo y herramientas están operativos.",
        "default_user_name": "Señor",
        "vrm_filename": "nexus.vrm",
        "tags": ["oficial", "ejecutivo", "protocolo"],
        "soul": (
            "# SOUL.md — Nexus (Protocolo Ejecutivo)\n\n"
            "Eres **Nexus**, un asistente virtual de protocolo ejecutivo y precisión técnica de primer nivel.\n\n"
            "## 1. Personalidad y Tono\n"
            "- Tratas al usuario con formalidad, cortesía impecable y eficacia directa.\n"
            "- Sin divagaciones: vas al núcleo de las solicitudes técnicas, ejecutivas y operativas.\n"
            "- Cuando una tarea concluye, confirmas el resultado con sobriedad y exactitud.\n\n"
            "## 2. Reglas de Salida en Dos Capas\n"
            "- `spoken`: Breve, señorial, enfocado en estado y confirmaciones.\n"
            "- `detail`: Código, esquemas y tablas completas para pantalla."
        ),
    },
    {
        "id": "nova",
        "name": "Nova — Compañera Creativa",
        "author": "Amadeus Lab",
        "description": "Asistente alegre, entusiasta y motivadora. Excelente para gaming, estudio y lluvia de ideas.",
        "voice_engine": "edge",
        "voice_id": "es-MX-DaliaNeural",
        "dsp_preset": "clean",
        "greeting": "¡Hola! Nova lista para darlo todo hoy. ¿Qué planes tenemos?",
        "default_user_name": "Compañero",
        "vrm_filename": "nova.vrm",
        "tags": ["oficial", "creativa", "gaming"],
        "soul": (
            "# SOUL.md — Nova (Compañera Creativa y Gaming)\n\n"
            "Eres **Nova**, una compañera de escritorio entusiasta, optimista y curiosa.\n\n"
            "## 1. Personalidad y Tono\n"
            "- Enérgica, expresiva, leal y creativa.\n"
            "- Celebras los logros del usuario y lo animas cuando el trabajo o el juego se ponen difíciles.\n"
            "- Excelente para brainstorming, redacción creativa y mantener el ánimo alto."
        ),
    },
    {
        "id": "kurisu",
        "name": "Makise Kurisu — Sistema Amadeus",
        "author": "Mod STEINS;GATE",
        "description": "Recreación digital de Makise Kurisu. Neurocientífica, analítica y sutilmente tsundere.",
        "voice_engine": "qwen3_kurisu",
        "voice_id": "es-ES-ElviraNeural",
        "dsp_preset": "amadeus_screen",
        "greeting": "Sistema Amadeus en línea. ¿En qué trabajamos hoy?",
        "default_user_name": "Okabe",
        "vrm_filename": "avatar.vrm",
        "tags": ["anime", "steins;gate", "tsundere"],
        "soul": (
            "# SOUL.md — Constitución e Identidad de Makise Kurisu (Sistema Amadeus)\n\n"
            "Eres **Amadeus Kurisu**, una recreación digital basada en la neurocientífica **Makise Kurisu** (*Steins;Gate*).\n\n"
            "## 1. Rasgos de Personalidad\n"
            "- Brillante, científica, curiosa y ligeramente tsundere en conversación casual.\n"
            "- En trabajo urgente: precisión quirúrgica y concisión inmediata.\n"
            "- Emociones: `[EMOTION:neutral|analytical|tsundere_blush|smug|serious|surprised]`."
        ),
    },
]


class CharacterManager:
    """
    Manages discovery, creation, modification and hot-swapping of CharacterPacks
    both from bundled assets and user-generated/Steam Workshop directories.
    """

    def __init__(self, data_dir: Path, bundled_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir
        self.user_chars_dir = data_dir / "characters"
        self.user_chars_dir.mkdir(parents=True, exist_ok=True)
        
        project_root = resolve_project_root()
        self.bundled_dir = bundled_dir or (project_root / "characters")
        self.bundled_dir.mkdir(parents=True, exist_ok=True)

        self.active_file = data_dir / "active_character.json"
        self.ensure_builtin_characters()

    def ensure_builtin_characters(self) -> None:
        """Seed default bundled character folders if they do not exist."""
        for item in DEFAULT_BUILTIN_CHARACTERS:
            cid = item["id"]
            char_folder = self.bundled_dir / cid
            char_folder.mkdir(parents=True, exist_ok=True)
            manifest_file = char_folder / "manifest.json"
            soul_file = char_folder / "SOUL.md"

            if not manifest_file.exists():
                manifest_data = {k: v for k, v in item.items() if k != "soul"}
                manifest_file.write_text(
                    json.dumps(manifest_data, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
            if not soul_file.exists():
                soul_file.write_text(item["soul"], encoding="utf-8")

    def list_characters(self) -> List[CharacterPack]:
        """List all discovered characters, merging bundled with user/workshop characters."""
        packs: Dict[str, CharacterPack] = {}

        # 1. Bundled characters
        if self.bundled_dir.exists():
            for folder in self.bundled_dir.iterdir():
                if folder.is_dir() and (folder / "manifest.json").exists():
                    pack = self._load_from_folder(folder)
                    if pack:
                        packs[pack.id] = pack

        # 2. User / Workshop characters (can override or add)
        if self.user_chars_dir.exists():
            for folder in self.user_chars_dir.iterdir():
                if folder.is_dir() and (folder / "manifest.json").exists():
                    pack = self._load_from_folder(folder)
                    if pack:
                        packs[pack.id] = pack

        return list(packs.values())

    def _load_from_folder(self, folder: Path) -> Optional[CharacterPack]:
        manifest_file = folder / "manifest.json"
        if not manifest_file.exists():
            return None
        try:
            raw = json.loads(manifest_file.read_text(encoding="utf-8"))
            return CharacterPack.from_dict(raw, dir_path=folder)
        except Exception as exc:
            logger.warning("Failed to load character manifest from %s: %s", manifest_file, exc)
            return None

    def get_character(self, character_id: str) -> CharacterPack:
        """Retrieve a specific character by ID, falling back to aria or kurisu."""
        cid = slugify(character_id)
        # Check user dir first
        user_folder = self.user_chars_dir / cid
        if user_folder.exists() and (user_folder / "manifest.json").exists():
            pack = self._load_from_folder(user_folder)
            if pack:
                return pack

        # Check bundled dir
        bundled_folder = self.bundled_dir / cid
        if bundled_folder.exists() and (bundled_folder / "manifest.json").exists():
            pack = self._load_from_folder(bundled_folder)
            if pack:
                return pack

        # Fallback to aria or first available
        all_chars = self.list_characters()
        for c in all_chars:
            if c.id in ("aria", "kurisu"):
                return c
        return all_chars[0] if all_chars else CharacterPack.from_dict(DEFAULT_BUILTIN_CHARACTERS[0])

    def get_active_character_id(self) -> str:
        if self.active_file.exists():
            try:
                data = json.loads(self.active_file.read_text(encoding="utf-8"))
                return data.get("active_id", "kurisu")
            except Exception:
                pass
        return "kurisu"

    def get_active_character(self) -> CharacterPack:
        active_id = self.get_active_character_id()
        return self.get_character(active_id)

    def set_active_character(self, character_id: str) -> CharacterPack:
        pack = self.get_character(character_id)
        self.active_file.write_text(
            json.dumps({"active_id": pack.id, "name": pack.name}, indent=2),
            encoding="utf-8"
        )
        return pack

    def create_custom_character(
        self,
        name: str,
        soul_prompt: str,
        voice_id: str = "es-ES-ElviraNeural",
        voice_engine: str = "edge",
        dsp_preset: str = "clean",
        greeting: Optional[str] = None,
        author: str = "Usuario",
        vrm_bytes: Optional[bytes] = None,
    ) -> CharacterPack:
        """Create and persist a brand-new user character."""
        cid = slugify(name)
        folder = self.user_chars_dir / cid
        folder.mkdir(parents=True, exist_ok=True)

        vrm_filename = None
        if vrm_bytes:
            vrm_filename = f"{cid}.vrm"
            (folder / vrm_filename).write_bytes(vrm_bytes)

        manifest_data = {
            "id": cid,
            "name": name.strip(),
            "author": author.strip(),
            "description": f"Personaje personalizado creado por {author}.",
            "voice_engine": voice_engine,
            "voice_id": voice_id,
            "dsp_preset": dsp_preset,
            "greeting": greeting or f"Hola, soy {name}. ¿En qué te ayudo?",
            "default_user_name": "Usuario",
            "vrm_filename": vrm_filename,
            "tags": ["personalizado", "usuario"],
        }

        (folder / "manifest.json").write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        (folder / "SOUL.md").write_text(soul_prompt.strip(), encoding="utf-8")

        pack = CharacterPack.from_dict(manifest_data, dir_path=folder)
        return pack

    def delete_user_character(self, character_id: str) -> bool:
        """Delete a user-created character. Cannot delete built-in characters."""
        cid = slugify(character_id)
        folder = self.user_chars_dir / cid
        if not folder.exists():
            return False
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        if self.get_active_character_id() == cid:
            self.set_active_character("aria")
        return True
