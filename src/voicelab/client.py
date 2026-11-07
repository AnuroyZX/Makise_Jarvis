from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Optional
import httpx

logger = logging.getLogger("voicelab.client")


class VoiceLabSidecarClient:
    """
    Client for the VoiceLab local TTS sidecar process.
    Connects to the sidecar loopback server, or lazily spawns it when requested.
    """

    def __init__(
        self,
        base_url: str = "",
        auth_token: str = "",
        auto_spawn: bool = True,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.auto_spawn = auto_spawn
        self._external_client = http_client is not None
        self._client = http_client
        self._proc: Optional[subprocess.Popen] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0))
        return self._client

    async def is_healthy(self) -> bool:
        if not self.base_url:
            return False
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def synthesize(
        self,
        text: str,
        speaker_profile: str = "kurisu_amadeus",
        pitch_shift: int = 0,
        index_rate: float = 0.75,
    ) -> Optional[tuple[bytes, str]]:
        """
        Synthesize speech using the VoiceLab sidecar.
        Returns `(wav_bytes, "audio/wav")` or None if unavailable.
        """
        if not self.base_url:
            return None

        try:
            client = await self._get_client()
            headers = {
                "X-Amadeus-Token": self.auth_token,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "speaker_profile": speaker_profile,
                "pitch_shift": pitch_shift,
                "index_rate": index_rate,
            }
            resp = await client.post(f"{self.base_url}/synthesize", headers=headers, json=payload)
            if resp.status_code == 200 and resp.content:
                return resp.content, "audio/wav"
            return None
        except Exception as exc:
            logger.debug("VoiceLab sidecar synthesis failed: %s", exc)
            return None

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
