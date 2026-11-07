from __future__ import annotations

import re
from typing import Optional, Tuple

# Matches [emotion:smug], [gesture:nod], [mood:tsundere], etc. (case-insensitive)
BRACKET_TAG_PATTERN = re.compile(
    r"\[\s*(emotion|gesture|mood|action|thought|status|pose)\s*:\s*([^\]]+)\]",
    re.IGNORECASE,
)

# Matches <emotion>smug</emotion>, <gesture>nod</gesture>, etc.
XML_TAG_PATTERN = re.compile(
    r"<\s*(emotion|gesture|mood|action|thought|status)\s*>([^<]+)</\s*\1\s*>",
    re.IGNORECASE,
)

# Matches directives like "Mood: tsundere." or "Action: smile" without eating the rest of the sentence
DIRECTIVE_PATTERN = re.compile(
    r"(?i)\b(mood|emotion|action|gesture|directiva|pensamiento|estado)\s*:\s*[\w\-]+[.,;]?"
)

# Matches roleplay / stage directions like *suspira*, *sonríe*
STAGE_DIRECTION_PATTERN = re.compile(r"\*[^*]+\*")

# Cuts off detail separator and everything after it
DETAIL_SPLIT_PATTERN = re.compile(r"---DETALLE---[\s\S]*$", re.IGNORECASE)

# Strips markdown code blocks
CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")

# Extracts inline code content `code` -> code
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")

# Strips raw URLs
URL_PATTERN = re.compile(r"https?://\S+")

# Markdown line markers (headers, quotes, bullets at start of line)
MD_LINE_MARKERS = re.compile(r"(?m)^[#>\-*+]\s+")

# Markdown inline styling asterisks/underscores (*bold*, _italic_)
MD_INLINE_STYLING = re.compile(r"[*_~|]")

MULTIPLE_SPACES_PATTERN = re.compile(r"[ \t]+")


def extract_emotions_and_gestures(
    text: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extracts emotion and gesture tags from text, returning
    (cleaned_text, emotion, gesture).
    """
    found_emotion: Optional[str] = None
    found_gesture: Optional[str] = None

    def _tag_replacer(match: re.Match[str]) -> str:
        nonlocal found_emotion, found_gesture
        tag_type = match.group(1).lower()
        tag_val = match.group(2).strip().lower()
        if tag_type in ("emotion", "mood") and not found_emotion:
            found_emotion = tag_val
        elif tag_type in ("gesture", "action", "pose") and not found_gesture:
            found_gesture = tag_val
        return ""

    clean = BRACKET_TAG_PATTERN.sub(_tag_replacer, text)
    clean = XML_TAG_PATTERN.sub(_tag_replacer, clean)
    clean = DIRECTIVE_PATTERN.sub("", clean)
    clean = clean.strip()
    return clean, found_emotion, found_gesture


def sanitize_for_bubble(text: str) -> str:
    """
    Removes emotion/gesture tags and internal directives, preserving natural
    punctuation and text for the visual dialog bubble.
    """
    if not text:
        return ""
    clean, _, _ = extract_emotions_and_gestures(text)
    clean = BRACKET_TAG_PATTERN.sub("", clean)
    clean = XML_TAG_PATTERN.sub("", clean)
    clean = DIRECTIVE_PATTERN.sub("", clean)
    # Strip markdown headers/bullets at start of lines if any
    clean = MD_LINE_MARKERS.sub("", clean)
    # Normalize excessive spaces
    clean = MULTIPLE_SPACES_PATTERN.sub(" ", clean)
    return clean.strip()


def sanitize_for_speech(text: str) -> str:
    """
    Cleans text thoroughly for voice synthesis (TTS):
    - Cuts off ---DETALLE--- and trailing tool output.
    - Strips bracket tags and directives (emotion, gesture, mood).
    - Strips stage directions (*suspira*, *mira de reojo*).
    - Strips code blocks, URLs, and formatting markers.
    - Preserves internal hyphenation (e.g. b-baka).
    """
    if not text:
        return ""

    # 1. Cut off written detail section
    res = DETAIL_SPLIT_PATTERN.sub("", text)

    # 2. Extract and remove bracket tags
    res, _, _ = extract_emotions_and_gestures(res)

    # 3. Strip code blocks and keep inline code readable
    res = CODE_BLOCK_PATTERN.sub("", res)
    res = INLINE_CODE_PATTERN.sub(r"\1", res)

    # 4. Strip URLs
    res = URL_PATTERN.sub("", res)

    # 5. Strip directives & stage directions
    res = DIRECTIVE_PATTERN.sub("", res)
    res = STAGE_DIRECTION_PATTERN.sub("", res)

    # 6. Strip markdown line markers & styling characters
    res = MD_LINE_MARKERS.sub("", res)
    res = MD_INLINE_STYLING.sub("", res)

    # 7. Normalize spaces and dangling punctuation
    res = MULTIPLE_SPACES_PATTERN.sub(" ", res)
    res = re.sub(r"\s+([.,;:!?])", r"\1", res)
    res = re.sub(r"([.,;:!?]){2,}", r"\1", res)
    return res.strip()
