from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
import webbrowser

from amadeus.house.resource_governor import PowerMode

if TYPE_CHECKING:
    from amadeus.system_builder import AmadeusSystem


class AmadeusTrayController:
    """
    Module 1 (Casa - Bandeja del Sistema / System Tray):
    Lazy-loads `pystray` and `Pillow` only when the user runs tray mode,
    keeping background memory minimal (~20-35 MB).
    """

    def __init__(self, system: AmadeusSystem, loop: asyncio.AbstractEventLoop) -> None:
        self.system = system
        self.loop = loop
        self._icon = None

    def create_tray_image(self):
        """Generate a sleek crimson/gold 'A' (Amadeus) emblem in-memory without external asset files."""
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (11, 12, 16, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 60, 60), outline=(249, 168, 38, 255), width=3)
        draw.polygon([(32, 12), (16, 50), (24, 50), (32, 28), (40, 50), (48, 50)], fill=(230, 92, 0, 255))
        return img

    def open_panel(self, icon=None, item=None) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self.system.web_ui.start(), self.loop
        )
        url = future.result(timeout=5.0)
        webbrowser.open(url)

    def switch_eco(self, icon=None, item=None) -> None:
        self.system.governor.switch_mode(PowerMode.BACKGROUND_ECO)

    def switch_active(self, icon=None, item=None) -> None:
        self.system.governor.switch_mode(PowerMode.FOREGROUND_ACTIVE)

    def quit_app(self, icon=None, item=None) -> None:
        if self._icon is not None:
            self._icon.stop()
        asyncio.run_coroutine_threadsafe(self.system.shutdown(), self.loop)

    def run_detached(self) -> bool:
        try:
            import pystray

            image = self.create_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("Abrir Panel Amadeus / USER.md", self.open_panel, default=True),
                pystray.MenuItem("Modo Activo (1er Plano)", self.switch_active),
                pystray.MenuItem("Modo Eco (2º Plano - Ahorro RAM)", self.switch_eco),
                pystray.MenuItem("Salir de Amadeus", self.quit_app),
            )
            self._icon = pystray.Icon(
                "AmadeusKurisu", image, "Amadeus System // Makise Kurisu", menu
            )
            self._icon.run_detached()
            return True
        except Exception:
            return False
