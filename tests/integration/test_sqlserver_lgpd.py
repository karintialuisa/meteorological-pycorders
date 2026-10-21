"""Testes opt-in de LGPD em banco SQL Server descartavel e dedicado."""

import json
import logging
import os
import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlserver_support import (
    TEST_CONFIG_PATH, load_test_config as _load_test_config,
    database_name as _database_name, apply_ddl as _apply_project_ddl,
    drop_project_tables as _drop_project_tables, disposable_engine,
)


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


def _cpf_sintetico(prefix: str = "123456789") -> str:
    digits = [int(char) for char in prefix]

    def check_digit(values, weights):
        remainder = sum(value * weight for value, weight in zip(values, weights)) % 11
        return 0 if remainder < 2 else 11 - remainder

    first = check_digit(digits, range(10, 1, -1))
    second = check_digit(digits + [first], range(11, 1, -1))
    return f"{prefix}{first}{second}"


def _authorize_operator_loader(principal: str, action: str) -> bool:
    return principal == "operator-loader" and action == "decrypt_operator_name"


@pytest.fixture
def lgpd_engine():
    with disposable_engine(initialize=False) as engine:
        yield engine


def _assert_operator_schema(engine):
    with engine.connect() as connection:
        columns = connection.execute(text(
            "SELECT c.name, t.name, c.max_length, c.is_nullable, c.is_identity "
            "FROM sys.columns c JOIN sys.types t ON c.user_type_id = t.user_type_id "
            "WHERE c.object_id = OBJECT_ID('dbo.operadores') ORDER BY c.column_id"
        )).all()
        assert columns == [
            ("id", "bigint", 8, False, True),
            ("cpf_hash", "char", 64, False, False),
            ("nome_completo_cifrado", "varchar", -1, False, False),
            ("status", "bit", 1, True, False),
            ("id_estacao", "bigint", 8, False, False),
            ("criado_em", "datetimeoffset", 10, False, False),
        ]
        keys = connection.execute(text(
            "SELECT i.is_primary_key, i.is_unique, i.is_disabled, c.name "
            "FROM sys.indexes i JOIN sys.index_columns ic "
            "ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
            "JOIN sys.columns c ON c.object_id = ic.object_id "
            "AND c.column_id = ic.column_id "
            "WHERE i.object_id = OBJECT_ID('dbo.operadores') AND ic.key_ordinal > 0"
        )).all()
        assert sorted(keys) == sorted([
            (True, True, False, "id"), (False, True, False, "cpf_hash"),
        ])
        fk = connection.execute(text(
            "SELECT COL_NAME(f.parent_object_id, fc.parent_column_id), "
            "OBJECT_NAME(f.referenced_object_id), "
            "COL_NAME(f.referenced_object_id, fc.referenced_column_id), "
            "f.is_disabled, f.is_not_trusted, f.delete_referential_action_desc "
            "FROM sys.foreign_keys f JOIN sys.foreign_key_columns fc "
            "ON fc.constraint_object_id = f.object_id "
            "WHERE f.parent_object_id = OBJECT_ID('dbo.operadores')"
        )).all()
        assert fk == [("id_estacao", "estacao", "id", False, False, "CASCADE")]
        check = connection.execute(text(
            "SELECT definition, is_disabled, is_not_trusted "
            "FROM sys.check_constraints "
            "WHERE parent_object_id = OBJECT_ID('dbo.operadores')"
        )).one()
        assert "len([cpf_hash])=(64)" in check.definition.lower().replace(" ", "")
        assert not check.is_disabled and not check.is_not_trusted
        default = connection.execute(text(
            "SELECT d.definition FROM sys.default_constraints d "
            "JOIN sys.columns c ON c.object_id = d.parent_object_id "
            "AND c.column_id = d.parent_column_id "
            "WHERE d.parent_object_id = OBJECT_ID('dbo.operadores') "
            "AND c.name = 'criado_em'"
        )).scalar_one()
        assert "sysdatetimeoffset()" in default.lower()

    for values in [
        {"hash": None, "name": "ciphertext", "station": 1},
        {"hash": "f" * 64, "name": None, "station": 1},
        {"hash": "f" * 64, "name": "ciphertext", "station": None},
        {"hash": "f" * 64, "name": "ciphertext", "station": -1},
        {"hash": "short", "name": "ciphertext", "station": 1},
    ]:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO dbo.operadores "
                    "(cpf_hash, nome_completo_cifrado, id_estacao) "
                    "VALUES (:hash, :name, :station)"
                ), values)


def _assert_operator_json_loading(engine, tmp_path, caplog):
    from cryptography.fernet import Fernet
    from src.database.dml.Insert_Operadores import carregar_operadores
    from src.silver.security.pii import decrypt_name, hash_cpf

    key = Fernet.generate_key().decode("ascii")
    secret = "json-operator-test-secret"
    cpf = _cpf_sintetico("987654321")
    path = tmp_path / "operadores.json"
    operator = {
        "cpf": cpf, "nome": "Operador JSON Sintetico",
        "estacao_id": "LGPD-TEST-STATION", "status": "ativo",
    }
    query = text(
        "SELECT id, cpf_hash, nome_completo_cifrado, status, id_estacao, criado_em "
        "FROM dbo.operadores WHERE cpf_hash = :hash"
    )

    def load(records):
        path.write_text(
            json.dumps({"date": "2026-10-14", "operadores": records}),
            encoding="utf-8",
        )
        return carregar_operadores(path, engine, secret, key)

    def stored():
        with engine.connect() as connection:
            return connection.execute(query, {"hash": hash_cpf(cpf, secret)}).one()

    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO dbo.estacao "
            "(codigo_origem, nome, status, id_cidade, id_estado) "
            "SELECT 'LGPD-SECOND-STATION', 'Segunda Estacao Teste', 1, "
            "id_cidade, id_estado FROM dbo.estacao "
            "WHERE codigo_origem = 'LGPD-TEST-STATION'"
        ))
    assert load([operator]) == (1, 0)
    initial = stored()
    assert len(initial.cpf_hash) == 64
    assert initial.status == 1 and initial.criado_em is not None
    with engine.connect() as connection:
        stations = dict(connection.execute(text(
            "SELECT codigo_origem, id FROM dbo.estacao"
        )).all())
    assert initial.id_estacao == stations[operator["estacao_id"]]
    assert load([operator]) == (0, 0)
    assert stored() == initial

    updated = {**operator, "nome": "Nome JSON Atualizado",
               "status": "inativo", "estacao_id": "LGPD-SECOND-STATION"}
    assert load([updated]) == (0, 1)
    after = stored()
    assert (after.id, after.cpf_hash, after.criado_em) == (
        initial.id, initial.cpf_hash, initial.criado_em,
    )
    assert after.status == 0
    assert after.id_estacao == stations["LGPD-SECOND-STATION"]
    assert after.nome_completo_cifrado != initial.nome_completo_cifrado
    assert decrypt_name(
        after.nome_completo_cifrado, key, principal="operator-loader",
        authorize=_authorize_operator_loader,
    ) == updated["nome"]

    for status in (None, "desconhecido"):
        assert load([
            {**updated, "cpf": "123", "status": "ativo"},
            {**updated, "nome": None, "status": "ativo"},
            {**updated, "estacao_id": "UNKNOWN", "status": "ativo"},
            {**updated, "status": status},
        ]) == (0, 0)
        assert stored() == after
    assert any(record.levelno == logging.ERROR for record in caplog.records)
    assert "Status de operador ausente ou nao reconhecido" in caplog.text
    assert "estacao_id=UNKNOWN" in caplog.text
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM dbo.operadores WHERE cpf_hash = :hash"
        ), {"hash": initial.cpf_hash}).scalar_one() == 1
    for value in (cpf, operator["nome"], updated["nome"], key, secret,
                  initial.nome_completo_cifrado, after.nome_completo_cifrado):
        assert value not in caplog.text


@pytest.mark.skipif(
    not RUN_TESTS,
    reason=(
        "Habilite RUN_SQLSERVER_LGPD_TESTS=1 em src/config/.env "
        "ou no ambiente para executar a integracao SQL Server."
    ),
)
def test_catalog_and_operator_protection_on_disposable_sql_server(
    caplog, catalogo_lgpd_esperado, tmp_path, lgpd_engine
):
    caplog.set_level(logging.INFO)

    from cryptography.fernet import Fernet

    from src.database.dml.Insert_Catalogo_LGPD import inserir_catalogo_lgpd
    from src.database.dml.Insert_Operadores import inserir_operadores
    from src.silver.security.pii import decrypt_name, hash_cpf

    database = _database_name(TEST_URL)
    if not re.search(r"_(test|tests|disposable|scratch)$", database, re.IGNORECASE):
        pytest.fail(
            "O banco SQL Server opt-in precisa ter sufixo _test, _tests, "
            "_disposable ou _scratch; nenhum objeto foi alterado."
        )

    engine = lgpd_engine
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
            _assert_operator_schema(engine)
            _assert_operator_json_loading(engine, tmp_path, caplog)
        finally:
            if objects_created:
                _drop_project_tables(engine)
    finally:
        engine.dispose()