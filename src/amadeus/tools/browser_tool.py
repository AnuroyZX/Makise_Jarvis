from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import subprocess
import time
from typing import List, Optional
import webbrowser
import httpx

from amadeus.house.resource_governor import ResourceGovernor
from amadeus.tools.mail_calendar import wrap_untrusted


class _LightHTMLTextExtractor(HTMLParser):
    """Zero-dependency HTML-to-readable-text extractor."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_tags = {"script", "style", "noscript", "svg", "head"}
        self._current_skip = 0
        self.chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._skip_tags:
            self._current_skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags and self._current_skip > 0:
            self._current_skip -= 1

    def handle_data(self, data: str) -> None:
        if self._current_skip == 0:
            cleaned = data.strip()
            if cleaned:
                self.chunks.append(cleaned)

    def get_clean_text(self, max_chars: int = 4000) -> str:
        full = " ".join(self.chunks)
        return full[:max_chars]


class EphemeralBrowserTool:
    """
    Module 7 (Herramientas - Navegador Inteligente con Ahorro de RAM):
    - Level 1 (0 MB extra RAM): Async HTTP fetch + clean text extraction wrapped in <untrusted_data>.
    - Level 2 (Interactive on-demand): Launches an ephemeral browser subprocess or default browser
      with an automatic idle watchdog (default 120s) that kills the ephemeral process and trims RAM.
    """

    def __init__(
        self,
        governor: Optional[ResourceGovernor] = None,
        idle_timeout_sec: float = 120.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.governor = governor
        self.idle_timeout_sec = idle_timeout_sec
        self._external_client = http_client is not None
        self._client = http_client
        self._ephemeral_proc: Optional[subprocess.Popen] = None
        self._last_active_ts: float = 0.0
        self._watchdog_task: Optional[asyncio.Task] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(12.0, connect=5.0),
                follow_redirects=True,
                headers={"User-Agent": "AmadeusKurisu/1.0 (Lightweight Research Agent)"},
            )
        return self._client

    async def fetch_clean_page(self, url: str, max_chars: int = 3500) -> str:
        """Level 1: Ultra-lightweight web page reader with zero browser RAM overhead."""
        client = await self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        parser = _LightHTMLTextExtractor()
        parser.feed(resp.text)
        extracted = parser.get_clean_text(max_chars=max_chars)
        return wrap_untrusted(extracted, source_label=url)

    def open_in_user_browser(self, url: str) -> str:
        """Open URL in the user's default system browser."""
        webbrowser.open(url)
        return f"URL abierta en tu navegador predeterminado: {url}"

    def attach_ephemeral_process(self, proc: subprocess.Popen) -> None:
        """Track an ephemeral headless/automation browser process with idle timeout."""
        self._ephemeral_proc = proc
        self._last_active_ts = time.monotonic()
        try:
            loop = asyncio.get_running_loop()
            if self._watchdog_task is None or self._watchdog_task.done():
                self._watchdog_task = loop.create_task(self._idle_watchdog_loop())
        except RuntimeError:
            pass

    def touch_activity(self) -> None:
        self._last_active_ts = time.monotonic()

    def close_ephemeral_if_idle(self, force: bool = False) -> bool:
        """Terminate ephemeral browser if idle beyond threshold and trim RAM via Module 1."""
        if self._ephemeral_proc is None:
            return False
        elapsed = time.monotonic() - self._last_active_ts
        if force or elapsed >= self.idle_timeout_sec:
            try:
                if self._ephemeral_proc.poll() is None:
                    self._ephemeral_proc.terminate()
            except Exception:
                pass
            self._ephemeral_proc = None
            if self.governor is not None:
                self.governor.trim_working_set()
            return True
        return False

    async def _idle_watchdog_loop(self) -> None:
        while self._ephemeral_proc is not None:
            await asyncio.sleep(min(1.0, self.idle_timeout_sec / 2.0))
            if self.close_ephemeral_if_idle(force=False):
                break
