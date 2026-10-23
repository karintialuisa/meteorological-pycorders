"""Valida a estrutura modular esperada para o projeto integrador."""

import ast
import importlib
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values
import pytest

from config.settings import PROJECT_ROOT
from src.database.dml.Insert_Operadores import OPERADORES_JSON
from src.gold import analytics_stat
from sqlserver_support import ROOT, TEST_CONFIG_PATH


def test_root_and_expected_directories_match_repository_layout():
    assert PROJECT_ROOT == Path(__file__).resolve().parents[1]
    for directory in (
        "data_lakehouse/bronze",
        "data_lakehouse/silver",
        "data_lakehouse/gold",
        "sql",
        "src/bronze",
        "src/silver",
        "src/database",
        "src/gold",
        "tests",
    ):
        assert (PROJECT_ROOT / directory).is_dir(), directory


def test_root_configuration_and_sql_artifacts_exist():
    for filename in ("config/.env", ".gitignore", "config/requirements.txt", "config/README.md"):
        assert (PROJECT_ROOT / filename).is_file(), filename
    for filename in (
        "sql/ddl_banco_relacional.sql",
        "sql/ddl/create-legacy-measurements.sql",
        "sql/queries_analiticas.sql",
        "sql/consultas-essenciais.sql",
    ):
        assert (PROJECT_ROOT / filename).is_file(), filename
    assert ROOT == PROJECT_ROOT
    assert TEST_CONFIG_PATH == PROJECT_ROOT / "config" / ".env"


def test_environment_example_points_to_existing_layer_files():
    example = dotenv_values(PROJECT_ROOT / "config" / ".env", interpolate=False)
    keys = [
        "INSERT_LOCALIZACAO",
        "INSERT_LEITURA_AMBIENTAL",
        "INSERT_LEITURA_METEOROLOGICA",
        "INGESTION_LEITURA_AMBIENTAL",
        "INGESTION_LEITURA_METEOROLOGICA",
        "INGESTION_LOCALIZACAO_ESTADOS",
        "INGESTION_LOCALIZACAO_MUNICIPIOS",
        "INGESTION_LOCALIZACAO_ESTACOES",
    ]
    for key in keys:
        value = example[key]
        assert value, key
        path = PROJECT_ROOT / value
        assert path.is_file(), key


def test_layer_data_and_analytics_outputs_are_in_data_lakehouse():
    assert OPERADORES_JSON == (
        PROJECT_ROOT / "data_lakehouse" / "bronze" / "cadastros" / "operadores.json"
    )
    assert OPERADORES_JSON.is_file()
    assert analytics_stat.SAIDA_PADRAO == (
        PROJECT_ROOT / "data_lakehouse" / "gold" / "estatisticas_descritivas.csv"
    )
    assert analytics_stat.SAIDA_ZSCORE == (
        PROJECT_ROOT / "data_lakehouse" / "gold" / "z_scores.csv"
    )
    for folder in ("bronze", "silver", "gold"):
        assert (PROJECT_ROOT / "data_lakehouse" / folder).is_dir()


def test_bronze_package_has_no_sql_scripts():
    assert not list((PROJECT_ROOT / "src" / "bronze").rglob("*.sql"))
    assert not list((PROJECT_ROOT / "data_lakehouse" / "bronze").rglob("*.sql"))


@pytest.mark.parametrize(
    "module",
    [
        "src.bronze.ingestion",
        "src.silver.quality_governance",
        "src.database.database_manager",
        "src.bronze.agritempo",
        "src.ingestion",
        "src.quality_governance",
        "src.database_manager",
        "src.analytics_stat",
        "src.pipeline_orchestrator",
        "src.silver.etl.Parse_LeituraAmbiental",
        "src.silver.etl.Parse_LeituraMetereologica",
        "src.silver.etl.Parse_localizacao_JSON",
        "src.database.dml.Backfill_Leituras",
        "src.database.dml.Insert_Leituras_ambiental",
        "src.database.dml.Insert_Leituras_Meteorologica",
        "src.gold.analytics_stat",
    ],
)
def test_layer_modules_import_without_external_services(module):
    assert importlib.import_module(module).__name__ == module


def test_source_imports_use_the_src_package_namespace():
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".", 1)[0] not in {
                    "bronze",
                    "silver",
                    "database",
                    "security",
                }, path


@pytest.mark.parametrize(
    "script",
    [
        Path("src") / "database" / "dml" / "Backfill_Leituras.py",
        Path("src") / "database" / "dml" / "Migrar_Leituras.py",
        Path("src") / "gold" / "analytics_stat.py",
    ],
)
def test_cli_help_runs_outside_repository(script, tmp_path):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()
