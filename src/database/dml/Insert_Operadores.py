"""Persiste operadores sem armazenar CPF ou nome completo em texto claro."""

import json
import logging
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import PROJECT_ROOT, configure_logging, create_db_engine, get_env
from src.database.dialect import require_sqlserver
from src.silver.security.pii import decrypt_name, encrypt_name, hash_cpf

# Referencia: projeto_final.pdf, secao 1 (Operadores - origem dos dados), features.csv ID 10.
# Referencia: projeto_final.pdf, secao 3.3 (Operadores - tabela cadastral), ID 38.
# LGPD dos operadores: projeto_final.pdf, secao 3.2; features.csv IDs 32-34 e 38.


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
    _validar_chaves_operador(hmac_secret, encryption_key)
    target_engine = engine or create_db_engine()
    require_sqlserver(target_engine)
    table_name = "dbo.operadores"
    station_table = "dbo.estacao"

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
        if decrypt_name(
            existing["nome_completo_cifrado"],
            encryption_key,
            principal="operator-loader",
            authorize=_autorizar_descriptografia_loader,
        ) != operator["nome_completo"].strip():
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


# projeto_final.pdf secao 3.2 LGPD -> features.csv IDs 33 e 34.
def _validar_chaves_operador(hmac_secret: str, encryption_key: str) -> None:
    for nome, valor in (
        ("HMAC_SECRET_KEY", hmac_secret),
        ("ENCRYPTION_KEY", encryption_key),
    ):
        if not valor.strip() or valor.strip().casefold().startswith("replace-with"):
            raise ValueError(f"{nome} deve conter um segredo real, não um placeholder")


def _autorizar_descriptografia_loader(principal: str, action: str) -> bool:
    """Permite a leitura do nome somente ao fluxo interno de carga."""
    return principal == "operator-loader" and action == "decrypt_operator_name"


OPERADORES_JSON = (
    PROJECT_ROOT / "data_lakehouse" / "bronze" / "cadastros" / "operadores.json"
)
_STATUS_ATIVO = {"1", "ativo", "ativa", "active", "true"}
_STATUS_INATIVO = {"0", "inativo", "inativa", "inactive", "false", "desativado"}


def _normalizar_status(status: object) -> str:
    if isinstance(status, bool):
        return str(int(status))
    return "" if status is None else str(status).strip().lower()


# projeto_final.pdf secao 3.3 (Operadores - tabela cadastral) -> features.csv IDs 10 e 38.
def _converter_status_operador(status: object) -> int:
    """Retorna 1 somente para status ativo; qualquer outro valor grava 0."""
    return int(_normalizar_status(status) in _STATUS_ATIVO)


def _status_reconhecido(status: object) -> bool:
    return _normalizar_status(status) in (_STATUS_ATIVO | _STATUS_INATIVO)


# projeto_final.pdf secoes 3.2 (LGPD) e 3.3 -> features.csv IDs 32-34 e 38; ETL na camada DML.
def carregar_operadores(
    path_arquivo: str | Path | None = None,
    engine=None,
    hmac_secret: str | None = None,
    encryption_key: str | None = None,
) -> tuple[int, int]:
    """Le operadores do JSON, normaliza o contrato e persiste via inserir_operadores."""
    source_path = Path(path_arquivo) if path_arquivo else OPERADORES_JSON
    source_date = "desconhecida"
    try:
        with open(source_path, "r", encoding="utf-8") as arquivo:
            payload = json.load(arquivo)
        source_date = str(payload.get("date") or "desconhecida")
        operators = payload.get("operadores")
        if not isinstance(operators, list):
            raise ValueError("lista de operadores ausente ou invalida")
    except (OSError, json.JSONDecodeError, AttributeError, ValueError) as error:
        logging.error(
            "Falha ao ler operadores: data_leitura=%s estacao_id=desconhecida erro=%s",
            source_date,
            type(error).__name__,
        )
        return 0, 0

    normalized_operators = []
    for operator in operators:
        station_code = (
            str(operator.get("estacao_id") or "").strip()
            if isinstance(operator, dict)
            else ""
        )
        try:
            if not isinstance(operator, dict):
                raise ValueError("registro invalido")
            if not station_code:
                logging.error(
                    "Estacao nao informada; cadastre-a antes do operador: "
                    "data_leitura=%s estacao_id=desconhecida",
                    source_date,
                )
                continue

            status = operator.get("status")
            if not _status_reconhecido(status):
                logging.warning(
                    "Status de operador ausente ou nao reconhecido; gravado como "
                    "inativo (0): data_leitura=%s estacao_id=%s",
                    source_date,
                    station_code,
                )
            normalized_operators.append({
                **operator,
                "nome_completo": operator.get("nome"),
                "status": _converter_status_operador(status),
            })
        except Exception as error:
            logging.error(
                "Falha no ETL do operador: data_leitura=%s estacao_id=%s erro=%s",
                source_date,
                station_code or "desconhecida",
                type(error).__name__,
            )

    return inserir_operadores(
        normalized_operators,
        hmac_secret=hmac_secret,
        encryption_key=encryption_key,
        engine=engine,
        data_leitura=source_date,
    )


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    carregar_operadores()