"""Primitivas para protecao de CPF e nome completo de operadores."""

import hashlib
import hmac
import re

from cryptography.fernet import Fernet


def normalize_cpf(cpf: str) -> str:
    """Remove a formatacao do CPF e valida seus digitos verificadores."""
    if not isinstance(cpf, str):
        raise TypeError("CPF deve ser informado como texto")

    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11 or len(set(digits)) == 1:
        raise ValueError("CPF invalido")

    numbers = [int(digit) for digit in digits]
    first_digit = _cpf_check_digit(numbers[:9], range(10, 1, -1))
    second_digit = _cpf_check_digit(numbers[:10], range(11, 1, -1))
    if numbers[-2:] != [first_digit, second_digit]:
        raise ValueError("CPF invalido")

    return digits


def _cpf_check_digit(digits: list[int], weights: range) -> int:
    remainder = sum(digit * weight for digit, weight in zip(digits, weights)) % 11
    return 0 if remainder < 2 else 11 - remainder


# 3.2 SHA-256 (item 33): HMAC-SHA-256 pseudonimiza o CPF com chave secreta.
def hash_cpf(cpf: str, secret_key: str | bytes) -> str:
    """Gera HMAC-SHA-256 deterministico para permitir comparacao do CPF."""
    key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    if not key:
        raise ValueError("A chave HMAC nao pode ser vazia")

    normalized_cpf = normalize_cpf(cpf)
    return hmac.new(key, normalized_cpf.encode("ascii"), hashlib.sha256).hexdigest()


# 3.2 LGPD (item 34): Fernet permite recuperar o nome somente com a chave autorizada.
def encrypt_name(name: str, encryption_key: str | bytes) -> str:
    """Cifra o nome usando uma chave Fernet fornecida pelo chamador."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nome completo obrigatorio")

    key = encryption_key.encode("ascii") if isinstance(encryption_key, str) else encryption_key
    return Fernet(key).encrypt(name.strip().encode("utf-8")).decode("ascii")


def decrypt_name(ciphertext: str, encryption_key: str | bytes) -> str:
    """Recupera o nome usando a chave Fernet autorizada."""
    key = encryption_key.encode("ascii") if isinstance(encryption_key, str) else encryption_key
    return Fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")