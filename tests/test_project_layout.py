"""Verifica a estrutura por camadas sem carregar ou modificar dados reais."""

import ast
import importlib
import os
from pathlib import Path
import runpy
import subprocess
import sys

from dotenv import dotenv_values
import pytest

from src.bronze import agritempo
from src.config.settings import PROJECT_ROOT
from src.database.dml.Insert_Operadores import OPERADORES_JSON
from src.gold import analytics_statistics
from sqlserver_support import ROOT, TEST_CONFIG_PATH


def test_example_paths_exist_with_exact_case():
    example = dotenv_values(PROJECT_ROOT / ".env.example", interpolate=False)
    keys = [
        "INSERT_LOCALIZACAO", "INSERT_LEITURA_AMBIENTAL", "INSERT_LEITURA_METEOROLOGICA",
        "INGESTION_LEITURA_AMBIENTAL", "INGESTION_LEITURA_METEOROLOGICA",
        "INGESTION_LOCALIZACAO_ESTADOS", "INGESTION_LOCALIZACAO_MUNICIPIOS",
        "INGESTION_LOCALIZACAO_ESTACOES",
    ]
    for key in keys:
        value = example[key]
        assert value, key
        current = PROJECT_ROOT
        for component in Path(value).parts:
            assert component in {child.name for child in current.iterdir()}, key
            current /= component
        assert current.is_file(), key


def test_sql_support_keeps_project_root_and_finds_moved_ddl():
    assert ROOT == PROJECT_ROOT
    assert TEST_CONFIG_PATH == PROJECT_ROOT / "src" / "config" / ".env"
    assert (ROOT / "sql" / "ddl" / "create-tables.sql").is_file()
    assert (ROOT / "sql" / "ddl" / "create-legacy-measurements.sql").is_file()
    assert (ROOT / "sql" / "dql" / "consultas-essenciais.sql").is_file()


def test_data_and_analytics_destinations_match_the_layers():
    assert OPERADORES_JSON == PROJECT_ROOT / "data_lake" / "bronze" / "cadastros" / "operadores.json"
    assert OPERADORES_JSON.is_file()
    assert analytics_statistics.SAIDA_PADRAO == PROJECT_ROOT / "data_lake" / "gold" / "estatisticas_descritivas.csv"
    assert analytics_statistics.SAIDA_ZSCORE == PROJECT_ROOT / "data_lake" / "gold" / "z_scores.csv"
    for folder in ("bronze", "silver", "gold"):
        assert (PROJECT_ROOT / "data_lake" / folder).is_dir()


def test_legacy_agritempo_entry_delegates_without_collecting(monkeypatch):
    calls = []
    monkeypatch.setattr(agritempo, "main", lambda: calls.append("main") or 7)
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(PROJECT_ROOT / "Get_dados.py"), run_name="__main__")
    assert result.value.code == 7
    assert calls == ["main"]


def test_menu_entry_still_starts_and_exits_without_api_or_sql(tmp_path):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src" / "main.py")],
        cwd=tmp_path, input="4\n", capture_output=True, text=True,
        env=dict(os.environ, LOGS_DIR=str(tmp_path / "logs")),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Aplicação encerrada" in result.stdout + result.stderr


@pytest.mark.parametrize("module", [
    "src.bronze.api_ingestion",
    "src.silver.leituras.Parse_LeituraAmbiental",
    "src.silver.leituras.Parse_LeituraMetereologica",
    "src.silver.localizacao.Parse_localizacao_JSON",
    "src.database.dml.Backfill_Leituras",
    "src.database.dml.Insert_Leituras_ambiental",
    "src.database.dml.Insert_Leituras_Meteorologica",
    "src.gold.analytics_statistics",
])
def test_layer_modules_import_without_an_api_service(module):
    assert importlib.import_module(module).__name__ == module


def test_project_imports_use_one_package_identity():
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                first = node.module.split(".")[0]
                assert first not in {"database", "ingestion", "config", "security"}, path.name


@pytest.mark.parametrize("script", [
    Path("src") / "database" / "dml" / "Backfill_Leituras.py",
    Path("src") / "database" / "dml" / "Migrar_Leituras.py",
    Path("src") / "gold" / "analytics_statistics.py",
])
def test_cli_help_works_outside_repository(script, tmp_path):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / script), "--help"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout
