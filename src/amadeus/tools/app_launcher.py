from __future__ import annotations

import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class DiscoveredApp:
    name: str
    executable_path: str
    source: str  # "registry" | "start_menu" | "path" | "custom"
    category: str = "general"


class WindowsAppLauncher:
    """
    Module 7 (Herramientas - Aplicaciones Frecuentes):
    Automatically scans Windows Registry (App Paths), Start Menu folders, and PATH
    so Amadeus adapts to whatever apps are installed on your PC or your friend's PC.
    Enforces ECC AgentShield: never uses shell=True, only executes verified discovered binaries.
    """

    CATEGORIES: Dict[str, List[str]] = {
        "development": [
            "code", "vscode", "visual studio", "pycharm", "intellij", "git", "terminal",
            "powershell", "cmd", "wt", "sublime", "postman", "docker", "cursor", "rider", "eclipse"
        ],
        "browser": [
            "chrome", "firefox", "edge", "msedge", "brave", "opera", "vivaldi", "tor", "safari"
        ],
        "communication": [
            "discord", "slack", "teams", "telegram", "whatsapp", "zoom", "skype", "thunderbird", "outlook"
        ],
        "media": [
            "spotify", "vlc", "obs", "gimp", "photoshop", "audacity", "blender", "premiere",
            "filmora", "itunes", "music", "video", "photos", "paint"
        ],
        "gaming": [
            "steam", "epic", "battle.net", "riot", "minecraft", "unity", "unreal", "gog", "ubisoft", "ea"
        ],
        "utility": [
            "notepad", "calc", "calculator", "explorer", "taskmgr", "7z", "winrar", "settings", "control"
        ],
    }

    CATEGORY_ICONS: Dict[str, str] = {
        "development": "💻",
        "browser": "🌐",
        "communication": "💬",
        "media": "🎵",
        "gaming": "🎮",
        "utility": "🛠️",
        "general": "🪟",
    }

    WEB_SHORTCUTS: Dict[str, tuple[str, str]] = {
        "youtube": ("YouTube", "https://www.youtube.com"),
        "google": ("Google", "https://www.google.com"),
        "gmail": ("Gmail", "https://mail.google.com"),
        "netflix": ("Netflix", "https://www.netflix.com"),
        "spotify": ("Spotify Web", "https://open.spotify.com"),
        "twitch": ("Twitch", "https://www.twitch.tv"),
        "twitter": ("Twitter / X", "https://x.com"),
        "x": ("X (Twitter)", "https://x.com"),
        "github": ("GitHub", "https://github.com"),
        "chatgpt": ("ChatGPT", "https://chatgpt.com"),
        "reddit": ("Reddit", "https://www.reddit.com"),
        "whatsapp": ("WhatsApp Web", "https://web.whatsapp.com"),
    }

    @classmethod
    def guess_category(cls, name: str, path: str = "") -> str:
        text = f"{name} {path}".lower()
        for cat, kw_list in cls.CATEGORIES.items():
            if any(kw in text for kw in kw_list):
                return cat
        return "general"

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
                        name=alias,
                        executable_path=found,
                        source="path",
                        category=self.guess_category(alias, found),
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
                                                category=self.guess_category(stem, clean_path),
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
                            category=self.guess_category(lnk.stem, str(lnk)),
                        )
            except OSError:
                continue

    def add_custom_app(
        self,
        key: str,
        name: str,
        executable_path: str,
        category: str = "general",
    ) -> DiscoveredApp:
        clean_key = key.strip().lower()
        app = DiscoveredApp(
            name=name,
            executable_path=executable_path,
            source="custom",
            category=category or self.guess_category(name, executable_path),
        )
        self._catalog[clean_key] = app
        return app

    def get_apps_manifest(
        self, controlled_settings: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        settings = controlled_settings or {}
        result: List[Dict[str, Any]] = []
        for key, app in sorted(self._catalog.items(), key=lambda x: x[1].name.lower()):
            ctrl = settings.get(key, {})
            enabled = ctrl.get("enabled", True)
            custom_aliases = ctrl.get("aliases")
            if custom_aliases is None:
                aliases = self.COMMON_ALIASES.get(key, [key])
            else:
                aliases = custom_aliases
            cat = ctrl.get("category") or app.category or self.guess_category(app.name, app.executable_path)
            result.append({
                "id": key,
                "name": app.name,
                "executable_path": app.executable_path,
                "source": app.source,
                "category": cat,
                "icon": self.CATEGORY_ICONS.get(cat, "🪟"),
                "enabled": enabled,
                "aliases": aliases,
                "default_args": ctrl.get("default_args", ""),
                "require_confirm": ctrl.get("require_confirm", False),
            })
        return result

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

        # 3. Match whole words to prevent accidental substring false positives
        for key, app in self._catalog.items():
            if re.search(rf"\b{re.escape(q)}\b", key):
                return app

        # 4. Fuzzy match using difflib
        matches = difflib.get_close_matches(q, list(self._catalog.keys()), n=1, cutoff=0.72)
        if matches:
            return self._catalog[matches[0]]

        return None

    def launch(
        self,
        app_query: str,
        dry_run: bool = False,
        extra_args: str = "",
        controlled_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Safely launch a discovered application without shell=True (ECC AgentShield).
        Respects custom arguments and enabled/disabled permissions.
        """
        app = self.find_app(app_query)
        if app is None:
            q_clean = app_query.strip().lower()
            if q_clean in self.WEB_SHORTCUTS:
                svc_name, url = self.WEB_SHORTCUTS[q_clean]
                if dry_run:
                    return f"[Dry-Run] Abriría {svc_name} en el navegador ({url})."
                import webbrowser
                webbrowser.open(url)
                return f"Abriendo {svc_name} en tu navegador web."
            return f"No encontré la aplicación '{app_query}' instalada en este PC."

        ctrl = controlled_settings or {}
        if ctrl and not ctrl.get("enabled", True):
            return f"El control de la aplicación '{app.name}' está desactivado en tus ajustes de Amadeus."

        default_args = ctrl.get("default_args", "").strip() if ctrl else ""
        combined_args = f"{default_args} {extra_args}".strip()

        if dry_run:
            args_hint = f" con parámetros '{combined_args}'" if combined_args else ""
            return f"[Dry-Run] Lanzaría '{app.name}' desde '{app.executable_path}' ({app.source}){args_hint}."

        target = Path(app.executable_path)
        if not target.exists():
            return f"El ejecutable para '{app.name}' ya no existe en '{app.executable_path}'."

        if target.suffix.lower() == ".lnk" and os.name == "nt" and not combined_args:
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            cmd_args = [str(target)]
            if combined_args:
                import shlex
                try:
                    cmd_args.extend(shlex.split(combined_args, posix=False))
                except Exception:
                    cmd_args.extend(combined_args.split())
            subprocess.Popen(
                cmd_args,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return f"Aplicación '{app.name}' iniciada correctamente."
