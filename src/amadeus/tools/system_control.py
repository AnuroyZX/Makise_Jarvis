"""
Module 7 (Tools): Windows System & Media Controller + Background Timer Engine.
Provides zero-dependency Windows audio/media controls, hardware telemetry,
and real-time countdown timers inspired by Amazon Alexa and Meta Muse.
"""

from __future__ import annotations

import asyncio
import ctypes
from dataclasses import asdict, dataclass
import datetime
import logging
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional
import psutil

logger = logging.getLogger("amadeus.system_control")

# Windows Virtual-Key Codes for Multimedia & Audio (WinUser.h)
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def _send_vk(vk_code: int) -> bool:
    """Send a hardware virtual key stroke on Windows without external dependencies."""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.windll.user32
        # Key down
        user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        # Key up
        user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        return True
    except Exception as exc:
        logger.warning("Failed to send VK code 0x%02X: %s", vk_code, exc)
        return False


class WindowsSystemController:
    """Controls volume, media keys and queries hardware telemetry on Windows."""

    def __init__(self) -> None:
        pass

    def volume_up(self, steps: int = 3) -> str:
        """Increase master volume by N steps (typically 2% per step in Windows)."""
        for _ in range(max(1, steps)):
            _send_vk(VK_VOLUME_UP)
            time.sleep(0.02)
        return f"Volumen aumentado ({steps * 2}% aprox)."

    def volume_down(self, steps: int = 3) -> str:
        """Decrease master volume by N steps."""
        for _ in range(max(1, steps)):
            _send_vk(VK_VOLUME_DOWN)
            time.sleep(0.02)
        return f"Volumen reducido ({steps * 2}% aprox)."

    def toggle_mute(self) -> str:
        """Toggle master mute state."""
        _send_vk(VK_VOLUME_MUTE)
        return "Estado de silencio alternado (Mute)."

    def media_play_pause(self) -> str:
        """Toggle play/pause on active media player (Spotify, YouTube, VLC)."""
        _send_vk(VK_MEDIA_PLAY_PAUSE)
        return "Reproducción multimedia alternada (Play/Pausa)."

    def media_next(self) -> str:
        """Skip to next media track."""
        _send_vk(VK_MEDIA_NEXT_TRACK)
        return "Pista siguiente reproducida."

    def media_prev(self) -> str:
        """Go to previous media track."""
        _send_vk(VK_MEDIA_PREV_TRACK)
        return "Pista anterior reproducida."

    def media_stop(self) -> str:
        """Stop active media playback."""
        _send_vk(VK_MEDIA_STOP)
        return "Reproducción multimedia detenida."

    def get_telemetry(self) -> Dict[str, Any]:
        """Query real-time CPU, RAM, Battery and Time telemetry with zero blocking."""
        vmem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)

        battery_info: Optional[Dict[str, Any]] = None
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                battery_info = {
                    "percent": round(bat.percent, 1),
                    "power_plugged": bat.power_plugged,
                    "secs_left": bat.secsleft if bat.secsleft != psutil.POWER_TIME_UNLIMITED else -1,
                }
        except Exception:
            pass

        now = datetime.datetime.now()
        return {
            "cpu_percent": cpu,
            "ram_used_mb": round((vmem.total - vmem.available) / (1024 * 1024), 1),
            "ram_free_mb": round(vmem.available / (1024 * 1024), 1),
            "ram_percent": vmem.percent,
            "battery": battery_info,
            "time_str": now.strftime("%H:%M"),
            "date_str": now.strftime("%A, %d de %B de %Y"),
        }


@dataclass(slots=True)
class TimerItem:
    """Represents an active or expired countdown timer."""
    id: str
    label: str
    total_seconds: int
    remaining_seconds: int
    created_at: float
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TimerManager:
    """
    Background timer and alarm manager with async countdown loops,
    progress ticks and expiration callbacks.
    """

    def __init__(
        self,
        on_tick: Optional[Callable[[TimerItem], Awaitable[None]]] = None,
        on_expired: Optional[Callable[[TimerItem], Awaitable[None]]] = None,
    ) -> None:
        self.on_tick = on_tick
        self.on_expired = on_expired
        self._timers: Dict[str, TimerItem] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._counter: int = 0

    def start(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            if self._loop_task is None or self._loop_task.done():
                self._loop_task = loop.create_task(self._timer_tick_loop())
        except RuntimeError:
            pass  # No running event loop

    def stop(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            self._loop_task.cancel()
            self._loop_task = None

    def create_timer(self, seconds: int, label: str = "") -> TimerItem:
        """Create and start a new countdown timer."""
        self._counter += 1
        timer_id = f"timer_{int(time.time())}_{self._counter}"
        clean_label = label.strip() or f"Temporizador de {seconds}s"
        item = TimerItem(
            id=timer_id,
            label=clean_label,
            total_seconds=max(1, int(seconds)),
            remaining_seconds=max(1, int(seconds)),
            created_at=time.time(),
            is_active=True,
        )
        self._timers[timer_id] = item
        self.start()
        return item

    def cancel_timer(self, target: str = "") -> Optional[TimerItem]:
        """Cancel a timer by ID or matching label, or the last active timer if target is empty."""
        target_clean = target.strip().lower()
        if not self._timers:
            return None

        # 1. Exact ID match
        if target_clean in self._timers:
            t = self._timers.pop(target_clean)
            t.is_active = False
            return t

        # 2. Label match or cancel last
        matched_id: Optional[str] = None
        for tid, t in self._timers.items():
            if target_clean and target_clean in t.label.lower():
                matched_id = tid
                break

        if not matched_id and (not target_clean or target_clean in ("todos", "all", "el temporizador")):
            # Cancel most recent
            matched_id = list(self._timers.keys())[-1]

        if matched_id and matched_id in self._timers:
            t = self._timers.pop(matched_id)
            t.is_active = False
            return t
        return None

    def list_active_timers(self) -> List[TimerItem]:
        """Return all running timers."""
        return [t for t in self._timers.values() if t.is_active]

    async def _timer_tick_loop(self) -> None:
        """Async 1.0s tick loop driving countdowns and triggering expiration."""
        try:
            while self._timers:
                await asyncio.sleep(1.0)
                expired_ids: List[str] = []

                for tid, item in list(self._timers.items()):
                    if not item.is_active:
                        expired_ids.append(tid)
                        continue

                    item.remaining_seconds -= 1
                    if item.remaining_seconds <= 0:
                        item.remaining_seconds = 0
                        item.is_active = False
                        expired_ids.append(tid)
                        if self.on_expired is not None:
                            try:
                                await self.on_expired(item)
                            except Exception as exc:
                                logger.error("Error in timer on_expired callback: %s", exc)
                    else:
                        if self.on_tick is not None:
                            try:
                                await self.on_tick(item)
                            except Exception as exc:
                                logger.debug("Error in timer on_tick callback: %s", exc)

                for tid in expired_ids:
                    self._timers.pop(tid, None)
        except asyncio.CancelledError:
            pass
