from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import secrets
import time
from typing import TYPE_CHECKING, Any, Dict, Optional
import urllib.parse

from amadeus.config import classify_api_key
from amadeus.house.resource_governor import PowerMode

if TYPE_CHECKING:
    from amadeus.system_builder import AmadeusSystem


AMADEUS_HTML_UI = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>AMADEUS SYSTEM // Makise Kurisu v1.1</title>
<style>
  :root {
    --bg: #d8eeff;
    --panel: rgba(235, 246, 255, 0.72);
    --accent: #2f8fdc;
    --gold: #0284c7;
    --text: #122840;
    --muted: #47688a;
    --border: rgba(255, 255, 255, 0.88);
  }
  * { box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
  body {
    margin: 0; background: linear-gradient(145deg, #e6f4ff 0%, #bce0fd 55%, #9bd0fb 100%);
    color: var(--text); min-height: 100vh; padding: 20px;
  }
  .container { max-width: 1180px; margin: 0 auto; }
  header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 2px solid rgba(47, 143, 220, 0.35); padding-bottom: 12px; margin-bottom: 18px;
  }
  .brand h1 { margin: 0; font-size: 1.45rem; letter-spacing: 1.5px; color: var(--accent); }
  .brand small { color: var(--muted); }
  .badge {
    background: rgba(255, 255, 255, 0.82); border: 1.5px solid var(--border); color: var(--accent);
    padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;
    box-shadow: 0 4px 14px rgba(47, 143, 220, 0.16);
  }
  .grid { display: grid; grid-template-columns: 380px 1fr; gap: 18px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .card {
    background: linear-gradient(180deg, rgba(255,255,255,0.86) 0%, var(--panel) 50%, rgba(199,229,255,0.58) 100%);
    border: 1.5px solid var(--border);
    border-radius: 14px; padding: 16px;
    box-shadow: 0 10px 28px rgba(47, 143, 220, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(18px) saturate(140%);
  }
  .card h2 { margin-top: 0; font-size: 1.05rem; color: var(--accent); border-bottom: 1px solid rgba(47,143,220,0.22); padding-bottom: 8px; }
  label { display: block; font-size: 0.82rem; color: var(--muted); margin-top: 8px; font-weight: 600; }
  input, select, textarea {
    width: 100%; background: rgba(255, 255, 255, 0.9); border: 1px solid #7cc4fa;
    color: var(--text); padding: 8px 10px; border-radius: 8px; margin-top: 4px;
  }
  textarea { min-height: 110px; font-family: Consolas, monospace; font-size: 0.85rem; }
  button, .btn-file {
    display: inline-block; background: linear-gradient(180deg, #6ec3ff 0%, #2f8fdc 100%);
    color: #fff; font-weight: 700; border: 1px solid rgba(255,255,255,0.85); padding: 9px 14px;
    border-radius: 8px; cursor: pointer; margin-top: 10px; font-size: 0.88rem; text-align: center;
    box-shadow: 0 4px 12px rgba(47, 143, 220, 0.25);
  }
  button.secondary, .btn-file.secondary {
    background: rgba(255, 255, 255, 0.78); color: var(--accent); border: 1px solid #7cc4fa;
  }
  #chatBox {
    height: 250px; overflow-y: auto; background: rgba(255, 255, 255, 0.82);
    border: 1px solid #7cc4fa; border-radius: 10px; padding: 12px; margin-bottom: 10px;
  }
  .msg-user { color: #0369a1; margin-bottom: 8px; }
  .msg-kurisu { color: #1e3a8a; margin-bottom: 12px; line-height: 1.4; }
  #vrmStage {
    width: 100%; height: 390px; background: radial-gradient(circle, rgba(255,255,255,0.9) 0%, rgba(186,230,253,0.65) 85%);
    border: 1.5px solid var(--border); border-radius: 12px; position: relative; overflow: hidden;
  }
  #vrmOverlay {
    position: absolute; bottom: 8px; left: 10px; right: 10px;
    display: flex; justify-content: space-between; align-items: center;
    background: rgba(255, 255, 255, 0.82); padding: 6px 10px; border-radius: 8px;
    font-size: 0.8rem; color: var(--accent); border: 1px solid #7cc4fa; font-weight: 600;
  }
</style>
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/",
    "@pixiv/three-vrm": "https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@3.1.2/lib/three-vrm.module.min.js"
  }
}
</script>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <h1>AMADEUS SYSTEM // MAKISE KURISU</h1>
      <small>Victor Chondria University & Future Gadget Lab — 9-Module Eco-Core + VRoid Stage</small>
    </div>
    <div id="statusBadge" class="badge">Cargando estado...</div>
  </header>

  <div class="grid">
    <!-- Left Column: VRoid 3D Avatar Stage -->
    <div class="card">
      <h2>🎭 Avatar 3D VRoid (.VRM) — Amadeus Link</h2>
      <div id="vrmStage">
        <div id="vrmOverlay">
          <span id="vrmStatusText">Sin modelo .vrm cargado</span>
          <span id="emotionIndicator">Emoción: neutral</span>
        </div>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:6px;">
        <label class="btn-file" style="margin-top:6px; flex:1;">
          📂 Cargar Modelo .VRM
          <input id="vrmFileInput" type="file" accept=".vrm" style="display:none" onchange="uploadVrmFile(this.files[0])">
        </label>
        <button class="secondary" style="margin-top:6px;" onclick="testAvatarEmotion()">✨ Probar Expresión</button>
      </div>
      <small style="color:var(--muted); display:block; margin-top:6px;">
        El modelo se guarda en tu carpeta portable (<code>data/avatar.vrm</code>) y sincroniza emociones y labios con la voz de Kurisu.
      </small>
    </div>

    <!-- Right Column: Direct Chat & Brain Config -->
    <div style="display:flex; flex-direction:column; gap:18px;">
      <div class="card">
        <h2>💬 Consola Directa con Kurisu (Módulos 2, 3, 8, 9)</h2>
        <div id="chatBox"></div>
        <div style="display:flex; gap:8px;">
          <button class="secondary" id="micBtn" style="margin-top:4px;" onclick="toggleMic()" title="Hablar por micrófono (Push-to-Talk)">🎙️</button>
          <input id="chatInput" placeholder="Habla con Kurisu o usa /status, /brain free, /agenda, /open notepad..." onkeypress="if(event.key==='Enter') sendChat()">
          <button style="margin-top:4px;" onclick="sendChat()">Enviar</button>
        </div>
        <div style="margin-top:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <button class="secondary" onclick="setMode('foreground_active')">⚡ Modo 1er Plano</button>
          <button class="secondary" onclick="setMode('background_eco')">🍃 Modo Eco 2º Plano</button>
          <audio id="kurisuAudio" controls style="height:32px; margin-top:10px; flex:1;"></audio>
        </div>
      </div>

      <div class="card">
        <h2>🧠 Configuración de Cerebro, Voz y Canales</h2>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
          <div>
            <label>Tu Nombre / Apodo</label>
            <input id="user_display_name" placeholder="Okabe">
          </div>
          <div>
            <label>Cerebro Activo (Módulo 3)</label>
            <select id="active_brain">
              <option value="auto">Auto (Usa tu API Key o Modelo Gratuito automáticamente)</option>
              <option value="free">Gratis Directo (Sin API Key — Funciona al instante)</option>
              <option value="gemini">Google Gemini (gemini-3-flash / lite)</option>
              <option value="claude">Anthropic Claude</option>
              <option value="codex">OpenAI GPT / Codex</option>
              <option value="openrouter">OpenRouter (Modelos Free/Pro)</option>
            </select>
          </div>
          <div>
            <label>Gemini API Key (Opcional si usas Gratis Directo)</label>
            <input id="gemini_api_key" type="password" placeholder="Dejar en blanco para mantener actual">
          </div>
          <div>
            <label>Otra API Key: Claude / OpenAI / OpenRouter (se detecta sola)</label>
            <input id="extra_api_key" type="password" placeholder="sk-ant-... / sk-... / sk-or-...">
          </div>
          <div>
            <label>Honcho Cloud API Key (Módulo 5 - Opcional)</label>
            <input id="honcho_api_key" type="password" placeholder="Respaldo SQLite FTS5 siempre activo">
          </div>
          <div>
            <label>ElevenLabs API Key (Módulo 9 - Opcional)</label>
            <input id="elevenlabs_api_key" type="password" placeholder="Respaldo gratuito Edge-TTS siempre activo">
          </div>
          <div>
            <label>Telegram Bot Token (Módulo 8 - de @BotFather)</label>
            <input id="telegram_bot_token" type="password" placeholder="123456:ABC-...">
          </div>
          <div>
            <label>Tus IDs de Telegram autorizados (separados por coma)</label>
            <input id="telegram_allowed_user_ids" placeholder="Ej: 123456789 (pídelo a @userinfobot)">
          </div>
        </div>
        <div id="keysSummary" style="font-size:0.78rem; color:var(--muted); margin-top:8px;"></div>
        <button onclick="saveSettings()">💾 Guardar Configuración</button>
      </div>
    </div>

    <div class="card" style="grid-column: 1 / -1;">
      <h2>👤 Módulo 4: Quién Eres (USER.md — Gustos, Costumbres y Horarios)</h2>
      <textarea id="userMdEditor"></textarea>
      <button onclick="saveUserMd()">💾 Actualizar USER.md</button>
    </div>
  </div>
</div>

<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

let currentVrm = null;
let speakingActive = false;
let currentEmotion = 'neutral';

const stage = document.getElementById('vrmStage');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(stage.clientWidth, stage.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
stage.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(30.0, stage.clientWidth / stage.clientHeight, 0.1, 20.0);
camera.position.set(0.0, 1.38, 1.45);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0.0, 1.32, 0.0);
controls.update();

const scene = new THREE.Scene();
const light = new THREE.DirectionalLight(0xffffff, Math.PI);
light.position.set(1.0, 2.0, 2.0);
scene.add(light);
scene.add(new THREE.AmbientLight(0xffd6aa, 1.2));

const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

async function loadVrmFromUrl(url) {
  const statusEl = document.getElementById('vrmStatusText');
  statusEl.innerText = 'Cargando modelo .vrm...';
  loader.load(
    url,
    (gltf) => {
      const vrm = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryVertices(gltf.scene);
      VRMUtils.removeUnnecessaryJoints(gltf.scene);
      if (currentVrm) {
        scene.remove(currentVrm.scene);
        VRMUtils.deepDispose(currentVrm.scene);
      }
      currentVrm = vrm;
      vrm.scene.rotation.y = Math.PI;
      scene.add(vrm.scene);
      statusEl.innerText = '✅ Modelo .VRM conectado a Amadeus';
      applyVrmEmotion(currentEmotion);
    },
    undefined,
    () => {
      statusEl.innerText = 'Usa "Cargar Modelo .VRM" para subir tu avatar';
    }
  );
}

function applyVrmEmotion(emotion) {
  currentEmotion = emotion || 'neutral';
  document.getElementById('emotionIndicator').innerText = `Emoción: ${currentEmotion}`;
  if (!currentVrm || !currentVrm.expressionManager) return;
  const em = currentVrm.expressionManager;
  for (const preset of ['neutral', 'happy', 'angry', 'sad', 'relaxed', 'surprised']) {
    em.setValue(preset, 0.0);
  }
  if (currentEmotion === 'smug') em.setValue('happy', 0.85);
  else if (currentEmotion === 'tsundere_blush') { em.setValue('angry', 0.45); em.setValue('relaxed', 0.4); }
  else if (currentEmotion === 'analytical') em.setValue('relaxed', 0.65);
  else if (currentEmotion === 'serious') em.setValue('angry', 0.75);
  else if (currentEmotion === 'surprised') em.setValue('surprised', 0.9);
  else em.setValue('neutral', 1.0);
}

window.applyVrmEmotion = applyVrmEmotion;
window.loadVrmFromUrl = loadVrmFromUrl;

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  const elapsed = clock.getElapsedTime();
  if (currentVrm) {
    // Subtle breathing motion
    const spine = currentVrm.humanoid?.getNormalizedBoneNode('spine');
    if (spine) spine.rotation.x = Math.sin(elapsed * 2.0) * 0.02;
    // Lip-sync mouth animation while Kurisu audio is playing
    if (currentVrm.expressionManager) {
      const mouthOpen = speakingActive ? (Math.sin(elapsed * 22.0) * 0.4 + 0.45) : 0.0;
      currentVrm.expressionManager.setValue('aa', mouthOpen);
    }
    currentVrm.update(delta);
  }
  renderer.render(scene, camera);
}
animate();

const audioEl = document.getElementById('kurisuAudio');
audioEl.addEventListener('play', () => { speakingActive = true; });
audioEl.addEventListener('ended', () => { speakingActive = false; });
audioEl.addEventListener('pause', () => { speakingActive = false; });

// Check if a saved avatar.vrm already exists
fetch('/api/state').then(r => r.json()).then(d => {
  if (d.has_vrm) loadVrmFromUrl('/api/avatar.vrm?t=' + Date.now());
});
</script>

<script>
async function refreshStatus() {
  const r = await fetch('/api/state');
  const d = await r.json();
  document.getElementById('statusBadge').innerText =
    `Modo: ${d.power_mode} | RAM: ${d.rss_mb} MB | Cerebro: ${d.active_brain} (${d.active_provider}) | Apps: ${d.discovered_apps_count}`;
  document.getElementById('user_display_name').value = d.user_display_name || '';
  document.getElementById('active_brain').value = d.active_brain || 'auto';
  document.getElementById('userMdEditor').value = d.user_md || '';
  document.getElementById('telegram_allowed_user_ids').value = (d.telegram_allowed_user_ids || []).join(', ');
  const k = d.masked_keys || {};
  document.getElementById('keysSummary').innerText =
    `Claves guardadas → Gemini: ${k.gemini_api_key} | Claude: ${k.anthropic_api_key} | OpenAI: ${k.openai_api_key} | OpenRouter: ${k.openrouter_api_key} | Telegram: ${k.telegram_bot_token}`;
}

// Heartbeat: keeps the ephemeral server alive only while this tab is open.
setInterval(() => { fetch('/api/ping').catch(() => {}); }, 30000);

function appendChatLine(cssClass, label, text) {
  const box = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = cssClass;
  const b = document.createElement('b');
  b.textContent = label + ' ';
  div.appendChild(b);
  div.appendChild(document.createTextNode(text));  // textContent: no HTML injection
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// Push-to-Talk via the browser's built-in speech recognition (Edge/Chrome). 0 MB in Python.
let recognizer = null;
function toggleMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = document.getElementById('micBtn');
  if (!SR) { alert('Tu navegador no soporta reconocimiento de voz. Usa Edge o Chrome.'); return; }
  if (recognizer) { recognizer.stop(); return; }
  recognizer = new SR();
  recognizer.lang = 'es-ES';
  recognizer.interimResults = false;
  recognizer.onresult = (ev) => {
    document.getElementById('chatInput').value = ev.results[0][0].transcript;
    sendChat();
  };
  recognizer.onend = () => { recognizer = null; btn.textContent = '🎙️'; };
  btn.textContent = '🔴';
  recognizer.start();
}

async function uploadVrmFile(file) {
  if (!file) return;
  document.getElementById('vrmStatusText').innerText = `Subiendo ${file.name}...`;
  const buf = await file.arrayBuffer();
  const r = await fetch('/api/upload_vrm', {
    method: 'POST',
    headers: {'Content-Type': 'application/octet-stream'},
    body: buf
  });
  if (r.ok && window.loadVrmFromUrl) {
    window.loadVrmFromUrl('/api/avatar.vrm?t=' + Date.now());
  } else {
    alert('Error al guardar el archivo .vrm');
  }
}

function testAvatarEmotion() {
  const states = ['neutral', 'tsundere_blush', 'analytical', 'smug', 'serious', 'surprised'];
  const pick = states[Math.floor(Math.random() * states.length)];
  if (window.applyVrmEmotion) window.applyVrmEmotion(pick);
}

async function sendChat() {
  const inp = document.getElementById('chatInput');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  appendChatLine('msg-user', 'Tú:', text);

  const r = await fetch('/api/chat', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text})
  });
  const d = await r.json();
  appendChatLine('msg-kurisu', `Kurisu [${d.emotion}]:`, d.reply);

  if (window.applyVrmEmotion) window.applyVrmEmotion(d.emotion);
  if (d.has_audio) {
    const audioEl = document.getElementById('kurisuAudio');
    audioEl.src = '/api/voice_audio?t=' + Date.now();
    audioEl.play().catch(() => {});
  }
  refreshStatus();
}

async function setMode(mode) {
  await fetch('/api/mode', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mode})
  });
  refreshStatus();
}

async function saveSettings() {
  const fields = ['user_display_name','active_brain','gemini_api_key','extra_api_key','honcho_api_key','elevenlabs_api_key','telegram_bot_token','telegram_allowed_user_ids'];
  const payload = {};
  for (const f of fields) {
    const el = document.getElementById(f);
    if (el && el.value.trim()) payload[f] = el.value.trim();
  }
  const r = await fetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  const d = await r.json();
  for (const f of ['gemini_api_key','extra_api_key','honcho_api_key','elevenlabs_api_key','telegram_bot_token']) {
    document.getElementById(f).value = '';
  }
  alert(d.warning ? `Guardado, pero: ${d.warning}` : 'Configuración guardada correctamente.');
  refreshStatus();
}

async function saveUserMd() {
  const content = document.getElementById('userMdEditor').value;
  await fetch('/api/user_md', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({content})
  });
  alert('Perfil USER.md actualizado.');
}
refreshStatus();
</script>
</body>
</html>
"""


class EphemeralOnboardingServer:
    """
    Module 1 (Casa - Interfaz Web Efímera de Configuración, Chat y Escenario VRoid .VRM):
    Runs strictly on 127.0.0.1 using zero-dependency asyncio streams.
    Automatically shuts down after `idle_timeout_sec` (default 120s) and trims RAM.
    """

    def __init__(
        self,
        system: AmadeusSystem,
        host: str = "127.0.0.1",
        port: int = 0,
        idle_timeout_sec: float = 120.0,
        auth_token: Optional[str] = None,
    ) -> None:
        self.system = system
        self.host = host
        self.port = port
        self.idle_timeout_sec = idle_timeout_sec
        self.auth_token: str = (
            auth_token
            or getattr(self.system.settings, "auth_token", "")
            or secrets.token_urlsafe(24)
        )
        self.system.settings.auth_token = self.auth_token
        self._server: Optional[asyncio.AbstractServer] = None
        self._last_request_ts: float = 0.0
        self._watchdog_task: Optional[asyncio.Task] = None
        self._last_audio_path: Optional[Path] = None

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.is_serving()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def vrm_file_path(self) -> Path:
        return self.system.data_dir / "avatar.vrm"

    async def start(self) -> str:
        if hasattr(self.system, "ws_bridge") and self.system.ws_bridge is not None:
            self.system.ws_bridge.auth_token = self.auth_token

        if self.is_running:
            self._last_request_ts = time.monotonic()
            return self.url

        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        sockets = self._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]

        self._last_request_ts = time.monotonic()
        self._watchdog_task = asyncio.create_task(self._idle_watchdog())
        return self.url

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self.system.governor.trim_working_set()

    async def _idle_watchdog(self) -> None:
        while self.is_running:
            await asyncio.sleep(min(1.0, self.idle_timeout_sec / 2.0))
            if (time.monotonic() - self._last_request_ts) >= self.idle_timeout_sec:
                await self.stop()
                break

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._last_request_ts = time.monotonic()
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not request_line:
                return
            parts = request_line.decode("utf-8", errors="replace").strip().split()
            if len(parts) < 2:
                return
            method, raw_path = parts[0], parts[1]
            parsed_url = urllib.parse.urlparse(raw_path)
            path = parsed_url.path
            query_params = dict(urllib.parse.parse_qsl(parsed_url.query))

            headers: dict[str, str] = {}
            content_length = 0
            while True:
                hdr = await reader.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
                hdr_str = hdr.decode("utf-8", errors="replace").strip()
                if ":" in hdr_str:
                    k, v = hdr_str.split(":", 1)
                    headers[k.lower().strip()] = v.strip()
                    if k.lower().strip() == "content-length":
                        try:
                            content_length = int(v.strip())
                        except ValueError:
                            content_length = 0

            # 1. DNS Rebinding Shield: Loopback Host verification
            host_header = headers.get("host", "").split(":")[0].strip().lower()
            if host_header and host_header not in ("127.0.0.1", "localhost"):
                status = "403 Forbidden"
                content_type = "text/plain"
                resp_bytes = b"Forbidden: Host must be loopback (127.0.0.1 or localhost)"
                allow_origin_hdr = ""
            else:
                # 2. CORS Restriction: Reflect verified loopback origin only
                origin = headers.get("origin", "")
                allow_origin_hdr = ""
                if origin:
                    orig_host = urllib.parse.urlparse(origin).hostname
                    if orig_host in ("127.0.0.1", "localhost"):
                        allow_origin_hdr = f"Access-Control-Allow-Origin: {origin}\r\nAccess-Control-Allow-Credentials: true\r\n"

                # 3. Auth Token Gate for /api/* endpoints
                if path.startswith("/api/"):
                    req_token = headers.get("x-amadeus-token") or query_params.get("token")
                    if req_token != self.auth_token and method != "OPTIONS":
                        status = "401 Unauthorized"
                        content_type = "application/json"
                        resp_bytes = b'{"error":"unauthorized_invalid_token"}'
                    else:
                        # Support up to 100 MB for .vrm binary model uploads
                        body_bytes = (
                            await reader.readexactly(content_length)
                            if 0 < content_length <= 100 * 1024 * 1024
                            else b""
                        )
                        status, content_type, resp_bytes = await self._route_request(
                            method, path, body_bytes, query_params
                        )
                else:
                    body_bytes = b""
                    status, content_type, resp_bytes = await self._route_request(
                        method, path, body_bytes, query_params
                    )

            header_block = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(resp_bytes)}\r\n"
                f"{allow_origin_hdr}"
                f"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                f"Access-Control-Allow-Headers: Content-Type, X-Amadeus-Token\r\n"
                f"Cache-Control: no-store\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")
            writer.write(header_block + resp_bytes)
            await writer.drain()
        except Exception as exc:
            logging.getLogger("amadeus.onboarding_ui").debug("HTTP client error: %s", exc)
        finally:
            writer.close()

    async def _route_request(
        self, method: str, path: str, body: bytes, query_params: Optional[Dict[str, str]] = None
    ) -> tuple[str, str, bytes]:
        if method == "OPTIONS":
            return "204 No Content", "text/plain", b""

        if method == "GET" and path == "/":
            token_shim = (
                f"<script>\n"
                f"window.__AMADEUS_TOKEN__ = {json.dumps(self.auth_token)};\n"
                f"(function() {{\n"
                f"  const _f = window.fetch;\n"
                f"  window.fetch = function(url, init) {{\n"
                f"    init = init || {{}};\n"
                f"    init.headers = init.headers || {{}};\n"
                f"    if (window.__AMADEUS_TOKEN__) {{\n"
                f"      if (typeof init.headers.set === 'function') {{\n"
                f"        init.headers.set('X-Amadeus-Token', window.__AMADEUS_TOKEN__);\n"
                f"      }} else {{\n"
                f"        init.headers['X-Amadeus-Token'] = window.__AMADEUS_TOKEN__;\n"
                f"      }}\n"
                f"    }}\n"
                f"    return _f(url, init);\n"
                f"  }};\n"
                f"}})();\n"
                f"</script>\n</head>"
            )
            html = AMADEUS_HTML_UI.replace("</head>", token_shim)
            return "200 OK", "text/html; charset=utf-8", html.encode("utf-8")

        if method == "GET" and path == "/api/ping":
            return "200 OK", "application/json", b'{"status":"alive"}'

        if method == "GET" and path == "/api/state":
            snap = self.system.governor.snapshot()
            prov, mod = self.system.brain.select_provider_and_model(snap.power_mode)
            payload = {
                "power_mode": snap.power_mode.value,
                "rss_mb": snap.process_rss_mb,
                "active_brain": self.system.settings.active_brain,
                "active_provider": f"{prov}:{mod}",
                "user_display_name": self.system.settings.user_display_name,
                "discovered_apps_count": len(self.system.toolkit.app_launcher.catalog),
                "user_md": self.system.identity.read_user_profile(),
                "has_vrm": self.vrm_file_path.exists(),
                "has_kikivoice_ref": (self.system.data_dir / "kikivoice_ref.mp3").exists(),
                "telegram_allowed_user_ids": self.system.settings.telegram_allowed_user_ids,
                "active_profile": self.system.settings.active_profile,
                "dsp_preset": self.system.settings.dsp_preset,
                "profiles": self.system.profiles.list_profiles(),
                "voice_engine": self.system.settings.voice_engine,
                "qwen3_speaker": self.system.settings.qwen3_speaker,
                "fish_model_id": self.system.settings.fish_model_id,
                "elevenlabs_voice_id": self.system.settings.elevenlabs_voice_id,
                "bubbles_mode": self.system.settings.bubbles_mode,
                "cloud_vision_consent": self.system.settings.cloud_vision_consent,
                "cloud_stt_consent": self.system.settings.cloud_stt_consent,
                "masked_keys": self.system.settings.masked_summary(),
            }
            return "200 OK", "application/json", json.dumps(payload).encode("utf-8")

        if method == "GET" and path == "/api/test_qwen3.wav":
            synth = await self.system.voice.synthesize(
                "Hola Okabe. Soy el sistema Amadeus con la voz de Makise Kurisu. El Psy Kongroo.",
                for_telegram_opus=False,
                save_to_disk=False,
            )
            if synth.audio_bytes:
                return "200 OK", synth.mime_type, synth.audio_bytes
            return "500 Internal Server Error", "application/json", b'{"error":"voice_failed"}'

        if method == "GET" and path == "/api/kikivoice_ref":
            ref_file = self.system.data_dir / "kikivoice_ref.mp3"
            if ref_file.exists():
                return "200 OK", "audio/mpeg", ref_file.read_bytes()
            return "404 Not Found", "application/json", b'{"error":"no_kikivoice_ref"}'

        if method == "GET" and path == "/api/kurisu_reference.mp3":
            from amadeus.config import get_config_dir
            ref_path = get_config_dir() / "kurisu_reference.mp3"
            if ref_path.exists():
                return "200 OK", "audio/mpeg", ref_path.read_bytes()
            return "404 Not Found", "application/json", b'{"error":"no_ref"}'

        if method == "POST" and path == "/api/upload_vrm":
            if not body:
                return "400 Bad Request", "application/json", b'{"error":"empty_vrm"}'
            self.vrm_file_path.write_bytes(body)
            if hasattr(self.system, "ws_bridge") and self.system.ws_bridge is not None:
                await self.system.ws_bridge.broadcast({"type": "reload_vrm"})
            return (
                "200 OK",
                "application/json",
                json.dumps({"status": "vrm_saved", "size_bytes": len(body)}).encode("utf-8"),
            )

        if method == "POST" and path == "/api/upload_voice_ref":
            if not body:
                return "400 Bad Request", "application/json", b'{"error":"empty_audio"}'
            ref_file = self.system.data_dir / "kikivoice_ref.mp3"
            ref_file.write_bytes(body)
            return (
                "200 OK",
                "application/json",
                json.dumps({"status": "voice_ref_saved", "size_bytes": len(body)}).encode("utf-8"),
            )

        if method == "GET" and path == "/api/avatar.vrm":
            if not self.vrm_file_path.exists():
                return "404 Not Found", "application/json", b'{"error":"no_vrm"}'
            return "200 OK", "model/gltf-binary", self.vrm_file_path.read_bytes()

        if method == "GET" and path == "/api/voice_audio":
            if self._last_audio_path and self._last_audio_path.exists():
                mime = (
                    "audio/ogg"
                    if self._last_audio_path.suffix.lower() == ".ogg"
                    else "audio/mpeg"
                )
                return "200 OK", mime, self._last_audio_path.read_bytes()
            return "404 Not Found", "application/json", b'{"error":"no_audio"}'

        try:
            data: Dict[str, Any] = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if method == "POST" and path == "/api/chat":
            text = str(data.get("text", "")).strip()
            reply, audio_path_str = await self.system.pc_gateway.send_local_prompt(
                text, synthesize_voice=True
            )
            self._last_audio_path = Path(audio_path_str) if audio_path_str else None
            return (
                "200 OK",
                "application/json",
                json.dumps(
                    {
                        "reply": reply.content,
                        "emotion": reply.emotion.value,
                        "has_audio": bool(
                            self._last_audio_path and self._last_audio_path.exists()
                        ),
                    }
                ).encode("utf-8"),
            )

        if method == "POST" and path == "/api/mode":
            target = str(data.get("mode", "background_eco"))
            mode = (
                PowerMode.FOREGROUND_ACTIVE
                if target == "foreground_active"
                else PowerMode.BACKGROUND_ECO
            )
            snap = self.system.governor.switch_mode(mode)
            return (
                "200 OK",
                "application/json",
                json.dumps({"power_mode": snap.power_mode.value, "rss_mb": snap.process_rss_mb}).encode("utf-8"),
            )

        if method == "POST" and path == "/api/settings":
            warning = ""
            if "active_profile" in data and str(data["active_profile"]).strip():
                prof_id = str(data["active_profile"]).strip()
                prof = self.system.profiles.get_profile(prof_id)
                self.system.settings.active_profile = prof.id
                self.system.settings.voice_engine = prof.voice_engine
                self.system.settings.qwen3_speaker = prof.qwen3_speaker
                self.system.settings.dsp_preset = prof.dsp_preset

            for key in (
                "user_display_name",
                "active_brain",
                "gemini_api_key",
                "anthropic_api_key",
                "openai_api_key",
                "openrouter_api_key",
                "honcho_api_key",
                "voice_engine",
                "qwen3_speaker",
                "dsp_preset",
                "fish_audio_api_key",
                "fish_model_id",
                "elevenlabs_api_key",
                "elevenlabs_voice_id",
                "bubbles_mode",
                "telegram_bot_token",
            ):
                if key in data and str(data[key]).strip():
                    setattr(self.system.settings, key, str(data[key]).strip())

            if hasattr(self.system, "ws_bridge") and self.system.ws_bridge is not None:
                await self.system.ws_bridge.broadcast(
                    {
                        "type": "dsp_changed",
                        "dsp_preset": self.system.settings.dsp_preset,
                        "bubbles_mode": self.system.settings.bubbles_mode,
                    }
                )

            if "extra_api_key" in data and str(data["extra_api_key"]).strip():
                raw_extra = str(data["extra_api_key"]).strip()
                target_field = classify_api_key(raw_extra)
                if target_field:
                    setattr(self.system.settings, target_field, raw_extra)
                else:
                    warning = (
                        "No se reconoció el prefijo de la clave adicional "
                        "(usa sk-ant-... para Claude, sk-or-... para OpenRouter o sk-... para OpenAI)."
                    )

            if "telegram_allowed_user_ids" in data:
                raw_ids = data["telegram_allowed_user_ids"]
                if isinstance(raw_ids, list):
                    parsed_ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]
                else:
                    parsed_ids = [
                        int(p.strip())
                        for p in str(raw_ids).split(",")
                        if p.strip().isdigit()
                    ]
                self.system.settings.telegram_allowed_user_ids = parsed_ids

            if "cloud_vision_consent" in data:
                self.system.settings.cloud_vision_consent = bool(data["cloud_vision_consent"])
            if "cloud_stt_consent" in data:
                self.system.settings.cloud_stt_consent = bool(data["cloud_stt_consent"])

            self.system.settings.onboarding_completed = True
            self.system.settings.save(self.system.data_dir)
            resp_obj: Dict[str, Any] = {"status": "saved"}
            if warning:
                resp_obj["warning"] = warning
            return "200 OK", "application/json", json.dumps(resp_obj).encode("utf-8")

        if method == "POST" and path == "/api/sync_fish_agent":
            try:
                res = await self.system.voice.sync_fish_agent_config()
                self.system.settings.save(self.system.data_dir)
                return (
                    "200 OK",
                    "application/json",
                    json.dumps(
                        {
                            "status": "ok",
                            "fish_model_id": self.system.settings.fish_model_id,
                            "details": res,
                        }
                    ).encode("utf-8"),
                )
            except Exception as exc:
                return (
                    "500 Internal Server Error",
                    "application/json",
                    json.dumps({"error": str(exc)}).encode("utf-8"),
                )

        if method == "POST" and path == "/api/user_md":
            content = str(data.get("content", ""))
            self.system.identity.update_user_profile(content)
            return "200 OK", "application/json", b'{"status":"updated"}'

        return "404 Not Found", "application/json", b'{"error":"not_found"}'
