from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Dict, List, Optional
import uuid

from amadeus.identity.soul_manager import SoulManager

SENSITIVE_PATTERNS = re.compile(
    r"(?:password|contraseña|tarjeta|cvv|iban|ssn|sk-[a-zA-Z0-9_-]{8,}|AIza[a-zA-Z0-9_-]{10,}|diagnóstico médico|cuenta bancaria)",
    re.IGNORECASE,
)

STYLE_CORRECTION_PATTERNS = [
    (
        re.compile(r"no me llames\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ0-9_-]+)", re.IGNORECASE),
        lambda m: f"Nunca llamar al usuario '{m.group(1).strip()}'.",
    ),
    (
        re.compile(r"llámame\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ0-9_-]+)", re.IGNORECASE),
        lambda m: f"Llamar siempre al usuario '{m.group(1).strip()}'.",
    ),
    (
        re.compile(r"(?:háblame|responde)\s+(más\s+(?:corto|breve|formal|informal|directo|técnico))", re.IGNORECASE),
        lambda m: f"Preferencia de tono: responder {m.group(1).strip()}.",
    ),
]


@dataclass(slots=True)
class LearnedFactItem:
    fact_id: str
    text: str
    category: str  # "gusto" | "rutina" | "proyecto" | "persona"
    confidence: float


class ReflectionEngine:
    """
    Phase F5 (Aprendizaje Transparente y Revisable + Reglas de Estilo):
    - Filters out any facts with confidence < 0.7 or matching sensitive patterns (passwords, bank, health).
    - Learns permanent `style_rules` immediately when the user corrects Kurisu ("no me llames Okabe", "háblame más breve").
    - Marks contradictory `obsolete_ids` and updates `## Aprendido` and `## Reglas de estilo` inside USER.md.
    - Every learned item has a stable `[id:xxxx]` so the user can review and delete individual lines from the Panel.
    """

    MIN_CONFIDENCE = 0.70

    def __init__(self, soul_manager: SoulManager) -> None:
        self.soul = soul_manager

    @staticmethod
    def is_sensitive(text: str) -> bool:
        return bool(SENSITIVE_PATTERNS.search(text))

    def detect_direct_style_correction(self, user_message: str) -> Optional[str]:
        """Detect immediate user style corrections in natural conversation."""
        for pat, builder in STYLE_CORRECTION_PATTERNS:
            m = pat.search(user_message.strip())
            if m:
                rule_text = builder(m)
                if not self.is_sensitive(rule_text):
                    self.apply_reflection_payload(
                        {"facts": [], "style_rules": [rule_text], "obsolete_ids": []}
                    )
                    return rule_text
        return None

    def apply_reflection_payload(self, payload: Dict[str, Any]) -> Dict[str, int]:
        """
        Apply a reflection JSON payload `{facts: [...], style_rules: [...], obsolete_ids: [...]}`
        directly into `USER.md`, removing any `obsolete_ids` and filtering out low-confidence or sensitive data.
        """
        raw_md = self.soul.read_user_profile()
        obsolete = {str(x).strip() for x in (payload.get("obsolete_ids") or []) if x}

        # 1. Remove any lines containing `[id:<obsolete_id>]`
        if obsolete:
            kept_lines = []
            for line in raw_md.splitlines():
                if any(f"[id:{obs}]" in line for obs in obsolete):
                    continue
                kept_lines.append(line)
            raw_md = "\n".join(kept_lines)

        # 2. Filter and format valid facts (confidence >= 0.7 and not sensitive)
        added_facts: List[str] = []
        for item in payload.get("facts") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            conf = float(item.get("confidence") or 0.0)
            cat = str(item.get("category") or "gusto").strip()
            if not text or conf < self.MIN_CONFIDENCE or self.is_sensitive(text):
                continue
            fid = str(item.get("id") or uuid.uuid4().hex[:6])
            entry = f"- [id:{fid}] ({cat}) {text}"
            if text not in raw_md:
                added_facts.append(entry)

        # 3. Filter and format style rules
        added_rules: List[str] = []
        for rule in payload.get("style_rules") or []:
            r_text = str(rule).strip()
            if not r_text or self.is_sensitive(r_text):
                continue
            rid = uuid.uuid4().hex[:6]
            entry = f"- [id:{rid}] {r_text}"
            if r_text not in raw_md:
                added_rules.append(entry)

        if added_facts:
            if "## Aprendido" not in raw_md:
                raw_md = raw_md.rstrip() + "\n\n## Aprendido\n"
            raw_md = self._append_under_section(raw_md, "## Aprendido", added_facts)

        if added_rules:
            if "## Reglas de estilo" not in raw_md:
                raw_md = raw_md.rstrip() + "\n\n## Reglas de estilo\n"
            raw_md = self._append_under_section(raw_md, "## Reglas de estilo", added_rules)

        self.soul.update_user_profile(raw_md)
        return {
            "added_facts": len(added_facts),
            "added_rules": len(added_rules),
            "removed_obsolete": len(obsolete),
        }

    def delete_learned_item_by_id(self, item_id: str) -> bool:
        target_tag = f"[id:{item_id.strip()}]"
        raw_md = self.soul.read_user_profile()
        lines = raw_md.splitlines()
        filtered = [ln for ln in lines if target_tag not in ln]
        if len(filtered) == len(lines):
            return False
        self.soul.update_user_profile("\n".join(filtered))
        return True

    @staticmethod
    def _append_under_section(markdown: str, header: str, new_lines: List[str]) -> str:
        idx = markdown.find(header)
        if idx == -1:
            return markdown.rstrip() + f"\n\n{header}\n" + "\n".join(new_lines) + "\n"
        insert_pos = idx + len(header)
        next_Line = markdown.find("\n", insert_pos)
        if next_Line == -1:
            return markdown + "\n" + "\n".join(new_lines) + "\n"
        block = "\n" + "\n".join(new_lines)
        return markdown[:next_Line] + block + markdown[next_Line:]
