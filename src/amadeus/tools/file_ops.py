from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Dict, List, Optional, Tuple
import uuid

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore
from amadeus.config import AmadeusSettings, get_default_data_dir

RESERVED_WIN_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

FORBIDDEN_SYSTEM_PREFIXES = (
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata",
)

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".reg",
    ".wsf", ".scr", ".com", ".pif", ".cpl", ".hta", ".jar", ".lnk",
}


@dataclass(slots=True)
class PendingFileOperation:
    op_id: str
    op_type: str  # "move" | "rename" | "delete"
    summary: str
    items: List[Tuple[str, str]]  # [(src_path, dst_path_or_empty)]
    created_monotonic: float = field(default_factory=time.monotonic)
    ttl_sec: float = 120.0

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_monotonic) > self.ttl_sec


class SafeFileManager:
    """
    Phase F3 (Herramientas de Archivos con Sandbox, Confirmación, Papelera y /deshacer):
    - Only operates inside allowed personal folders (Desktop, Documents, Downloads, Pictures, Music, Videos + user roots).
    - Direct execution: list, search, open, create_folder, create_file.
    - Requires confirmation (PendingFileOperation): move, rename, delete.
    - Delete sends to Windows Recycle Bin (`FOF_ALLOWUNDO`) + stores a reversible staging copy for instant `/deshacer`.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        data_dir: Optional[Path] = None,
        extra_roots: Optional[List[Path]] = None,
    ) -> None:
        self.settings = settings
        self.data_dir = data_dir or get_default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "amadeus_memory.db"
        self.trash_staging_dir = self.data_dir / "undo_staging"
        self.trash_staging_dir.mkdir(parents=True, exist_ok=True)
        self._extra_roots: List[Path] = [p.resolve() for p in (extra_roots or [])]
        self._pending: Dict[str, PendingFileOperation] = {}
        self._init_journal_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=5.0)

    def _init_journal_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fs_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    op_type TEXT NOT NULL,
                    src_path TEXT NOT NULL,
                    dst_path TEXT DEFAULT '',
                    timestamp TEXT NOT NULL,
                    undone INTEGER DEFAULT 0
                );
                """
            )

    def get_allowed_roots(self) -> List[Path]:
        """Resolve standard personal folders + custom configured roots."""
        home = Path.home()
        candidates: List[Path] = []
        for folder_name in (
            "Desktop", "Escritorio",
            "Documents", "Documentos",
            "Downloads", "Descargas",
            "Pictures", "Imágenes",
            "Music", "Música",
            "Videos", "Vídeos",
        ):
            p = home / folder_name
            if p.exists():
                candidates.append(p.resolve())

        # Also check OneDrive redirected folders if present
        onedrive = os.environ.get("OneDrive")
        if onedrive:
            od_path = Path(onedrive)
            for sub in ("Desktop", "Escritorio", "Documents", "Documentos"):
                p = od_path / sub
                if p.exists():
                    candidates.append(p.resolve())

        for custom in self.settings.allowed_fs_roots:
            cp = Path(custom)
            if cp.exists():
                candidates.append(cp.resolve())

        candidates.extend(self._extra_roots)
        # Deduplicate preserving order
        seen = set()
        unique: List[Path] = []
        for c in candidates:
            s = str(c).lower()
            if s not in seen:
                seen.add(s)
                unique.append(c)
        return unique

    def resolve_user_folder(self, alias: str = "desktop") -> Path:
        """Resolve a user folder alias ('escritorio', 'descargas', 'documentos', etc.) to the existing Path on disk."""
        a = alias.strip().lower().rstrip("/\\")
        roots = self.get_allowed_roots()
        folder_map = {
            "escritorio": ("escritorio", "desktop"),
            "desktop": ("desktop", "escritorio"),
            "descargas": ("descargas", "downloads"),
            "downloads": ("downloads", "descargas"),
            "documentos": ("documentos", "documents"),
            "documents": ("documents", "documentos"),
            "imagenes": ("imágenes", "imagenes", "pictures"),
            "imágenes": ("imágenes", "imagenes", "pictures"),
            "pictures": ("pictures", "imágenes", "imagenes"),
            "musica": ("música", "musica", "music"),
            "música": ("música", "musica", "music"),
            "music": ("music", "música", "musica"),
            "videos": ("videos", "vídeos"),
            "vídeos": ("vídeos", "videos"),
        }
        targets = folder_map.get(a, (a,))
        # Check custom configured roots and _extra_roots first
        for custom_root in [*(Path(c).resolve() for c in self.settings.allowed_fs_roots if Path(c).exists()), *self._extra_roots]:
            if custom_root.name.lower() in targets:
                return custom_root

        matched: List[Path] = []
        for r in roots:
            if r.name.lower() in targets:
                matched.append(r)
        if matched:
            for m in matched:
                if "onedrive" in str(m).lower():
                    return m
            return matched[0]
        return roots[0] if roots else Path.home()

    def _normalize_input_path(self, raw_path: str | Path) -> Path:
        """Translate Spanish/English folder aliases ('Escritorio/Prueba', 'Descargas', 'nota.txt') into full safe paths."""
        if isinstance(raw_path, Path):
            if raw_path.is_absolute():
                return raw_path
            raw_str = str(raw_path)
        else:
            raw_str = str(raw_path).strip().strip("\"'")

        if not raw_str:
            return self.resolve_user_folder("escritorio")

        p = Path(raw_str).expanduser()
        if p.is_absolute():
            return p

        parts = [pt for pt in raw_str.replace("\\", "/").split("/") if pt and pt != "."]
        if not parts:
            return self.resolve_user_folder("escritorio")

        first_lower = parts[0].lower()
        known_aliases = {
            "escritorio", "desktop",
            "descargas", "downloads",
            "documentos", "documents",
            "imagenes", "imágenes", "pictures",
            "musica", "música", "music",
            "videos", "vídeos",
        }
        if first_lower in known_aliases:
            base = self.resolve_user_folder(first_lower)
            return base.joinpath(*parts[1:]) if len(parts) > 1 else base

        # Default bare relative paths (e.g. "Prueba" or "nota.txt") to the user's Desktop (or first allowed root)
        base = self.resolve_user_folder("escritorio")
        return base.joinpath(*parts)

    def validate_safe_path(self, raw_path: str | Path, must_exist: bool = False) -> Path:
        """
        Verify target path is strictly inside an allowed user root, has no reserved Windows names,
        and never touches Windows/Program Files directories.
        """
        p = self._normalize_input_path(raw_path)
        resolved = p.resolve(strict=must_exist)
        res_lower = str(resolved).lower()

        for forbidden in FORBIDDEN_SYSTEM_PREFIXES:
            if res_lower.startswith(forbidden):
                raise PermissionError(
                    f"Ruta bloqueada por seguridad (carpeta de sistema): {resolved}"
                )

        stem_upper = resolved.stem.upper()
        if stem_upper in RESERVED_WIN_NAMES:
            raise ValueError(f"Nombre de archivo reservado por Windows no permitido: {resolved.name}")

        allowed = self.get_allowed_roots()
        is_inside = any(
            resolved == root or root in resolved.parents for root in allowed
        )
        if not is_inside:
            raise PermissionError(
                f"La ruta '{resolved}' está fuera de las carpetas personales autorizadas."
            )
        return resolved

    # --- Direct Execution Operations (Level 1: Safe) ---

    def fs_list(self, folder_path: str | Path) -> List[str]:
        target = self.validate_safe_path(folder_path, must_exist=True)
        if not target.is_dir():
            raise NotADirectoryError(f"'{target}' no es una carpeta.")
        return sorted(item.name + ("/" if item.is_dir() else "") for item in target.iterdir())

    def fs_search(self, root_folder: str | Path, pattern: str) -> List[str]:
        target = self.validate_safe_path(root_folder, must_exist=True)
        matches = []
        for p in target.rglob(f"*{pattern}*"):
            try:
                self.validate_safe_path(p)
                matches.append(str(p))
                if len(matches) >= 50:
                    break
            except PermissionError:
                continue
        return matches

    def fs_create_folder(self, folder_path: str | Path) -> str:
        target = self.validate_safe_path(folder_path, must_exist=False)
        target.mkdir(parents=True, exist_ok=True)
        self._record_journal(uuid.uuid4().hex[:8], "create_folder", str(target), "")
        return f"Carpeta creada: {target}"

    def fs_create_file(self, file_path: str | Path, content: str = "", overwrite: bool = False) -> str:
        target = self.validate_safe_path(file_path, must_exist=False)
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"El archivo '{target.name}' ya existe en esa ubicación. Especifica 'sobrescribir' si deseas reemplazarlo."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._record_journal(uuid.uuid4().hex[:8], "create_file", str(target), "")
        return f"Archivo creado: {target}"

    def fs_open(self, path: str | Path, dry_run: bool = False) -> str:
        try:
            target = self.validate_safe_path(path, must_exist=True)
        except FileNotFoundError:
            # Search across allowed roots (Desktop, Downloads, Documents) for matching file/folder name
            query_name = Path(str(path).strip().strip("\"'")).name.lower()
            found: Optional[Path] = None
            for root in self.get_allowed_roots():
                candidate = root / query_name
                if candidate.exists():
                    found = candidate
                    break
                for item in root.iterdir():
                    if item.name.lower() == query_name or item.stem.lower() == query_name:
                        found = item
                        break
                if found:
                    break
            if found is None:
                raise FileNotFoundError(f"No encontré el archivo o carpeta '{path}' en tu Escritorio, Descargas ni Documentos.")
            target = self.validate_safe_path(found, must_exist=True)

        if target.suffix.lower() in DANGEROUS_EXTENSIONS:
            raise PermissionError(
                f"Apertura bloqueada por seguridad: no se permite ejecutar binarios o scripts ({target.suffix}). "
                "Para iniciar programas autorizados, usa el comando de aplicación."
            )

        if dry_run or os.name != "nt":
            return f"Abierto: {target}"
        os.startfile(str(target))  # type: ignore[attr-defined]
        return f"Abierto: {target}"

    # --- Confirmation-Gated Operations (Level 2: Move, Rename, Delete) ---

    def request_move(self, src_paths: List[str | Path], dst_folder: str | Path) -> PendingFileOperation:
        dst_dir = self.validate_safe_path(dst_folder, must_exist=False)
        pairs: List[Tuple[str, str]] = []
        for s in src_paths:
            src = self.validate_safe_path(s, must_exist=True)
            pairs.append((str(src), str(dst_dir / src.name)))
        op_id = uuid.uuid4().hex[:8]
        summary = f"Voy a mover {len(pairs)} elemento(s) hacia '{dst_dir.name}'. ¿Confirmas?"
        op = PendingFileOperation(op_id=op_id, op_type="move", summary=summary, items=pairs)
        self._pending[op_id] = op
        return op

    def request_rename(self, src_path: str | Path, new_name: str) -> PendingFileOperation:
        if "/" in new_name or "\\" in new_name or ".." in new_name:
            raise ValueError("El nuevo nombre no debe contener barras de ruta.")
        src = self.validate_safe_path(src_path, must_exist=True)
        dst = self.validate_safe_path(src.parent / new_name, must_exist=False)
        op_id = uuid.uuid4().hex[:8]
        summary = f"Voy a renombrar '{src.name}' a '{dst.name}'. ¿Confirmas?"
        op = PendingFileOperation(
            op_id=op_id, op_type="rename", summary=summary, items=[(str(src), str(dst))]
        )
        self._pending[op_id] = op
        return op

    def request_delete(self, target_paths: List[str | Path]) -> PendingFileOperation:
        pairs: List[Tuple[str, str]] = []
        for t in target_paths:
            resolved = self.validate_safe_path(t, must_exist=True)
            pairs.append((str(resolved), ""))
        op_id = uuid.uuid4().hex[:8]
        summary = (
            f"Voy a enviar {len(pairs)} elemento(s) a la Papelera de reciclaje. ¿Confirmas?"
        )
        op = PendingFileOperation(op_id=op_id, op_type="delete", summary=summary, items=pairs)
        self._pending[op_id] = op
        return op

    def request_execute(
        self, path: str | Path, args: Optional[List[str]] = None
    ) -> PendingFileOperation:
        try:
            target = self.validate_safe_path(path, must_exist=True)
        except FileNotFoundError:
            # Search across allowed roots
            query_name = Path(str(path).strip().strip("\"'")).name.lower()
            found: Optional[Path] = None
            for root in self.get_allowed_roots():
                candidate = root / query_name
                if candidate.exists():
                    found = candidate
                    break
                for item in root.iterdir():
                    if item.name.lower() == query_name or item.stem.lower() == query_name:
                        found = item
                        break
                if found:
                    break
            if found is None:
                raise FileNotFoundError(
                    f"No encontré el archivo '{path}' para ejecutar en tus carpetas personales."
                )
            target = self.validate_safe_path(found, must_exist=True)

        if not target.is_file():
            raise IsADirectoryError(f"'{target}' es una carpeta, no un archivo ejecutable.")

        op_id = uuid.uuid4().hex[:8]
        args_list = args or []
        summary = f"¿Autorizas ejecutar '{target.name}'?"
        op = PendingFileOperation(
            op_id=op_id,
            op_type="execute",
            summary=summary,
            items=[(str(target), json.dumps(args_list))],
        )
        self._pending[op_id] = op
        return op

    def resolve_pending(self, op_id: str, approved: bool) -> str:
        op = self._pending.pop(op_id, None)
        if op is None:
            return "No encontré esa operación pendiente o ya fue procesada."
        if op.is_expired:
            return "La solicitud de confirmación caducó por seguridad (más de 2 minutos)."
        if not approved:
            return "Operación cancelada; no se modificó ni ejecutó ningún archivo."

        batch_id = op.op_id
        if op.op_type == "execute":
            import subprocess
            import sys

            target = Path(op.items[0][0])
            args_raw = json.loads(op.items[0][1]) if op.items[0][1] else []
            suf = target.suffix.lower()

            if suf == ".py":
                cmd = [sys.executable, str(target), *args_raw]
            elif suf in (".bat", ".cmd"):
                cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(target), *args_raw]
            elif suf == ".ps1":
                cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(target), *args_raw]
            else:
                cmd = [str(target), *args_raw]

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=20.0,
                    shell=False,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                out_clean = output.strip() or "(Ejecución finalizada sin salida en consola)"
                return f"Ejecución de '{target.name}' finalizada (código {proc.returncode}).\n---DETALLE---\n{out_clean}"
            except subprocess.TimeoutExpired:
                return f"Ejecución de '{target.name}' cancelada: superó el límite de tiempo (20s)."
            except Exception as exc:
                return f"Error al ejecutar '{target.name}': {exc}"

        if op.op_type in ("move", "rename"):
            for src_str, dst_str in op.items:
                src = Path(src_str)
                dst = Path(dst_str)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                self._record_journal(batch_id, op.op_type, src_str, dst_str)
            return f"Listo: {len(op.items)} elemento(s) procesados ({op.op_type}). Puedes revertirlo con `/deshacer`."

        if op.op_type == "delete":
            for src_str, _ in op.items:
                src = Path(src_str)
                staged_path = self.trash_staging_dir / f"{batch_id}_{src.name}"
                # Keep a staging copy for instant reliable /deshacer AND send original to Windows Recycle Bin
                if src.is_dir():
                    shutil.copytree(src, staged_path)
                else:
                    shutil.copy2(src, staged_path)
                self._send_to_windows_recycle_bin(src)
                self._record_journal(batch_id, "delete", src_str, str(staged_path))
            return f"Enviados {len(op.items)} elemento(s) a la Papelera. Usa `/deshacer` si quieres restaurarlos."

        return "Tipo de operación desconocido."

    @staticmethod
    def _send_to_windows_recycle_bin(target: Path) -> None:
        """Send file/folder to Windows Recycle Bin via SHFileOperationW with FOF_ALLOWUNDO."""
        if os.name == "nt":
            try:
                class SHFILEOPSTRUCTW(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", ctypes.c_void_p),
                        ("wFunc", ctypes.c_uint),
                        ("pFrom", ctypes.c_wchar_p),
                        ("pTo", ctypes.c_wchar_p),
                        ("fFlags", ctypes.c_ushort),
                        ("fAnyOperationsAborted", ctypes.c_int),
                        ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", ctypes.c_wchar_p),
                    ]

                FO_DELETE = 3
                FOF_SILENT = 0x0004
                FOF_NOCONFIRMATION = 0x0010
                FOF_ALLOWUNDO = 0x0040
                FOF_NOERRORUI = 0x0400

                op = SHFILEOPSTRUCTW()
                op.wFunc = FO_DELETE
                op.pFrom = str(target) + "\0\0"
                op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
                res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
                if res == 0 and not target.exists():
                    return
            except Exception:
                pass

        # Fallback if running in headless test container where Shell Recycle Bin is unavailable:
        # Note: a full copy is already preserved in `trash_staging_dir` before this is called.
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    def _record_journal(self, batch_id: str, op_type: str, src: str, dst: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fs_journal (batch_id, op_type, src_path, dst_path, timestamp, undone)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (batch_id, op_type, src, dst, now),
            )

    def undo_last_batch(self) -> str:
        """Reverse the most recent file operation batch (/deshacer)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT batch_id FROM fs_journal WHERE undone = 0 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return "No hay operaciones de archivos pendientes por deshacer."
            batch_id = row[0]
            items = conn.execute(
                "SELECT id, op_type, src_path, dst_path FROM fs_journal WHERE batch_id = ? AND undone = 0 ORDER BY id DESC",
                (batch_id,),
            ).fetchall()

            restored_count = 0
            for row_id, op_type, src_str, dst_str in items:
                src = Path(src_str)
                dst = Path(dst_str) if dst_str else None
                if op_type in ("move", "rename") and dst and dst.exists():
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
                    restored_count += 1
                elif op_type == "delete" and dst and dst.exists():
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
                    restored_count += 1
                elif op_type == "create_file" and src.exists():
                    src.unlink()
                    restored_count += 1
                elif op_type == "create_folder" and src.exists():
                    try:
                        src.rmdir()
                        restored_count += 1
                    except OSError:
                        pass
                conn.execute("UPDATE fs_journal SET undone = 1 WHERE id = ?", (row_id,))

        return f"Deshecho lote `{batch_id}` ({restored_count} cambio(s) revertidos)."

    def bind_commands(self, core: AmadeusAgentCore) -> None:
        async def _cmd_undo(args: str, msg: AgentMessage) -> str:
            return self.undo_last_batch()

        core.register_command("deshacer", _cmd_undo)
        core.register_command("undo", _cmd_undo)
