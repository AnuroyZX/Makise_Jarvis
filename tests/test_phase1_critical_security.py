from __future__ import annotations

import asyncio
from pathlib import Path
import httpx
import pytest

from amadeus.body.agent_core import AgentMessage
from amadeus.config import AmadeusSettings
from amadeus.house.onboarding_ui import EphemeralOnboardingServer
from amadeus.house.resource_governor import PowerMode
from amadeus.system_builder import AmadeusSystem
from amadeus.tools.file_ops import SafeFileManager


@pytest.mark.asyncio
async def test_s1_onboarding_ui_token_and_dns_rebinding_defense(tmp_path: Path) -> None:
    """
    S1 Test:
    1. Requests to /api/* without token return 401 Unauthorized.
    2. Requests with incorrect token return 401 Unauthorized.
    3. Requests with valid X-Amadeus-Token header return 200 OK.
    4. Query param token works for asset endpoints.
    5. Host headers other than 127.0.0.1/localhost return 403 Forbidden (DNS rebinding defense).
    """
    system = AmadeusSystem(data_dir=tmp_path)
    server = EphemeralOnboardingServer(system=system, host="127.0.0.1", port=0)
    url = await server.start()
    token = server.auth_token

    async with httpx.AsyncClient() as client:
        # 1. Without token -> 401
        r_unauth = await client.get(f"{url}/api/state")
        assert r_unauth.status_code == 401
        assert "unauthorized" in r_unauth.text

        # 2. Wrong token -> 401
        r_bad = await client.get(
            f"{url}/api/state", headers={"X-Amadeus-Token": "wrong-token-12345"}
        )
        assert r_bad.status_code == 401

        # 3. Valid token header -> 200
        r_ok = await client.get(
            f"{url}/api/state", headers={"X-Amadeus-Token": token}
        )
        assert r_ok.status_code == 200
        data = r_ok.json()
        assert "active_brain" in data
        assert "cloud_vision_consent" in data
        assert "cloud_stt_consent" in data

        # 4. Valid token in query param -> 200
        r_query = await client.get(f"{url}/api/state?token={token}")
        assert r_query.status_code == 200

        # 5. DNS Rebinding: Malicious Host header -> 403
        r_rebind = await client.get(
            f"{url}/api/state?token={token}",
            headers={"Host": "attacker-controlled-site.com"},
        )
        assert r_rebind.status_code == 403
        assert "Forbidden" in r_rebind.text

    await server.stop()
    await system.shutdown()


@pytest.mark.asyncio
async def test_s2_gemini_key_isolated_in_headers_not_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    S2 Test:
    Verify Gemini API keys are never passed in the URL query string (?key=AIza...),
    preventing leaks into proxy logs and tracebacks. Verifies 'x-goog-api-key' header.
    """
    captured_urls: list[str] = []
    captured_headers: list[dict[str, str]] = []

    def mock_gemini_transport(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        captured_headers.append(dict(request.headers))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "[EMOTION:analytical] Clave recibida en encabezado seguro."}]
                        }
                    }
                ]
            },
        )

    test_key = "AIzaSySecretTestKey1234567890"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(mock_gemini_transport)
    ) as mock_client:
        settings = AmadeusSettings(
            active_brain="gemini",
            gemini_api_key=test_key,
            cloud_vision_consent=True,
        )
        settings.save(tmp_path)
        system = AmadeusSystem(data_dir=tmp_path, http_client=mock_client)

        reply = await system.core.process_user_message(
            AgentMessage(role="user", content="Hola")
        )
        assert reply.emotion.value == "analytical"

        assert len(captured_urls) >= 1
        for url in captured_urls:
            assert f"key={test_key}" not in url
            assert "key=" not in url

        assert any(
            h.get("x-goog-api-key") == test_key for h in captured_headers
        )
        await system.shutdown()


def test_s3_fs_open_blocks_dangerous_binaries_and_scripts(tmp_path: Path) -> None:
    """
    S3 Test:
    Verify fs_open strictly blocks .exe, .bat, .cmd, .ps1, etc.
    even when located in authorized folders.
    """
    settings = AmadeusSettings()
    manager = SafeFileManager(settings=settings, data_dir=tmp_path, extra_roots=[tmp_path])

    dangerous_file = tmp_path / "payload.exe"
    dangerous_file.write_bytes(b"MZ\x00\x00FAKE_EXE")

    with pytest.raises(PermissionError) as exc_info:
        manager.fs_open(dangerous_file)
    assert "bloqueada por seguridad" in str(exc_info.value)

    dangerous_script = tmp_path / "script.bat"
    dangerous_script.write_text("@echo off\necho test\n", encoding="utf-8")

    with pytest.raises(PermissionError) as exc_info2:
        manager.fs_open(dangerous_script)
    assert "bloqueada por seguridad" in str(exc_info2.value)


def test_s4_fs_create_file_prevents_accidental_overwrite(tmp_path: Path) -> None:
    """
    S4 Test:
    Verify fs_create_file raises FileExistsError if target exists and overwrite=False.
    """
    settings = AmadeusSettings()
    manager = SafeFileManager(settings=settings, data_dir=tmp_path, extra_roots=[tmp_path])

    test_file = tmp_path / "important_document.txt"
    manager.fs_create_file(test_file, content="Contenido original")
    assert test_file.read_text(encoding="utf-8") == "Contenido original"

    with pytest.raises(FileExistsError) as exc_info:
        manager.fs_create_file(test_file, content="Contenido sobreescrito")
    assert "ya existe" in str(exc_info.value)
    assert test_file.read_text(encoding="utf-8") == "Contenido original"

    # Explicit overwrite works
    manager.fs_create_file(test_file, content="Contenido nuevo", overwrite=True)
    assert test_file.read_text(encoding="utf-8") == "Contenido nuevo"


@pytest.mark.asyncio
async def test_s6_privacy_consent_guard(tmp_path: Path) -> None:
    """
    S6 Test:
    Verify that with cloud_vision_consent=False (default), screen analysis
    refuses to send pixels to cloud vision and gives a clear privacy explanation.
    """
    settings = AmadeusSettings(
        gemini_api_key="AIzaSyTest123",
        cloud_vision_consent=False,
    )
    settings.save(tmp_path)
    system = AmadeusSystem(data_dir=tmp_path)

    res = await system.screen.analyze_current_screen("¿Qué hay en mi pantalla?")
    assert "[Privacidad]" in res
    assert "desactivado por defecto" in res
    await system.shutdown()
