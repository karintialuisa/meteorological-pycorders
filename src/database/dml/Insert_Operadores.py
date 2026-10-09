"""Persiste operadores sem armazenar CPF ou nome completo em texto claro."""

import logging
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, create_db_engine, get_env
from security.pii import decrypt_name, encrypt_name, hash_cpf


class EstacaoNaoCadastradaError(ValueError):
    """Indica que o codigo de origem nao existe no cadastro de estacoes."""


def inserir_operadores(
    operadores: Iterable[Mapping[str, object]],
    hmac_secret: str | None = None,
    encryption_key: str | None = None,
    engine=None,
    data_leitura: str | None = None,
) -> tuple[int, int]:
    """Valida, protege e persiste operadores; retorna (inseridos, atualizados).

    Cada registro deve conter `cpf` e `nome_completo`. Os valores originais
    existem apenas durante a chamada e nunca sao escritos em logs ou no banco.
    Quando `data_leitura` e informada, falhas sao registradas por operador e
    nao impedem o processamento dos demais registros do lote.
    """
    hmac_secret = hmac_secret or get_env("HMAC_SECRET_KEY")
    encryption_key = encryption_key or get_env("ENCRYPTION_KEY")
    target_engine = engine or create_db_engine()
    table_name = "dbo.operadores" if target_engine.dialect.name == "mssql" else "operadores"
    station_table = "dbo.estacao" if target_engine.dialect.name == "mssql" else "estacao"

    def station_id_for(operator):
        if not isinstance(operator, Mapping):
            return "desconhecida"
        return str(operator.get("estacao_id") or "desconhecida")

    try:
        with target_engine.connect() as connection:
            estacoes_banco = pd.read_sql(
                text(
                    f"SELECT id AS id_estacao, codigo_origem FROM {station_table}"
                ),
                connection,
            )
        station_ids = {
            str(row.codigo_origem): row.id_estacao
            for row in estacoes_banco.itertuples(index=False)
        }
    except Exception as error:
        if data_leitura is None:
            raise
        for operator in operadores:
            logging.error(
                "Falha ao consultar estacoes para operador: data_leitura=%s "
                "estacao_id=%s erro=%s",
                data_leitura,
                station_id_for(operator),
                type(error).__name__,
            )
        return 0, 0

    inserted = 0
    updated = 0

    def persist(connection, operator):
        nonlocal inserted, updated
        if not isinstance(operator, Mapping):
            raise TypeError("Cada operador deve ser um mapeamento")
        if "cpf" not in operator or "nome_completo" not in operator:
            raise ValueError("Cada operador deve informar cpf e nome_completo")
        station_code = str(operator.get("estacao_id") or "").strip()
        if not station_code or station_code not in station_ids:
            raise EstacaoNaoCadastradaError(station_code)
        station_id = station_ids[station_code]

        protected_values = {
            "cpf_hash": hash_cpf(operator["cpf"], hmac_secret),
            "nome_completo_cifrado": encrypt_name(
                operator["nome_completo"], encryption_key
            ),
        }
        existing = connection.execute(
            text(
                "SELECT id, nome_completo_cifrado, status, id_estacao "
                f"FROM {table_name} WHERE cpf_hash = :cpf_hash"
            ),
            {"cpf_hash": protected_values["cpf_hash"]},
        ).mappings().one_or_none()

        if existing is None:
            connection.execute(
                text(
                    f"INSERT INTO {table_name} "
                    "(cpf_hash, nome_completo_cifrado, status, id_estacao) "
                    "VALUES (:cpf_hash, :nome_completo_cifrado, :status, :id_estacao)"
                ),
                {
                    **protected_values,
                    "status": operator.get("status"),
                    "id_estacao": station_id,
                },
            )
            inserted += 1
            return

        changes = {}
        if decrypt_name(existing["nome_completo_cifrado"], encryption_key) != operator["nome_completo"].strip():
            changes["nome_completo_cifrado"] = protected_values["nome_completo_cifrado"]
        new_status = operator.get("status")
        if new_status is not None and new_status != existing["status"]:
            changes["status"] = new_status
        if station_id != existing["id_estacao"]:
            changes["id_estacao"] = station_id

        if changes:
            assignments = ", ".join(f"{column} = :{column}" for column in changes)
            connection.execute(
                text(f"UPDATE {table_name} SET {assignments} WHERE id = :id"),
                {**changes, "id": existing["id"]},
            )
            updated += 1
            if "id_estacao" in changes:
                logging.info(
                    "Estacao do operador atualizada: data_leitura=%s "
                    "estacao_id_anterior=%s estacao_id=%s",
                    data_leitura or "desconhecida",
                    existing["id_estacao"],
                    changes["id_estacao"],
                )

    if data_leitura is None:
        with target_engine.begin() as connection:
            for operator in operadores:
                persist(connection, operator)
    else:
        for operator in operadores:
            try:
                with target_engine.begin() as connection:
                    persist(connection, operator)
            except EstacaoNaoCadastradaError:
                logging.error(
                    "Nao foi possivel identificar a estacao no banco; "
                    "operador nao inserido. Cadastre a estacao primeiro: "
                    "data_leitura=%s estacao_id=%s",
                    data_leitura,
                    station_id_for(operator),
                )
            except Exception as error:
                logging.error(
                    "Falha ao processar operador: data_leitura=%s estacao_id=%s erro=%s",
                    data_leitura,
                    station_id_for(operator),
                    type(error).__name__,
                )

    logging.info(
        "Carga de operadores concluida: data_leitura=%s inseridos=%s atualizados=%s",
        data_leitura or "desconhecida",
        inserted,
        updated,
    )
    return inserted, updated


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(
        "Informe registros de uma fonte aprovada chamando inserir_operadores()."
    )