"""Testes opt-in de LGPD em banco SQL Server descartavel e dedicado."""

import os
import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


TEST_URL = os.getenv("SQLSERVER_LGPD_TEST_URL")
RUN_TESTS = os.getenv("RUN_SQLSERVER_LGPD_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not (RUN_TESTS and TEST_URL),
    reason=(
        "Defina RUN_SQLSERVER_LGPD_TESTS=1 e SQLSERVER_LGPD_TEST_URL "
        "para habilitar os testes opt-in."
    ),
)


def _cpf_sintetico() -> str:
    digits = [int(char) for char in "123456789"]

    def check_digit(values, weights):
        remainder = sum(value * weight for value, weight in zip(values, weights)) % 11
        return 0 if remainder < 2 else 11 - remainder

    first = check_digit(digits, range(10, 1, -1))
    second = check_digit(digits + [first], range(11, 1, -1))
    return f"123456789{first}{second}"


def _database_name(connection_url: str) -> str:
    url = make_url(connection_url)
    if url.database:
        return url.database

    odbc_connect = url.query.get("odbc_connect", "")
    match = re.search(
        r"(?:^|;)\s*(?:DATABASE|INITIAL CATALOG)\s*=\s*([^;]+)",
        odbc_connect,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def test_catalog_and_operator_protection_on_disposable_sql_server():
    from cryptography.fernet import Fernet

    from src.database.dml.Insert_Catalogo_LGPD import inserir_catalogo_lgpd
    from src.database.dml.Insert_Operadores import inserir_operadores
    from src.security.pii import decrypt_name, hash_cpf

    database = _database_name(TEST_URL)
    if not re.search(r"_(test|tests|disposable|scratch)$", database, re.IGNORECASE):
        pytest.fail(
            "O banco SQL Server opt-in precisa ter sufixo _test, _tests, "
            "_disposable ou _scratch; nenhum objeto foi alterado."
        )

    engine = create_engine(TEST_URL)
    table_names = {"catalogo_dados", "estacao", "operadores"}
    objects_created = False
    try:
        with engine.connect() as connection:
            existentes = set(
                connection.execute(
                    text(
                        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                        "WHERE TABLE_SCHEMA = 'dbo'"
                    )
                ).scalars()
            )
        ocupadas = table_names & existentes
        if ocupadas:
            pytest.fail(
                "O banco descartavel ja contem tabelas que este teste precisa "
                f"criar ({sorted(ocupadas)}); nenhum objeto foi alterado."
            )

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE dbo.estacao ("
                        "id BIGINT IDENTITY(1,1) PRIMARY KEY, "
                        "codigo_origem VARCHAR(50) NOT NULL UNIQUE)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE TABLE dbo.catalogo_dados ("
                        "id BIGINT IDENTITY(1,1) PRIMARY KEY, "
                        "schema_name VARCHAR(128) NOT NULL, "
                        "tabela VARCHAR(128) NOT NULL, "
                        "campo_logico VARCHAR(128) NOT NULL, "
                        "coluna_armazenada VARCHAR(128) NOT NULL, "
                        "classificacao VARCHAR(50) NOT NULL, "
                        "finalidade VARCHAR(300) NOT NULL, "
                        "protecao VARCHAR(100) NOT NULL, "
                        "politica_acesso VARCHAR(300) NOT NULL, "
                        "criado_em DATETIMEOFFSET NOT NULL "
                        "DEFAULT SYSDATETIMEOFFSET(), "
                        "CONSTRAINT uq_lgpd_test_catalog UNIQUE "
                        "(schema_name, tabela, campo_logico), "
                        "CONSTRAINT ck_lgpd_test_classification "
                        "CHECK (classificacao = 'Dado pessoal'))"
                    )
                )
                connection.execute(
                    text(
                        "CREATE TABLE dbo.operadores ("
                        "id BIGINT IDENTITY(1,1) PRIMARY KEY, "
                        "cpf_hash CHAR(64) NOT NULL UNIQUE, "
                        "nome_completo_cifrado VARCHAR(MAX) NOT NULL, "
                        "status BIT NULL, id_estacao BIGINT NOT NULL, "
                        "criado_em DATETIMEOFFSET NOT NULL "
                        "DEFAULT SYSDATETIMEOFFSET(), "
                        "CONSTRAINT fk_lgpd_test_operator_station "
                        "FOREIGN KEY (id_estacao) REFERENCES dbo.estacao(id))"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO dbo.estacao (codigo_origem) "
                        "VALUES ('LGPD-TEST-STATION')"
                    )
                )
            objects_created = True

            assert inserir_catalogo_lgpd(engine) == 2
            assert inserir_catalogo_lgpd(engine) == 2
            cpf = _cpf_sintetico()
            hmac_secret = "sqlserver-disposable-test-secret"
            encryption_key = Fernet.generate_key().decode("ascii")
            operator = {
                "cpf": cpf,
                "nome_completo": "Operador Sintetico de Teste",
                "estacao_id": "LGPD-TEST-STATION",
                "status": 1,
            }

            assert inserir_operadores(
                [operator], hmac_secret, encryption_key, engine
            ) == (1, 0)

            with engine.connect() as connection:
                catalog_count = connection.execute(
                    text("SELECT COUNT(*) FROM dbo.catalogo_dados")
                ).scalar_one()
                stored = connection.execute(
                    text(
                        "SELECT cpf_hash, nome_completo_cifrado "
                        "FROM dbo.operadores"
                    )
                ).one()

            assert catalog_count == 2
            assert stored.cpf_hash == hash_cpf(cpf, hmac_secret)
            assert cpf not in stored.cpf_hash
            assert operator["nome_completo"] not in stored.nome_completo_cifrado
            assert decrypt_name(stored.nome_completo_cifrado, encryption_key) == operator[
                "nome_completo"
            ]
        finally:
            if objects_created:
                with engine.begin() as connection:
                    connection.execute(text("DROP TABLE dbo.operadores"))
                    connection.execute(text("DROP TABLE dbo.catalogo_dados"))
                    connection.execute(text("DROP TABLE dbo.estacao"))
    finally:
        engine.dispose()