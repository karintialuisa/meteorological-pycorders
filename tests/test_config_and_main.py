"""Testa caminhos, logging e a entrada real do pipeline."""

import subprocess
import sys
from pathlib import Path
import urllib.parse

import pytest

from config import settings


def test_get_env_requires_a_configured_value(monkeypatch):
    monkeypatch.delenv("REQUIRED_TEST_SETTING", raising=False)

    with pytest.raises(KeyError, match="REQUIRED_TEST_SETTING"):
        settings.get_env("REQUIRED_TEST_SETTING")


def test_project_root_and_environment_file_match_repository():
    root = Path(__file__).resolve().parents[1]
    assert settings.PROJECT_ROOT == root
    assert settings.ENV_FILE == root / "src" / "config" / ".env"


def test_get_path_resolves_relative_and_absolute_paths(monkeypatch, tmp_path):
    relative_path = "data/input.json"
    absolute_path = tmp_path / "absolute.json"
    monkeypatch.setattr(settings, "get_env", lambda key: relative_path)
    assert settings.get_path("INPUT_PATH") == settings.PROJECT_ROOT / relative_path

    monkeypatch.setattr(settings, "get_env", lambda key: str(absolute_path))
    assert settings.get_path("INPUT_PATH") == absolute_path


def test_get_silver_dir_resolves_default_relative_and_absolute(monkeypatch, tmp_path):
    monkeypatch.delenv("SILVER_DIR", raising=False)
    assert settings.get_silver_dir() == settings.PROJECT_ROOT / "data_lakehouse" / "silver"

    monkeypatch.setenv("SILVER_DIR", "lake/custom-silver")
    assert settings.get_silver_dir() == settings.PROJECT_ROOT / "lake" / "custom-silver"

    absolute_path = tmp_path / "silver"
    monkeypatch.setenv("SILVER_DIR", str(absolute_path))
    assert settings.get_silver_dir() == absolute_path


def test_get_api_raw_dir_uses_bronze_path(monkeypatch, tmp_path):
    monkeypatch.delenv("API_RAW_DIR", raising=False)
    assert settings.get_api_raw_dir() == settings.PROJECT_ROOT / "data_lakehouse" / "bronze" / "api"

    monkeypatch.setenv("API_RAW_DIR", "data/raw-api")
    assert settings.get_api_raw_dir() == settings.PROJECT_ROOT / "data" / "raw-api"

    absolute_path = tmp_path / "api-raw"
    monkeypatch.setenv("API_RAW_DIR", str(absolute_path))
    assert settings.get_api_raw_dir() == absolute_path


def test_get_agritempo_dir_is_independent_of_rest_batches(monkeypatch, tmp_path):
    monkeypatch.delenv("AGRITEMPO_RAW_DIR", raising=False)
    monkeypatch.setenv("API_RAW_DIR", str(tmp_path / "api"))
    assert settings.get_agritempo_raw_dir() == settings.PROJECT_ROOT / "data_lakehouse" / "bronze" / "agritempo"

    monkeypatch.setenv("AGRITEMPO_RAW_DIR", "lake/agritempo")
    assert settings.get_agritempo_raw_dir() == settings.PROJECT_ROOT / "lake" / "agritempo"

    monkeypatch.setenv("AGRITEMPO_RAW_DIR", str(tmp_path / "agritempo"))
    assert settings.get_agritempo_raw_dir() == tmp_path / "agritempo"


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
        settings.logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
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


@pytest.mark.parametrize(
    "categoria,arquivo",
    [
        ("tratamento", "tratamento_dados.log"),
        ("insercao", "insercao_dados.log"),
    ],
)
def test_configure_logging_selects_file_by_category(
    monkeypatch, tmp_path, categoria, arquivo
):
    captured = {}
    monkeypatch.setattr(settings, "get_env", lambda key: "logs")
    monkeypatch.setattr(
        settings.logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
    )

    settings.configure_logging(tmp_path, categoria=categoria)

    assert any(handler.baseFilename.endswith(arquivo) for handler in captured["handlers"])
    for handler in captured["handlers"]:
        handler.close()


def test_pipeline_cli_help_runs_without_database_access():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "src.pipeline_orchestrator", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--apenas-gold" in result.stdout
