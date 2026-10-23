"""Testa caminhos, logging e a entrada real do pipeline."""

import subprocess
import sys
from pathlib import Path
<<<<<<< HEAD
from unittest.mock import MagicMock
=======
import urllib.parse

>>>>>>> origin/feature/wagner2
import pytest

from config import settings


def test_get_env_requires_a_configured_value(monkeypatch):
    monkeypatch.delenv("REQUIRED_TEST_SETTING", raising=False)

    with pytest.raises(KeyError, match="REQUIRED_TEST_SETTING"):
        settings.get_env("REQUIRED_TEST_SETTING")


def test_project_root_and_environment_file_match_repository():
    root = Path(__file__).resolve().parents[1]
    assert settings.PROJECT_ROOT == root
    assert settings.ENV_FILE == root / "config" / ".env"


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


<<<<<<< HEAD
@pytest.fixture
def main_module(monkeypatch, tmp_path):
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    return importlib.import_module("src.main")


def test_exibir_menu_returns_trimmed_selection(main_module, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: " 2 ")

    assert main_module.exibir_menu() == "2"


def test_menu_preserves_remaining_option_numbers(main_module):
    assert set(main_module.MENU) == {"1", "2", "3", "4", "5", "6", "7"}


def test_executar_script_handles_missing_script(main_module, tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)

    assert main_module.executar_script("missing.py") is False


@pytest.mark.parametrize("return_code, expected", [(0, True), (1, False)])
def test_executar_script_streams_output_before_waiting(
    main_module, tmp_path, monkeypatch, capsys, caplog, return_code, expected
):
    script = tmp_path / "job.py"
    script.touch()
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)
    def executar(*args, **kwargs):
        kwargs["stderr"].write("failure")
        processo = MagicMock()
        processo.__enter__.return_value = processo
        processo.stdout = iter(["job output\n"])
        def aguardar():
            assert capsys.readouterr().out == "job output\n"
            return return_code
        processo.wait.side_effect = aguardar
        return processo

    monkeypatch.setattr(main_module.subprocess, "Popen", executar)

    assert main_module.executar_script("job.py") is expected
    mensagem = "Sucesso em job.py" if expected else "Falha em job.py:\nfailure"
    assert mensagem in caplog.messages
    assert mensagem.isascii()


@pytest.mark.parametrize("argumentos", [None, ["--analise", "zscore"]])
def test_executar_script_passes_optional_arguments_without_shell(
    main_module, tmp_path, monkeypatch, argumentos
):
    script = tmp_path / "job com espaco.py"
    script.touch()
    capturado = {}
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)

    def executar(comando, **opcoes):
        capturado.update(comando=comando, opcoes=opcoes)
        processo = MagicMock()
        processo.__enter__.return_value = processo
        processo.stdout = iter([])
        processo.wait.return_value = 0
        return processo

    monkeypatch.setattr(main_module.subprocess, "Popen", executar)

    assert main_module.executar_script(script.name, argumentos)
    assert capturado["comando"] == [main_module.sys.executable, str(script)] + (argumentos or [])
    assert not capturado["opcoes"].get("shell", False)


@pytest.mark.parametrize("return_code", [0, 1])
def test_executar_script_real_child_output_and_errors(
    main_module, tmp_path, monkeypatch, capsys, caplog, return_code
):
    script = tmp_path / "progress.py"
    script.write_text(
        "import sys\n"
        "print('Meteorologia: 1/1 leituras processadas', flush=True)\n"
        "print('erro do processo', file=sys.stderr)\n"
        f"sys.exit({return_code})\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main_module, "BASE_DIR", tmp_path)
    assert main_module.executar_script(script.name) is (return_code == 0)
    assert "Meteorologia: 1/1 leituras processadas" in capsys.readouterr().out
    if return_code:
        assert "Falha em progress.py:\nerro do processo" in caplog.messages


def test_main_dispatches_menu_actions_and_exits(main_module, monkeypatch):
    options = iter(["1", "4"])
    calls = []
    scripts = {
        "INSERT_LOCALIZACAO": "locations.py",
        "INSERT_LEITURA_AMBIENTAL": "water.py",
        "INSERT_LEITURA_METEOROLOGICA": "weather.py",
    }
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(main_module, "get_env", scripts.__getitem__)
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path) or True,
    )

    main_module.main()

    assert calls == [
        "locations.py",
        "src/database/dml/Insert_Parametros.py",
        "water.py",
        "weather.py",
    ]


def test_main_does_not_dispatch_invalid_option(main_module, monkeypatch, caplog):
    options = iter(["9", "4"])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path) or True,
    )

    main_module.main()

    assert calls == []
    assert "Opção inválida. Digite 1, 2, 3, 4, 5, 6 ou 7." in caplog.text


@pytest.mark.parametrize("modo", ["", "n", "s"])
def test_main_dispatches_backfill_with_period(main_module, monkeypatch, modo):
    options = iter(["7", "4"])
    answers = iter(["ambos", "2026-09-15", "2026-09-17", modo])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(
        main_module, "executar_script",
        lambda path, args: calls.append((path, args)) or True,
    )

    main_module.main()

    assert calls == [(
        "src/database/dml/Backfill_Leituras.py",
        ["--dataset", "ambos", "--data-inicio", "2026-09-15", "--data-fim", "2026-09-17"]
        + (["--reconstruir-silver"] if modo == "s" else []),
    )]


def test_main_rejects_unknown_reconstruction_mode(main_module, monkeypatch, caplog):
    options = iter(["7", "4"])
    answers = iter(["ambos", "2026-09-15", "2026-09-17", "talvez"])
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(main_module, "executar_script", lambda *_args: pytest.fail("Execucao inesperada"))
    main_module.main()
    assert "Resposta invalida" in caplog.text


def test_main_stops_etl_after_a_script_fails(main_module, monkeypatch):
    options = iter(["1", "4"])
    calls = []
    scripts = {
        "INSERT_LOCALIZACAO": "locations.py",
        "INSERT_LEITURA_AMBIENTAL": "water.py",
        "INSERT_LEITURA_METEOROLOGICA": "weather.py",
    }
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(main_module, "get_env", scripts.__getitem__)
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path) and False,
    )

    main_module.main()

    assert calls == ["locations.py"]


def test_main_stops_etl_when_parameter_seed_fails(main_module, monkeypatch):
    options = iter(["1", "4"])
    calls = []
    scripts = {
        "INSERT_LOCALIZACAO": "locations.py",
        "INSERT_LEITURA_AMBIENTAL": "water.py",
        "INSERT_LEITURA_METEOROLOGICA": "weather.py",
    }
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(main_module, "get_env", scripts.__getitem__)
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path)
        or path != "src/database/dml/Insert_Parametros.py",
    )

    main_module.main()

    assert calls == ["locations.py", "src/database/dml/Insert_Parametros.py"]


def test_main_dispatches_rest_ingestion(main_module, monkeypatch):
    options = iter(["2", "4"])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path) or True,
    )

    main_module.main()

    assert calls == ["Get_dados.py"]


# projeto_final.pdf secoes 3.2/3.3 -> features.csv IDs 32-34, 38 e 39.
def test_main_dispatches_cadastro_scripts_in_dependency_order(main_module, monkeypatch):
    options = iter(["3", "4"])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path) or True,
    )

    main_module.main()

    assert calls == [
        "src/database/dml/Insert_Parametros.py",
        "src/database/dml/Insert_Catalogo_LGPD.py",
        "src/database/dml/Insert_Operadores.py",
    ]


def test_main_stops_cadastro_after_a_script_fails(main_module, monkeypatch):
    options = iter(["3", "4"])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(
        main_module,
        "executar_script",
        lambda path: calls.append(path) and False,
    )

    main_module.main()

    assert calls == ["src/database/dml/Insert_Parametros.py"]


@pytest.mark.parametrize("sucesso", [True, False])
def test_main_dispatches_statistics_and_returns_to_menu(main_module, monkeypatch, sucesso):
    options = iter(["5", "4"])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(
        main_module, "executar_script", lambda caminho: calls.append(caminho) or sucesso
    )

    main_module.main()

    assert calls == ["src/gold/analytics_statistics.py"]


@pytest.mark.parametrize("sucesso", [True, False])
def test_main_dispatches_zscore_and_returns_to_menu(main_module, monkeypatch, sucesso):
    options = iter(["6", "4"])
    calls = []
    monkeypatch.setattr(main_module, "exibir_menu", lambda: next(options))
    monkeypatch.setattr(
        main_module, "executar_script",
        lambda caminho, argumentos=None: calls.append((caminho, argumentos)) or sucesso,
    )

    main_module.main()

    assert calls == [("src/gold/analytics_statistics.py", ["--analise", "zscore"])]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
=======
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
>>>>>>> origin/feature/wagner2
