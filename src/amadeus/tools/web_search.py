from __future__ import annotations

import asyncio
from dataclasses import dataclass
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.parse

import httpx

from amadeus.tools.mail_calendar import wrap_untrusted

logger = logging.getLogger("amadeus.web_search")


@dataclass(slots=True)
class SearchResult:
    title: str
    snippet: str
    url: str


class WebSearchTool:
    """
    Module 7 (Herramientas - Búsqueda Web e Información Rápida):
    Zero-config web search and fact retriever powered by DuckDuckGo.
    Requires 0 API keys and strictly wraps external content in ECC AgentShield delimiters.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._http = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is not None and not self._http.is_closed:
            return self._http
        return httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "AmadeusKurisu/1.0"})

    async def search(self, query: str, max_results: int = 4) -> str:
        clean = query.strip()
        if not clean:
            return "[emotion:serious] Por favor indica qué deseas buscar en internet."

        client = await self._get_client()

        # 1. Try DuckDuckGo Instant Answer API first
        try:
            encoded = urllib.parse.quote(clean)
            instant_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            resp = await client.get(instant_url)
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("AbstractText", "").strip()
                source = data.get("AbstractSource", "DuckDuckGo")
                source_url = data.get("AbstractURL", "")
                heading = data.get("Heading", clean)

                if abstract:
                    spoken = f"[emotion:analytical] [gesture:nod] Según {source}, {abstract}"
                    detail_content = (
                        f"🌐 **{heading}**\n\n"
                        f"{abstract}\n\n"
                        f"Fuente: [{source}]({source_url})" if source_url else f"Fuente: {source}"
                    )
                    safe_detail = wrap_untrusted(detail_content, source_label="duckduckgo_instant")
                    return f"{spoken}\n---DETALLE---\n{safe_detail}"
        except Exception as exc:
            logger.debug("DuckDuckGo Instant Answer failed: %s", exc)

        # 2. Fallback to DuckDuckGo Lite / HTML Search
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean)}"
            resp = await client.get(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                },
            )
            if resp.status_code == 200:
                raw_html = resp.text
                results: List[SearchResult] = []
                blocks = re.findall(
                    r'<a[^>]+class="result__snippet[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    raw_html,
                    re.DOTALL | re.IGNORECASE,
                )
                if not blocks:
                    blocks = re.findall(
                        r'<a[^>]+class="result__url[^"]*"[^>]*href="([^"]+)"[^>]*>.*?</a>.*?<a[^>]+class="result__snippet[^"]*"[^>]*>(.*?)</a>',
                        raw_html,
                        re.DOTALL | re.IGNORECASE,
                    )
                for u, snip in blocks[:max_results]:
                    clean_snip = html.unescape(re.sub(r"<[^>]+>", "", snip)).strip()
                    if clean_snip:
                        results.append(SearchResult(title=clean, snippet=clean_snip, url=u))

                if results:
                    top_snip = results[0].snippet
                    spoken = (
                        f"[emotion:analytical] [gesture:nod] Encontré información sobre '{clean}': "
                        f"{top_snip[:180]}..."
                    )
                    lines = [f"• {r.snippet}" for r in results]
                    detail_body = f"🔍 **Resultados de Búsqueda para '{clean}'**:\n" + "\n".join(lines)
                    safe_detail = wrap_untrusted(detail_body, source_label="duckduckgo_web")
                    return f"{spoken}\n---DETALLE---\n{safe_detail}"
        except Exception as exc:
            logger.warning("DuckDuckGo web search failed: %s", exc)

        return (
            f"[emotion:serious] [gesture:shrug] No encontré resultados web específicos para '{clean}'. "
            "Intenta formular la búsqueda con otros términos."
        )
