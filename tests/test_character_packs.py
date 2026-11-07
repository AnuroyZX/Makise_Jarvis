from __future__ import annotations

from pathlib import Path
import pytest

from amadeus.identity.character_pack import CharacterManager, CharacterPack
from amadeus.identity.soul_manager import SoulManager
from amadeus.identity.profile_manager import ProfileManager


@pytest.fixture
def char_dirs(tmp_path: Path):
    data_dir = tmp_path / "data"
    bundled_dir = tmp_path / "bundled_characters"
    data_dir.mkdir()
    bundled_dir.mkdir()
    return data_dir, bundled_dir


def test_builtin_characters_initialization(char_dirs):
    data_dir, bundled_dir = char_dirs
    manager = CharacterManager(data_dir=data_dir, bundled_dir=bundled_dir)
    chars = manager.list_characters()
    char_ids = {c.id for c in chars}

    assert "aria" in char_ids
    assert "nexus" in char_ids
    assert "nova" in char_ids
    assert "kurisu" in char_ids

    aria = manager.get_character("aria")
    assert "Aria" in aria.name
    assert aria.voice_engine == "edge"
    assert "Aria" in aria.get_soul_content()


def test_switch_and_persist_active_character(char_dirs):
    data_dir, bundled_dir = char_dirs
    manager = CharacterManager(data_dir=data_dir, bundled_dir=bundled_dir)

    default_active = manager.get_active_character()
    assert default_active.id == "kurisu"

    # Switch to nexus
    nexus = manager.set_active_character("nexus")
    assert nexus.id == "nexus"
    assert manager.get_active_character_id() == "nexus"

    # Reload new manager instance to verify persistence in active_character.json
    manager2 = CharacterManager(data_dir=data_dir, bundled_dir=bundled_dir)
    assert manager2.get_active_character_id() == "nexus"
    assert manager2.get_active_character().name == nexus.name


def test_create_and_delete_custom_character(char_dirs):
    data_dir, bundled_dir = char_dirs
    manager = CharacterManager(data_dir=data_dir, bundled_dir=bundled_dir)

    custom = manager.create_custom_character(
        name="Capitán Drake",
        soul_prompt="Eres un capitán pirata cibernético del siglo XXV. Hablas con jerga náutica.",
        voice_id="es-ES-AlvaroNeural",
        voice_engine="edge",
        dsp_preset="clean",
        greeting="¡A la mar, grumete! ¿Qué orden tenemos hoy?",
        author="Capitán",
    )

    assert custom.id == "capitan_drake"
    assert "pirata" in custom.get_soul_content()

    # Verify it appears in list
    all_chars = manager.list_characters()
    assert any(c.id == "capitan_drake" for c in all_chars)

    # Set as active
    manager.set_active_character("capitan_drake")
    assert manager.get_active_character().id == "capitan_drake"

    # Delete custom character
    deleted = manager.delete_user_character("capitan_drake")
    assert deleted is True
    assert manager.get_active_character_id() != "capitan_drake"


def test_soul_manager_integrates_active_character(char_dirs):
    data_dir, bundled_dir = char_dirs
    char_mgr = CharacterManager(data_dir=data_dir, bundled_dir=bundled_dir)
    nexus = char_mgr.get_character("nexus")

    soul_mgr = SoulManager(data_dir=data_dir, active_character=nexus)
    soul_text = soul_mgr.read_soul()
    assert "Nexus" in soul_text

    sys_prompt = soul_mgr.build_system_prompt()
    assert "Nexus" in sys_prompt
    assert "PERFIL DEL USUARIO" in sys_prompt

    # Switch in real time to Aria
    aria = char_mgr.get_character("aria")
    soul_mgr.set_active_character(aria)
    assert "Aria" in soul_mgr.read_soul()


def test_profile_manager_backward_compatibility(char_dirs):
    data_dir, bundled_dir = char_dirs
    prof_mgr = ProfileManager(data_dir=data_dir, bundled_dir=bundled_dir)

    profiles = prof_mgr.list_profiles()
    assert len(profiles) >= 4

    # Test legacy profile retrieval
    prof_kurisu = prof_mgr.get_profile("kurisu_amadeus")
    assert prof_kurisu.id == "kurisu_amadeus"

    # Test universal character retrieval via profile manager
    char_nexus = prof_mgr.get_character("nexus")
    assert char_nexus.id == "nexus"
    assert char_nexus.voice_id == "es-ES-AlvaroNeural"
