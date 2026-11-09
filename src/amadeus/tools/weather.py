from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import time
from typing import Any, Dict, Optional
import urllib.parse

import httpx

from amadeus.tools.mail_calendar import wrap_untrusted

logger = logging.getLogger("amadeus.weather")

WMO_WEATHER_CODES: Dict[int, tuple[str, str]] = {
    0: ("Despejado / Soleado", "☀️"),
    1: ("Principalmente despejado", "🌤️"),
    2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁️"),
    45: ("Niebla", "🌫️"),
    48: ("Niebla con escarcha", "🌫️"),
    51: ("Llovizna ligera", "🌦️"),
    53: ("Llovizna moderada", "🌦️"),
    55: ("Llovizna densa", "🌧️"),
    61: ("Lluvia ligera", "🌧️"),
    63: ("Lluvia moderada", "🌧️"),
    65: ("Lluvia intensa", "🌧️"),
    71: ("Nevada ligera", "❄️"),
    73: ("Nevada moderada", "❄️"),
    75: ("Nevada intensa", "❄️"),
    77: ("Granos de nieve", "❄️"),
    80: ("Chubascos ligeros", "🌧️"),
    81: ("Chubascos moderados", "🌧️"),
    82: ("Chubascos violentos", "⛈️"),
    85: ("Chubascos de nieve", "🌨️"),
    86: ("Chubascos de nieve intensos", "🌨️"),
    95: ("Tormenta eléctrica", "⛈️"),
    96: ("Tormenta con granizo ligero", "⛈️"),
    99: ("Tormenta con granizo fuerte", "⛈️"),
}


@dataclass(slots=True)
class WeatherData:
    location_name: str
    temperature_c: float
    apparent_temp_c: float
    humidity_pct: int
    precipitation_mm: float
    wind_kmh: float
    weather_code: int
    condition_es: str
    condition_icon: str
    is_day: bool = True


class WeatherTool:
    """
    Module 7 (Herramientas - Clima en Tiempo Real):
    Zero-config real-time weather service powered by Open-Meteo & free IP geolocation.
    Requires 0 API keys and 0 user configuration.
    """

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        default_city: str = "",
    ) -> None:
        self._http = http_client
        self.default_city = default_city.strip()
        self._cached_ip_location: Optional[tuple[float, float, str]] = None
        self._ip_cache_expiry: float = 0.0
        self._weather_cache: Dict[str, tuple[float, WeatherData]] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is not None and not self._http.is_closed:
            return self._http
        return httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "AmadeusKurisu/1.0"})

    async def _detect_ip_location(self) -> Optional[tuple[float, float, str]]:
        now = time.time()
        if self._cached_ip_location is not None and now < self._ip_cache_expiry:
            return self._cached_ip_location

        client = await self._get_client()
        try:
            resp = await client.get(
                "http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon"
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    lat = float(data["lat"])
                    lon = float(data["lon"])
                    loc_name = f"{data.get('city', '')}, {data.get('country', '')}".strip(", ")
                    self._cached_ip_location = (lat, lon, loc_name)
                    self._ip_cache_expiry = now + 86400  # 24 hour cache
                    return self._cached_ip_location
        except Exception as exc:
            logger.warning("IP geolocation failed: %s", exc)
        return None

    async def _geocode_city(self, city: str) -> Optional[tuple[float, float, str]]:
        client = await self._get_client()
        try:
            encoded = urllib.parse.quote(city.strip())
            url = (
                f"https://geocoding-api.open-meteo.com/v1/search?"
                f"name={encoded}&count=1&language=es&format=json"
            )
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    r = results[0]
                    lat = float(r["latitude"])
                    lon = float(r["longitude"])
                    country = r.get("country") or ""
                    admin = r.get("admin1") or ""
                    parts = [r["name"]]
                    if admin and admin != r["name"]:
                        parts.append(admin)
                    if country:
                        parts.append(country)
                    loc_name = ", ".join(parts)
                    return lat, lon, loc_name
        except Exception as exc:
            logger.warning("Geocoding failed for %s: %s", city, exc)
        return None

    async def fetch_weather_data(self, location_query: str = "") -> Optional[WeatherData]:
        target = location_query.strip() or self.default_city
        cache_key = target.lower() if target else "__auto_ip__"
        now = time.time()

        if cache_key in self._weather_cache:
            cache_ts, cached_data = self._weather_cache[cache_key]
            if now - cache_ts < 600:  # 10 minutes cache
                return cached_data

        lat: float = 0.0
        lon: float = 0.0
        loc_name = ""

        if target:
            geo = await self._geocode_city(target)
            if geo:
                lat, lon, loc_name = geo
            else:
                return None
        else:
            ip_geo = await self._detect_ip_location()
            if ip_geo:
                lat, lon, loc_name = ip_geo
            else:
                # Ultimate fallback to Madrid if all offline
                lat, lon, loc_name = 40.4165, -3.70256, "Madrid, España"

        client = await self._get_client()
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&"
                f"current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                f"precipitation,weather_code,wind_speed_10m,is_day&timezone=auto"
            )
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            curr = resp.json().get("current") or {}
            w_code = int(curr.get("weather_code", 0))
            cond_es, icon = WMO_WEATHER_CODES.get(w_code, ("Tiempo variable", "🌤️"))
            w_data = WeatherData(
                location_name=loc_name,
                temperature_c=float(curr.get("temperature_2m", 0.0)),
                apparent_temp_c=float(curr.get("apparent_temperature", 0.0)),
                humidity_pct=int(curr.get("relative_humidity_2m", 0)),
                precipitation_mm=float(curr.get("precipitation", 0.0)),
                wind_kmh=float(curr.get("wind_speed_10m", 0.0)),
                weather_code=w_code,
                condition_es=cond_es,
                condition_icon=icon,
                is_day=bool(curr.get("is_day", 1)),
            )
            self._weather_cache[cache_key] = (now, w_data)
            return w_data
        except Exception as exc:
            logger.warning("Forecast query failed for %s: %s", loc_name, exc)
            return None

    async def get_weather(self, location_query: str = "") -> str:
        """
        Returns full DualLayer text: spoken Kurisu voice sentence + glass UI detail card.
        """
        data = await self.fetch_weather_data(location_query)
        if data is None:
            query_str = f" para '{location_query}'" if location_query else ""
            return (
                f"[emotion:serious] [gesture:shrug] No pude consultar los datos meteorológicos{query_str}. "
                "Verifica tu conexión a internet o especifica una ciudad válida."
            )

        spoken = (
            f"[emotion:analytical] [gesture:nod] En {data.location_name} la temperatura actual "
            f"es de {round(data.temperature_c, 1)} grados con {data.condition_es.lower()} "
            f"y una sensación térmica de {round(data.apparent_temp_c, 1)} grados."
        )

        precip_str = (
            f"• Precipitación: {data.precipitation_mm} mm"
            if data.precipitation_mm > 0
            else "• Sin precipitaciones registradas"
        )

        detail = (
            f"---DETALLE---\n"
            f"{data.condition_icon} **Clima en {data.location_name}**:\n"
            f"• Temperatura: {round(data.temperature_c, 1)}°C (Sensación: {round(data.apparent_temp_c, 1)}°C)\n"
            f"• Condición: {data.condition_es}\n"
            f"• Humedad: {data.humidity_pct}%\n"
            f"• Viento: {round(data.wind_kmh, 1)} km/h\n"
            f"{precip_str}\n"
            f"*(Datos en tiempo real vía Open-Meteo)*"
        )

        return f"{spoken}\n{detail}"
