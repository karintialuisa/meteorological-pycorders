"""Carga idempotente dos cabecalhos relacionais de leitura."""

import logging
import sys
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from src.database.dialect import require_sqlserver
from src.database.dml.etl_lock import adquirir_lock_etl


# Referencia: projeto_final.pdf, secao 3.3 (Leituras - cabecalho);
# features.csv IDs 37, 38 e 40. IDs internos sao resolvidos no banco.
ORIGENS_VALIDAS = {"qualidade_agua", "leitura_meteorologica"}


class RegistroLeituraInvalidoError(ValueError):
    """Indica registro rejeitado por dados obrigatorios ou relacoes invalidas."""


def _normalizar_instante(valor: object) -> datetime:
    if hasattr(valor, "to_pydatetime"):
        valor = valor.to_pydatetime()
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.endswith("Z"):
            texto = f"{texto[:-1]}+00:00"
        try:
            valor = datetime.fromisoformat(texto)
        except ValueError as error:
            raise ValueError("data_leitura invalida") from error
    if not isinstance(valor, datetime):
        raise ValueError("data_leitura obrigatoria")
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("data_leitura deve incluir fuso horario")
    return valor.astimezone(timezone.utc)


def chave_natural_leitura(
    origem: str,
    codigo_estacao: str,
    data_leitura: object,
    id_leitura_origem: object = None,
) -> str:
    """Gera a chave estavel da fonte, mantendo as chaves legadas de replay."""
    origem_normalizada = origem.strip().lower() if isinstance(origem, str) else ""
    if origem_normalizada not in ORIGENS_VALIDAS:
        raise ValueError("origem de leitura desconhecida")

    if origem_normalizada == "qualidade_agua":
        if not isinstance(id_leitura_origem, str) or not id_leitura_origem.strip():
            raise ValueError("id_leitura_origem obrigatorio para qualidade_agua")
        return id_leitura_origem.strip()

    if not isinstance(codigo_estacao, str) or not codigo_estacao.strip():
        raise ValueError("codigo da estacao obrigatorio para leitura_meteorologica")
    instante_utc = _normalizar_instante(data_leitura)
    return f"{codigo_estacao.strip()}|{instante_utc.isoformat(timespec='microseconds')}"


def _normalizar_registro(
    leitura: Mapping[str, object], indice: int
) -> dict[str, object]:
    if not isinstance(leitura, Mapping):
        raise TypeError(f"registro no indice {indice} deve ser um mapeamento")

    origem = leitura.get("origem")
    if not isinstance(origem, str) or origem.strip().lower() not in ORIGENS_VALIDAS:
        raise ValueError(f"origem ausente ou invalida no indice {indice}")
    origem = origem.strip().lower()

    codigo_estacao = leitura.get("codigo_estacao", leitura.get("estacao_id"))
    if not isinstance(codigo_estacao, str) or not codigo_estacao.strip():
        raise ValueError(f"codigo da estacao ausente no indice {indice}")
    codigo_estacao = codigo_estacao.strip()
    if len(codigo_estacao) > 50:
        raise ValueError(f"codigo da estacao excede 50 caracteres no indice {indice}")

    instante = _normalizar_instante(leitura.get("data_leitura", leitura.get("timestamp")))
    chave = chave_natural_leitura(
        origem,
        codigo_estacao,
        instante,
        leitura.get("id_leitura_origem", leitura.get("chave_origem")),
    )
    chave_informada = leitura.get("chave_origem")
    if chave_informada is not None and str(chave_informada).strip() != chave:
        raise ValueError(f"chave_origem nao corresponde a chave natural no indice {indice}")
    if len(chave) > 150:
        raise ValueError(f"chave_origem excede 150 caracteres no indice {indice}")

    operador_hash = leitura.get("operador_cpf_hash")
    if operador_hash is not None:
        if not isinstance(operador_hash, str):
            raise ValueError(f"operador_cpf_hash invalido no indice {indice}")
        operador_hash = operador_hash.strip().lower()
        if len(operador_hash) != 64 or any(
            caractere not in "0123456789abcdef" for caractere in operador_hash
        ):
            raise ValueError(f"operador_cpf_hash invalido no indice {indice}")

    return {
        "origem": origem,
        "chave_origem": chave,
        "codigo_estacao": codigo_estacao,
        "data_leitura": instante,
        "operador_cpf_hash": operador_hash,
    }


def inserir_leituras(
    leituras: Iterable[Mapping[str, object]], engine=None, *,
    connection: Connection | None = None, strict: bool = False,
) -> tuple[int, int, int]:
    """Persiste cabecalhos; retorna (inseridos, enriquecidos, rejeitados).

    Cada registro deve informar origem, codigo_estacao/estacao_id e data_leitura.
    Agua exige id_leitura_origem; meteorologia usa estacao + instante UTC.
    operador_cpf_hash e opcional, mas quando informado deve existir em operadores.
    connection exige transacao ativa; strict propaga rejeicoes para rollback do evento.
    """
    if connection is not None and not connection.in_transaction():
        raise ValueError("connection exige transacao ativa")
    supplied_connection = connection
    target_engine = connection.engine if connection is not None else (engine or create_db_engine())
    require_sqlserver(target_engine)
    leitura_table = "dbo.leituras"
    station_table = "dbo.estacao"
    operator_table = "dbo.operadores"
    inseridos = 0
    retransmissoes = 0
    enriquecidos = 0
    rejeitados = 0

    for indice, entrada in enumerate(leituras):
        try:
            leitura = _normalizar_registro(entrada, indice)
        except (TypeError, ValueError) as error:
            logging.warning(
                "Cabecalho de leitura rejeitado: indice=%s motivo=%s",
                indice,
                str(error),
            )
            if strict:
                raise
            rejeitados += 1
            continue

        try:
            resultado_registro = "retransmissao"
            with (nullcontext(supplied_connection) if supplied_connection is not None else target_engine.begin()) as connection:
                adquirir_lock_etl(connection, "etl:leituras")
                id_estacao = connection.execute(
                    text(
                        f"SELECT id FROM {station_table} "
                        "WHERE codigo_origem = :codigo_origem"
                    ),
                    {"codigo_origem": leitura["codigo_estacao"]},
                ).scalar_one_or_none()
                if id_estacao is None:
                    raise RegistroLeituraInvalidoError("estacao nao cadastrada")

                id_operador = None
                if leitura["operador_cpf_hash"] is not None:
                    id_operador = connection.execute(
                        text(
                            f"SELECT id FROM {operator_table} "
                            "WHERE cpf_hash = :cpf_hash"
                        ),
                        {"cpf_hash": leitura["operador_cpf_hash"]},
                    ).scalar_one_or_none()
                    if id_operador is None:
                        raise RegistroLeituraInvalidoError("operador nao cadastrado")

                existente = connection.execute(
                    text(
                        f"SELECT id, id_estacao, id_operador, data_leitura "
                        f"FROM {leitura_table} "
                        "WHERE origem = :origem AND chave_origem = :chave_origem"
                    ),
                    {
                        "origem": leitura["origem"],
                        "chave_origem": leitura["chave_origem"],
                    },
                ).mappings().one_or_none()

                if existente is None:
                    connection.execute(
                        text(
                            f"INSERT INTO {leitura_table} "
                            "(origem, chave_origem, id_estacao, id_operador, data_leitura) "
                            "VALUES (:origem, :chave_origem, :id_estacao, "
                            ":id_operador, :data_leitura)"
                        ),
                        {
                            "origem": leitura["origem"],
                            "chave_origem": leitura["chave_origem"],
                            "id_estacao": id_estacao,
                            "id_operador": id_operador,
                            "data_leitura": leitura["data_leitura"],
                        },
                    )
                    resultado_registro = "inserida"
                else:
                    data_existente = _normalizar_instante(existente["data_leitura"])
                    if (
                        existente["id_estacao"] != id_estacao
                        or data_existente != leitura["data_leitura"]
                        or (
                            existente["id_operador"] is not None
                            and id_operador is not None
                            and existente["id_operador"] != id_operador
                        )
                    ):
                        raise RegistroLeituraInvalidoError(
                            "retransmissao conflitante para chave de origem existente"
                        )

                    if existente["id_operador"] is None and id_operador is not None:
                        connection.execute(
                            text(
                                f"UPDATE {leitura_table} SET id_operador = :id_operador "
                                "WHERE id = :id"
                            ),
                            {"id_operador": id_operador, "id": existente["id"]},
                        )
                        resultado_registro = "enriquecida"
            if resultado_registro == "inserida":
                inseridos += 1
            elif resultado_registro == "enriquecida":
                enriquecidos += 1
            else:
                retransmissoes += 1
        except (RegistroLeituraInvalidoError, TypeError, ValueError) as error:
            logging.warning(
                "Cabecalho de leitura rejeitado: origem=%s chave=%s motivo=%s",
                leitura["origem"],
                leitura["chave_origem"],
                str(error),
            )
            if strict:
                raise
            rejeitados += 1
        except Exception as error:
            logging.error(
                "Falha na carga do cabecalho: origem=%s chave=%s erro=%s",
                leitura["origem"],
                leitura["chave_origem"],
                type(error).__name__,
            )
            raise

    logging.info(
        "Carga de cabecalhos concluida: recebidos=%s inseridos=%s "
        "retransmissoes=%s enriquecidos=%s rejeitados=%s",
        inseridos + retransmissoes + enriquecidos + rejeitados,
        inseridos,
        retransmissoes,
        enriquecidos,
        rejeitados,
    )
    return inseridos, enriquecidos, rejeitados


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    raise SystemExit("Informe os registros chamando inserir_leituras().")