"""Persiste operadores sem armazenar CPF ou nome completo em texto claro."""

import logging
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, create_db_engine, get_env
from security.pii import encrypt_name, hash_cpf


def inserir_operadores(
    operadores: Iterable[Mapping[str, str]],
    hmac_secret: str | None = None,
    encryption_key: str | None = None,
    engine=None,
) -> tuple[int, int]:
    """Insere ou atualiza operadores e retorna (inseridos, atualizados).

    Cada registro deve conter `cpf` e `nome_completo`. Os valores originais
    existem apenas durante a chamada e nunca sao escritos em logs ou no banco.
    """
    hmac_secret = hmac_secret or get_env("HMAC_SECRET_KEY")
    encryption_key = encryption_key or get_env("ENCRYPTION_KEY")
    target_engine = engine or create_db_engine()
    find_existing = text(
        "SELECT id FROM operadores WHERE cpf_hash = :cpf_hash"
    )
    insert = text(
        "INSERT INTO operadores (cpf_hash, nome_completo_cifrado) "
        "VALUES (:cpf_hash, :nome_completo_cifrado)"
    )
    update = text(
        "UPDATE operadores SET nome_completo_cifrado = :nome_completo_cifrado "
        "WHERE id = :id"
    )

    inserted = 0
    updated = 0
    with target_engine.begin() as connection:
        for operator in operadores:
            if not isinstance(operator, Mapping):
                raise TypeError("Cada operador deve ser um mapeamento")
            if "cpf" not in operator or "nome_completo" not in operator:
                raise ValueError("Cada operador deve informar cpf e nome_completo")

            protected_values = {
                "cpf_hash": hash_cpf(operator["cpf"], hmac_secret),
                "nome_completo_cifrado": encrypt_name(
                    operator["nome_completo"], encryption_key
                ),
            }
            existing_id = connection.execute(
                find_existing, {"cpf_hash": protected_values["cpf_hash"]}
            ).scalar_one_or_none()

            if existing_id is None:
                connection.execute(insert, protected_values)
                inserted += 1
            else:
                connection.execute(
                    update, {**protected_values, "id": existing_id}
                )
                updated += 1

    logging.info(
        "Carga de operadores concluida: %s inseridos, %s atualizados.",
        inserted,
        updated,
    )
    return inserted, updated


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(
        "Informe registros de uma fonte aprovada chamando inserir_operadores()."
    )