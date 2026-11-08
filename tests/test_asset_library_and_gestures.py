from __future__ import annotations

import json
from pathlib import Path
import pytest
import httpx

from amadeus.house.asset_library import (
    AssetItem,
    AssetLibraryManager,
    CustomGesture,
    CURATED_ASSET_CATALOG,
    BUILTIN_GESTURE_PRESETS,
)
from amadeus.system_builder import AmadeusSystem
from amadeus.house.resource_governor import PowerMode


@pytest.mark.asyncio
async def test_asset_library_manager_catalog(tmp_path: Path):
    manager = AssetLibraryManager(data_dir=tmp_path)

    # 1. Test search all
    all_assets = manager.search_assets()
    assert len(all_assets) >= len(CURATED_ASSET_CATALOG)

    # 2. Test filter by type
    voices = manager.search_assets(asset_type="voice")
    assert all(a["asset_type"] == "voice" for a in voices)
    assert len(voices) > 0

    models = manager.search_assets(asset_type="model")
    assert all(a["asset_type"] == "model" for a in models)
    assert len(models) > 0

    animations = manager.search_assets(asset_type="animation")
    assert all(a["asset_type"] == "animation" for a in animations)
    assert len(animations) > 0

    # 3. Test text query
    kurisu_items = manager.search_assets(query="kurisu")
    assert any("kurisu" in k["name"].lower() or "kurisu" in k["description"].lower() for k in kurisu_items)


@pytest.mark.asyncio
async def test_custom_gesture_crud_and_persistence(tmp_path: Path):
    manager = AssetLibraryManager(data_dir=tmp_path)

    # List builtin presets
    initial = manager.list_all_gestures()
    assert len(initial) >= len(BUILTIN_GESTURE_PRESETS)

    # Create new custom gesture
    new_data = {
        "id": "my_test_gesture",
        "name": "Prueba de Saludo",
        "description": "Gesto de prueba unitaria",
        "head_x": 0.12,
        "head_z": 0.05,
        "r_arm_x": -0.4,
        "r_arm_z": -0.8,
        "motion_type": "wave",
        "motion_speed": 1.5,
        "motion_amplitude": 0.4,
        "linked_emotion": "happy",
        "trigger_event": "greeting",
    }
    saved = manager.save_custom_gesture(new_data)
    assert saved.id == "my_test_gesture"
    assert saved.is_custom is True
    assert saved.head_x == 0.12

    # Verify persistent reloading from disk
    manager2 = AssetLibraryManager(data_dir=tmp_path)
    loaded = manager2.get_gesture("my_test_gesture")
    assert loaded is not None
    assert loaded.name == "Prueba de Saludo"
    assert loaded.motion_speed == 1.5

    # Delete gesture
    deleted = manager2.delete_custom_gesture("my_test_gesture")
    assert deleted is True
    assert manager2.get_gesture("my_test_gesture") is None


@pytest.mark.asyncio
async def test_library_and_gestures_http_endpoints(tmp_path: Path):
    system = AmadeusSystem(
        data_dir=tmp_path,
        initial_mode=PowerMode.BACKGROUND_ECO,
    )
    url = await system.web_ui.start()
    token = system.web_ui.auth_token
    headers = {"X-Amadeus-Token": token}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. GET /api/library/assets
            res_assets = await client.get(f"{url}/api/library/assets", headers=headers)
            assert res_assets.status_code == 200
            data_assets = res_assets.json()
            assert "assets" in data_assets
            assert data_assets["total"] > 0

            # 2. GET /api/gestures
            res_gestures = await client.get(f"{url}/api/gestures", headers=headers)
            assert res_gestures.status_code == 200
            data_gestures = res_gestures.json()
            assert "gestures" in data_gestures
            assert data_gestures["total"] >= len(BUILTIN_GESTURE_PRESETS)

            # 3. POST /api/gestures/save
            save_payload = {
                "name": "Gesto API Test",
                "description": "Gesto creado vía HTTP",
                "head_x": -0.05,
                "r_arm_x": 0.2,
                "motion_type": "nod",
                "linked_emotion": "smug",
            }
            res_save = await client.post(
                f"{url}/api/gestures/save",
                headers=headers,
                json=save_payload,
            )
            assert res_save.status_code == 200
            saved_obj = res_save.json().get("gesture")
            assert saved_obj["name"] == "Gesto API Test"
            gid = saved_obj["id"]

            # 4. POST /api/gestures/preview
            res_preview = await client.post(
                f"{url}/api/gestures/preview",
                headers=headers,
                json=saved_obj,
            )
            assert res_preview.status_code == 200
            assert res_preview.json()["status"] == "previewing"

            # 5. POST /api/library/load (test voice loading)
            voice_item = {
                "id": "voice_es_elvira",
                "asset_type": "voice",
                "preview_url": "es-ES-ElviraNeural",
            }
            res_load_voice = await client.post(
                f"{url}/api/library/load",
                headers=headers,
                json=voice_item,
            )
            assert res_load_voice.status_code == 200
            assert res_load_voice.json()["status"] == "loaded"

            # 6. POST /api/gestures/delete
            res_del = await client.post(
                f"{url}/api/gestures/delete",
                headers=headers,
                json={"id": gid},
            )
            assert res_del.status_code == 200
            assert res_del.json()["status"] == "deleted"

    finally:
        await system.shutdown()
