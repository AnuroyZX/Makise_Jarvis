---
trigger: always_on
description: "ECC Clean Code & Modular Engineering Standards for Python & Windows Portability"
---

# ECC Clean Code & Modular Architecture Rules

1. **Single Responsibility & Small Functions**:
   - Every module belongs strictly to one of the 9 Amadeus layers (`house`, `body`, `brain`, `identity`, `memory`, `skills`, `tools`, `channels`, `voice`).
   - Keep functions focused (< 40 lines where practical) and avoid deep nesting (max 3 levels).

2. **Strict Type Annotations**:
   - All public functions, methods, and dataclasses/models must use explicit Python type hints (`from __future__ import annotations`).
   - Prefer immutable structures or validated schemas (`dataclass(slots=True)` / `Pydantic`) at module boundaries.

3. **Zero Hardcoded Machine Paths (Portability First)**:
   - Never hardcode user-specific paths (`C:\Users\...`). Always resolve paths dynamically via `os.environ`, `pathlib.Path.home()`, `%APPDATA%`, or the `EnvironmentScanner` so the compiled binary runs identically on any Windows PC.

4. **Explicit Error Handling & Graceful Degradation**:
   - Never use bare `except:` or silent `except Exception: pass`. Catch specific exceptions, log structured context, and provide deterministic fallbacks (e.g., `HonchoCloudAdapter` -> `LocalSQLiteMemory`, `FishAudio` -> `Edge-TTS`).
   - Log warning/error details with context so silent failures in background loops (like WebSockets or async tasks) can be diagnosed quickly.

5. **Observable Fallbacks & User Transparency**:
   - When a primary service or model falls back (e.g. cloud TTS 429/quota exceeded falling back to Edge-TTS, or vision provider failure), explicitly surface the active provider or fallback reason to the UI / metadata so the user knows what is happening.
