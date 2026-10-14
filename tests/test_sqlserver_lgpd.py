"""Testes opt-in de LGPD em banco SQL Server descartavel e dedicado."""

import logging
import os
import re
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url


TEST_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "config" / ".env.test"
)


def _load_test_config(path: Path) -> tuple[bool, str | None]:
    """Le apenas a configuracao de teste, sem alterar o ambiente do processo."""
    values = dotenv_values(path, interpolate=False)
    enabled = os.getenv(
        "RUN_SQLSERVER_LGPD_TESTS", values.get("RUN_SQLSERVER_LGPD_TESTS") or "0"
    )
    if enabled not in {"0", "1"}:
        raise ValueError("RUN_SQLSERVER_LGPD_TESTS deve ser 0 ou 1")
    url = os.getenv("SQLSERVER_LGPD_TEST_URL", values.get("SQLSERVER_LGPD_TEST_URL"))
    if enabled == "1" and (not url or not url.strip()):
        raise ValueError(
            "SQLSERVER_LGPD_TEST_URL obrigatoria quando RUN_SQLSERVER_LGPD_TESTS=1"
        )
    return enabled == "1", url


RUN_TESTS, TEST_URL = _load_test_config(TEST_CONFIG_PATH)


@pytest.mark.parametrize("enabled", ["0", "1"])
def test_local_test_config_is_loaded_without_exporting_environment(
    tmp_path, monkeypatch, enabled
):
    monkeypatch.delenv("RUN_SQLSERVER_LGPD_TESTS", raising=False)
    monkeypatch.delenv("SQLSERVER_LGPD_TEST_URL", raising=False)
    path = tmp_path / ".env.test"
    path.write_text(
        f"RUN_SQLSERVER_LGPD_TESTS={enabled}\nSQLSERVER_LGPD_TEST_URL=test-url\n",
        encoding="utf-8",
    )
    assert _load_test_config(path) == (enabled == "1", "test-url")
    assert "RUN_SQLSERVER_LGPD_TESTS" not in os.environ
    assert "SQLSERVER_LGPD_TEST_URL" not in os.environ


def test_process_environment_overrides_test_config(tmp_path, monkeypatch):
    path = tmp_path / ".env.test"
    path.write_text(
        "RUN_SQLSERVER_LGPD_TESTS=1\nSQLSERVER_LGPD_TEST_URL=file-url\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RUN_SQLSERVER_LGPD_TESTS", "0")
    monkeypatch.setenv("SQLSERVER_LGPD_TEST_URL", "environment-url")
    assert _load_test_config(path) == (False, "environment-url")


def test_missing_config_keeps_integration_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("RUN_SQLSERVER_LGPD_TESTS", raising=False)
    monkeypatch.delenv("SQLSERVER_LGPD_TEST_URL", raising=False)
    assert _load_test_config(tmp_path / ".env.test") == (False, None)


def test_enabled_config_without_url_fails_explicitly(tmp_path, monkeypatch):
    monkeypatch.delenv("RUN_SQLSERVER_LGPD_TESTS", raising=False)
    monkeypatch.delenv("SQLSERVER_LGPD_TEST_URL", raising=False)
    path = tmp_path / ".env.test"
    path.write_text("RUN_SQLSERVER_LGPD_TESTS=1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SQLSERVER_LGPD_TEST_URL obrigatoria"):
        _load_test_config(path)


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


def _apply_project_ddl(engine) -> None:
    ddl_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "database"
        / "ddl"
        / "create-tables.sql"
    )
    ddl = ddl_path.read_text(encoding="utf-8-sig")
    ddl = re.sub(
        r"(?im)^\s*USE\s+\[?monitoramento\]?\s*;?\s*\r?\n\s*GO\s*$",
        "",
        ddl,
        count=1,
    )
    batches = re.split(r"(?im)^\s*GO\s*$", ddl)
    with engine.begin() as connection:
        for batch in batches:
            if batch.strip():
                connection.exec_driver_sql(batch)


def _drop_project_tables(engine) -> None:
    table_names = (
        "leitura_itens",
        "leituras",
        "operadores",
        "parametros",
        "leitura_meteorologica",
        "qualidade_agua",
        "estacao",
        "cidade",
        "estado",
        "catalogo_dados",
    )
    with engine.begin() as connection:
        for table_name in table_names:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS dbo.{table_name}")


def _authorize_operator_loader(principal: str, action: str) -> bool:
    return principal == "operator-loader" and action == "decrypt_operator_name"


@pytest.mark.skipif(
    not RUN_TESTS,
    reason=(
        "Habilite RUN_SQLSERVER_LGPD_TESTS=1 em src/config/.env.test "
        "ou no ambiente para executar a integracao SQL Server."
    ),
)
def test_catalog_and_operator_protection_on_disposable_sql_server(
    caplog, catalogo_lgpd_esperado
):
    caplog.set_level(logging.INFO)

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
        if existentes:
            pytest.fail(
                "O banco descartavel precisa estar vazio para aplicar o DDL "
                f"oficial; tabelas existentes: {sorted(existentes)}."
            )

        try:
            objects_created = True
            _apply_project_ddl(engine)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO dbo.estado (codigo_ibge, sigla, nome) "
                        "VALUES (99, 'ZZ', 'Estado LGPD Teste')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO dbo.cidade (id_estado, codigo_ibge, nome) "
                        "VALUES ((SELECT id FROM dbo.estado WHERE sigla = 'ZZ'), "
                        "9999999, 'Cidade LGPD Teste')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO dbo.estacao "
                        "(codigo_origem, nome, status, id_cidade, id_estado) "
                        "VALUES ('LGPD-TEST-STATION', 'Estacao LGPD Teste', 1, "
                        "(SELECT id FROM dbo.cidade WHERE codigo_ibge = 9999999), "
                        "(SELECT id FROM dbo.estado WHERE sigla = 'ZZ'))"
                    )
                )

            catalog_query = text(
                "SELECT schema_name, tabela, campo_logico, coluna_armazenada, "
                "classificacao, finalidade, protecao, politica_acesso "
                "FROM dbo.catalogo_dados ORDER BY campo_logico"
            )
            identity_query = text(
                "SELECT id, campo_logico, criado_em "
                "FROM dbo.catalogo_dados ORDER BY campo_logico"
            )
            assert inserir_catalogo_lgpd(engine) == 2
            with engine.connect() as connection:
                assert connection.execute(catalog_query).all() == catalogo_lgpd_esperado
                original_identity = connection.execute(identity_query).all()
            assert all(row.criado_em is not None for row in original_identity)

            assert inserir_catalogo_lgpd(engine) == 2
            with engine.connect() as connection:
                assert connection.execute(catalog_query).all() == catalogo_lgpd_esperado
                assert connection.execute(identity_query).all() == original_identity

            with engine.begin() as connection:
                connection.execute(text(
                    "UPDATE dbo.catalogo_dados SET finalidade = 'Desatualizada', "
                    "politica_acesso = 'Desatualizada'"
                ))
            assert inserir_catalogo_lgpd(engine) == 2
            with engine.connect() as connection:
                assert connection.execute(catalog_query).all() == catalogo_lgpd_esperado
                assert connection.execute(identity_query).all() == original_identity

            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO dbo.catalogo_dados "
                        "(schema_name, tabela, campo_logico, coluna_armazenada, "
                        "classificacao, finalidade, protecao, politica_acesso) "
                        "SELECT schema_name, tabela, campo_logico, coluna_armazenada, "
                        "classificacao, finalidade, protecao, politica_acesso "
                        "FROM dbo.catalogo_dados WHERE campo_logico = 'cpf'"
                    ))
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text(
                        "UPDATE dbo.catalogo_dados SET classificacao = 'Nao pessoal' "
                        "WHERE campo_logico = 'cpf'"
                    ))
            with engine.connect() as connection:
                assert connection.execute(catalog_query).all() == catalogo_lgpd_esperado
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
            assert inserir_operadores(
                [operator], hmac_secret, encryption_key, engine
            ) == (0, 0)

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
            assert decrypt_name(
                stored.nome_completo_cifrado,
                encryption_key,
                principal="operator-loader",
                authorize=_authorize_operator_loader,
            ) == operator["nome_completo"]
            assert "principal=operator-loader" in caplog.text
            assert operator["nome_completo"] not in caplog.text
            assert encryption_key not in caplog.text

            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO dbo.operadores "
                            "(cpf_hash, nome_completo_cifrado, id_estacao) "
                            "VALUES (:cpf_hash, 'ciphertext', "
                            "(SELECT id FROM dbo.estacao "
                            "WHERE codigo_origem = 'LGPD-TEST-STATION'))"
                        ),
                        {"cpf_hash": stored.cpf_hash},
                    )
        finally:
            if objects_created:
                _drop_project_tables(engine)
    finally:
        engine.dispose()