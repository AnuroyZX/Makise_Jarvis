from __future__ import annotations

import locale
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
import psutil


@dataclass(slots=True)
class HostProfile:
    os_name: str
    os_release: str
    cpu_cores_logical: int
    total_ram_gb: float
    available_ram_gb: float
    is_modest_pc: bool
    system_language: str
    appdata_dir: str
    default_browser_cmd: str
    discovered_cli_tools: Dict[str, str]


class EnvironmentScanner:
    """
    Module 1 (Casa): Auto-detects host hardware, OS paths, and environment capabilities
    so the compiled binary adapts automatically to your PC or your friend's PC.
    """

    MODEST_PC_RAM_THRESHOLD_GB: float = 12.0

    @classmethod
    def scan(cls) -> HostProfile:
        vm = psutil.virtual_memory()
        total_gb = round(vm.total / (1024**3), 2)
        avail_gb = round(vm.available / (1024**3), 2)
        cores = psutil.cpu_count(logical=True) or 2

        # Consider a PC "modest" if total RAM <= 12 GB or <= 4 logical cores
        is_modest = total_gb <= cls.MODEST_PC_RAM_THRESHOLD_GB or cores <= 4

        sys_lang = "es"
        try:
            loc = locale.getlocale()[0]
            if loc:
                sys_lang = loc.split("_")[0][:2].lower()
        except Exception:
            pass

        appdata = os.environ.get("APPDATA") or str(Path.home() / ".config")
        cli_tools: Dict[str, str] = {}
        for tool in ("git", "code", "ffmpeg", "node", "python"):
            resolved = shutil.which(tool)
            if resolved:
                cli_tools[tool] = resolved

        return HostProfile(
            os_name=platform.system(),
            os_release=platform.release(),
            cpu_cores_logical=cores,
            total_ram_gb=total_gb,
            available_ram_gb=avail_gb,
            is_modest_pc=is_modest,
            system_language=sys_lang,
            appdata_dir=appdata,
            default_browser_cmd=cls._detect_default_browser(),
            discovered_cli_tools=cli_tools,
        )

    @staticmethod
    def _detect_default_browser() -> str:
        if os.name != "nt":
            return "default"
        try:
            import winreg

            reg_path = (
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                return str(prog_id)
        except Exception:
            return "windows-default"
