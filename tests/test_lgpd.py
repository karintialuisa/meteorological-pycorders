"""Testes das primitivas de protecao de dados pessoais."""

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

from src.database.dml.Insert_Catalogo_LGPD import inserir_catalogo_lgpd
from src.database.dml.Insert_Operadores import inserir_operadores
from src.security.pii import decrypt_name, encrypt_name, hash_cpf, normalize_cpf


def _synthetic_cpf(prefix: str = "123456789") -> str:
    digits = [int(digit) for digit in prefix]

    def check_digit(values, weights):
        remainder = sum(value * weight for value, weight in zip(values, weights)) % 11
        return 0 if remainder < 2 else 11 - remainder

    first_digit = check_digit(digits, range(10, 1, -1))
    second_digit = check_digit(digits + [first_digit], range(11, 1, -1))
    return f"{prefix}{first_digit}{second_digit}"


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
    cpf = _synthetic_cpf()
    key = Fernet.generate_key().decode("ascii")
    hmac_secret = "test-hmac-secret"
    operator = {"cpf": cpf, "nome_completo": "Operador de Teste"}

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
    cpf = _synthetic_cpf()
    key = Fernet.generate_key().decode("ascii")
    hmac_secret = "test-hmac-secret"
    assert inserir_operadores(
        [{"cpf": cpf, "nome_completo": "Nome Inicial"}],
        hmac_secret,
        key,
        banco_teste,
    ) == (1, 0)

    assert inserir_operadores(
        [{"cpf": cpf, "nome_completo": "Nome Atualizado"}],
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
    key = Fernet.generate_key().decode("ascii")
    records = [
        {"cpf": _synthetic_cpf(), "nome_completo": "Operador de Teste"},
        {"cpf": "invalido", "nome_completo": "Outro Operador"},
    ]

    with pytest.raises(ValueError, match="CPF invalido"):
        inserir_operadores(records, "test-hmac-secret", key, banco_teste)

    with banco_teste.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM operadores")
        ).scalar_one()

    assert count == 0