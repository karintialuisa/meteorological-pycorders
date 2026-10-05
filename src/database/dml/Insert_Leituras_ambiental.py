
"""Carga das leituras ambientais no banco de dados.

Este módulo lê os dados de qualidade da água tratados em JSON, resolve os IDs
de estação no banco e insere os registros na tabela qualidade_agua.
"""
import logging

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text


sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import PROJECT_ROOT, configure_logging, create_db_engine

from ingestion.leituras.Parse_LeituraAmbiental import tabela_ambiental
from ingestion.localizacao.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estacao,
    tabela_estado,
)

BASE_DIR = PROJECT_ROOT

tabela_destino = "qualidade_agua"
modo_carga = "append"



def resolver_id_estacao(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    """Converte o identificador da estação do JSON para o ID do banco.

    A função rejeita leituras cujo `estacao_id` não encontra correspondência no
    cadastro da estação e registra o motivo para auditoria. O restante do lote
    continua em processamento.

    Args:
        df_leituras (pd.DataFrame): DataFrame com as leituras ambientais.
        connection: Conexão ativa com o banco de dados.

    Returns:
        pd.DataFrame: DataFrame com a coluna de estação convertida para id_estacao.
    """
    if df_leituras.empty:
        return df_leituras.copy()

    df_estacao = tabela_estacao(tabela_cidade(), tabela_estado())[["id", "nome"]]
    duplicados = df_estacao[df_estacao["id"].duplicated(keep=False)]
    if not duplicados.empty:
        raise ValueError(
            "Código de estação repetido em estacoes.json: "
            f"{sorted(duplicados['id'].unique())}"
        )

    estacoes_banco = pd.read_sql(
        text("SELECT id AS id_estacao, nome FROM estacao"), connection
    )
    df_estacao = df_estacao.merge(
        estacoes_banco, on="nome", how="left", validate="one_to_one"
    )

    df_leituras = df_leituras.copy()
    df_leituras["estacao_id"] = pd.to_numeric(
        df_leituras["estacao_id"], errors="coerce"
    )
    df_estacao["id"] = pd.to_numeric(df_estacao["id"], errors="coerce")

    df_leituras = df_leituras.merge(
        df_estacao[["id", "id_estacao"]],
        left_on="estacao_id",
        right_on="id",
        how="left",
        validate="many_to_one",
    )

    for indice in df_leituras.index[df_leituras["id_estacao"].isna()]:
        logging.warning(
            "Leitura ambiental rejeitada por estação sem correspondência: "
            "indice=%s, estacao_id=%s, data_leitura=%s",
            indice,
            df_leituras.at[indice, "estacao_id"],
            df_leituras.at[indice, "data_leitura"],
        )

    df_leituras = df_leituras.loc[df_leituras["id_estacao"].notna()].copy()
    df_leituras["id_estacao"] = df_leituras["id_estacao"].astype("int64")
    return df_leituras.drop(columns=["estacao_id", "id"])


def inserir_dados():
    """Executa a inserção dos dados ambientais no banco de dados.

    O processo inclui carregamento dos dados, resolução do ID da estação,
    gravação dos registros e confirmação final da operação.
    """
    try:
        logging.info("Obtendo dados tratados do Parse JSON...")
        df_dados = tabela_ambiental()

        if df_dados.empty:
            logging.info("Nenhum dado encontrado para inserir.")
            return

        with create_db_engine().begin() as connection:
            df_dados = resolver_id_estacao(df_dados, connection)
            if df_dados.empty:
                logging.info("Nenhuma leitura com estação cadastrada para inserir.")
                return

            logging.info(
                "Inserindo %s registros na tabela '%s'...",
                len(df_dados),
                tabela_destino,
            )

            df_dados.to_sql(
                name=tabela_destino,
                con=connection,
                if_exists=modo_carga,
                index=False,
            )

        logging.info("Carga realizada com sucesso!")

    except Exception as e:
        logging.exception("Erro durante a inserção dos dados: %s", e)


if __name__ == "__main__":
    configure_logging(BASE_DIR)
    inserir_dados()