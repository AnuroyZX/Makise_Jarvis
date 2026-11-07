from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import imaplib
import email
from email.header import decode_header
import json
from pathlib import Path
from typing import List, Optional

from amadeus.config import AmadeusSettings, get_default_data_dir


def wrap_untrusted(content: str, source_label: str) -> str:
    """
    ECC AgentShield Rule 3: Always wrap external emails, web pages, and calendar items
    inside <untrusted_data> delimiters to neutralize prompt injection attempts.
    """
    sanitized = content.replace("</untrusted_data>", "[/untrusted_data]")
    return f"<untrusted_data source=\"{source_label}\">\n{sanitized}\n</untrusted_data>"


@dataclass(slots=True)
class CalendarEvent:
    title: str
    start_iso: str
    notes: str = ""


class MailCalendarTool:
    """
    Module 7 (Herramientas - Correo y Calendario):
    Provides IMAP unread email summary (compatible with Gmail App Passwords, Outlook, etc.)
    and a portable local + CalDAV-ready Calendar Agenda with AgentShield untrusted wrapping.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        data_dir: Optional[Path] = None,
    ) -> None:
        self.settings = settings
        self.data_dir = data_dir or get_default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.calendar_file = self.data_dir / "calendar_events.json"

    def add_calendar_event(self, title: str, start_iso: str, notes: str = "") -> CalendarEvent:
        events = self.list_calendar_events()
        ev = CalendarEvent(title=title.strip(), start_iso=start_iso.strip(), notes=notes.strip())
        events.append(ev)
        events.sort(key=lambda x: x.start_iso)
        self.calendar_file.write_text(
            json.dumps([asdict(e) for e in events], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return ev

    def list_calendar_events(self) -> List[CalendarEvent]:
        if not self.calendar_file.exists():
            return []
        try:
            raw = json.loads(self.calendar_file.read_text(encoding="utf-8"))
            return [CalendarEvent(**item) for item in raw]
        except Exception:
            return []

    def get_agenda_summary(self) -> str:
        events = self.list_calendar_events()
        if not events:
            return "No tienes eventos programados en tu agenda local."
        lines = [
            f"• [{e.start_iso}] {e.title}" + (f" ({e.notes})" if e.notes else "")
            for e in events[:10]
        ]
        return wrap_untrusted("\n".join(lines), source_label="calendar")

    def fetch_recent_unread_emails(self, max_count: int = 5) -> str:
        """Fetch recent unread email subjects/senders via IMAP over SSL."""
        if not (self.settings.imap_host and self.settings.imap_user and self.settings.imap_password):
            return (
                "El correo IMAP no está configurado todavía. "
                "Puedes añadir tu servidor IMAP/Gmail en el asistente de Amadeus."
            )
        try:
            with imaplib.IMAP4_SSL(self.settings.imap_host, timeout=8) as mail:
                mail.login(self.settings.imap_user, self.settings.imap_password)
                mail.select("INBOX", readonly=True)
                _, search_data = mail.search(None, "UNSEEN")
                ids = search_data[0].split() if search_data and search_data[0] else []
                if not ids:
                    return "No tienes correos nuevos sin leer en tu bandeja de entrada."

                recent_ids = ids[-max_count:]
                summaries: List[str] = []
                for msg_id in reversed(recent_ids):
                    _, msg_data = mail.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                    if msg_data and msg_data[0] and isinstance(msg_data[0], tuple):
                        msg = email.message_from_bytes(msg_data[0][1])
                        subj = self._decode_mime_header(msg.get("Subject", "(Sin asunto)"))
                        sender = self._decode_mime_header(msg.get("From", "(Desconocido)"))
                        summaries.append(f"• De: {sender} | Asunto: {subj}")

                return wrap_untrusted("\n".join(summaries), source_label="email_inbox")
        except Exception as exc:
            return f"No se pudo consultar el correo IMAP ({type(exc).__name__})."

    @staticmethod
    def _decode_mime_header(raw_header: str) -> str:
        parts = decode_header(raw_header)
        decoded: List[str] = []
        for content, enc in parts:
            if isinstance(content, bytes):
                decoded.append(content.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(content))
        return "".join(decoded).strip()
