"""Carga meteorologica no modelo 3FN e na Silver."""

import logging
import sys
from pathlib import Path
from time import monotonic

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from src.database.dialect import require_sqlserver
from src.database.dml.Persistir_Medicoes import carregar_dataframe
from src.silver.etl.Parse_LeituraMetereologica import tabela_metereologica
from src.silver.persistencia.Persistir_Silver import persistir_silver


def resolver_id_cidade(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    require_sqlserver(connection)
    estacoes = pd.read_sql(
        text("SELECT id AS id_estacao, id_cidade FROM estacao"), connection
    )
    result = df_leituras.merge(estacoes, on="id_estacao", how="left", validate="many_to_one")
    if result["id_cidade"].isna().any():
        raise ValueError("Estações sem cidade cadastrada no banco")
    return result.drop(columns=["cidade", "estado"], errors="ignore")


def exibir_progresso(processadas: int, total: int) -> None:
    if processadas % 100 == 0 or processadas == total:
        print(f"Meteorologia: {processadas}/{total} leituras processadas", flush=True)


def inserir_dados():
    inicio = monotonic()
    logging.info("Carga meteorologica iniciada: lendo e tratando JSON Bronze")
    dados = tabela_metereologica()
    logging.info("Tratamento meteorologico concluido: leituras=%s tempo=%.1fs", len(dados), monotonic() - inicio)
    if dados.empty:
        logging.info("Nenhum dado encontrado para inserir.")
        return
    aprovados = carregar_dataframe(
        dados, "leitura_meteorologica", create_db_engine(),
        progresso=exibir_progresso,
    )
    if not aprovados.empty:
        inicio_silver = monotonic()
        logging.info("Persistencia Silver iniciada: leituras=%s", len(aprovados))
        persistir_silver(aprovados, "leitura_meteorologica")
        logging.info("Persistencia Silver concluida: tempo=%.1fs", monotonic() - inicio_silver)
    logging.info("Carga meteorologica 3FN: aceitos=%s rejeitados=%s tempo_total=%.1fs",
                 len(aprovados), len(dados) - len(aprovados), monotonic() - inicio)


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    inserir_dados()
