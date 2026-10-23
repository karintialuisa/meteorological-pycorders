"""Configuracao e lifecycle exclusivos da homologacao SQL Server."""

import os
import re
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
TEST_CONFIG_PATH = ROOT / "config" / ".env"


def load_test_config(path: Path) -> tuple[bool, str | None]:
    values = dotenv_values(path, interpolate=False)
    enabled = os.getenv("RUN_SQLSERVER_LGPD_TESTS", values.get("RUN_SQLSERVER_LGPD_TESTS") or "0")
    if enabled not in {"0", "1"}:
        raise ValueError("RUN_SQLSERVER_LGPD_TESTS deve ser 0 ou 1")
    url = os.getenv("SQLSERVER_LGPD_TEST_URL", values.get("SQLSERVER_LGPD_TEST_URL"))
    if enabled == "1" and (not url or not url.strip()):
        raise ValueError("SQLSERVER_LGPD_TEST_URL obrigatoria quando RUN_SQLSERVER_LGPD_TESTS=1")
    return enabled == "1", url


def database_name(connection_url: str) -> str:
    url = make_url(connection_url)
    if url.database:
        return url.database
    match = re.search(
        r"(?:^|;)\s*(?:DATABASE|INITIAL CATALOG)\s*=\s*([^;]+)",
        url.query.get("odbc_connect", ""), re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def apply_ddl(engine, filename: str = "ddl_banco_relacional.sql") -> None:
    caminho = (
        ROOT / "sql" / filename
        if filename == "ddl_banco_relacional.sql"
        else ROOT / "sql" / "ddl" / filename
    )
    ddl = caminho.read_text(encoding="utf-8-sig")
    ddl = re.sub(
        r"(?im)^\s*USE\s+\[?monitoramento\]?\s*;?\s*\r?\n\s*GO\s*$", "", ddl, count=1
    )
    if re.search(r"(?im)^\s*USE\s+", ddl):
        raise ValueError("DDL de teste nao pode trocar de banco")
    with engine.begin() as connection:
        for batch in re.split(r"(?im)^\s*GO\s*$", ddl):
            if batch.strip():
                connection.exec_driver_sql(batch)


def drop_project_tables(engine) -> None:
    with engine.begin() as connection:
        for table in (
            "leitura_itens", "leituras", "legado_leitura_meteorologica",
            "legado_qualidade_agua", "leitura_meteorologica", "qualidade_agua",
            "operadores", "parametros", "estacao", "cidade", "estado", "catalogo_dados",
        ):
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS dbo.{table}")


RUN_TESTS, TEST_URL = load_test_config(TEST_CONFIG_PATH)


@contextmanager
def disposable_engine(*, legacy: bool = False, initialize: bool = True):
    if not RUN_TESTS or not TEST_URL:
        raise ValueError("homologacao SQL Server nao habilitada")
    expected_database = database_name(TEST_URL)
    if not re.search(r"_(test|tests|disposable|scratch)$", expected_database, re.IGNORECASE):
        raise ValueError("banco de homologacao exige sufixo descartavel; nenhum objeto alterado")
    engine = create_engine(TEST_URL, pool_pre_ping=True)
    created = False
    try:
        with engine.connect() as lock_connection:
            database, server = lock_connection.execute(text(
                "SELECT DB_NAME(), CONVERT(nvarchar(128),SERVERPROPERTY('ServerName'))"
            )).one()
            if database.casefold() != expected_database.casefold():
                raise ValueError("banco conectado diverge do alvo descartavel")
            print(f"SQL Server alvo: {server} / {database}")
            result = lock_connection.execute(text(
                "DECLARE @result int; EXEC @result=sys.sp_getapplock "
                "@Resource='pytest:project-ddl', @LockMode='Exclusive', "
                "@LockOwner='Session', @LockTimeout=60000; SELECT @result;"
            )).scalar_one()
            if result < 0:
                raise RuntimeError("nao foi possivel reservar lifecycle SQL Server")
            lock_connection.commit()
            try:
                tables = lock_connection.execute(text(
                    "SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('dbo')"
                )).scalars().all()
                if tables:
                    raise ValueError(f"banco descartavel precisa estar vazio: {tables}")
                created = True
                if initialize:
                    apply_ddl(engine)
                if legacy:
                    apply_ddl(engine, "create-legacy-measurements.sql")
                yield engine
            finally:
                if created:
                    drop_project_tables(engine)
                    with engine.connect() as connection:
                        assert connection.execute(text(
                            "SELECT COUNT(*) FROM sys.tables WHERE schema_id=SCHEMA_ID('dbo')"
                        )).scalar_one() == 0
                lock_connection.execute(text(
                    "EXEC sys.sp_releaseapplock @Resource='pytest:project-ddl', @LockOwner='Session'"
                ))
                lock_connection.commit()
    finally:
        engine.dispose()
