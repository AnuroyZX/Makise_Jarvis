# Amadeus System // Makise Kurisu v2.0

Asistente de escritorio estilo J.A.R.V.I.S. inspirado en **Makise Kurisu** (*Steins;Gate 0 — Sistema Amadeus*), diseñado en **9 capas modulares** en Python (`asyncio`) junto con una aplicación de escritorio en **Electron + Three.js (`@pixiv/three-vrm`)** con estética **Windows Aero / Soft Air** en tonos azules claros.

## Arquitectura de 9 Módulos + Escritorio 3D

1. **Módulo 1 — Casa (`src/amadeus/house/` + `desktop/`)**:
   - `resource_governor.py`: Gobernador de recursos (`FOREGROUND_ACTIVE` vs `BACKGROUND_ECO` con vaciado de Working Set en Windows 64-bit).
   - `environment_scanner.py`: Escáner portátil del entorno Windows sin rutas fijas.
   - `ws_bridge.py`: Puente WebSocket local autenticado (`127.0.0.1`) con cola de oraciones TTS, interrupción en tiempo real (`interrupt`) y supresión de eco (`audio_playing`), inspirado en patrones MIT de *Open-LLM-VTuber*.
   - `onboarding_ui.py`: Servidor HTTP local para estado, perfil `USER.md` y carga en vivo de modelos `.vrm`.
2. **Módulo 2 — Cuerpo (`src/amadeus/body/`)**:
   - `agent_core.py`: Orquestador asíncrono, comandos rápidos y bus de eventos 3D (`AvatarEvent` + `EmotionState`).
3. **Módulo 3 — Cerebro (`src/amadeus/brain/`)**:
   - `router.py`: Enrutador multi-LLM (`auto`, `free`, `gemini`, `claude`, `codex`, `openrouter`).
   - `dual_response.py`: Respuestas en **doble capa** (`spoken` breve y natural para voz + `detail` estructurado en pantalla).
   - `tool_loop.py`: Despachador de herramientas seguras para el LLM.
4. **Módulo 4 — Identidad (`src/amadeus/identity/` + `config/SOUL.md`)**:
   - Personalidad de Makise Kurisu, reglas de modulación verbal y defensa contra inyección de prompts (`<untrusted_data>`).
5. **Módulo 5 — Memoria (`src/amadeus/memory/`)**:
   - `hybrid_memory.py`: Memoria híbrida (`HonchoCloudAdapter` + `LocalSQLiteMemory` con búsqueda FTS5).
   - `reflection.py` & `habits.py`: Aprendizaje transparente en `USER.md` con etiquetas `[id:xxxx]` y detección local de hábitos.
6. **Módulo 6 — Habilidades (`src/amadeus/skills/` + `skills/`)**:
   - Cargador de *Skills* modulares en Markdown (`file_steward`, `screen_companion`, `daily_briefing`, `code_review_assistant`).
7. **Módulo 7 — Herramientas (`src/amadeus/tools/`)**:
   - `file_ops.py`: Operaciones seguras de archivos en carpetas personales, confirmación obligatoria antes de mover/renombrar/borrar, envío a Papelera de Reciclaje de Windows (`SHFileOperationW` + `FOF_ALLOWUNDO`) y comando `/deshacer`.
   - `screen_context.py`: Detección de ventana activa con lista de exclusión de privacidad y análisis visual bajo demanda con Gemini Vision (`Ctrl+Alt+V`).
   - `app_launcher.py`, `mail_calendar.py`, `browser_tool.py`.
8. **Módulo 8 — Canales (`src/amadeus/channels/`)**:
   - `telegram_gateway.py` (con lista blanca estricta `allowed_user_ids`) y `pc_and_whatsapp.py`.
9. **Módulo 9 — Voz (`src/amadeus/voice/`)**:
   - `tts_engine.py`: Síntesis expresiva con **ElevenLabs (`eleven_multilingual_v2`)** y respaldo gratuito automático con **Edge-TTS**.
   - `listener.py`: Escucha local con wake-word (`"Oye Kurisu"`) y carga perezosa de `faster-whisper`.

## Instalación Rápida

```powershell
# 1. Entorno Python
python -m venv .venv
.\.venv\Scripts\pip install -e .[dev]

# 2. Dependencias de la App de Escritorio (Electron)
cd desktop
npm install
npm start
```

## Atajos Globales

- `Ctrl + Alt + Espacio`: Mostrar/ocultar barra de entrada rápida junto a Kurisu.
- `Ctrl + Alt + V`: Analizar lo que hay en pantalla con Gemini Vision.
- `Ctrl + Alt + E`: Alternar entre modo activo y `BACKGROUND_ECO`.

## Pruebas

```powershell
.\.venv\Scripts\pytest tests/ -v
node --test desktop/test/dodge.test.js
```
