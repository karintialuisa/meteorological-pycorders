"""Persistencia atomica e mapeamento comum de eventos 3FN."""

import logging
from collections.abc import Mapping

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from database.dml.Insert_Leituras import _normalizar_registro, inserir_leituras
from database.dml.Insert_Leitura_Itens import _normalizar_item, inserir_leitura_itens
from database.dml.etl_lock import adquirir_lock_etl


MAPEAMENTO = {
    "qualidade_agua": {
        "temperatura_agua": "TEMP_AGUA", "ph": "PH", "oxigenio": "OD",
        "condutividade": "COND_ELETRICA", "turbidez": "TURBIDEZ",
    },
    "leitura_meteorologica": {
        "temperatura_ar": "TEMP_AR", "umidade": "UMIDADE", "chuva": "CHUVA",
        "vento": "VENTO", "condicao": "CONDICAO_METEO",
    },
}


def preparar_evento(registro: Mapping[str, object], origem: str):
    if origem not in MAPEAMENTO:
        raise ValueError("origem de medicao desconhecida")
    codigo_estacao = registro.get("estacao_id")
    if codigo_estacao is None or pd.isna(codigo_estacao) or not str(codigo_estacao).strip():
        raise ValueError("codigo da estacao obrigatorio")
    cabecalho = _normalizar_registro(
        {
            "origem": origem,
            "codigo_estacao": str(codigo_estacao).strip(),
            "data_leitura": registro["data_leitura"],
            "id_leitura_origem": registro.get("id_leitura_origem"),
            "operador_cpf_hash": registro.get("operador_cpf_hash"),
        },
        0,
    )
    itens = []
    for coluna, codigo in MAPEAMENTO[origem].items():
        valor = registro.get(coluna)
        if valor is None or pd.isna(valor):
            if origem == "leitura_meteorologica":
                raise ValueError(f"medicao meteorologica obrigatoria: {coluna}")
            continue
        item = {
            "origem": origem, "chave_origem": cabecalho["chave_origem"],
            "codigo_parametro": codigo,
            "valor_texto" if codigo == "CONDICAO_METEO" else "valor_numerico": valor,
        }
        itens.append(_normalizar_item(item, len(itens)))
    if not itens:
        raise ValueError("evento sem medicoes")
    return cabecalho, itens


def persistir_evento(connection: Connection, cabecalho, itens) -> None:
    """Usa a transacao do chamador; rejeicao deve causar rollback."""
    if not connection.in_transaction():
        raise ValueError("persistencia de evento exige transacao ativa")
    adquirir_lock_etl(connection, "etl:leituras")
    adquirir_lock_etl(connection, "etl:leitura_itens")
    inserir_leituras([cabecalho], connection=connection, strict=True)
    tabela = "dbo.leitura_itens" if connection.dialect.name == "mssql" else "leitura_itens"
    existente = connection.execute(
        text(
            f"SELECT p.codigo FROM {tabela} i JOIN parametros p ON p.id=i.id_parametro "
            "JOIN leituras l ON l.id=i.id_leitura "
            "WHERE l.origem=:origem AND l.chave_origem=:chave"
        ),
        {"origem": cabecalho["origem"], "chave": cabecalho["chave_origem"]},
    ).scalars().all()
    codigos = {item["codigo_parametro"] for item in itens}
    if existente and set(existente) != codigos:
        raise ValueError("retransmissao conflitante: conjunto de parametros diferente")
    inserir_leitura_itens(itens, connection=connection, strict=True)


def carregar_dataframe(df: pd.DataFrame, origem: str, engine) -> pd.DataFrame:
    """Aceita/rejeita cada evento; falhas SQL tecnicas nao sao suprimidas."""
    if origem not in MAPEAMENTO:
        raise ValueError("origem de medicao desconhecida")
    with engine.connect() as connection:
        schema = "dbo" if connection.dialect.name == "mssql" else None
        existentes = set(inspect(connection).get_table_names(schema=schema))
        for tabela in MAPEAMENTO:
            if tabela in existentes and connection.execute(
                text(f"SELECT COUNT(*) FROM {tabela}")
            ).scalar_one():
                raise ValueError("legado ativo com dados: realizar migracao e arquivamento antes da carga")
    aprovados = []
    for indice, registro in enumerate(df.to_dict("records")):
        try:
            cabecalho, itens = preparar_evento(registro, origem)
            with engine.begin() as connection:
                persistir_evento(connection, cabecalho, itens)
                estacao = connection.execute(
                    text("SELECT id, id_cidade FROM estacao WHERE codigo_origem=:codigo"),
                    {"codigo": cabecalho["codigo_estacao"]},
                ).one()
            silver = dict(registro)
            silver["id_estacao"] = estacao.id
            if origem == "leitura_meteorologica":
                silver["id_cidade"] = estacao.id_cidade
            silver.pop("estacao_id", None)
            silver.pop("operador_cpf_hash", None)
            silver.pop("cidade", None)
            silver.pop("estado", None)
            aprovados.append(silver)
        except ValueError as error:
            logging.warning(
                "Evento rejeitado: origem=%s indice=%s motivo=%s", origem, indice, error
            )
    return pd.DataFrame(aprovados)
