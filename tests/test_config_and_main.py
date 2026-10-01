"""Testa configurações, logging, menu e execução dos scripts principais."""

import importlib
import urllib.parse

import pytest

from src.config import settings


def test_get_env_requires_a_configured_value(monkeypatch):
    monkeypatch.delenv("REQUIRED_TEST_SETTING", raising=False)

    with pytest.raises(KeyError, match="REQUIRED_TEST_SETTING"):
        settings.get_env("REQUIRED_TEST_SETTING")


def test_get_path_resolves_relative_and_absolute_paths(monkeypatch, tmp_path):
    relative_path = "data/input.json"
    absolute_path = tmp_path / "absolute.json"
    monkeypatch.setattr(settings, "get_env", lambda key: relative_path)
    assert settings.get_path("INPUT_PATH") == settings.PROJECT_ROOT / relative_path

    monkeypatch.setattr(settings, "get_env", lambda key: str(absolute_path))
    assert settings.get_path("INPUT_PATH") == absolute_path


def test_create_db_engine_builds_sql_server_connection(monkeypatch):
    values = {
        "DB_HOST": "sql.example.test",
        "DB_PORT": "1433",
        "DB_NAME": "monitoramento",
        "DB_TRUSTED_CONNECTION": "yes",
    }
    captured = {}
    monkeypatch.setattr(settings, "get_env", values.__getitem__)
    monkeypatch.setattr(
        settings, "create_engine", lambda url: captured.setdefault("url", url)
    )

    result = settings.create_db_engine()
    connection_string = urllib.parse.unquote_plus(captured["url"])

    assert result == captured["url"]
    assert captured["url"].startswith("mssql+pyodbc:///")
    assert "SERVER=sql.example.test,1433" in connection_string
    assert "DATABASE=monitoramento" in connection_string


def test_configure_logging_creates_log_directory(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(settings, "get_env", lambda key: "logs")
    monkeypatch.setattr(
        settings.logging,
        "basicConfig",
        lambda **kwargs: captured.update(kwargs),
    )

    settings.configure_logging(tmp_path)

    assert (tmp_path / "logs").is_dir()
    assert captured["force"] is True
    assert any(
        handler.baseFilename.endswith("execucao_relatorio.log")
        for handler in captured["handlers"]
    )
    for handler in captured["handlers"]:
        handler.close()


@pytest.fixture
def main_module(monkeypatch, tmp_path):
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    return importlib.import_module("src.main")


def test_exibir_menu_returns_trimmed_selection(main_module, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: " 2 ")

    assert main_module.exibir_menu() == "2"


def test_executar_script_handles_missing_script(main_module, tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)

    assert main_module.executar_script("missing.py") is False


@pytest.mark.parametrize("return_code, expected", [(0, True), (1, False)])
def test_executar_script_captures_output(
    main_module, tmp_path, monkeypatch, capsys, return_code, expected
):
    script = tmp_path / "job.py"
    script.touch()
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        main_module.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "returncode": return_code,
                "stdout": "job output\n",
                "stderr": "failure",
            },
        )(),
    )

    assert main_module.executar_script("job.py") is expected
    assert capsys.readouterr().out == "job output\n"


def test_executar_script_runs_interactively(main_module, tmp_path, monkeypatch):
    script = tmp_path / "report.py"
    script.touch()
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(
        main_module.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs))
        or type("Result", (), {"returncode": 0})(),
    )

    assert main_module.executar_script("report.py", interativo=True) is True
    assert len(calls) == 1
    assert calls[0][1] == {}


def test_main_dispatches_menu_actions_and_exits(main_module, monkeypatch):
    options = iter(["1", "2", "3"])
    calls = []
    scripts = {
        "INSERT_LOCALIZACAO": "locations.py",
        "INSERT_LEITURA_AMBIENTAL": "water.py",
        "INSERT_LEITURA_METEOROLOGICA": "weather.py",
        "RELATORIO_ESTATISTICO": "report.py",
    }
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(main_module, "get_env", scripts.__getitem__)
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path, interativo=False: calls.append((path, interativo)),
    )

    main_module.main()

    assert calls == [
        ("locations.py", False),
        ("water.py", False),
        ("weather.py", False),
        ("report.py", True),
    ]