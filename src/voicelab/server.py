from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, Optional
import urllib.parse

from voicelab.chatterbox_engine import ChatterboxEngine
from voicelab.models import SynthesisRequest
from voicelab.rvc_engine import RVCEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [voicelab]: %(message)s")
logger = logging.getLogger("voicelab.server")


class VoiceLabSidecarServer:
    """
    Isolated VoiceLab Sidecar HTTP Server (`127.0.0.1`).
    Provides authenticated, VRAM-guarded local voice cloning for Amadeus Kurisu.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        auth_token: Optional[str] = None,
        idle_timeout_sec: float = 120.0,
        model_dir: Optional[Path] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token or secrets.token_urlsafe(24)
        self.idle_timeout_sec = idle_timeout_sec
        self._server: Optional[asyncio.AbstractServer] = None
        self._last_req_ts = time.monotonic()
        self._watchdog_task: Optional[asyncio.Task] = None

        self.rvc = RVCEngine(model_dir=model_dir)
        self.chatterbox = ChatterboxEngine()

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.is_serving()

    async def start(self) -> str:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        sockets = self._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]
        self._last_req_ts = time.monotonic()
        self._watchdog_task = asyncio.create_task(self._idle_watchdog())
        logger.info("VoiceLab Sidecar started on http://%s:%d (auth_token=%s)", self.host, self.port, self.auth_token)
        return f"http://{self.host}:{self.port}"

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self.rvc.unload()
        self.chatterbox.unload()
        logger.info("VoiceLab Sidecar stopped cleanly.")

    async def _idle_watchdog(self) -> None:
        while self.is_running:
            await asyncio.sleep(min(2.0, self.idle_timeout_sec / 2.0))
            if (time.monotonic() - self._last_req_ts) >= self.idle_timeout_sec:
                if self.rvc._is_loaded:
                    logger.info("Idle timeout (%.0fs) reached. Offloading RVC models to free VRAM for games.", self.idle_timeout_sec)
                    self.rvc.unload()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._last_req_ts = time.monotonic()
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                return
            parts = line.decode("utf-8", errors="replace").strip().split()
            if len(parts) < 2:
                return
            method, raw_path = parts[0], parts[1]
            path = urllib.parse.urlparse(raw_path).path

            headers: dict[str, str] = {}
            content_length = 0
            while True:
                hdr = await reader.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
                s = hdr.decode("utf-8", errors="replace").strip()
                if ":" in s:
                    k, v = s.split(":", 1)
                    headers[k.lower().strip()] = v.strip()
                    if k.lower().strip() == "content-length":
                        try:
                            content_length = int(v.strip())
                        except ValueError:
                            content_length = 0

            # DNS Rebinding check
            host_hdr = headers.get("host", "").split(":")[0].strip().lower()
            if host_hdr and host_hdr not in ("127.0.0.1", "localhost"):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\nForbidden")
                await writer.drain()
                return

            # Auth Token check
            token = headers.get("x-amadeus-token", "")
            if not secrets.compare_digest(token, self.auth_token) and path != "/health":
                writer.write(b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\nUnauthorized")
                await writer.drain()
                return

            body = await reader.readexactly(content_length) if 0 < content_length <= 50 * 1024 * 1024 else b""
            status, ctype, resp = await self._route(method, path, body)

            header_block = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: {ctype}\r\n"
                f"Content-Length: {len(resp)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")
            writer.write(header_block + resp)
            await writer.drain()
        except Exception as exc:
            logger.debug("Client handler error: %s", exc)
        finally:
            writer.close()

    async def _route(self, method: str, path: str, body: bytes) -> tuple[str, str, bytes]:
        if method == "GET" and path == "/health":
            info = self.rvc.get_info()
            payload = {
                "status": "ok",
                "model_available": self.rvc.is_available,
                "model_loaded": info.is_loaded,
                "vram_mb": info.vram_mb,
            }
            return "200 OK", "application/json", json.dumps(payload).encode("utf-8")

        if method == "POST" and path == "/unload":
            self.rvc.unload()
            return "200 OK", "application/json", b'{"status":"unloaded"}'

        if method == "POST" and path == "/synthesize":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                return "400 Bad Request", "application/json", b'{"error":"invalid_json"}'

            text = str(data.get("text", "")).strip()
            if not text:
                return "400 Bad Request", "application/json", b'{"error":"empty_text"}'

            pitch = int(data.get("pitch_shift", 0))
            index_rate = float(data.get("index_rate", 0.75))

            # 1. Base TTS (Chatterbox / Edge)
            base_audio = await self.chatterbox.generate_base_speech(text)

            # 2. RVC Voice Timbre Conversion
            final_audio = self.rvc.convert_audio(base_audio, pitch_shift=pitch, index_rate=index_rate)
            return "200 OK", "audio/wav", final_audio

        return "404 Not Found", "application/json", b'{"error":"not_found"}'


def main() -> None:
    parser = argparse.ArgumentParser(description="Amadeus VoiceLab Sidecar Server")
    parser.add_argument("--port", type=int, default=0, help="Port to bind to (0 for ephemeral)")
    parser.add_argument("--token", type=str, default="", help="Auth token for loopback API")
    parser.add_argument("--idle-timeout", type=float, default=120.0, help="Idle timeout in seconds before VRAM offload")
    args = parser.parse_args()

    async def _run():
        server = VoiceLabSidecarServer(port=args.port, auth_token=args.token, idle_timeout_sec=args.idle_timeout)
        url = await server.start()
        print(f"VOICELAB_READY url={url} port={server.port} token={server.auth_token}", flush=True)
        try:
            while True:
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await server.stop()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
