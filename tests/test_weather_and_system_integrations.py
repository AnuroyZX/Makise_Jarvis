from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amadeus.brain.tool_loop import AmadeusToolDispatcher
from amadeus.config import AmadeusSettings
from amadeus.tools.app_launcher import WindowsAppLauncher
from amadeus.tools.calculator import CalculatorTool
from amadeus.tools.file_ops import SafeFileManager
from amadeus.tools.mail_calendar import MailCalendarTool
from amadeus.tools.screen_context import ScreenContextManager
from amadeus.tools.system_control import TimerManager, WindowsSystemController
from amadeus.tools.weather import WeatherData, WeatherTool
from amadeus.tools.web_search import WebSearchTool


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.asyncio
async def test_weather_tool_formatting():
    weather = WeatherTool()
    dummy_data = WeatherData(
        location_name="Saltillo, Mexico",
        temperature_c=18.5,
        apparent_temp_c=18.0,
        humidity_pct=42,
        precipitation_mm=0.0,
        wind_kmh=8.5,
        weather_code=0,
        condition_es="Despejado / Soleado",
        condition_icon="☀️",
        is_day=True,
    )

    with patch.object(weather, "fetch_weather_data", AsyncMock(return_value=dummy_data)):
        reply = await weather.get_weather("Saltillo")
        assert "Saltillo" in reply
        assert "18.5 grados" in reply
        assert "☀️" in reply
        assert "---DETALLE---" in reply
        assert "Despejado / Soleado" in reply


@pytest.mark.asyncio
async def test_weather_tool_offline_fallback():
    weather = WeatherTool()
    with patch.object(weather, "fetch_weather_data", AsyncMock(return_value=None)):
        reply = await weather.get_weather("Atlantis")
        assert "No pude consultar los datos meteorológicos" in reply
        assert "Atlantis" in reply


def test_calculator_tool_safety_and_operations():
    # Basic math
    assert CalculatorTool.safe_calculate("25 * 4") == 100.0
    assert CalculatorTool.safe_calculate("144 / 12") == 12.0
    assert CalculatorTool.safe_calculate("2^3") == 8.0
    assert CalculatorTool.safe_calculate("sqrt(16) + 10") == 14.0

    # Malicious injection attempt should return None, NOT execute
    assert CalculatorTool.safe_calculate("__import__('os').system('dir')") is None
    assert CalculatorTool.safe_calculate("eval('2+2')") is None

    # Natural language evaluations
    res_pct = CalculatorTool.evaluate_natural_language("calcula el 15% de 3000")
    assert res_pct is not None
    assert "450" in res_pct

    res_km = CalculatorTool.evaluate_natural_language("10 km a millas")
    assert res_km is not None
    assert "6.21" in res_km

    res_arith = CalculatorTool.evaluate_natural_language("cuánto es 50 por 6")
    assert res_arith is not None
    assert "300" in res_arith


@pytest.mark.asyncio
async def test_web_search_untrusted_wrapping():
    searcher = WebSearchTool()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "AbstractText": "Python is a widely used high-level programming language.",
        "AbstractSource": "Wikipedia",
        "AbstractURL": "https://en.wikipedia.org/wiki/Python",
        "Heading": "Python (programming language)",
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(searcher, "_get_client", AsyncMock(return_value=mock_client)):
        res = await searcher.search("Python language")
        assert "Wikipedia" in res
        assert "<untrusted_data source=\"duckduckgo_instant\">" in res
        assert "</untrusted_data>" in res


def test_app_launcher_web_shortcuts():
    launcher = WindowsAppLauncher()
    with patch("webbrowser.open") as mock_open:
        res = launcher.launch("youtube")
        assert "YouTube" in res
        mock_open.assert_called_once_with("https://www.youtube.com")

    # Dry-run
    res_dry = launcher.launch("netflix", dry_run=True)
    assert "[Dry-Run]" in res_dry
    assert "https://www.netflix.com" in res_dry


@pytest.mark.asyncio
async def test_tool_dispatcher_deterministic_guards(temp_data_dir: Path):
    settings = AmadeusSettings()
    file_ops = SafeFileManager(settings=settings, data_dir=temp_data_dir)
    screen = ScreenContextManager(settings=settings)
    app_launcher = WindowsAppLauncher()
    sys_ctrl = WindowsSystemController()
    timer_mgr = TimerManager()
    weather = WeatherTool()
    web_search = WebSearchTool()
    mail_cal = MailCalendarTool(settings=settings, data_dir=temp_data_dir)
    calc = CalculatorTool()

    dispatcher = AmadeusToolDispatcher(
        file_ops=file_ops,
        screen=screen,
        app_launcher=app_launcher,
        system_control=sys_ctrl,
        timer_manager=timer_mgr,
        weather=weather,
        web_search=web_search,
        mail_calendar=mail_cal,
        calculator=calc,
    )

    # 1. Weather Guard Intercept
    with patch.object(weather, "get_weather", AsyncMock(return_value="[emotion:happy] Clima despejado")):
        res = await dispatcher.try_natural_language_action("cómo está el clima hoy")
        assert res is not None
        assert "Clima despejado" in res[0]
        weather.get_weather.assert_called_once_with("")

    with patch.object(weather, "get_weather", AsyncMock(return_value="[emotion:happy] Clima en Tokio: 12 grados")):
        res2 = await dispatcher.try_natural_language_action("cuál es el clima en Tokio")
        assert res2 is not None
        assert "Tokio" in res2[0]

    # 2. Math Guard Intercept
    res_math = await dispatcher.try_natural_language_action("cuánto es 15 por 20")
    assert res_math is not None
    assert "300" in res_math[0]

    # 3. Calendar & Agenda Guard Intercept
    res_agenda = await dispatcher.try_natural_language_action("qué tengo en la agenda")
    assert res_agenda is not None
    assert "agenda local" in res_agenda[0]

    res_add = await dispatcher.try_natural_language_action("agrega una cita para el 2026-11-15 10:00 | Dentista")
    assert res_add is not None
    assert "Dentista" in res_add[0]

    events = mail_cal.list_calendar_events()
    assert len(events) == 1
    assert events[0].title == "Dentista"

    # 4. Web Search Guard Intercept
    with patch.object(web_search, "search", AsyncMock(return_value="[emotion:analytical] Info encontrada")):
        res_s = await dispatcher.try_natural_language_action("busca en internet historia de la relatividad")
        assert res_s is not None
        assert "Info encontrada" in res_s[0]
        web_search.search.assert_called_once_with("historia de la relatividad")


@pytest.mark.asyncio
async def test_tool_dispatcher_llm_tool_calls(temp_data_dir: Path):
    settings = AmadeusSettings()
    file_ops = SafeFileManager(settings=settings, data_dir=temp_data_dir)
    screen = ScreenContextManager(settings=settings)
    app_launcher = WindowsAppLauncher()
    weather = WeatherTool()
    calc = CalculatorTool()

    dispatcher = AmadeusToolDispatcher(
        file_ops=file_ops,
        screen=screen,
        app_launcher=app_launcher,
        weather=weather,
        calculator=calc,
    )

    # Prompt instructions contain strict external function rules
    instructions = dispatcher.build_tools_prompt_instructions()
    assert "weather_query" in instructions
    assert "web_search" in instructions
    assert "calculate" in instructions
    assert "REGLA CRÍTICA: No inventes datos meteorológicos" in instructions

    # Execute calculate tool call
    res, op = await dispatcher.execute_tool_call("calculate", {"expression": "100 / 4"})
    assert "25" in res
    assert op is None

    # Execute weather tool call
    with patch.object(weather, "get_weather", AsyncMock(return_value="Clima en Madrid: 20C")):
        w_res, _ = await dispatcher.execute_tool_call("weather_query", {"location": "Madrid"})
        assert "Madrid" in w_res
