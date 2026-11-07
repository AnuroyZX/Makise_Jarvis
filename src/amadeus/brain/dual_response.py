from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import List

from amadeus.body.agent_core import EmotionState
from amadeus.brain.router import parse_emotion_tag

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
        Slices `spoken` into clean discrete sentences for parallel TTS streaming.
        """
        raw_parts = SENTENCE_SPLIT_RE.split(self.spoken.strip())
        sentences: List[str] = []
        for part in raw_parts:
            cleaned = re.sub(r"[*_`#>-]", "", part).strip()
            if cleaned:
                sentences.append(cleaned)
        return sentences or ([self.spoken.strip()] if self.spoken.strip() else [])


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
    with tolerant fallback if the model emits plain text or inline [EMOTION:...] tags.
    """
    text_clean, tag_emotion = parse_emotion_tag(raw_llm_text)

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
                raw_emo = str(obj.get("emotion") or tag_emotion.value).lower().strip()
                raw_gest = str(obj.get("gesture") or "idle").lower().strip()

                try:
                    emo = EmotionState(raw_emo)
                except ValueError:
                    emo = tag_emotion

                gesture = raw_gest if raw_gest in VALID_GESTURES else "idle"
                spoken = truncate_at_sentence_boundary(
                    raw_spoken or "Listo, te dejo los detalles en pantalla."
                )
                return DualLayerReply(
                    spoken=spoken,
                    detail=raw_detail,
                    emotion=emo,
                    gesture=gesture,
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
            spoken_summary = f"{first_line} Te dejo el detalle completo en pantalla."
        return DualLayerReply(
            spoken=truncate_at_sentence_boundary(spoken_summary),
            detail=text_clean,
            emotion=tag_emotion,
            gesture="point",
        )

    return DualLayerReply(
        spoken=truncate_at_sentence_boundary(text_clean),
        detail="",
        emotion=tag_emotion,
        gesture="idle",
    )
