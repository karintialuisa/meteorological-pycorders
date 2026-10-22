"""Leitura das configurações locais do projeto."""

import logging
import os
import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine


CONFIG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIG_DIR.parent
SQL_DRIVER = "ODBC Driver 17 for SQL Server"

ENV_FILE = PROJECT_ROOT / "config" / ".env"
load_dotenv(dotenv_path=ENV_FILE)


def get_env(key: str) -> str:
    """Retorna uma variável obrigatória definida no arquivo de configuração."""
    value = os.getenv(key)
    if not value:
        raise KeyError(f"Configuracao ausente em {ENV_FILE}: {key}")
    return value


def get_path(key: str) -> Path:
    """Resolve um caminho configurado, relativo à raiz do projeto."""
    path = Path(get_env(key))
    return path if path.is_absolute() else PROJECT_ROOT / path


def get_silver_dir() -> Path:
    """Resolve SILVER_DIR ou retorna data_lakehouse/silver sob a raiz."""
    path = Path(os.getenv("SILVER_DIR") or "data_lakehouse/silver").expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def get_api_raw_dir() -> Path:
    """Resolve o destino Bronze dos lotes REST genericos."""
    path = Path(os.getenv("API_RAW_DIR") or "data_lakehouse/bronze/api").expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def get_agritempo_raw_dir() -> Path:
    """Resolve o destino Bronze do JSON cumulativo Agritempo."""
    path = Path(os.getenv("AGRITEMPO_RAW_DIR") or "data_lakehouse/bronze/agritempo").expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def create_db_engine():
    """Cria a engine SQL Server usando as configurações locais."""
    server = get_env("DB_HOST")
    port = get_env("DB_PORT")
    if "\\" not in server:
        server = f"{server},{port}"
    params = urllib.parse.quote_plus(
        f"DRIVER={{{SQL_DRIVER}}};"
        f"SERVER={server};"
        f"DATABASE={get_env('DB_NAME')};"
        f"Trusted_Connection={get_env('DB_TRUSTED_CONNECTION')};"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


def configure_logging(
    project_root: Path | None = None, categoria: str = "execucao"
) -> None:
    """Registra logs no console e no arquivo correspondente à categoria."""
    arquivos_log = {
        "execucao": "execucao_relatorio.log",
        "tratamento": "tratamento_dados.log",
        "insercao": "insercao_dados.log",
    }
    if categoria not in arquivos_log:
        raise ValueError(f"Categoria de log desconhecida: {categoria}")

    root = project_root or PROJECT_ROOT
    logs_dir = Path(get_env("LOGS_DIR"))
    if not logs_dir.is_absolute():
        logs_dir = root / logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%d-%m-%Y %H:%M",
        handlers=[
            logging.FileHandler(
                logs_dir / arquivos_log[categoria], encoding="utf-8"
            ),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )