---
trigger: always_on
description: "ECC AgentShield Security & Secret Protection Rules"
---

# ECC AgentShield Security Rules

1. **Secret Isolation**:
   - Never hardcode or log API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `HONCHO_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_BOT_TOKEN`).
   - Mask secrets in any UI/log output (`sk-***...`).

2. **Channel & Tool Authorization**:
   - External channels (Telegram, WhatsApp) must enforce an explicit `allowed_user_ids` whitelist before executing any agent loop or local tool.
   - Local application launching (`app_launcher.py`) must only execute discovered/whitelisted executables via argument arrays (`subprocess.Popen([exe_path, ...], shell=False)`) — never pass unsanitized user strings to `shell=True`.

3. **Prompt Injection Defense**:
   - Wrap untrusted external content (emails, web pages, calendar descriptions) inside explicit `<untrusted_data>` delimiters before passing to the LLM brain.
   - Maintain `SOUL.md` system boundaries above any external tool output.
