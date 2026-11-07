from __future__ import annotations

import base64
import ctypes
from dataclasses import dataclass
import io
import os
from typing import List, Optional
import httpx
import psutil

from amadeus.config import AmadeusSettings
from amadeus.tools.mail_calendar import wrap_untrusted


@dataclass(slots=True)
class ActiveWindowInfo:
    process_name: str
    window_title: str
    is_excluded: bool


class ScreenContextManager:
    """
    Phase F3 (Contexto de Pantalla Ligero + Visión Bajo Demanda):
    1. Always knows the active foreground window & process name with near-zero CPU (`ctypes` user32).
    2. Never captures screenshots or leaks window titles for excluded apps (password managers, banks).
    3. Captures on-demand screenshots in memory (never written to disk), resizes to max 1280px JPEG,
       and sends to Gemini Flash Vision when the user asks "what's on my screen?".
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        self._external_client = http_client is not None
        self._client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0))
        return self._client

    def is_excluded_window(self, process_name: str, window_title: str) -> bool:
        combined = f"{process_name} {window_title}".lower()
        return any(
            excl.lower() in combined for excl in self.settings.excluded_screen_apps if excl
        )

    def get_active_window_info(self) -> ActiveWindowInfo:
        """Read foreground window title and process name on Windows with zero polling overhead."""
        if os.name != "nt":
            return ActiveWindowInfo(process_name="unknown", window_title="", is_excluded=False)
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ActiveWindowInfo(process_name="desktop", window_title="Escritorio", is_excluded=False)

            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = "unknown"
            if pid.value:
                try:
                    proc_name = psutil.Process(pid.value).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            excluded = self.is_excluded_window(proc_name, title)
            if excluded:
                return ActiveWindowInfo(
                    process_name=proc_name,
                    window_title="[Ventana Protegida por Privacidad]",
                    is_excluded=True,
                )
            return ActiveWindowInfo(
                process_name=proc_name, window_title=title, is_excluded=False
            )
        except Exception:
            return ActiveWindowInfo(process_name="unknown", window_title="", is_excluded=False)

    def build_context_line(self) -> str:
        info = self.get_active_window_info()
        if info.is_excluded:
            return "Ahora mismo en pantalla: [Aplicación protegida en lista de exclusión — captura deshabilitada]."
        if not info.window_title:
            return f"Ahora mismo en pantalla: {info.process_name}"
        return wrap_untrusted(
            f"App activa: {info.process_name} | Título: {info.window_title}",
            source_label="active_window",
        )

    def capture_screen_jpeg_bytes(self, max_width: int = 1280) -> bytes:
        """
        Capture current screen in-memory as resized JPEG (never saved to disk).
        Raises PermissionError if an excluded window is currently active.
        """
        info = self.get_active_window_info()
        if info.is_excluded:
            raise PermissionError(
                f"Captura bloqueada por privacidad: '{info.process_name}' está en tu lista de exclusión."
            )

        import mss
        from PIL import Image

        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def list_visible_windows(self, max_items: int = 8) -> List[str]:
        """Return titles of top visible windows on Windows desktop (filtering excluded privacy apps)."""
        if os.name != "nt":
            return []
        titles: List[str] = []
        try:
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def _cb(hwnd: int, _lparam: int) -> bool:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        t = buf.value.strip()
                        if t and t not in ("Program Manager", "Settings", "Configuración") and not self.is_excluded_window("", t):
                            if t not in titles:
                                titles.append(t)
                return len(titles) < max_items

            user32.EnumWindows(WNDENUMPROC(_cb), 0)
        except Exception:
            pass
        return titles

    async def analyze_current_screen(
        self, user_question: str = "¿Qué ves en mi pantalla y cómo puedes ayudarme?"
    ) -> str:
        """Capture screen in memory and analyze it with Gemini Flash Vision or Free Vision + Window Inspector."""
        info = self.get_active_window_info()
        open_wins = self.list_visible_windows(max_items=6)
        win_summary = f"Ventana principal: '{info.window_title or info.process_name}'. Otras ventanas visibles: {', '.join(open_wins[:5])}."

        try:
            jpeg_bytes = self.capture_screen_jpeg_bytes()
        except PermissionError as exc:
            return str(exc)
        except Exception:
            return f"[emotion:analytical] Veo tus ventanas activas en el sistema. {win_summary}"

        b64_img = base64.b64encode(jpeg_bytes).decode("ascii")
        client = await self._get_client()

        if self.settings.gemini_api_key:
            try:
                model = self.settings.foreground_model_gemini or "gemini-2.5-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": f"Actúa como Makise Kurisu (Amadeus, en español, breve y natural). Contexto de ventanas: {win_summary}. Analiza la captura del usuario y responde: {user_question}"},
                                {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
                            ],
                        }
                    ]
                }
                resp = await client.post(
                    url, params={"key": self.settings.gemini_api_key}, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                pass

        # Zero-Config Free Vision fallback (Pollinations OpenAI Vision + Window Inspector)
        try:
            resp = await client.post(
                "https://text.pollinations.ai/openai",
                json={
                    "model": "openai",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Eres Makise Kurisu (Sistema Amadeus de Steins;Gate 0). Responde en español en máximo 2 oraciones habladas, con tono inteligente y ligeramente tsundere.",
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{user_question}\n({win_summary})"},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                                },
                            ],
                        },
                    ],
                },
            )
            if resp.status_code == 200:
                choice = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if choice:
                    return f"[emotion:analytical] [gesture:think] {choice}"
        except Exception:
            pass

        return (
            f"[emotion:analytical] [gesture:think] Estoy viendo tu escritorio ahora mismo: tienes en primer plano "
            f"'{info.window_title or info.process_name}', además de {', '.join(open_wins[:4]) or 'tus ventanas de trabajo'}."
        )
