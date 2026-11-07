from __future__ import annotations

import json
from pathlib import Path
import pytest

from amadeus.house.steam_bridge import SteamBridge
from amadeus.system_builder import AmadeusSystem
from amadeus.house.onboarding_ui import EphemeralOnboardingServer


def test_steam_bridge_standalone_graceful_degradation(tmp_path: Path):
    bridge = SteamBridge(app_id=480, project_root=tmp_path)
    # When steam_api64.dll is not present, bridge falls back gracefully
    assert not bridge.status.is_available
    assert bridge.status.app_id == 480
    assert len(bridge.status.unlocked_achievements) == 0

    # Local achievements recording
    res = bridge.unlock_achievement("ACH_FIRST_WORDS")
    assert res is True
    assert "ACH_FIRST_WORDS" in bridge.status.unlocked_achievements

    # Idempotent unlock
    res2 = bridge.unlock_achievement("ACH_FIRST_WORDS")
    assert res2 is True

    # Invalid achievement
    res_fake = bridge.unlock_achievement("ACH_DOES_NOT_EXIST")
    assert res_fake is False

    bridge.shutdown()


@pytest.mark.asyncio
async def test_steam_status_api_endpoint(tmp_path: Path):
    system = AmadeusSystem(data_dir=tmp_path)
    server = EphemeralOnboardingServer(system=system, host="127.0.0.1", port=0)

    code, mime, body = await server._route_request("GET", "/api/steam/status", b"")
    assert code == "200 OK"
    data = json.loads(body.decode("utf-8"))
    assert "is_available" in data
    assert "unlocked_achievements" in data
    assert isinstance(data["unlocked_achievements"], list)

    await server.stop()
