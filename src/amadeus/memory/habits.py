from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import List, Optional

from amadeus.config import get_default_data_dir


class HabitTracker:
    """
    Phase F5 (Aprendizaje Local de Hábitos de Uso de Aplicaciones):
    - Stores `app_usage(week_key, weekday, hour, process, seconds)` strictly in local SQLite.
    - Never sends habit data to external clouds.
    - Suggests opening a habitual app at most ONCE per calendar day when the app was used
      in >= 3 distinct weeks in the current `(weekday, hour)` slot and is not currently running.
    """

    MIN_WEEKS_FOR_HABIT = 3
    MIN_SECONDS_PER_SLOT = 120

    def __init__(self, db_path: Optional[Path] = None) -> None:
        target_dir = get_default_data_dir()
        self.db_path = db_path or (target_dir / "amadeus_memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_suggestion_date: Optional[str] = None
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=5.0)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_usage (
                    week_key TEXT NOT NULL,
                    weekday INTEGER NOT NULL,
                    hour INTEGER NOT NULL,
                    process TEXT NOT NULL,
                    seconds INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (week_key, weekday, hour, process)
                );
                """
            )

    def record_usage(
        self,
        process_name: str,
        seconds: int = 60,
        when: Optional[datetime] = None,
    ) -> None:
        proc = process_name.strip().lower()
        if not proc or proc in ("unknown", "desktop", "explorer.exe", "idle"):
            return
        dt = when or datetime.now()
        iso_year, iso_week, _ = dt.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekday = dt.weekday()
        hour = dt.hour

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_usage (week_key, weekday, hour, process, seconds)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(week_key, weekday, hour, process)
                DO UPDATE SET seconds = seconds + excluded.seconds;
                """,
                (week_key, weekday, hour, proc, int(seconds)),
            )

    def get_habit_suggestion(
        self,
        currently_open_processes: Optional[List[str]] = None,
        when: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Return at most 1 gentle suggestion per day if a habitual app for this (weekday, hour)
        is not currently open.
        """
        dt = when or datetime.now()
        today_str = dt.date().isoformat()
        if self._last_suggestion_date == today_str:
            return None

        open_set = {p.lower() for p in (currently_open_processes or [])}
        weekday = dt.weekday()
        hour = dt.hour

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT process, COUNT(DISTINCT week_key) AS weeks_count, SUM(seconds) AS total_sec
                FROM app_usage
                WHERE weekday = ? AND hour = ? AND seconds >= ?
                GROUP BY process
                HAVING weeks_count >= ?
                ORDER BY weeks_count DESC, total_sec DESC
                LIMIT 3
                """,
                (weekday, hour, self.MIN_SECONDS_PER_SLOT, self.MIN_WEEKS_FOR_HABIT),
            ).fetchall()

        for proc, weeks_count, _ in rows:
            if proc.lower() not in open_set:
                self._last_suggestion_date = today_str
                clean_name = proc.replace(".exe", "")
                return f"¿Te abro {clean_name}? A esta hora sueles utilizarlo ({weeks_count} semanas registradas)."

        return None
