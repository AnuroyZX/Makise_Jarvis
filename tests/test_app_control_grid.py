from __future__ import annotations

from pathlib import Path
import httpx
import pytest

from amadeus.config import AmadeusSettings
from amadeus.house.onboarding_ui import EphemeralOnboardingServer
from amadeus.system_builder import AmadeusSystem
from amadeus.tools.app_launcher import DiscoveredApp, WindowsAppLauncher


def test_app_launcher_categories_and_manifest() -> None:
    launcher = WindowsAppLauncher()
    # Add mock apps across categories
    launcher.add_custom_app("vscode_test", "VS Code Test", "C:/fake/code.exe", "development")
    launcher.add_custom_app("chrome_test", "Chrome Test", "C:/fake/chrome.exe", "browser")
    launcher.add_custom_app("game_test", "Steam Game Test", "C:/fake/game.exe", "gaming")

    controlled_settings = {
        "vscode_test": {
            "enabled": True,
            "aliases": ["codigo", "code"],
            "default_args": "--new-window",
            "require_confirm": True,
        },
        "chrome_test": {
            "enabled": False,
            "aliases": ["navegador"],
        },
    }

    manifest = launcher.get_apps_manifest(controlled_settings)
    assert len(manifest) >= 3

    vs_entry = next((a for a in manifest if a["id"] == "vscode_test"), None)
    assert vs_entry is not None
    assert vs_entry["enabled"] is True
    assert vs_entry["default_args"] == "--new-window"
    assert vs_entry["require_confirm"] is True
    assert vs_entry["icon"] == "💻"

    chrome_entry = next((a for a in manifest if a["id"] == "chrome_test"), None)
    assert chrome_entry is not None
    assert chrome_entry["enabled"] is False
    assert chrome_entry["icon"] == "🌐"


def test_app_launcher_launch_permissions_and_args() -> None:
    launcher = WindowsAppLauncher()
    launcher.add_custom_app("mock_app", "Mock App", "C:/fake/app.exe", "utility")

    # Disabled app
    disabled_res = launcher.launch(
        "mock_app",
        dry_run=True,
        controlled_settings={"enabled": False},
    )
    assert "desactivado" in disabled_res

    # Enabled app with default args
    enabled_res = launcher.launch(
        "mock_app",
        dry_run=True,
        extra_args="--extra",
        controlled_settings={"enabled": True, "default_args": "--default"},
    )
    assert "[Dry-Run]" in enabled_res
    assert "--default --extra" in enabled_res


@pytest.mark.asyncio
async def test_app_control_grid_http_endpoints(tmp_path: Path) -> None:
    system = AmadeusSystem(data_dir=tmp_path)
    # Add a mock executable in tmp_path for custom app test
    fake_exe = tmp_path / "custom_tool.exe"
    fake_exe.write_bytes(b"MZ\x90\x00FAKE_EXE")

    ui_url = await system.web_ui.start()
    token = system.web_ui.auth_token

    async with httpx.AsyncClient() as client:
        headers = {"X-Amadeus-Token": token}

        # 1. GET /api/apps
        get_res = await client.get(f"{ui_url}/api/apps", headers=headers)
        assert get_res.status_code == 200
        data = get_res.json()
        assert "apps" in data
        assert "total" in data

        # 2. POST /api/apps/add_custom
        add_res = await client.post(
            f"{ui_url}/api/apps/add_custom",
            headers=headers,
            json={
                "name": "Mi Script Especial",
                "executable_path": str(fake_exe),
                "aliases": ["script", "especial"],
                "default_args": "--run-fast",
                "require_confirm": True,
                "category": "utility",
            },
        )
        assert add_res.status_code == 200
        added_id = add_res.json()["app_id"]

        # 3. POST /api/apps/configure
        conf_res = await client.post(
            f"{ui_url}/api/apps/configure",
            headers=headers,
            json={
                "id": added_id,
                "enabled": False,
                "default_args": "--safe-mode",
            },
        )
        assert conf_res.status_code == 200
        assert conf_res.json()["config"]["enabled"] is False
        assert conf_res.json()["config"]["default_args"] == "--safe-mode"

        # 4. POST /api/apps/launch_test (dry-run)
        test_launch = await client.post(
            f"{ui_url}/api/apps/launch_test",
            headers=headers,
            json={"id": added_id, "dry_run": True},
        )
        assert test_launch.status_code == 200
        # Since it was disabled, it reports disabled
        assert "desactivado" in test_launch.json()["message"]

        # Re-enable and test dry-run launch
        await client.post(
            f"{ui_url}/api/apps/configure",
            headers=headers,
            json={"id": added_id, "enabled": True},
        )
        test_launch2 = await client.post(
            f"{ui_url}/api/apps/launch_test",
            headers=headers,
            json={"id": added_id, "dry_run": True},
        )
        assert "[Dry-Run]" in test_launch2.json()["message"]

        # 5. POST /api/apps/rescan
        rescan_res = await client.post(f"{ui_url}/api/apps/rescan", headers=headers)
        assert rescan_res.status_code == 200
        assert rescan_res.json()["status"] == "rescanned"

    await system.web_ui.stop()
