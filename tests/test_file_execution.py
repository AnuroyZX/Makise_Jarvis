from __future__ import annotations

from pathlib import Path
import pytest

from amadeus.config import AmadeusSettings
from amadeus.tools.file_ops import SafeFileManager


def test_file_creation_and_execution_confirmation(tmp_path: Path):
    settings = AmadeusSettings()
    mgr = SafeFileManager(settings=settings, data_dir=tmp_path, extra_roots=[tmp_path])

    script_path = tmp_path / "hello_lab.py"
    res = mgr.fs_create_file(script_path, 'print("El Psy Kongroo")')
    assert "creado" in res.lower()
    assert script_path.exists()

    # 1. Request execution requires confirmation
    op = mgr.request_execute(script_path)
    assert op.op_type == "execute"
    assert "hello_lab.py" in op.summary

    # 2. Cancelation
    cancel_msg = mgr.resolve_pending(op.op_id, approved=False)
    assert "cancelada" in cancel_msg.lower()

    # 3. Approval executes and returns detail
    op2 = mgr.request_execute(script_path)
    exec_msg = mgr.resolve_pending(op2.op_id, approved=True)
    assert "---DETALLE---" in exec_msg
    assert "El Psy Kongroo" in exec_msg
