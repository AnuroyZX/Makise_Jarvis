from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(slots=True)
class DiscoveredApp:
    name: str
    executable_path: str
    source: str  # "registry" | "start_menu" | "path"


class WindowsAppLauncher:
    """
    Module 7 (Herramientas - Aplicaciones Frecuentes):
    Automatically scans Windows Registry (App Paths), Start Menu folders, and PATH
    so Amadeus adapts to whatever apps are installed on your PC or your friend's PC.
    Enforces ECC AgentShield: never uses shell=True, only executes verified discovered binaries.
    """

    COMMON_ALIASES: Dict[str, List[str]] = {
        "vscode": ["code", "visual studio code"],
        "chrome": ["chrome", "google chrome"],
        "edge": ["msedge", "microsoft edge"],
        "firefox": ["firefox", "mozilla firefox"],
        "discord": ["discord"],
        "spotify": ["spotify"],
        "steam": ["steam"],
        "notepad": ["notepad", "bloc de notas"],
        "calculator": ["calc", "calculadora"],
        "explorer": ["explorer", "explorador"],
        "terminal": ["wt", "powershell", "cmd"],
    }

    def __init__(self) -> None:
        self._catalog: Dict[str, DiscoveredApp] = {}
        self.refresh_catalog()

    @property
    def catalog(self) -> Dict[str, DiscoveredApp]:
        return dict(self._catalog)

    def refresh_catalog(self) -> int:
        self._catalog.clear()
        self._scan_system_path()
        if os.name == "nt":
            self._scan_windows_registry()
            self._scan_start_menu_shortcuts()
        return len(self._catalog)

    def _scan_system_path(self) -> None:
        for alias, candidates in self.COMMON_ALIASES.items():
            for cand in candidates:
                found = shutil.which(cand)
                if found and Path(found).exists():
                    self._catalog[alias] = DiscoveredApp(
                        name=alias, executable_path=found, source="path"
                    )
                    break

    def _scan_windows_registry(self) -> None:
        if os.name != "nt":
            return
        try:
            import winreg

            reg_roots = [
                winreg.HKEY_CURRENT_USER,
                winreg.HKEY_LOCAL_MACHINE,
            ]
            subkey_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
            for root in reg_roots:
                try:
                    with winreg.OpenKey(root, subkey_path) as app_paths_key:
                        num_subkeys, _, _ = winreg.QueryInfoKey(app_paths_key)
                        for idx in range(num_subkeys):
                            exe_name = winreg.EnumKey(app_paths_key, idx)
                            try:
                                with winreg.OpenKey(app_paths_key, exe_name) as subk:
                                    val, _ = winreg.QueryValueEx(subk, "")
                                    if val and isinstance(val, str):
                                        clean_path = val.strip('"')
                                        if Path(clean_path).exists():
                                            stem = Path(exe_name).stem.lower()
                                            self._catalog[stem] = DiscoveredApp(
                                                name=stem,
                                                executable_path=clean_path,
                                                source="registry",
                                            )
                            except OSError:
                                continue
                except OSError:
                    continue
        except ImportError:
            pass

    def _scan_start_menu_shortcuts(self) -> None:
        """Index .lnk shortcut names in Start Menu for quick launching via os.startfile."""
        start_dirs: List[Path] = []
        for env_var in ("APPDATA", "PROGRAMDATA"):
            base = os.environ.get(env_var)
            if base:
                p = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                if p.exists():
                    start_dirs.append(p)

        for sdir in start_dirs:
            try:
                for lnk in sdir.rglob("*.lnk"):
                    key = lnk.stem.lower()
                    if key not in self._catalog:
                        self._catalog[key] = DiscoveredApp(
                            name=lnk.stem,
                            executable_path=str(lnk),
                            source="start_menu",
                        )
            except OSError:
                continue

    FORBIDDEN_METACHARS = set("&|;><`$\n\r")

    def find_app(self, query: str) -> Optional[DiscoveredApp]:
        q = query.strip().lower()
        if not q or any(ch in self.FORBIDDEN_METACHARS for ch in q):
            return None
        if q in self._catalog:
            return self._catalog[q]
        for alias, synonyms in self.COMMON_ALIASES.items():
            if q == alias or q in synonyms:
                if alias in self._catalog:
                    return self._catalog[alias]
                for syn in synonyms:
                    if syn in self._catalog:
                        return self._catalog[syn]
        for key, app in self._catalog.items():
            if q in key:
                return app
        return None

    def launch(self, app_query: str, dry_run: bool = False) -> str:
        """
        Safely launch a discovered application without shell=True (ECC AgentShield).
        """
        app = self.find_app(app_query)
        if app is None:
            return f"No encontré la aplicación '{app_query}' instalada en este PC."

        if dry_run:
            return f"[Dry-Run] Lanzaría '{app.name}' desde '{app.executable_path}' ({app.source})."

        target = Path(app.executable_path)
        if not target.exists():
            return f"El ejecutable para '{app.name}' ya no existe en '{app.executable_path}'."

        if target.suffix.lower() == ".lnk" and os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(
                [str(target)],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return f"Aplicación '{app.name}' iniciada correctamente."
