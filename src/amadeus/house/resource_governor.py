from __future__ import annotations

import ctypes
import gc
import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List
import psutil


class PowerMode(str, Enum):
    BACKGROUND_ECO = "background_eco"
    FOREGROUND_ACTIVE = "foreground_active"


@dataclass(slots=True)
class ResourceSnapshot:
    power_mode: PowerMode
    process_rss_mb: float
    system_ram_percent: float
    polling_interval_sec: float
    llm_tier: str  # "eco" | "full"


class ResourceGovernor:
    """
    Module 1 (Casa): Manages CPU priority, Windows Working Set RAM trimming,
    and adaptive polling/model routing between Background Eco and Foreground Active modes.
    Enforces a generous high-performance RAM ceiling of up to 1024 MB (1 GB) for fluid responsiveness.
    """

    MAX_WORKING_SET_MB: float = 1024.0

    def __init__(
        self,
        initial_mode: PowerMode = PowerMode.BACKGROUND_ECO,
        max_working_set_mb: float = 1024.0,
    ) -> None:
        self._mode: PowerMode = initial_mode
        self._process = psutil.Process(os.getpid())
        self._listeners: List[Callable[[PowerMode], None]] = []
        self.max_working_set_mb: float = max_working_set_mb
        self._apply_os_priority(initial_mode)

    @property
    def mode(self) -> PowerMode:
        return self._mode

    @property
    def polling_interval_sec(self) -> float:
        """Adaptive polling: slow in background (3.5s) to save CPU, fast in foreground (0.8s)."""
        return 3.5 if self._mode == PowerMode.BACKGROUND_ECO else 0.8

    @property
    def recommended_llm_tier(self) -> str:
        """Smart routing hint for Module 3 (Brain)."""
        return "eco" if self._mode == PowerMode.BACKGROUND_ECO else "full"

    def register_listener(self, callback: Callable[[PowerMode], None]) -> None:
        """Connect other modules (e.g., Body, Brain, Channels) to power mode transitions."""
        self._listeners.append(callback)

    def switch_mode(self, new_mode: PowerMode) -> ResourceSnapshot:
        """Transition between BACKGROUND_ECO and FOREGROUND_ACTIVE and notify connected modules."""
        if self._mode != new_mode:
            self._mode = new_mode
            self._apply_os_priority(new_mode)
            if new_mode == PowerMode.BACKGROUND_ECO:
                self.trim_working_set(force=True)
            for listener in self._listeners:
                listener(new_mode)
        return self.snapshot()

    def _apply_os_priority(self, mode: PowerMode) -> None:
        try:
            if os.name == "nt":
                target_nice = (
                    psutil.BELOW_NORMAL_PRIORITY_CLASS
                    if mode == PowerMode.BACKGROUND_ECO
                    else psutil.ABOVE_NORMAL_PRIORITY_CLASS
                )
                self._process.nice(target_nice)
        except (psutil.AccessDenied, OSError):
            pass

    def trim_working_set(self, force: bool = False) -> float:
        """
        Run garbage collection and ask Windows Kernel (SetProcessWorkingSetSize)
        to page out unused memory pages. If force is False, only trims if process RSS
        exceeds `max_working_set_mb` (1 GB) to preserve zero-latency hot models in RAM.
        Returns current RSS in MB.
        """
        current_rss = self.get_process_memory_mb()
        if not force and current_rss < self.max_working_set_mb:
            return current_rss

        gc.collect()
        if os.name == "nt":
            try:
                from ctypes import wintypes

                kernel32 = ctypes.windll.kernel32
                kernel32.GetCurrentProcess.restype = wintypes.HANDLE
                kernel32.SetProcessWorkingSetSize.argtypes = [
                    wintypes.HANDLE,
                    ctypes.c_size_t,
                    ctypes.c_size_t,
                ]
                kernel32.SetProcessWorkingSetSize.restype = wintypes.BOOL
                handle = kernel32.GetCurrentProcess()
                kernel32.SetProcessWorkingSetSize(
                    handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1)
                )
            except Exception:
                pass
        return self.get_process_memory_mb()

    def get_process_memory_mb(self) -> float:
        mem_info = self._process.memory_info()
        return round(mem_info.rss / (1024 * 1024), 2)

    def snapshot(self) -> ResourceSnapshot:
        sys_mem = psutil.virtual_memory()
        return ResourceSnapshot(
            power_mode=self._mode,
            process_rss_mb=self.get_process_memory_mb(),
            system_ram_percent=sys_mem.percent,
            polling_interval_sec=self.polling_interval_sec,
            llm_tier=self.recommended_llm_tier,
        )
