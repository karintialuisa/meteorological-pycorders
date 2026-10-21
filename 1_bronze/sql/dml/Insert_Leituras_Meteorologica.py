"""Carga meteorologica no modelo 3FN e na Silver."""

import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from bronze.sql.dml.Persistir_Medicoes import carregar_dataframe
from silver.etl.Parse_LeituraMetereologica import tabela_metereologica
from silver.persistencia.Persistir_Silver import persistir_silver


def resolver_id_cidade(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    estacoes = pd.read_sql(
        text("SELECT id AS id_estacao, id_cidade FROM estacao"), connection
    )
    result = df_leituras.merge(estacoes, on="id_estacao", how="left", validate="many_to_one")
    if result["id_cidade"].isna().any():
        raise ValueError("Estações sem cidade cadastrada no banco")
    return result.drop(columns=["cidade", "estado"], errors="ignore")


def inserir_dados():
    dados = tabela_metereologica()
    if dados.empty:
        logging.info("Nenhum dado encontrado para inserir.")
        return
    aprovados = carregar_dataframe(dados, "leitura_meteorologica", create_db_engine())
    if not aprovados.empty:
        persistir_silver(aprovados, "leitura_meteorologica")
    logging.info("Carga meteorologica 3FN: aceitos=%s rejeitados=%s", len(aprovados), len(dados) - len(aprovados))


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    inserir_dados()
