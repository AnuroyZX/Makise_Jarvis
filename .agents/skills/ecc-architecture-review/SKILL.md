---
name: ecc-architecture-review
description: "ECC Architecture, Security, and Portability Audit checklist before packaging Amadeus Kurisu for distribution."
---

# ECC Architecture & Portability Review

Before packaging the application for end-users:

1. **Portability Check**:
   - Confirm all user data (`USER.md`, `amadeus_memory.db`, `.env` / `settings.json`) is stored in a configurable portable `data/` directory or `%APPDATA%\AmadeusKurisu` so a friend can install and run without path errors.
2. **Fallback Resilience Check**:
   - Verify Brain router gracefully handles missing provider keys and switches via `/brain`.
   - Verify Memory works seamlessly with local SQLite FTS5 when `HONCHO_API_KEY` is blank.
   - Verify Voice falls back to `Edge-TTS` when `ELEVENLABS_API_KEY` is blank or quota is exceeded.
3. **Eco-Core RAM Audit**:
   - Measure process RSS/Working Set in `BACKGROUND_ECO` mode after `trim_working_set()` and verify it stays lightweight (< 45 MB).
