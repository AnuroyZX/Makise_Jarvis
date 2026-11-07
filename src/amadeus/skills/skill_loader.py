from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from amadeus.identity.soul_manager import resolve_bundle_root


@dataclass(slots=True)
class SkillDefinition:
    name: str
    description: str
    triggers: List[str]
    file_path: Path

    def load_full_instructions(self) -> str:
        """Progressive disclosure: read full SKILL.md body only when triggered."""
        raw = self.file_path.read_text(encoding="utf-8")
        # Strip YAML frontmatter if present
        match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)$", raw, re.DOTALL)
        return match.group(1).strip() if match else raw.strip()


class SkillRegistry:
    """
    Module 6 (Habilidades):
    Scans bundled and user skills/ directories, keeps only lightweight metadata in RAM,
    and progressively injects full SKILL.md instructions only when a user request matches.
    """

    def __init__(
        self,
        bundled_skills_dir: Optional[Path] = None,
        user_skills_dir: Optional[Path] = None,
    ) -> None:
        root = resolve_bundle_root()
        self.bundled_dir = bundled_skills_dir or (root / "skills")
        self.user_dir = user_skills_dir
        self._skills: Dict[str, SkillDefinition] = {}
        self.reload()

    @property
    def skills(self) -> Dict[str, SkillDefinition]:
        return dict(self._skills)

    def reload(self) -> None:
        self._skills.clear()
        for folder in (self.bundled_dir, self.user_dir):
            if folder and folder.exists():
                for skill_md in folder.glob("*/SKILL.md"):
                    parsed = self._parse_skill_metadata(skill_md)
                    if parsed:
                        self._skills[parsed.name] = parsed

    @staticmethod
    def _parse_skill_metadata(skill_md: Path) -> Optional[SkillDefinition]:
        try:
            raw = skill_md.read_text(encoding="utf-8")
        except OSError:
            return None

        name = skill_md.parent.name
        description = ""
        triggers: List[str] = []

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip().strip('"').strip("'")
                    if k == "name" and v:
                        name = v
                    elif k == "description" and v:
                        description = v
                    elif k == "triggers" and v:
                        triggers = [
                            t.strip().lower()
                            for t in v.strip("[]").split(",")
                            if t.strip()
                        ]
        return SkillDefinition(
            name=name,
            description=description or f"Skill {name}",
            triggers=triggers,
            file_path=skill_md,
        )

    def match_skills_for_query(self, user_query: str) -> List[SkillDefinition]:
        """Find skills whose triggers or name match the user's message."""
        q_lower = user_query.lower()
        matched: List[SkillDefinition] = []
        for skill in self._skills.values():
            if skill.name.lower() in q_lower or any(
                trig in q_lower for trig in skill.triggers
            ):
                matched.append(skill)
        return matched

    def build_progressive_context(self, user_query: str) -> str:
        """
        Return lightweight catalog summary + full instructions ONLY for matched skills.
        Saves tokens and RAM on every turn.
        """
        if not self._skills:
            return ""

        catalog_lines = [
            f"- `{s.name}`: {s.description}" for s in self._skills.values()
        ]
        matched = self.match_skills_for_query(user_query)
        parts = ["Catálogo de Habilidades (Skills):\n" + "\n".join(catalog_lines)]

        for m in matched:
            parts.append(
                f"### [SKILL ACTIVA: {m.name}]\n{m.load_full_instructions()}"
            )
        return "\n\n".join(parts)
