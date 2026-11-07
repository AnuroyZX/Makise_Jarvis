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
                return (
                    self.file_ops.fs_create_file(
                        str(args.get("path", "")), str(args.get("content", ""))
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
