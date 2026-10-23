"""Carga ambiental no modelo 3FN e na Silver, sem dual-write."""

import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from src.database.dialect import require_sqlserver
from src.database.dml.Persistir_Medicoes import carregar_dataframe
from src.silver.etl.Parse_LeituraAmbiental import tabela_ambiental
from src.silver.persistencia.Persistir_Silver import persistir_silver


def resolver_id_estacao(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    """Resolve codigo_origem, nunca nome, sem alterar o cadastro."""
    require_sqlserver(connection)
    if df_leituras.empty:
        return df_leituras.copy()
    estacoes = pd.read_sql(
        text("SELECT id AS id_estacao, codigo_origem FROM estacao"), connection
    )
    leituras = df_leituras.copy()
    leituras["estacao_id"] = leituras["estacao_id"].astype("string").str.strip()
    result = leituras.merge(
        estacoes, left_on="estacao_id", right_on="codigo_origem",
        how="left", validate="many_to_one",
    )
    for _ in result.loc[result["id_estacao"].isna()].index:
        logging.warning("Leitura rejeitada por estação sem correspondência")
    result = result.loc[result["id_estacao"].notna()].copy()
    result["id_estacao"] = result["id_estacao"].astype("int64")
    return result.drop(columns=["estacao_id", "codigo_origem"])


def inserir_dados():
    dados = tabela_ambiental()
    if dados.empty:
        logging.info("Nenhum dado encontrado para inserir.")
        return
    aprovados = carregar_dataframe(dados, "qualidade_agua", create_db_engine())
    if not aprovados.empty:
        # SQL ja foi confirmado; replay SQL tambem repara Silver ausente.
        persistir_silver(aprovados, "qualidade_agua")
    logging.info("Carga ambiental 3FN: aceitos=%s rejeitados=%s", len(aprovados), len(dados) - len(aprovados))


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    inserir_dados()
