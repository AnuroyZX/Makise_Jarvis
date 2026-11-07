from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
import httpx

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore, EmotionState
from amadeus.config import AmadeusSettings
from amadeus.house.resource_governor import PowerMode, ResourceGovernor

EMOTION_TAG_RE = re.compile(
    r"\[EMOTION:(neutral|tsundere_blush|analytical|smug|serious|surprised)\]",
    re.IGNORECASE,
)


def parse_emotion_tag(text: str) -> Tuple[str, EmotionState]:
    """Extract optional [EMOTION:...] tag from LLM output for VRoid Hub compatibility."""
    match = EMOTION_TAG_RE.search(text)
    if not match:
        return text.strip(), EmotionState.NEUTRAL
    raw_emotion = match.group(1).lower()
    clean_text = EMOTION_TAG_RE.sub("", text).strip()
    try:
        return clean_text, EmotionState(raw_emotion)
    except ValueError:
        return clean_text, EmotionState.NEUTRAL


class MultiBrainRouter:
    """
    Module 3 (Cerebro): Interchanges seamlessly between Free (Zero-Key), Gemini, Claude,
    Codex (OpenAI), and OpenRouter. Supports Smart Routing ('auto' mode) that selects
    lightweight models in BACKGROUND_ECO, flagship models in FOREGROUND_ACTIVE, and
    automatically falls back to free models when no API key is configured or a quota error occurs.
    """

    VALID_BRAINS = ("auto", "free", "gemini", "claude", "codex", "openrouter", "local")
    GEMINI_FALLBACK_CHAIN = (
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemma-4-31b-it",
    )

    def __init__(
        self,
        settings: AmadeusSettings,
        governor: Optional[ResourceGovernor] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        self._external_client = http_client is not None
        self._client: Optional[httpx.AsyncClient] = http_client
        if governor is not None:
            governor.register_listener(self._on_power_mode_changed)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=8.0))
        return self._client

    def _on_power_mode_changed(self, mode: PowerMode) -> None:
        pass

    async def close(self) -> None:
        if self._client is not None and not self._external_client and not self._client.is_closed:
            await self._client.aclose()

    def select_provider_and_model(self, power_mode: PowerMode) -> Tuple[str, str]:
        """
        Determine the active provider and model name based on user preference (/brain)
        and current PowerMode (Smart Routing).
        """
        choice = self.settings.active_brain.lower()
        if choice not in self.VALID_BRAINS:
            choice = "auto"

        if choice == "free":
            return "free", "openai-free"
        if choice == "gemini":
            model = (
                self.settings.background_model_gemini
                if power_mode == PowerMode.BACKGROUND_ECO
                else self.settings.foreground_model_gemini
            )
            return "gemini", model
        if choice == "claude":
            return "claude", self.settings.foreground_model_claude
        if choice == "codex":
            return "codex", self.settings.foreground_model_codex
        if choice == "openrouter":
            return "openrouter", self.settings.openrouter_model
        if choice == "local":
            return "local", self.settings.local_llm_model

        # Smart Routing ("auto"):
        # In BACKGROUND_ECO, prioritize fast/free-tier Gemini Flash Lite if available
        if power_mode == PowerMode.BACKGROUND_ECO and self.settings.gemini_api_key:
            return "gemini", self.settings.background_model_gemini

        # In FOREGROUND_ACTIVE, pick the strongest configured provider in priority order
        if self.settings.anthropic_api_key:
            return "claude", self.settings.foreground_model_claude
        if self.settings.gemini_api_key:
            return "gemini", self.settings.foreground_model_gemini
        if self.settings.openai_api_key:
            return "codex", self.settings.foreground_model_codex
        if self.settings.openrouter_api_key:
            return "openrouter", self.settings.openrouter_model

        # Zero-key default: if no API keys are configured yet, use the built-in free provider
        return "free", "openai-free"

    def bind_commands(self, core: AmadeusAgentCore) -> None:
        """Register /brain command into Module 2 (AmadeusAgentCore)."""
        async def _cmd_brain(args: str, msg: AgentMessage) -> str:
            target = args.strip().lower()
            if not target:
                prov, mod = self.select_provider_and_model(core.governor.mode)
                return (
                    f"Cerebro actual: modo='{self.settings.active_brain}' "
                    f"-> activo='{prov}' ({mod}).\n"
                    f"Opciones: /brain auto | /brain free | /brain gemini | /brain claude | /brain codex | /brain openrouter"
                )
            if target not in self.VALID_BRAINS:
                return f"Cerebro '{target}' no válido. Usa: {', '.join(self.VALID_BRAINS)}"
            self.settings.active_brain = target
            prov, mod = self.select_provider_and_model(core.governor.mode)
            return f"Cerebro cambiado a '{target}' (Proveedor activo: {prov} / Modelo: {mod})."

        core.register_command("brain", _cmd_brain)

    async def generate_reply(
        self,
        messages: List[AgentMessage],
        system_prompt: str,
        power_mode: PowerMode,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentMessage:
        provider, model = self.select_provider_and_model(power_mode)
        last_user = messages[-1] if messages else AgentMessage(role="user", content="")

        try:
            if provider == "free":
                raw_text = await self._call_free_model(messages, system_prompt)
            elif provider == "gemini":
                raw_text = await self._call_gemini_with_fallback(
                    messages, system_prompt, model
                )
            elif provider == "claude":
                raw_text = await self._call_claude(messages, system_prompt, model)
            elif provider == "codex":
                raw_text = await self._call_openai_compatible(
                    messages,
                    system_prompt,
                    model,
                    url="https://api.openai.com/v1/chat/completions",
                    api_key=self.settings.openai_api_key,
                )
            elif provider == "local":
                raw_text = await self._call_openai_compatible(
                    messages,
                    system_prompt,
                    model,
                    url=self.settings.local_llm_url,
                    api_key="local-no-key",
                )
            else:
                raw_text = await self._call_openai_compatible(
                    messages,
                    system_prompt,
                    model,
                    url="https://openrouter.ai/api/v1/chat/completions",
                    api_key=self.settings.openrouter_api_key,
                )
        except Exception as exc:
            # If the user is in 'auto' mode and their configured key failed, try free model before giving up
            if self.settings.active_brain == "auto" and provider != "free":
                try:
                    raw_text = await self._call_free_model(messages, system_prompt)
                    provider, model = "free", "openai-free"
                except Exception:
                    raw_text = (
                        f"[EMOTION:serious] Error de conexión con el cerebro '{provider}' ({model}): "
                        f"{type(exc).__name__}. Verifica tu API key o usa `/brain free`."
                    )
            else:
                raw_text = (
                    f"[EMOTION:serious] Error de conexión con el cerebro '{provider}' ({model}): "
                    f"{type(exc).__name__}. Verifica tu API key o cambia de cerebro con `/brain free`."
                )

        clean_text, emotion = parse_emotion_tag(raw_text)
        return AgentMessage(
            role="assistant",
            content=clean_text,
            channel=last_user.channel,
            user_id=last_user.user_id,
            emotion=emotion,
            metadata={"provider": provider, "model": model},
        )

    async def _call_free_model(
        self, messages: List[AgentMessage], system_prompt: str
    ) -> str:
        """
        Zero-API-key free model endpoint (Pollinations OpenAI-compatible API).
        Works out-of-the-box on any PC without registration or keys.
        """
        client = await self._get_client()
        chat_msgs = [{"role": "system", "content": system_prompt}] + [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages[-10:]
            if m.role in ("user", "assistant")
        ]
        payload = {
            "model": "openai",
            "messages": chat_msgs,
            "temperature": 0.65,
        }
        resp = await client.post(
            "https://text.pollinations.ai/openai", json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_gemini_with_fallback(
        self, messages: List[AgentMessage], system_prompt: str, primary_model: str
    ) -> str:
        if not self.settings.gemini_api_key:
            return await self._call_free_model(messages, system_prompt)

        candidates = [primary_model] + [
            m for m in self.GEMINI_FALLBACK_CHAIN if m != primary_model
        ]
        last_exc: Optional[Exception] = None
        for candidate_model in candidates:
            try:
                return await self._call_gemini_single(
                    messages, system_prompt, candidate_model
                )
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # If 404 (model renamed/deprecated) or 429 (quota limit), try next Gemini model in chain
                if exc.response.status_code in (400, 404, 429, 503):
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                continue

        if last_exc is not None:
            raise last_exc
        return await self._call_free_model(messages, system_prompt)

    async def _call_gemini_single(
        self, messages: List[AgentMessage], system_prompt: str, model: str
    ) -> str:
        client = await self._get_client()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        contents = [
            {
                "role": "user" if m.role == "user" else "model",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
        }
        headers = {"x-goog-api-key": self.settings.gemini_api_key}
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_claude(
        self, messages: List[AgentMessage], system_prompt: str, model: str
    ) -> str:
        if not self.settings.anthropic_api_key:
            return (
                "[EMOTION:tsundere_blush] Falta configurar `ANTHROPIC_API_KEY` para usar Claude. "
                "Puedes cambiar al modelo gratuito con `/brain free` o a Gemini con `/brain gemini`."
            )
        client = await self._get_client()
        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        chat_msgs = [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": chat_msgs,
        }
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", headers=headers, json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    async def _call_openai_compatible(
        self,
        messages: List[AgentMessage],
        system_prompt: str,
        model: str,
        url: str,
        api_key: str,
    ) -> str:
        if not api_key:
            return (
                "[EMOTION:tsundere_blush] No hay API key configurada para este proveedor. "
                "Configúrala en el panel de Amadeus o usa `/brain free`."
            )
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        chat_msgs = [{"role": "system", "content": system_prompt}] + [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload = {"model": model, "messages": chat_msgs, "temperature": 0.6}
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
