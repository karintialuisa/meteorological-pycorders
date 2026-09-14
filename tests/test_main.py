import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import main


def test_main_prints_start_message(capsys):
    main()
    captured = capsys.readouterr()
    assert "Pipeline PyCordersMeteorological iniciado." in captured.out
