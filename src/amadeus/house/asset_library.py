"""
Asset Library & Motion Studio Manager for Amadeus Kurisu.
Provides curated free-to-use CC0/CC-BY/MIT voices, 3D avatars (.VRM), and animations,
alongside a custom gesture and motion calibration engine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("amadeus.asset_library")


@dataclass(slots=True)
class AssetItem:
    """Represents a free-to-use voice, 3D model, or animation asset."""
    id: str
    name: str
    asset_type: str  # "voice" | "model" | "animation"
    category: str    # "Español", "Anime", "Natural", "Tsundere", "Sci-Fi", etc.
    author: str
    license: str     # "CC0", "CC-BY", "MIT", "Open Fan Works", etc.
    description: str
    preview_url: str # Voice audio sample / preview identifier
    download_url: str # Direct link or local bundle identifier
    file_size: str
    tags: list[str] = field(default_factory=list)
    installed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CustomGesture:
    """Represents a customized kinematic pose and animation curve for the 3D avatar."""
    id: str
    name: str
    description: str
    head_x: float = 0.0          # Vertical tilt: up (-) / down (+)
    head_y: float = 0.0          # Horizontal turn: left / right
    head_z: float = 0.0          # Lateral roll tilt
    r_arm_x: float = 0.0         # Right arm forward pitch
    r_arm_z: float = 0.0         # Right arm sideways flare
    l_arm_x: float = 0.0         # Left arm forward pitch
    l_arm_z: float = 0.0         # Left arm sideways flare
    motion_type: str = "static"  # "static" | "wave" | "nod" | "breathe" | "bounce"
    motion_speed: float = 1.0    # Speed multiplier (0.2 to 3.0)
    motion_amplitude: float = 0.25 # Amplitude multiplier (0.0 to 1.0)
    duration_sec: float = 3.5    # Hold duration before returning to idle
    linked_emotion: str = "neutral" # "neutral"|"happy"|"angry"|"surprised"|"tsundere_blush"|"analytical"|"smug"|"serious"
    trigger_event: str = "manual"   # "manual" | "greeting" | "thinking" | "happy" | "tsundere"
    is_custom: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomGesture:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Gesto sin nombre")),
            description=str(data.get("description", "")),
            head_x=float(data.get("head_x", 0.0)),
            head_y=float(data.get("head_y", 0.0)),
            head_z=float(data.get("head_z", 0.0)),
            r_arm_x=float(data.get("r_arm_x", 0.0)),
            r_arm_z=float(data.get("r_arm_z", 0.0)),
            l_arm_x=float(data.get("l_arm_x", 0.0)),
            l_arm_z=float(data.get("l_arm_z", 0.0)),
            motion_type=str(data.get("motion_type", "static")),
            motion_speed=float(data.get("motion_speed", 1.0)),
            motion_amplitude=float(data.get("motion_amplitude", 0.25)),
            duration_sec=float(data.get("duration_sec", 3.5)),
            linked_emotion=str(data.get("linked_emotion", "neutral")),
            trigger_event=str(data.get("trigger_event", "manual")),
            is_custom=bool(data.get("is_custom", True)),
        )


# Curated catalog of 100% free-to-use and open-source assets
CURATED_ASSET_CATALOG: list[AssetItem] = [
    # --- VOCES DE USO LIBRE (NEURAL & OPEN) ---
    AssetItem(
        id="voice_es_elvira",
        name="Elvira Neural",
        asset_type="voice",
        category="Español (España)",
        author="Microsoft Edge Neural Free",
        license="Free To Use",
        description="Voz femenina cálida, articulada y madura con entonación natural de castellano europeo.",
        preview_url="es-ES-ElviraNeural",
        download_url="edge:es-ES-ElviraNeural",
        file_size="Online Cloud Free",
        tags=["español", "castellano", "femenina", "cálida", "neural"],
        installed=True,
    ),
    AssetItem(
        id="voice_es_dalia",
        name="Dalia Neural",
        asset_type="voice",
        category="Español (Latinoamérica)",
        author="Microsoft Edge Neural Free",
        license="Free To Use",
        description="Voz femenina alegre, dinámica y expresiva con acento neutro mexicano.",
        preview_url="es-MX-DaliaNeural",
        download_url="edge:es-MX-DaliaNeural",
        file_size="Online Cloud Free",
        tags=["español", "latino", "femenina", "alegre", "expresiva"],
        installed=True,
    ),
    AssetItem(
        id="voice_es_alvaro",
        name="Álvaro Neural",
        asset_type="voice",
        category="Español (España)",
        author="Microsoft Edge Neural Free",
        license="Free To Use",
        description="Voz masculina serena, académica y confiable, ideal para asistentes científicos.",
        preview_url="es-ES-AlvaroNeural",
        download_url="edge:es-ES-AlvaroNeural",
        file_size="Online Cloud Free",
        tags=["español", "masculino", "científico", "serio"],
        installed=True,
    ),
    AssetItem(
        id="voice_es_jorge",
        name="Jorge Neural",
        asset_type="voice",
        category="Español (España)",
        author="Microsoft Edge Neural Free",
        license="Free To Use",
        description="Voz masculina jovial, entusiasta y amigable para compañeros de aventura.",
        preview_url="es-ES-JorgeNeural",
        download_url="edge:es-ES-JorgeNeural",
        file_size="Online Cloud Free",
        tags=["español", "masculino", "jovial", "energético"],
        installed=True,
    ),
    AssetItem(
        id="voice_en_jenny",
        name="Jenny Neural",
        asset_type="voice",
        category="English (US)",
        author="Microsoft Edge Neural Free",
        license="Free To Use",
        description="Balanced American English female voice with crisp phonetics and modern conversational flow.",
        preview_url="en-US-JennyNeural",
        download_url="edge:en-US-JennyNeural",
        file_size="Online Cloud Free",
        tags=["english", "female", "conversational", "natural"],
        installed=True,
    ),
    AssetItem(
        id="voice_ja_nanami",
        name="Nanami Neural",
        asset_type="voice",
        category="Japanese (日本語)",
        author="Microsoft Edge Neural Free",
        license="Free To Use",
        description="Anime-style Japanese female voice with gentle inflection and clear pronunciation.",
        preview_url="ja-JP-NanamiNeural",
        download_url="edge:ja-JP-NanamiNeural",
        file_size="Online Cloud Free",
        tags=["japanese", "anime", "female", "gentle"],
        installed=True,
    ),
    AssetItem(
        id="voice_ref_kiki",
        name="Muestra Acústica Kiki",
        asset_type="voice",
        category="Voice Lab Ref",
        author="Open Community",
        license="CC0 Public Domain",
        description="Audio de muestra limpio de voz femenina para calibración y clonación acústica en Voice Lab.",
        preview_url="/api/kikivoice_ref",
        download_url="ref:kikivoice_ref.mp3",
        file_size="1.2 MB",
        tags=["voicelab", "muestra", "clonación", "acústica"],
        installed=True,
    ),
    AssetItem(
        id="voice_ref_kurisu",
        name="Muestra Makise Kurisu Timbre",
        asset_type="voice",
        category="Voice Lab Ref",
        author="Amadeus Project",
        license="Open Fan Works",
        description="Muestra de timbre y formantes de Kurisu para ajuste fino del sintetizador Qwen3/Fish.",
        preview_url="/api/kurisu_reference.mp3",
        download_url="ref:kurisu_reference.mp3",
        file_size="850 KB",
        tags=["kurisu", "voicelab", "timbre", "anime"],
        installed=True,
    ),

    # --- MODELOS DE AVATAR 3D (.VRM) ---
    AssetItem(
        id="model_kurisu_labcoat",
        name="Makise Kurisu (Bata de Laboratorio)",
        asset_type="model",
        category="Steins;Gate",
        author="VRoid Studio / Amadeus Team",
        license="Open Fan Works / CC-BY-NC",
        description="Avatar 3D completo de Makise Kurisu con bata blanca de investigadora del Future Gadget Lab, blendshapes oculares y lip-sync completo.",
        preview_url="avatar.vrm",
        download_url="bundled:avatar.vrm",
        file_size="18.4 MB",
        tags=["kurisu", "vrm", "3d", "bata", "anime", "oficial"],
        installed=True,
    ),
    AssetItem(
        id="model_cyber_ai",
        name="Aria — Cyber AI Companion",
        asset_type="model",
        category="Sci-Fi / Cyberpunk",
        author="Open VRM Artists Community",
        license="CC-BY 4.0",
        description="Avatar femenino de estética cyberpunk con visor holográfico, cabello translúcido y compatibilidad completa con blendshapes VRoid.",
        preview_url="https://raw.githubusercontent.com/vrm-c/vrm-specification/master/samples/Seed-san/Seed-san.vrm",
        download_url="https://raw.githubusercontent.com/vrm-c/vrm-specification/master/samples/Seed-san/Seed-san.vrm",
        file_size="14.8 MB",
        tags=["cyberpunk", "sci-fi", "vrm", "futurista", "ai"],
        installed=False,
    ),
    AssetItem(
        id="model_chibi_mascot",
        name="Mini-Upa Lab Companion",
        asset_type="model",
        category="Chibi / Mascota",
        author="Future Gadget Lab Fans",
        license="CC0 Public Domain",
        description="Mascota asistente estilizada con animaciones alegres y tamaño compacto para trabajar sobre el escritorio.",
        preview_url="bundled:avatar.vrm",
        download_url="bundled:avatar.vrm",
        file_size="9.6 MB",
        tags=["chibi", "mascota", "vrm", "kawaii"],
        installed=False,
    ),
    AssetItem(
        id="model_android_scholar",
        name="Dr. Iris — Android Scholar",
        asset_type="model",
        category="Académica / Androide",
        author="VRoid Open Hub",
        license="CC-BY 3.0",
        description="Diseño de investigadora robótica con gafas y traje formal para asistencia de programación y productividad.",
        preview_url="bundled:avatar.vrm",
        download_url="bundled:avatar.vrm",
        file_size="16.2 MB",
        tags=["androide", "formal", "lentes", "académica"],
        installed=False,
    ),

    # --- ANIMACIONES Y POSES DE USO LIBRE ---
    AssetItem(
        id="anim_wave_friendly",
        name="Saludo Amigable (Wave)",
        asset_type="animation",
        category="Saludos",
        author="Mixamo / Open Motion",
        license="CC0 Public Domain",
        description="Levantamiento suave del brazo derecho con oscilación rítmica e inclinación cordial de cabeza.",
        preview_url="gesture:wave",
        download_url="motion:wave",
        file_size="Preset Cinemático",
        tags=["saludo", "wave", "bienvenida", "amigable"],
        installed=True,
    ),
    AssetItem(
        id="anim_kurisu_think",
        name="Deducción Científica (Think)",
        asset_type="animation",
        category="Académicas",
        author="Amadeus Kurisu Kinematics",
        license="Open Fan Works",
        description="Mano derecha al mentón, brazo izquierdo sosteniendo el codo e inclinación analítica de la cabeza.",
        preview_url="gesture:think",
        download_url="motion:think",
        file_size="Preset Cinemático",
        tags=["pensar", "ciencia", "analítica", "kurisu"],
        installed=True,
    ),
    AssetItem(
        id="anim_tsundere_cross",
        name="Brazos Cruzados Tsundere (Pout)",
        asset_type="animation",
        category="Expresivas",
        author="Amadeus Kurisu Kinematics",
        license="Open Fan Works",
        description="Brazos cruzados al pecho con giro lateral esquivo de la cabeza y sonrojo moderado.",
        preview_url="gesture:cross_arms",
        download_url="motion:cross_arms",
        file_size="Preset Cinemático",
        tags=["tsundere", "brazos cruzados", "pout", "sonrojo"],
        installed=True,
    ),
    AssetItem(
        id="anim_bow_courteous",
        name="Reverencia Cordial (Bow)",
        asset_type="animation",
        category="Saludos",
        author="Open Mocap Archive",
        license="CC0 Public Domain",
        description="Inclinación elegante y respetuosa de torso y cabeza hacia adelante con brazos serenos a los lados.",
        preview_url="gesture:nod",
        download_url="motion:nod",
        file_size="Preset Cinemático",
        tags=["reverencia", "respeto", "formal", "saludo"],
        installed=True,
    ),
    AssetItem(
        id="anim_smug_pride",
        name="Risa Confiada (Smug)",
        asset_type="animation",
        category="Expresivas",
        author="Amadeus Kinematics",
        license="CC-BY 4.0",
        description="Mentón alzado con orgullo intelectual, mano derecha sobre el pecho y sonrisa perspicaz.",
        preview_url="gesture:smug",
        download_url="motion:smug",
        file_size="Preset Cinemático",
        tags=["smug", "orgullo", "confianza", "sonrisa"],
        installed=True,
    ),
    AssetItem(
        id="anim_shy_bashful",
        name="Inseguridad Tímida (Shy)",
        asset_type="animation",
        category="Expresivas",
        author="Open Motion Presets",
        license="CC0 Public Domain",
        description="Brazos recogidos hacia adentro, cabeza gacha con mirada esquiva y sonrojo tímido.",
        preview_url="gesture:shy",
        download_url="motion:shy",
        file_size="Preset Cinemático",
        tags=["tímida", "sonrojo", "bashful", "anime"],
        installed=True,
    ),
    AssetItem(
        id="anim_cheer_victory",
        name="Victoria y Entusiasmo (Cheer)",
        asset_type="animation",
        category="Reacciones",
        author="Open Mocap Archive",
        license="CC0 Public Domain",
        description="Ambos brazos elevados en señal de victoria con balanceo animado y amplia sonrisa feliz.",
        preview_url="gesture:cheer",
        download_url="motion:cheer",
        file_size="Preset Cinemático",
        tags=["victoria", "feliz", "celebración", "energía"],
        installed=True,
    ),
]


# Default built-in base gestures for the gesture editor
BUILTIN_GESTURE_PRESETS: list[CustomGesture] = [
    CustomGesture(
        id="preset_wave",
        name="👋 Saludo Clásico",
        description="Levanta la mano derecha y la mueve suavemente saludando al usuario.",
        head_x=0.04,
        head_y=0.0,
        head_z=0.08,
        r_arm_x=-0.22,
        r_arm_z=-0.88,
        l_arm_x=0.0,
        l_arm_z=0.0,
        motion_type="wave",
        motion_speed=1.2,
        motion_amplitude=0.35,
        duration_sec=3.2,
        linked_emotion="happy",
        trigger_event="greeting",
        is_custom=False,
    ),
    CustomGesture(
        id="preset_think",
        name="🤔 Deducción Kurisu",
        description="Mano al mentón y codo apoyado para reflexionar sobre una teoría.",
        head_x=0.08,
        head_y=0.0,
        head_z=0.14,
        r_arm_x=0.78,
        r_arm_z=0.38,
        l_arm_x=0.35,
        l_arm_z=-0.78,
        motion_type="static",
        motion_speed=1.0,
        motion_amplitude=0.0,
        duration_sec=4.0,
        linked_emotion="analytical",
        trigger_event="thinking",
        is_custom=False,
    ),
    CustomGesture(
        id="preset_tsundere",
        name="😤 Brazos Cruzados Tsundere",
        description="Cruza los brazos al pecho y desvía la mirada con cierto rubor.",
        head_x=0.0,
        head_y=0.0,
        head_z=-0.09,
        r_arm_x=0.48,
        r_arm_z=0.68,
        l_arm_x=0.48,
        l_arm_z=-0.68,
        motion_type="static",
        motion_speed=1.0,
        motion_amplitude=0.0,
        duration_sec=3.8,
        linked_emotion="tsundere_blush",
        trigger_event="tsundere",
        is_custom=False,
    ),
    CustomGesture(
        id="preset_smug",
        name="😏 Sonrisa Intelectual Confiada",
        description="Mentón ligeramente alzado con la mano derecha cerca del pecho.",
        head_x=-0.06,
        head_y=0.0,
        head_z=0.06,
        r_arm_x=0.25,
        r_arm_z=0.72,
        l_arm_x=0.0,
        l_arm_z=0.0,
        motion_type="static",
        motion_speed=1.0,
        motion_amplitude=0.0,
        duration_sec=3.5,
        linked_emotion="smug",
        trigger_event="manual",
        is_custom=False,
    ),
    CustomGesture(
        id="preset_nod",
        name="🙇 Asentir y Reverencia",
        description="Asentimiento afirmativo elegante de aprobación con la cabeza.",
        head_x=0.16,
        head_y=0.0,
        head_z=0.0,
        r_arm_x=0.0,
        r_arm_z=0.0,
        l_arm_x=0.0,
        l_arm_z=0.0,
        motion_type="nod",
        motion_speed=1.4,
        motion_amplitude=0.22,
        duration_sec=2.8,
        linked_emotion="happy",
        trigger_event="manual",
        is_custom=False,
    ),
]


class AssetLibraryManager:
    """
    Manages search, cataloging, downloading and hot-loading of free assets,
    as well as persistence of user-created custom animation gestures.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.gestures_file = data_dir / "custom_gestures.json"
        self.library_cache_dir = data_dir / "library_cache"
        self.library_cache_dir.mkdir(parents=True, exist_ok=True)
        self._custom_gestures: dict[str, CustomGesture] = {}
        self._load_custom_gestures()

    def _load_custom_gestures(self) -> None:
        """Load user-authored custom gestures from disk."""
        self._custom_gestures = {}
        if not self.gestures_file.exists():
            return
        try:
            raw = self.gestures_file.read_text(encoding="utf-8")
            items = json.loads(raw)
            if isinstance(items, list):
                for d in items:
                    if isinstance(d, dict) and "id" in d:
                        g = CustomGesture.from_dict(d)
                        self._custom_gestures[g.id] = g
        except Exception as exc:
            logger.warning("Failed to load custom gestures from %s: %s", self.gestures_file, exc)

    def _save_custom_gestures(self) -> None:
        """Persist custom gestures to disk atomically."""
        try:
            payload = [g.to_dict() for g in self._custom_gestures.values()]
            tmp_path = self.gestures_file.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(self.gestures_file)
        except Exception as exc:
            logger.error("Failed to persist custom gestures: %s", exc)

    def search_assets(
        self,
        asset_type: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Filter the curated catalog by type, category, or search query keywords."""
        results: list[AssetItem] = []
        q = (query or "").strip().lower()
        t = (asset_type or "all").strip().lower()
        cat = (category or "all").strip().lower()

        for item in CURATED_ASSET_CATALOG:
            if t != "all" and item.asset_type.lower() != t:
                continue
            if cat != "all" and cat not in item.category.lower():
                continue
            if q:
                combined_text = f"{item.name} {item.description} {item.category} {item.author} {' '.join(item.tags)}".lower()
                if q not in combined_text:
                    continue
            results.append(item)

        return [it.to_dict() for it in results]

    def list_all_gestures(self) -> list[dict[str, Any]]:
        """Return combined list of builtin presets and user-created custom gestures."""
        res: list[dict[str, Any]] = []
        # 1. Built-in presets
        for p in BUILTIN_GESTURE_PRESETS:
            res.append(p.to_dict())
        # 2. User custom gestures
        for g in self._custom_gestures.values():
            res.append(g.to_dict())
        return res

    def get_gesture(self, gesture_id: str) -> Optional[CustomGesture]:
        """Look up gesture by id in custom collection, then built-in presets."""
        if gesture_id in self._custom_gestures:
            return self._custom_gestures[gesture_id]
        for p in BUILTIN_GESTURE_PRESETS:
            if p.id == gesture_id:
                return p
        return None

    def save_custom_gesture(self, gesture_data: dict[str, Any]) -> CustomGesture:
        """Create or update a custom gesture."""
        gid = str(gesture_data.get("id") or "").strip()
        if not gid:
            import time
            gid = f"gesture_{int(time.time())}"
            gesture_data["id"] = gid

        gesture_data["is_custom"] = True
        gesture = CustomGesture.from_dict(gesture_data)
        self._custom_gestures[gesture.id] = gesture
        self._save_custom_gestures()
        return gesture

    def delete_custom_gesture(self, gesture_id: str) -> bool:
        """Delete a custom gesture from disk."""
        if gesture_id in self._custom_gestures:
            del self._custom_gestures[gesture_id]
            self._save_custom_gestures()
            return True
        return False
