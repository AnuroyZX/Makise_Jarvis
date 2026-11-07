from __future__ import annotations

import argparse
import asyncio
import sys
import webbrowser

from amadeus.house.resource_governor import PowerMode
from amadeus.system_builder import AmadeusSystem


async def run_interactive_cli(system: AmadeusSystem, open_ui: bool = False) -> None:
    snap = system.governor.snapshot()
    print("=" * 68)
    print("  AMADEUS SYSTEM // MAKISE KURISU v1.0 (9-Module Architecture)")
    print(f"  Host: {system.host_profile.os_name} {system.host_profile.os_release} | "
          f"RAM Proceso: {snap.process_rss_mb} MB | Modo: {snap.power_mode.value}")
    print(f"  Apps Windows Detectadas: {len(system.toolkit.app_launcher.catalog)} | "
          f"Skills Cargadas: {len(system.skills.skills)}")
    print("  Comandos rápidos: /status, /brain, /remember, /whoami, /apps, /open, /agenda, /eco, /wake, /ui, /exit")
    print("=" * 68)

    if open_ui or not system.settings.onboarding_completed:
        url = await system.web_ui.start()
        print(f"[Amadeus Onboarding / Panel Web Efímero activo en]: {url}")
        webbrowser.open(url)

    while True:
        try:
            user_input = await asyncio.to_thread(input, "\n[Tú] > ")
        except (EOFError, KeyboardInterrupt):
            break

        clean = user_input.strip()
        if not clean:
            continue
        if clean.lower() in ("/exit", "/quit", "salir"):
            break
        if clean.lower() == "/ui":
            url = await system.web_ui.start()
            print(f"[Amadeus Web UI]: {url}")
            webbrowser.open(url)
            continue

        reply, audio_file = await system.pc_gateway.send_local_prompt(clean)
        print(f"\n[Kurisu ({reply.emotion.value})]: {reply.content}")
        if audio_file:
            print(f"  🔊 Audio sintetizado: {audio_file}")

    await system.shutdown()


async def run_headless_daemon(system: AmadeusSystem) -> None:
    """
    Phase F0/F1 Headless Daemon Mode for Electron Desktop Companion:
    Starts the authenticated WebSocket bridge (`127.0.0.1`), the Panel HTTP API,
    and background Telegram polling, then prints the connection handshake line to stdout.
    """
    ws_url = await system.ws_bridge.start()
    ui_url = await system.web_ui.start()
    # Disable auto-shutdown on the panel API when controlled by Electron
    system.web_ui.idle_timeout_sec = 86400.0
    print(
        f"AMADEUS_READY ws_port={system.ws_bridge.port} "
        f"ws_token={system.ws_bridge.auth_token} "
        f"http_url={ui_url}",
        flush=True,
    )
    tg_task = asyncio.create_task(system.telegram.run_forever())
    try:
        while True:
            await asyncio.sleep(1.0)
    except ( asyncio.CancelledError, KeyboardInterrupt ):
        pass
    finally:
        tg_task.cancel()
        await system.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Amadeus Kurisu — 9-Module AI Assistant")
    parser.add_argument(
        "--onboarding",
        action="store_true",
        help="Abrir el Asistente Web de Configuración al iniciar",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar como demonio sin consola para la app de escritorio Electron",
    )
    parser.add_argument(
        "--check-health",
        action="store_true",
        help="Ejecutar autodiagnóstico de los 9 módulos y salir",
    )
    args = parser.parse_args()

    system = AmadeusSystem(initial_mode=PowerMode.BACKGROUND_ECO)
    if args.check_health:
        snap = system.governor.snapshot()
        print(
            f"AMADEUS_HEALTH_OK | RAM={snap.process_rss_mb}MB | "
            f"SKILLS={len(system.skills.skills)} | APPS={len(system.toolkit.app_launcher.catalog)}"
        )
        return 0

    if args.headless:
        asyncio.run(run_headless_daemon(system))
        return 0

    asyncio.run(run_interactive_cli(system, open_ui=args.onboarding))
    return 0


if __name__ == "__main__":
    sys.exit(main())
