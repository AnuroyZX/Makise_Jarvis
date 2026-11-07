from __future__ import annotations

import pytest
from amadeus.voice.sanitizer import (
    sanitize_for_speech,
    sanitize_for_bubble,
    extract_emotions_and_gestures,
)


def test_sanitize_speech_strips_tags_and_actions():
    raw = "[emotion:smug] [gesture:nod] Hola Okabe, *suspira* ya terminé la tarea.\n---DETALLE---\nAquí está el log."
    speech = sanitize_for_speech(raw)
    assert "[emotion:smug]" not in speech
    assert "[gesture:nod]" not in speech
    assert "*suspira*" not in speech
    assert "---DETALLE---" not in speech
    assert "Aquí está el log" not in speech
    assert "Hola Okabe, ya terminé la tarea." in speech


def test_sanitize_speech_case_insensitive_and_mood_directives():
    raw = "[EMOTION:TSUNDERE_BLUSH] Mood: Tsundere. ¡No es como si lo hubiera hecho por ti, b-baka!"
    speech = sanitize_for_speech(raw)
    assert "[EMOTION:" not in speech
    assert "Mood:" not in speech.lower()
    assert "¡No es como si lo hubiera hecho por ti, b-baka!" in speech


def test_sanitize_speech_markdown_and_code():
    raw = "Aquí tienes el código:\n```python\nprint('hello')\n```\nRevisa el archivo `config.json` y visita https://github.com/test."
    speech = sanitize_for_speech(raw)
    assert "```" not in speech
    assert "print('hello')" not in speech
    assert "`config.json`" not in speech
    assert "https://" not in speech
    assert "config.json" in speech


def test_sanitize_bubble_keeps_text_clean():
    raw = "[emotion:analytical] [gesture:think] Analizando la divergencia temporal de la línea de mundo."
    bubble = sanitize_for_bubble(raw)
    assert "[emotion:" not in bubble
    assert "[gesture:" not in bubble
    assert bubble == "Analizando la divergencia temporal de la línea de mundo."


def test_extract_emotions_and_gestures():
    raw = "[emotion:surprised] [gesture:point] ¡¿Qué estás diciendo, idiota?!"
    clean, emotion, gesture = extract_emotions_and_gestures(raw)
    assert emotion == "surprised"
    assert gesture == "point"
    assert clean == "¡¿Qué estás diciendo, idiota?!"
