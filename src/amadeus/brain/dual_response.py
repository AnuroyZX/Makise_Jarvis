from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import List

from amadeus.body.agent_core import EmotionState
from amadeus.voice.sanitizer import (
    extract_emotions_and_gestures,
    sanitize_for_bubble,
    sanitize_for_speech,
)

VALID_GESTURES = (
    "idle",
    "wave",
    "think",
    "point",
    "cross_arms",
    "celebrate",
    "shrug",
    "nod",
    "facepalm",
    "bow",
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(slots=True)
class DualLayerReply:
    """
    Two-layer response structure for voice-first desktop interaction:
    - `spoken`: Short, natural spoken response (1-3 sentences, no markdown/lists/code).
    - `detail`: Optional detailed markdown/steps/code shown on screen in a glass card.
    - `emotion`: Makise Kurisu facial expression state.
    - `gesture`: Body animation clip / procedural gesture name.
    """

    spoken: str
    detail: str
    emotion: EmotionState
    gesture: str

    def split_spoken_sentences(self) -> List[str]:
        """
        Open-LLM-VTuber Sentence Divider:
        Slices `spoken` into clean discrete sentences for parallel TTS streaming,
        guaranteeing all emotion tags, directives and formatting are sanitized.
        """
        cleaned_spoken = sanitize_for_speech(self.spoken)
        raw_parts = SENTENCE_SPLIT_RE.split(cleaned_spoken.strip())
        sentences: List[str] = []
        for part in raw_parts:
            cleaned = sanitize_for_speech(part)
            if cleaned:
                sentences.append(cleaned)
        return sentences or ([cleaned_spoken] if cleaned_spoken else [])


def truncate_at_sentence_boundary(text: str, max_chars: int = 340) -> str:
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean
    window = clean[:max_chars]
    for sep in (". ", "! ", "? ", ".\n"):
        idx = window.rfind(sep)
        if idx > 40:
            return window[: idx + 1].strip()
    return window.rstrip() + "..."


def parse_dual_layer_output(raw_llm_text: str) -> DualLayerReply:
    """
    Parse structured JSON {spoken, detail, emotion, gesture} from LLM output,
    with tolerant fallback if the model emits plain text, inline [EMOTION:...] tags,
    or tool markers like ---DETALLE---.
    """
    text_clean, tag_emotion, tag_gesture = extract_emotions_and_gestures(raw_llm_text)
    
    # Map tag emotion string to EmotionState enum
    emo = EmotionState.NEUTRAL
    if tag_emotion:
        try:
            emo = EmotionState(tag_emotion.lower())
        except ValueError:
            emo = EmotionState.NEUTRAL

    gesture = tag_gesture if tag_gesture in VALID_GESTURES else "idle"

    # Check for explicit ---DETALLE--- marker
    if "---DETALLE---" in text_clean:
        parts = text_clean.split("---DETALLE---", 1)
        spoken_part = sanitize_for_bubble(parts[0])
        detail_part = parts[1].strip()
        if not spoken_part:
            spoken_part = "Listo, te dejo los detalles en pantalla."
        return DualLayerReply(
            spoken=truncate_at_sentence_boundary(spoken_part),
            detail=detail_part,
            emotion=emo,
            gesture="nod" if gesture == "idle" else gesture,
        )

    # 1. Try parsing JSON directly or extracting a JSON block
    candidate_json = text_clean.strip()
    if not candidate_json.startswith("{"):
        match = JSON_BLOCK_RE.search(candidate_json)
        if match:
            candidate_json = match.group(0)

    if candidate_json.startswith("{"):
        try:
            obj = json.loads(candidate_json)
            if isinstance(obj, dict) and ("spoken" in obj or "detail" in obj):
                raw_spoken = str(obj.get("spoken") or "").strip()
                raw_detail = str(obj.get("detail") or "").strip()
                raw_emo = str(obj.get("emotion") or (tag_emotion or emo.value)).lower().strip()
                raw_gest = str(obj.get("gesture") or gesture).lower().strip()

                try:
                    emo = EmotionState(raw_emo)
                except ValueError:
                    pass

                final_gesture = raw_gest if raw_gest in VALID_GESTURES else gesture
                spoken = truncate_at_sentence_boundary(
                    sanitize_for_bubble(raw_spoken) or "Listo, te dejo los detalles en pantalla."
                )
                return DualLayerReply(
                    spoken=spoken,
                    detail=raw_detail,
                    emotion=emo,
                    gesture=final_gesture,
                )
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. Tolerant fallback for plain text responses:
    # If text contains code blocks, numbered lists, or is longer than 340 chars -> split into spoken + detail
    has_structured_blocks = (
        "```" in text_clean
        or "\n1." in text_clean
        or "\n- " in text_clean
        or "\n• " in text_clean
        or len(text_clean) > 340
    )
    if has_structured_blocks:
        first_sentences = SENTENCE_SPLIT_RE.split(text_clean)
        first_line = first_sentences[0].strip() if first_sentences else ""
        if len(first_line) > 220 or "```" in first_line:
            spoken_summary = "He preparado la respuesta detallada; te la dejo aquí en pantalla."
        else:
            first_clean = sanitize_for_bubble(first_line)
            spoken_summary = f"{first_clean} Te dejo el detalle completo en pantalla."
        return DualLayerReply(
            spoken=truncate_at_sentence_boundary(spoken_summary),
            detail=text_clean,
            emotion=emo,
            gesture="point" if gesture == "idle" else gesture,
        )

    return DualLayerReply(
        spoken=truncate_at_sentence_boundary(sanitize_for_bubble(text_clean)),
        detail="",
        emotion=emo,
        gesture=gesture,
    )
