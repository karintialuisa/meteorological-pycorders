"""Testes das primitivas de protecao de dados pessoais."""

import json
import logging
from pathlib import Path
import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

from src.database.dml.Insert_Catalogo_LGPD import inserir_catalogo_lgpd
from src.database.dml.Insert_Operadores import inserir_operadores
from src.ingestion.localizacao import Parse_localizacao_JSON as localizacao
from src.security.pii import decrypt_name, encrypt_name, hash_cpf, normalize_cpf


def _synthetic_cpf(prefix: str = "123456789") -> str:
    digits = [int(digit) for digit in prefix]

    def check_digit(values, weights):
        remainder = sum(value * weight for value, weight in zip(values, weights)) % 11
        return 0 if remainder < 2 else 11 - remainder

    first_digit = check_digit(digits, range(10, 1, -1))
    second_digit = check_digit(digits + [first_digit], range(11, 1, -1))
    return f"{prefix}{first_digit}{second_digit}"


def _seed_operator_stations(engine):
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO estado (id, codigo_ibge, sigla, nome) VALUES (1, 35, 'SP', 'Sao Paulo')")
        )
        connection.execute(
            text("INSERT INTO cidade (id, id_estado, codigo_ibge, nome) VALUES (10, 1, 3550308, 'Sao Paulo')")
        )
        connection.execute(
            text(
                "INSERT INTO estacao (id, codigo_origem, nome, status, id_cidade, id_estado) "
                "VALUES (20, 'AMB-011', 'Estacao 011', 1, 10, 1), "
                "(21, 'AMB-012', 'Estacao 012', 1, 10, 1)"
            )
        )


def test_normalize_cpf_removes_punctuation_and_checks_digits():
    cpf = _synthetic_cpf()

    assert normalize_cpf(f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}") == cpf


@pytest.mark.parametrize("cpf", ["", "123", "111.111.111-11", "123.456.789-00"])
def test_normalize_cpf_rejects_invalid_values(cpf):
    with pytest.raises(ValueError, match="CPF invalido"):
        normalize_cpf(cpf)


def test_hash_cpf_is_deterministic_and_keyed():
    cpf = _synthetic_cpf()

    first_hash = hash_cpf(cpf, "test-secret-one")

    assert first_hash == hash_cpf(f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}", "test-secret-one")
    assert first_hash != hash_cpf(cpf, "test-secret-two")
    assert len(first_hash) == 64


def test_hash_cpf_rejects_empty_key():
    with pytest.raises(ValueError, match="chave HMAC"):
        hash_cpf(_synthetic_cpf(), "")


def test_encrypt_name_can_be_decrypted_with_the_same_key():
    key = Fernet.generate_key()

    ciphertext = encrypt_name("Operador de Teste", key)

    assert "Operador de Teste" not in ciphertext
    assert decrypt_name(ciphertext, key) == "Operador de Teste"


def test_decrypt_name_rejects_another_key():
    ciphertext = encrypt_name("Operador de Teste", Fernet.generate_key())

    with pytest.raises(InvalidToken):
        decrypt_name(ciphertext, Fernet.generate_key())


def test_catalog_seed_is_idempotent_and_classifies_both_fields(banco_teste):
    assert inserir_catalogo_lgpd(banco_teste) == 2
    assert inserir_catalogo_lgpd(banco_teste) == 2

    with banco_teste.connect() as connection:
        fields = connection.execute(
            text(
                "SELECT campo_logico, coluna_armazenada, classificacao, protecao "
                "FROM catalogo_dados ORDER BY campo_logico"
            )
        ).all()

    assert fields == [
        ("cpf", "cpf_hash", "Dado pessoal", "HMAC-SHA-256"),
        (
            "nome_completo",
            "nome_completo_cifrado",
            "Dado pessoal",
            "Fernet",
        ),
    ]


def test_operator_loader_persists_only_protected_values(banco_teste):
    _seed_operator_stations(banco_teste)
    cpf = _synthetic_cpf()
    key = Fernet.generate_key().decode("ascii")
    hmac_secret = "test-hmac-secret"
    operator = {
        "cpf": cpf,
        "nome_completo": "Operador de Teste",
        "estacao_id": "AMB-011",
        "status": 1,
    }

    assert inserir_operadores(
        [operator], hmac_secret, key, banco_teste
    ) == (1, 0)

    with banco_teste.connect() as connection:
        stored = connection.execute(
            text("SELECT cpf_hash, nome_completo_cifrado FROM operadores")
        ).one()

    assert stored.cpf_hash == hash_cpf(cpf, hmac_secret)
    assert cpf not in stored.cpf_hash
    assert "Operador de Teste" not in stored.nome_completo_cifrado
    assert decrypt_name(stored.nome_completo_cifrado, key) == "Operador de Teste"


def test_operator_loader_updates_existing_operator_without_duplicates(
    banco_teste,
):
    _seed_operator_stations(banco_teste)
    cpf = _synthetic_cpf()
    key = Fernet.generate_key().decode("ascii")
    hmac_secret = "test-hmac-secret"
    assert inserir_operadores(
        [{"cpf": cpf, "nome_completo": "Nome Inicial", "estacao_id": "AMB-011"}],
        hmac_secret,
        key,
        banco_teste,
    ) == (1, 0)

    assert inserir_operadores(
        [{"cpf": cpf, "nome_completo": "Nome Atualizado", "estacao_id": "AMB-011"}],
        hmac_secret,
        key,
        banco_teste,
    ) == (0, 1)

    with banco_teste.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM operadores")
        ).scalar_one()
        ciphertext = connection.execute(
            text("SELECT nome_completo_cifrado FROM operadores")
        ).scalar_one()

    assert count == 1
    assert decrypt_name(ciphertext, key) == "Nome Atualizado"


def test_operator_loader_rolls_back_batch_when_record_is_invalid(banco_teste):
    _seed_operator_stations(banco_teste)
    key = Fernet.generate_key().decode("ascii")
    records = [
        {"cpf": _synthetic_cpf(), "nome_completo": "Operador de Teste", "estacao_id": "AMB-011"},
        {"cpf": "invalido", "nome_completo": "Outro Operador", "estacao_id": "AMB-011"},
    ]

    with pytest.raises(ValueError, match="CPF invalido"):
        inserir_operadores(records, "test-hmac-secret", key, banco_teste)

    with banco_teste.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM operadores")
        ).scalar_one()

    assert count == 0


def test_cpf_validation_checks_check_digits():
    assert normalize_cpf(_synthetic_cpf()) == _synthetic_cpf()
    with pytest.raises(ValueError, match="CPF invalido"):
        normalize_cpf("111.111.111-11")
    with pytest.raises(ValueError, match="CPF invalido"):
        normalize_cpf("12345678900")


def test_json_loader_delegates_operator_upsert_and_logs_station_changes(
    banco_teste, tmp_path, caplog
):
    _seed_operator_stations(banco_teste)
    caplog.set_level(logging.INFO)
    cpf = _synthetic_cpf()
    key = Fernet.generate_key().decode("ascii")
    path = tmp_path / "operadores.json"
    path.write_text(
        json.dumps({
            "date": "2026-10-09",
            "operadores": [{
                "cpf": cpf,
                "nome": "Operador Confidencial",
                "estacao_id": "AMB-011",
                "status": "ativo",
            }],
        }),
        encoding="utf-8",
    )

    assert localizacao.carregar_operadores(
        path, banco_teste, "test-hmac-secret", key
    ) == (1, 0)

    path.write_text(
        json.dumps({
            "date": "2026-10-10",
            "operadores": [{
                "cpf": cpf,
                "nome": "Operador Confidencial",
                "estacao_id": "AMB-012",
                "status": "inativo",
            }],
        }),
        encoding="utf-8",
    )
    assert localizacao.carregar_operadores(
        path, banco_teste, "test-hmac-secret", key
    ) == (0, 1)

    with banco_teste.connect() as connection:
        row = connection.execute(
            text("SELECT cpf_hash, nome_completo_cifrado, status, id_estacao FROM operadores")
        ).one()
    assert row.cpf_hash == hash_cpf(cpf, "test-hmac-secret")
    assert cpf not in row.cpf_hash
    assert "Operador Confidencial" not in row.nome_completo_cifrado
    assert (row.status, row.id_estacao) == (0, 21)
    assert any("Estacao do operador atualizada" in record.message for record in caplog.records)
    assert all("Operador Confidencial" not in record.message for record in caplog.records)
    assert all(cpf not in record.message for record in caplog.records)


def test_json_loader_rejects_invalid_and_incomplete_records_with_context(
    banco_teste, tmp_path, caplog
):
    _seed_operator_stations(banco_teste)
    path = tmp_path / "operadores.json"
    path.write_text(
        json.dumps({
            "date": "2026-10-09",
            "operadores": [{
                "cpf": "11111111111",
                "nome": "Nome Confidencial",
                "estacao_id": "AMB-011",
                "status": "ativo",
            }],
        }),
        encoding="utf-8",
    )

    assert localizacao.carregar_operadores(
        path, banco_teste, "test-hmac-secret", Fernet.generate_key().decode("ascii")
    ) == (0, 0)
    assert any("data_leitura=2026-10-09" in record.message for record in caplog.records)
    assert any("estacao_id=AMB-011" in record.message for record in caplog.records)
    assert all("Nome Confidencial" not in record.message for record in caplog.records)


def test_json_loader_skips_operator_when_station_is_not_registered(
    banco_teste, tmp_path, caplog
):
    path = tmp_path / "operadores.json"
    path.write_text(
        json.dumps({
            "date": "2026-10-09",
            "operadores": [{
                "cpf": _synthetic_cpf(),
                "nome": "Operador Confidencial",
                "estacao_id": "AMB-999",
                "status": "ativo",
            }],
        }),
        encoding="utf-8",
    )

    assert localizacao.carregar_operadores(
        path, banco_teste, "test-hmac-secret", Fernet.generate_key().decode("ascii")
    ) == (0, 0)
    assert any(
        "estacao no banco" in record.message.lower()
        and "operador nao inserido" in record.message.lower()
        and "cadastre a estacao primeiro" in record.message.lower()
        for record in caplog.records
    )
    assert any("data_leitura=2026-10-09" in record.message for record in caplog.records)
    assert any("estacao_id=AMB-999" in record.message for record in caplog.records)
    with banco_teste.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM operadores")).scalar_one() == 0


def test_json_loader_rejects_invalid_operator_fixtures(
    banco_teste, tmp_path, caplog
):
    _seed_operator_stations(banco_teste)
    source_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ingestion"
        / "localizacao"
        / "operadores.json"
    )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    invalid_operators = [
        operator
        for operator in source["operadores"]
        if "observacoes" in operator
    ]
    path = tmp_path / "operadores_invalidos.json"
    path.write_text(
        json.dumps({"date": source["date"], "operadores": invalid_operators}),
        encoding="utf-8",
    )

    assert len(invalid_operators) == 6
    assert localizacao.carregar_operadores(
        path, banco_teste, "test-hmac-secret", Fernet.generate_key().decode("ascii")
    ) == (0, 0)
    assert any("data_leitura=2026-09-15" in record.message for record in caplog.records)
    assert any("estacao_id=AMB-001" in record.message for record in caplog.records)
    with banco_teste.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM operadores")).scalar_one() == 0