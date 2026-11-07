---
trigger: always_on
description: "ECC AgentShield Security & Secret Protection Rules"
---

# ECC AgentShield Security Rules

1. **Secret Isolation & Header Passing**:
   - Never hardcode or log API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `HONCHO_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `FISH_AUDIO_API_KEY`).
   - Mask secrets in any UI/log output (`sk-***...`).
   - Pass API keys via HTTP headers (`x-goog-api-key`, `Authorization: Bearer`), never as URL query parameters (`?key=`), to prevent leaks in logs, proxies, and error tracebacks.

2. **Channel & Tool Authorization**:
   - External channels (Telegram, WhatsApp) must enforce an explicit `allowed_user_ids` whitelist before executing any agent loop or local tool.
   - Local application launching (`app_launcher.py`) must only execute discovered/whitelisted executables via argument arrays (`subprocess.Popen([exe_path, ...], shell=False)`) — never pass unsanitized user strings to `shell=True`.
   - File openers (`fs_open`) must NEVER execute dangerous binaries or scripts (`.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.lnk`). System files and documents must be opened safely.

3. **Loopback Server Defense (Localhost Security)**:
   - All loopback HTTP/WebSocket servers listening on `127.0.0.1` must validate `Host` headers to prevent DNS rebinding attacks.
   - Require bearer or custom header token validation (`X-Amadeus-Token`) on all mutating and sensitive endpoints. Never expose open CORS (`Access-Control-Allow-Origin: *`) on local management APIs.

4. **Prompt Injection Defense**:
   - Wrap untrusted external content (emails, web pages, calendar descriptions) inside explicit `<untrusted_data>` delimiters before passing to the LLM brain.
   - Maintain `SOUL.md` system boundaries above any external tool output.
