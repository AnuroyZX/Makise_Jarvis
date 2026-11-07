from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from amadeus.tools.app_launcher import WindowsAppLauncher
from amadeus.tools.file_ops import PendingFileOperation, SafeFileManager
from amadeus.tools.mail_calendar import wrap_untrusted
from amadeus.tools.screen_context import ScreenContextManager

TOOL_CALL_JSON_RE = re.compile(r"\{[^{}]*\"tool\"\s*:\s*\"[^\"]+\".*\}", re.DOTALL)


class AmadeusToolDispatcher:
    """
    Phase F3 (Bucle de Herramientas y Acciones Naturales):
    Executes up to `max_steps` tool calls per user request across:
      - File system tools (`fs_list`, `fs_search`, `fs_open`, `fs_create_folder`, `fs_create_file`,
        and confirmation-gated `fs_move`, `fs_rename`, `fs_delete`)
      - Screen awareness (`screen_look`)
      - Application launching (`launch_app`)
    Stops immediately if a tool produces a `PendingFileOperation` requiring user confirmation.
    """

    MAX_STEPS = 6

    def __init__(
        self,
        file_ops: SafeFileManager,
        screen: ScreenContextManager,
        app_launcher: WindowsAppLauncher,
    ) -> None:
        self.file_ops = file_ops
        self.screen = screen
        self.app_launcher = app_launcher
        self.last_pending_operation: Optional[PendingFileOperation] = None

    @staticmethod
    def build_tools_prompt_instructions() -> str:
        return (
            "## HERRAMIENTAS DE ESCRITORIO Y ARCHIVOS (Módulo 7)\n"
            "Si el usuario pide ejecutar una acción sobre archivos, carpetas, apps o mirar su pantalla, "
            "puedes invocar una herramienta respondiendo con un bloque JSON:\n"
            "{\"tool\": \"<nombre>\", \"args\": {...}}\n"
            "Herramientas disponibles:\n"
            "- `fs_list`: {\"path\": \"...\"}\n"
            "- `fs_search`: {\"path\": \"...\", \"pattern\": \"...\"}\n"
            "- `fs_create_folder`: {\"path\": \"...\"}\n"
            "- `fs_create_file`: {\"path\": \"...\", \"content\": \"...\"}\n"
            "- `fs_open`: {\"path\": \"...\"}\n"
            "- `execute_file`: {\"path\": \"...\", \"args\": [\"...\"]} (pide confirmación para scripts/programas)\n"
            "- `fs_move`: {\"src_paths\": [\"...\"], \"dst_folder\": \"...\"} (pide confirmación)\n"
            "- `fs_rename`: {\"src_path\": \"...\", \"new_name\": \"...\"} (pide confirmación)\n"
            "- `fs_delete`: {\"target_paths\": [\"...\"]} (envía a Papelera con confirmación)\n"
            "- `screen_look`: {\"question\": \"...\"}\n"
            "- `launch_app`: {\"app\": \"...\"}"
        )

    def extract_tool_call(self, llm_output: str) -> Optional[Dict[str, Any]]:
        match = TOOL_CALL_JSON_RE.search(llm_output.strip())
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and "tool" in obj:
                return obj
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _extract_target_root(text_lower: str) -> str:
        for alias in (
            "descargas", "downloads",
            "documentos", "documents",
            "escritorio", "desktop",
            "imágenes", "imagenes", "pictures",
            "música", "musica", "music",
            "videos", "vídeos",
        ):
            if re.search(rf"\b{re.escape(alias)}\b", text_lower):
                return alias
        return "escritorio"

    async def try_natural_language_action(
        self, user_text: str
    ) -> Optional[tuple[str, Optional[PendingFileOperation]]]:
        """
        Deterministically detect and execute Spanish/English natural-language desktop commands
        (screen analysis, creating folders/files, listing folders, opening files/apps, deleting/renaming)
        so actions always execute reliably even with the Zero-Config Free LLM.
        """
        clean = user_text.strip()
        lower = clean.lower()

        # 1. Screen Look / Analysis
        if any(
            kw in lower
            for kw in (
                "qué ves en mi pantalla",
                "que ves en mi pantalla",
                "mira mi pantalla",
                "analiza mi pantalla",
                "analizar mi pantalla",
                "qué hay en mi pantalla",
                "que hay en mi pantalla",
            )
        ):
            res = await self.screen.analyze_current_screen(clean)
            return res, None

        # 2. List files in a folder ("Lista mis archivos recientes en Descargas", "ver descargas", "qué archivos hay en escritorio")
        if re.search(
            r"\b(lista|listar|muestra|mostrar|ver|qué archivos|que archivos)\b.*\b(descargas|downloads|escritorio|desktop|documentos|documents|imágenes|imagenes|música|musica|videos)\b",
            lower,
        ):
            root_alias = self._extract_target_root(lower)
            try:
                items = self.file_ops.fs_list(root_alias)
                count = len(items)
                preview = "\n".join(f"• {name}" for name in items[:25]) or "(Carpeta vacía)"
                reply = (
                    f"[emotion:analytical] [gesture:nod] Encontré {count} elementos en tu carpeta {root_alias.capitalize()}.\n"
                    f"---DETALLE---\n📂 {root_alias.capitalize()} ({count} elementos):\n{preview}"
                )
                return reply, None
            except Exception as exc:
                return f"[emotion:serious] No pude listar la carpeta {root_alias}: {exc}", None

        # 3. Create Folder ("Crea una carpeta llamada Prueba en Escritorio", "crea una carpeta Prueba")
        m_folder = re.search(
            r"\b(?:crea|crear|haz|hacer|nueva)\s+(?:una\s+|la\s+)?carpeta\s+(?:llamada\s+|con\s+nombre\s+)?[\"']?([^\"'\n]+?)[\"']?(?:\s+en\s+(?:el\s+|la\s+|mi\s+|mis\s+)?(escritorio|desktop|documentos|documents|descargas|downloads|imágenes|imagenes|música|musica|videos))?$",
            clean,
            re.IGNORECASE,
        )
        if m_folder:
            folder_name = m_folder.group(1).strip().strip("\"'.,")
            # Strip trailing "en escritorio" if captured inside group 1
            folder_name = re.sub(
                r"\s+en\s+(?:el\s+|la\s+|mi\s+)?(?:escritorio|desktop|documentos|documents|descargas|downloads).*$",
                "",
                folder_name,
                flags=re.IGNORECASE,
            ).strip()
            root_alias = (m_folder.group(2) or self._extract_target_root(lower)).lower()
            try:
                msg = self.file_ops.fs_create_folder(f"{root_alias}/{folder_name}")
                return (
                    f"[emotion:smug] [gesture:nod] Listo, he creado la carpeta '{folder_name}' en tu {root_alias.capitalize()}.\n---DETALLE---\n✅ {msg}",
                    None,
                )
            except Exception as exc:
                return f"[emotion:serious] No pude crear la carpeta '{folder_name}': {exc}", None

        # 4. Create File ("Crea un archivo nota.txt en Escritorio con Hola mundo", "crear archivo prueba.txt")
        m_file = re.search(
            r"\b(?:crea|crear|haz|hacer|escribe|escribir|nuevo|create|write)\s+(?:un\s+|el\s+|a\s+)?(?:archivo|script|documento|file)(?:\s+de\s+texto)?\s+(?:llamado\s+)?[\"']?([^\s\"']+?)[\"']?(?:\s+en\s+(?:el\s+|la\s+|mi\s+)?(escritorio|desktop|documentos|documents|descargas|downloads))?(?:\s+(?:con\s+el\s+texto|con\s+contenido|que\s+diga|con)\s+(.+))?$",
            clean,
            re.IGNORECASE,
        )
        if m_file:
            file_name = m_file.group(1).strip().strip("\"'.,")
            if "." not in file_name:
                file_name += ".txt"
            root_alias = (m_file.group(2) or self._extract_target_root(lower)).lower()
            content = (m_file.group(3) or "Creado por Makise Kurisu (Amadeus System).").strip().strip("\"'")
            try:
                msg = self.file_ops.fs_create_file(f"{root_alias}/{file_name}", content=content)
                return (
                    f"[emotion:smug] [gesture:nod] He creado el archivo '{file_name}' en tu {root_alias.capitalize()}.\n---DETALLE---\n✅ {msg}",
                    None,
                )
            except Exception as exc:
                return f"[emotion:serious] No pude crear el archivo '{file_name}': {exc}", None

        # 4b. Combined: Create and Execute ("Crea y ejecuta un script saludo.py con print('Hola')")
        m_create_and_exec = re.search(
            r"\b(?:crea\s+y\s+ejecuta|escribe\s+y\s+ejecuta|crear\s+y\s+ejecutar)\s+(?:un\s+|el\s+)?(?:script\s+|archivo\s+)?[\"']?([^\s\"']+?\.(?:py|bat|cmd|ps1))[\"']?(?:\s+(?:con\s+el\s+texto|con\s+contenido|que\s+diga|con)\s+(.+))?$",
            clean,
            re.IGNORECASE,
        )
        if m_create_and_exec:
            script_name = m_create_and_exec.group(1).strip().strip("\"'.,")
            root_alias = self._extract_target_root(lower).lower()
            content = (m_create_and_exec.group(2) or "print('Ejecutado por Amadeus Kurisu')").strip().strip("\"'")
            try:
                self.file_ops.fs_create_file(f"{root_alias}/{script_name}", content=content, overwrite=True)
                op = self.file_ops.request_execute(f"{root_alias}/{script_name}")
                self.last_pending_operation = op
                return f"[emotion:smug] He creado '{script_name}' en tu {root_alias.capitalize()}. {op.summary}", op
            except Exception as exc:
                return f"[emotion:serious] No pude preparar '{script_name}': {exc}", None

        # 4c. Execute Script / Program with Confirmation Card ("Ejecuta el script saludo.py", "corre prueba.py")
        m_exec = re.search(
            r"\b(?:ejecuta|ejecutar|corre|correr|run|execute)\s+(?:el\s+|the\s+)?(?:script\s+|archivo\s+|file\s+|código\s+)?[\"']?([^\s\"']+?\.(?:py|bat|cmd|ps1|exe))[\"']?(?:\s+(?:con\s+argumentos|args)\s+(.+))?$",
            clean,
            re.IGNORECASE,
        )
        if m_exec:
            script_name = m_exec.group(1).strip().strip("\"'.,")
            args_str = m_exec.group(2) or ""
            args_list = [a.strip() for a in args_str.split() if a.strip()]
            try:
                op = self.file_ops.request_execute(script_name, args=args_list)
                self.last_pending_operation = op
                return f"[emotion:serious] {op.summary}", op
            except Exception as exc:
                return f"[emotion:serious] No pude preparar la ejecución de '{script_name}': {exc}", None

        # 5. Open File, Folder, or Application ("Abre bloc de notas", "Abre la carpeta Descargas", "Abre nota.txt")
        m_open = re.search(
            r"^\s*(?:por\s+favor\s+)?(?:oye\s+kurisu\s*,?\s*)?(?:abre|abrir|ejecuta|ejecutar|inicia|iniciar|lanza|lanzar)\s+(?:el\s+|la\s+|los\s+|las\s+|mi\s+|mis\s+)?(?:aplicaci[oó]n\s+|programa\s+|archivo\s+|carpeta\s+)?[\"']?(.+?)[\"']?\.?\s*$",
            clean,
            re.IGNORECASE,
        )
        if m_open:
            target_raw = m_open.group(1).strip().strip("\"'.,")
            target_lower = target_raw.lower()

            # 5a. Is it a known user folder alias ("descargas", "escritorio", "documentos")?
            if target_lower in (
                "escritorio", "desktop",
                "descargas", "downloads",
                "documentos", "documents",
                "imágenes", "imagenes", "pictures",
                "música", "musica", "music",
                "videos", "vídeos",
            ):
                try:
                    msg = self.file_ops.fs_open(target_lower)
                    return f"[emotion:neutral] [gesture:nod] Abriendo tu carpeta {target_raw.capitalize()}.\n---DETALLE---\n📂 {msg}", None
                except Exception as exc:
                    return f"[emotion:serious] No pude abrir la carpeta {target_raw}: {exc}", None

            # 5b. Is it an application ("bloc de notas", "calculadora", "chrome", "vscode", etc.)?
            app = self.app_launcher.find_app(target_lower)
            if app is not None and "." not in target_lower:
                msg = self.app_launcher.launch(target_lower)
                return f"[emotion:smug] [gesture:nod] {msg}", None

            # 5c. Otherwise open file or folder in Desktop / Downloads / Documents
            try:
                msg = self.file_ops.fs_open(target_raw)
                return f"[emotion:neutral] [gesture:nod] He abierto '{target_raw}' en tu escritorio.\n---DETALLE---\n📄 {msg}", None
            except Exception as exc:
                if app is not None:
                    msg = self.app_launcher.launch(target_lower)
                    return f"[emotion:smug] [gesture:nod] {msg}", None
                return f"[emotion:serious] {exc}", None

        # 6. Delete file/folder (with confirmation card)
        m_del = re.search(
            r"\b(?:elimina|eliminar|borra|borrar|manda\s+a\s+la\s+papelera)\s+(?:el\s+|la\s+)?(?:archivo\s+|carpeta\s+)?[\"']?([^\"'\n]+?)[\"']?$",
            clean,
            re.IGNORECASE,
        )
        if m_del:
            target_raw = m_del.group(1).strip().strip("\"'.,")
            try:
                op = self.file_ops.request_delete([target_raw])
                self.last_pending_operation = op
                return f"[emotion:serious] {op.summary}", op
            except Exception as exc:
                return f"[emotion:serious] No encontré '{target_raw}' para eliminar: {exc}", None

        return None

    async def execute_tool_call(
        self, tool_name: str, args: Dict[str, Any]
    ) -> tuple[str, Optional[PendingFileOperation]]:
        """
        Execute a single tool call. Returns `(tool_result_text, pending_confirmation_or_none)`.
        """
        self.last_pending_operation = None
        name = tool_name.strip().lower()

        try:
            if name == "fs_list":
                items = self.file_ops.fs_list(str(args.get("path", "")))
                return wrap_untrusted("\n".join(items[:80]), source_label="fs_list"), None

            if name == "fs_search":
                matches = self.file_ops.fs_search(
                    str(args.get("path", "")), str(args.get("pattern", ""))
                )
                return wrap_untrusted("\n".join(matches), source_label="fs_search"), None

            if name == "fs_create_folder":
                return self.file_ops.fs_create_folder(str(args.get("path", ""))), None

            if name == "fs_create_file":
                overwrite = bool(args.get("overwrite", False))
                return (
                    self.file_ops.fs_create_file(
                        str(args.get("path", "")),
                        str(args.get("content", "")),
                        overwrite=overwrite,
                    ),
                    None,
                )

            if name == "fs_open":
                return (
                    self.file_ops.fs_open(
                        str(args.get("path", "")), dry_run=bool(args.get("dry_run", False))
                    ),
                    None,
                )

            if name == "execute_file":
                path_str = str(args.get("path", ""))
                args_arr = args.get("args") or []
                if isinstance(args_arr, str):
                    args_arr = [args_arr]
                op = self.file_ops.request_execute(path_str, args=args_arr)
                self.last_pending_operation = op
                return op.summary, op

            if name == "fs_move":
                srcs = [str(p) for p in (args.get("src_paths") or [])]
                dst = str(args.get("dst_folder", ""))
                op = self.file_ops.request_move(srcs, dst)
                self.last_pending_operation = op
                return op.summary, op

            if name == "fs_rename":
                op = self.file_ops.request_rename(
                    str(args.get("src_path", "")), str(args.get("new_name", ""))
                )
                self.last_pending_operation = op
                return op.summary, op

            if name == "fs_delete":
                targets = [str(p) for p in (args.get("target_paths") or [])]
                op = self.file_ops.request_delete(targets)
                self.last_pending_operation = op
                return op.summary, op

            if name == "screen_look":
                question = str(args.get("question") or "¿Qué hay en pantalla?")
                analysis = await self.screen.analyze_current_screen(question)
                return analysis, None

            if name == "launch_app":
                return (
                    self.app_launcher.launch(
                        str(args.get("app", "")), dry_run=bool(args.get("dry_run", False))
                    ),
                    None,
                )

            return f"Herramienta desconocida: {name}", None
        except Exception as exc:
            return f"Error al ejecutar {name}: {exc}", None
