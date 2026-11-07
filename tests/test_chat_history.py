from __future__ import annotations

from pathlib import Path
import pytest

from amadeus.body.agent_core import AgentMessage, AmadeusAgentCore, EmotionState
from amadeus.house.resource_governor import ResourceGovernor
from amadeus.memory.hybrid_memory import LocalSQLiteMemory


def test_sqlite_chat_sessions_and_messages(tmp_path: Path):
    db_file = tmp_path / "memory_test.db"
    mem = LocalSQLiteMemory(db_path=db_file)

    session_id = mem.create_new_session("Sesión Steins Gate")
    assert session_id

    mem.save_chat_message(session_id, "user", "Hola Kurisu", emotion="neutral")
    mem.save_chat_message(
        session_id, "assistant", "¡No me llames así, b-baka!", emotion="tsundere_blush"
    )

    recent = mem.load_recent_messages(session_id, limit=10)
    assert len(recent) == 2
    assert recent[0]["role"] == "user"
    assert recent[0]["content"] == "Hola Kurisu"
    assert recent[1]["role"] == "assistant"
    assert recent[1]["content"] == "¡No me llames así, b-baka!"

    sessions = mem.list_chat_sessions()
    assert len(sessions) >= 1
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["title"] == "Sesión Steins Gate"
    assert sessions[0]["msg_count"] == 2


@pytest.mark.asyncio
async def test_agent_core_persists_and_restores_history(tmp_path: Path):
    db_file = tmp_path / "core_mem.db"
    mem = LocalSQLiteMemory(db_path=db_file)
    gov = ResourceGovernor()

    core = AmadeusAgentCore(governor=gov, memory=mem)
    await core.process_user_message(
        AgentMessage(role="user", content="Recuerda que mi laboratorio es FG-Lab")
    )

    # Simulate app restart with a fresh AmadeusAgentCore on the same DB
    restarted_core = AmadeusAgentCore(governor=gov, memory=mem)
    history = restarted_core.history
    assert len(history) >= 2
    assert any("laboratorio es FG-Lab" in m.content for m in history)
