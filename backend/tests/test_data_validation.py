from __future__ import annotations

from app.scripts.validate_data import main as validate_main


def test_validate_data_passes(capsys) -> None:
    rc = validate_main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "✅" in out
    assert "正式 case: 8" in out
    assert "顺序模板: 4" in out
