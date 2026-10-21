"""Primitivas para protecao de CPF e nome completo de operadores."""

import hashlib
import hmac
import logging
import re
from collections.abc import Callable

from cryptography.fernet import Fernet, InvalidToken


_NAME_DECRYPTION_ACTION = "decrypt_operator_name"
_PRINCIPAL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_security_logger = logging.getLogger("security.pii")


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


# Referencia: projeto_final.pdf, secao 3.2 (anonimizacao irreversivel);
# features.csv ID 33. HMAC e pseudonimizacao, nao anonimizacao juridica.
def hash_cpf(cpf: str, secret_key: str | bytes) -> str:
    """Gera HMAC-SHA-256 deterministico para permitir comparacao do CPF."""
    key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    if not key:
        raise ValueError("A chave HMAC nao pode ser vazia")

    normalized_cpf = normalize_cpf(cpf)
    return hmac.new(key, normalized_cpf.encode("ascii"), hashlib.sha256).hexdigest()


# Referencia: projeto_final.pdf, secao 3.2 (criptografia reversivel);
# features.csv ID 34. Recuperacao exige a chave Fernet autorizada.
def encrypt_name(name: str, encryption_key: str | bytes) -> str:
    """Cifra o nome usando uma chave Fernet fornecida pelo chamador."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nome completo obrigatorio")

    key = encryption_key.encode("ascii") if isinstance(encryption_key, str) else encryption_key
    return Fernet(key).encrypt(name.strip().encode("utf-8")).decode("ascii")


def decrypt_name(
    ciphertext: str,
    encryption_key: str | bytes,
    *,
    principal: str,
    authorize: Callable[[str, str], bool],
) -> str:
    """Recupera o nome após autorização explícita e audita a tentativa.

    O chamador fornece o principal autenticado e a política de autorização da
    aplicação. O principal deve ser um identificador técnico, não PII.
    """
    if not isinstance(principal, str) or not _PRINCIPAL_PATTERN.fullmatch(principal):
        _security_logger.warning(
            "Descriptografia de nome negada: principal=invalid action=%s outcome=denied",
            _NAME_DECRYPTION_ACTION,
        )
        raise PermissionError("Principal invalido para descriptografia")

    if not authorize(principal, _NAME_DECRYPTION_ACTION):
        _security_logger.warning(
            "Descriptografia de nome negada: principal=%s action=%s outcome=denied",
            principal,
            _NAME_DECRYPTION_ACTION,
        )
        raise PermissionError("Principal sem autorizacao para descriptografia")

    key = encryption_key.encode("ascii") if isinstance(encryption_key, str) else encryption_key
    try:
        name = Fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        _security_logger.warning(
            "Descriptografia de nome autorizada mas malsucedida: "
            "principal=%s action=%s outcome=failed",
            principal,
            _NAME_DECRYPTION_ACTION,
        )
        raise

    _security_logger.info(
        "Descriptografia de nome autorizada: principal=%s action=%s outcome=success",
        principal,
        _NAME_DECRYPTION_ACTION,
    )
    return name