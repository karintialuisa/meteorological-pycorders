"""Carga idempotente dos parametros observados em cada leitura."""

import logging
import sys
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from src.database.dialect import require_sqlserver
from src.database.dml.Insert_Leituras import (
    ORIGENS_VALIDAS,
    chave_natural_leitura,
)
from src.database.dml.etl_lock import adquirir_lock_etl


# Referencia: projeto_final.pdf, secao 3.3 (associacao N:M);
# features.csv IDs 39-41. Codigos de parametro e cabecalhos sao resolvidos no banco.
_COMPRIMENTOS_MAXIMOS = {"chave_origem": 150, "codigo_parametro": 50}
LIMITES_NUMERICOS = {
    "TEMP_AGUA": (0, 50), "TEMP_AR": (-50, 60),
    "PH": (0, 14), "UMIDADE": (0, 100),
    "OD": (0, None), "COND_ELETRICA": (0, None),
    "TURBIDEZ": (0, None), "CHUVA": (0, None), "VENTO": (0, None),
}


class ItemLeituraInvalidoError(ValueError):
    """Indica item rejeitado por dados ausentes ou referencias inexistentes."""


def _normalizar_item(item: Mapping[str, object], indice: int) -> dict[str, object]:
    if not isinstance(item, Mapping):
        raise TypeError(f"item no indice {indice} deve ser um mapeamento")

    origem = item.get("origem")
    if not isinstance(origem, str) or origem.strip().lower() not in ORIGENS_VALIDAS:
        raise ValueError(f"origem ausente ou invalida no indice {indice}")
    origem = origem.strip().lower()

    chave = item.get("chave_origem")
    if chave is None:
        chave = chave_natural_leitura(
            origem,
            item.get("codigo_estacao", item.get("estacao_id")),
            item.get("data_leitura", item.get("timestamp")),
            item.get("id_leitura_origem"),
        )
    if not isinstance(chave, str) or not chave.strip():
        raise ValueError(f"chave_origem obrigatoria no indice {indice}")
    chave = chave.strip()

    codigo = item.get("codigo_parametro")
    if not isinstance(codigo, str) or not codigo.strip():
        raise ValueError(f"codigo_parametro obrigatorio no indice {indice}")
    codigo = codigo.strip().upper()

    valor_numerico = item.get("valor_numerico")
    valor_texto = item.get("valor_texto")
    tem_numero = valor_numerico is not None
    tem_texto = valor_texto is not None
    if tem_numero == tem_texto:
        raise ValueError(
            f"informe exatamente um valor numerico ou textual no indice {indice}"
        )

    if tem_numero:
        if isinstance(valor_numerico, bool):
            raise ValueError(f"valor numerico invalido no indice {indice}")
        try:
            numero = Decimal(str(valor_numerico))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"valor numerico invalido no indice {indice}") from error
        if not numero.is_finite():
            raise ValueError(f"valor numerico nao finito no indice {indice}")
        casas_decimais = max(-numero.as_tuple().exponent, 0)
        if casas_decimais > 6 or numero.adjusted() > 11:
            raise ValueError(f"valor excede NUMERIC(18,6) no indice {indice}")
        valor_numerico = numero
        if codigo == "CONDICAO_METEO":
            raise ValueError("condicao meteorologica exige valor textual")
        if codigo in LIMITES_NUMERICOS:
            minimo, maximo = LIMITES_NUMERICOS[codigo]
            if numero < minimo or (maximo is not None and numero > maximo):
                raise ValueError(f"valor fora do dominio do parametro {codigo}")
    else:
        if not isinstance(valor_texto, str) or not valor_texto.strip():
            raise ValueError(f"valor textual invalido no indice {indice}")
        valor_texto = valor_texto.strip()
        if len(valor_texto) > 200:
            raise ValueError(f"valor textual excede 200 caracteres no indice {indice}")
        if codigo in LIMITES_NUMERICOS:
            raise ValueError(f"parametro {codigo} exige valor numerico")

    return {
        "origem": origem,
        "chave_origem": chave,
        "codigo_parametro": codigo,
        "valor_numerico": valor_numerico,
        "valor_texto": valor_texto,
    }


def inserir_leitura_itens(
    itens: Iterable[Mapping[str, object]], engine=None, *,
    connection: Connection | None = None, strict: bool = False,
) -> tuple[int, int, int]:
    """Persiste itens; retorna (inseridos, retransmissoes, rejeitados).

    Cada item informa origem, chave_origem, codigo_parametro e exatamente um
    entre valor_numerico e valor_texto. Estacao/instante podem substituir a
    chave explicita para gerar a mesma chave natural usada por inserir_leituras.
    connection exige transacao ativa; strict propaga rejeicoes para rollback do evento.
    """
    if connection is not None and not connection.in_transaction():
        raise ValueError("connection exige transacao ativa")
    supplied_connection = connection
    target_engine = connection.engine if connection is not None else (engine or create_db_engine())
    require_sqlserver(target_engine)
    item_table = "dbo.leitura_itens"
    leitura_table = "dbo.leituras"
    parametro_table = "dbo.parametros"
    inseridos = 0
    retransmissoes = 0
    rejeitados = 0

    for indice, entrada in enumerate(itens):
        try:
            item = _normalizar_item(entrada, indice)
            if len(item["chave_origem"]) > _COMPRIMENTOS_MAXIMOS["chave_origem"]:
                raise ValueError(f"chave_origem excede 150 caracteres no indice {indice}")
            if len(item["codigo_parametro"]) > _COMPRIMENTOS_MAXIMOS["codigo_parametro"]:
                raise ValueError(f"codigo_parametro excede 50 caracteres no indice {indice}")
        except (TypeError, ValueError) as error:
            logging.warning("Item de leitura rejeitado: indice=%s motivo=%s", indice, str(error))
            if strict:
                raise
            rejeitados += 1
            continue

        try:
            resultado_registro = "retransmissao"
            with (nullcontext(supplied_connection) if supplied_connection is not None else target_engine.begin()) as connection:
                adquirir_lock_etl(connection, "etl:leituras")
                adquirir_lock_etl(connection, "etl:leitura_itens")
                id_leitura = connection.execute(
                    text(
                        f"SELECT id FROM {leitura_table} "
                        "WHERE origem = :origem AND chave_origem = :chave_origem"
                    ),
                    {"origem": item["origem"], "chave_origem": item["chave_origem"]},
                ).scalar_one_or_none()
                if id_leitura is None:
                    raise ItemLeituraInvalidoError("cabecalho de leitura nao encontrado")

                id_parametro = connection.execute(
                    text(
                        f"SELECT id FROM {parametro_table} "
                        "WHERE codigo = :codigo"
                    ),
                    {"codigo": item["codigo_parametro"]},
                ).scalar_one_or_none()
                if id_parametro is None:
                    raise ItemLeituraInvalidoError("codigo de parametro nao cadastrado")

                existente = connection.execute(
                    text(
                        f"SELECT valor_numerico, valor_texto FROM {item_table} "
                        "WHERE id_leitura = :id_leitura AND id_parametro = :id_parametro"
                    ),
                    {"id_leitura": id_leitura, "id_parametro": id_parametro},
                ).mappings().one_or_none()

                if existente is None:
                    valor_numerico = item["valor_numerico"]
                    connection.execute(
                        text(
                            f"INSERT INTO {item_table} "
                            "(id_leitura, id_parametro, valor_numerico, valor_texto) "
                            "VALUES (:id_leitura, :id_parametro, :valor_numerico, :valor_texto)"
                        ),
                        {
                            "id_leitura": id_leitura,
                            "id_parametro": id_parametro,
                            "valor_numerico": valor_numerico,
                            "valor_texto": item["valor_texto"],
                        },
                    )
                    resultado_registro = "inserido"
                else:
                    valor_existente = existente["valor_numerico"]
                    if item["valor_numerico"] is not None:
                        corresponde = (
                            valor_existente is not None
                            and Decimal(str(valor_existente)) == item["valor_numerico"]
                            and existente["valor_texto"] is None
                        )
                    else:
                        corresponde = (
                            existente["valor_texto"] == item["valor_texto"]
                            and valor_existente is None
                        )
                    if not corresponde:
                        raise ItemLeituraInvalidoError(
                            "retransmissao conflitante para parametro da leitura"
                        )
            if resultado_registro == "inserido":
                inseridos += 1
            else:
                retransmissoes += 1
        except (ItemLeituraInvalidoError, TypeError, ValueError) as error:
            logging.warning(
                "Item de leitura rejeitado: origem=%s chave=%s parametro=%s motivo=%s",
                item["origem"],
                item["chave_origem"],
                item["codigo_parametro"],
                str(error),
            )
            if strict:
                raise
            rejeitados += 1
        except Exception as error:
            logging.error(
                "Falha na carga do item: origem=%s chave=%s parametro=%s erro=%s",
                item["origem"],
                item["chave_origem"],
                item["codigo_parametro"],
                type(error).__name__,
            )
            raise

    logging.info(
        "Carga de itens concluida: inseridos=%s retransmissoes=%s rejeitados=%s",
        inseridos,
        retransmissoes,
        rejeitados,
    )
    return inseridos, retransmissoes, rejeitados


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    raise SystemExit("Informe os itens chamando inserir_leitura_itens().")