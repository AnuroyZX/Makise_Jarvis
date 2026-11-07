from __future__ import annotations

from typing import Optional

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor
from amadeus.tools.app_launcher import WindowsAppLauncher
from amadeus.tools.browser_tool import EphemeralBrowserTool
from amadeus.tools.mail_calendar import MailCalendarTool


class AmadeusToolkit:
    """
    Module 7 (Herramientas Unidas):
    Bundles WindowsAppLauncher, MailCalendarTool, and EphemeralBrowserTool,
    connects them to Module 1 (ResourceGovernor) to auto-kill idle browser on BACKGROUND_ECO,
    and binds direct commands & context gatherers to Module 2 (AmadeusAgentCore).
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        governor: ResourceGovernor,
        app_launcher: Optional[WindowsAppLauncher] = None,
        mail_calendar: Optional[MailCalendarTool] = None,
        browser: Optional[EphemeralBrowserTool] = None,
    ) -> None:
        self.settings = settings
        self.governor = governor
        self.app_launcher = app_launcher or WindowsAppLauncher()
        self.mail_calendar = mail_calendar or MailCalendarTool(settings=settings)
        self.browser = browser or EphemeralBrowserTool(
            governor=governor,
            idle_timeout_sec=float(settings.browser_idle_timeout_sec),
        )
        # When dropping to BACKGROUND_ECO, immediately close any ephemeral browser
        self.governor.register_listener(self._on_power_mode_changed)

    def _on_power_mode_changed(self, mode: PowerMode) -> None:
        if mode == PowerMode.BACKGROUND_ECO:
            self.browser.close_ephemeral_if_idle(force=True)

    def bind_commands(self, core: AmadeusAgentCore) -> None:
        async def _cmd_apps(args: str, msg: AgentMessage) -> str:
            sample = sorted(self.app_launcher.catalog.keys())[:25]
            return (
                f"Aplicaciones autodescubiertas en este PC ({len(self.app_launcher.catalog)} total):\n"
                + ", ".join(sample)
                + "\nUsa `/open <nombre>` para iniciar cualquiera."
            )

        async def _cmd_open(args: str, msg: AgentMessage) -> str:
            if not args.strip():
                return "Uso: `/open <nombre de aplicación>` (ej. `/open vscode`, `/open notepad`)"
            return self.app_launcher.launch(args.strip())

        async def _cmd_agenda(args: str, msg: AgentMessage) -> str:
            return f"📅 **Agenda**:\n{self.mail_calendar.get_agenda_summary()}"

        async def _cmd_event(args: str, msg: AgentMessage) -> str:
            if "|" not in args:
                return "Uso: `/event <YYYY-MM-DD HH:MM> | <Título del evento>`"
            when, title = args.split("|", 1)
            ev = self.mail_calendar.add_calendar_event(title=title, start_iso=when)
            return f"Evento añadido a tu agenda: [{ev.start_iso}] {ev.title}"

        async def _cmd_emails(args: str, msg: AgentMessage) -> str:
            return f"📬 **Correos recientes**:\n{self.mail_calendar.fetch_recent_unread_emails()}"

        core.register_command("apps", _cmd_apps)
        core.register_command("open", _cmd_open)
        core.register_command("agenda", _cmd_agenda)
        core.register_command("event", _cmd_event)
        core.register_command("emails", _cmd_emails)
