from __future__ import annotations

import json
from pathlib import Path
import pytest
import httpx

from amadeus.system_builder import AmadeusSystem
from amadeus.house.onboarding_ui import EphemeralOnboardingServer


@pytest.mark.asyncio
async def test_character_api_endpoints(tmp_path: Path):
    system = AmadeusSystem(data_dir=tmp_path)
    server = EphemeralOnboardingServer(system=system, host="127.0.0.1", port=0)

    # 1. Test GET /api/characters
    code, mime, body = await server._route_request("GET", "/api/characters", b"")
    assert code == "200 OK"
    data = json.loads(body.decode("utf-8"))
    assert "characters" in data
    assert len(data["characters"]) >= 4
    assert any(c["id"] == "aria" for c in data["characters"])

    # 2. Test POST /api/character/switch to nexus
    switch_body = json.dumps({"id": "nexus"}).encode("utf-8")
    code, mime, body = await server._route_request("POST", "/api/character/switch", switch_body)
    assert code == "200 OK"
    sw_data = json.loads(body.decode("utf-8"))
    assert sw_data["status"] == "switched"
    assert sw_data["character"]["id"] == "nexus"
    assert "Nexus" in system.identity.read_soul()

    # 3. Test POST /api/character/create
    create_body = json.dumps({
        "name": "Kira",
        "soul_prompt": "Eres Kira, una IA de soporte.",
        "voice_id": "es-MX-DaliaNeural",
    }).encode("utf-8")
    code, mime, body = await server._route_request("POST", "/api/character/create", create_body)
    assert code == "200 OK"
    cr_data = json.loads(body.decode("utf-8"))
    assert cr_data["status"] == "created"
    assert cr_data["character"]["id"] == "kira"

    # 3b. Test POST /api/character/update
    update_body = json.dumps({
        "id": "kira",
        "name": "Kira Modificada",
        "voice_engine": "edge",
        "voice_id": "es-ES-ElviraNeural",
        "dsp_preset": "phone",
        "custom_system_prompt": "Eres Kira Modificada con nueva directiva.",
    }).encode("utf-8")
    code, mime, body = await server._route_request("POST", "/api/character/update", update_body)
    assert code == "200 OK"
    up_data = json.loads(body.decode("utf-8"))
    assert up_data["status"] == "updated"
    assert up_data["character"]["name"] == "Kira Modificada"
    assert up_data["character"]["voice_id"] == "es-ES-ElviraNeural"
    assert up_data["character"]["dsp_preset"] == "phone"

    # 4. Test POST /api/character/delete
    del_body = json.dumps({"id": "kira"}).encode("utf-8")
    code, mime, body = await server._route_request("POST", "/api/character/delete", del_body)
    assert code == "200 OK"
    del_data = json.loads(body.decode("utf-8"))
    assert del_data["status"] == "deleted"

    await server.stop()
