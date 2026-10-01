
"""Carga das leituras ambientais no banco de dados.

Este módulo lê os dados de qualidade da água tratados em JSON, resolve os IDs
de estação no banco e insere os registros na tabela qualidade_agua.
"""
import os

import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text


sys.path.append(str(Path(__file__).resolve().parents[2]))

from ingestion.leituras.Parse_LeituraAmbiental import tabela_ambiental
from ingestion.localizacao.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estacao,
    tabela_estado,
)

# Localiza a raiz do projeto para o .env e sys.path
BASE_DIR = Path(__file__).resolve().parents[3]

# Carrega as variáveis de ambiente do arquivo .env localizado na raiz do projeto
load_dotenv(dotenv_path=BASE_DIR / ".env")


def get_env(chave: str) -> str:
    valor = os.getenv(chave)
    if not valor:
        raise KeyError(
            f"❌ Configuração ausente: A chave '{chave}' não foi encontrada no arquivo .env"
        )
    return valor


# Leitura direta das variáveis do .env
servidor = get_env("DB_HOST")
database = get_env("DB_NAME")
trusted_connection = get_env("DB_TRUSTED_CONNECTION")

tabela_destino = "qualidade_agua"
modo_carga = "append"



params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection={trusted_connection};"
)

engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


def resolver_id_estacao(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    """Converte o identificador da estação do JSON para o ID do banco.

    Args:
        df_leituras (pd.DataFrame): DataFrame com as leituras ambientais.
        connection: Conexão ativa com o banco de dados.

    Returns:
        pd.DataFrame: DataFrame com a coluna de estação convertida para id_estacao.
    """
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

    df_leituras = df_leituras.merge(
        df_estacao[["id", "id_estacao"]],
        left_on="estacao_id",
        right_on="id",
        how="left",
        validate="many_to_one",
    )
    sem_estacao = df_leituras.loc[df_leituras["id_estacao"].isna(), "estacao_id"]
    if not sem_estacao.empty:
        raise ValueError(
            f"Leituras sem estação cadastrada no banco: {sorted(sem_estacao.unique())}"
        )

    df_leituras["id_estacao"] = df_leituras["id_estacao"].astype("int64")
    return df_leituras.drop(columns=["estacao_id", "id"])


def inserir_dados():
    """Executa a inserção dos dados ambientais no banco de dados.

    O processo inclui carregamento dos dados, resolução do ID da estação,
    gravação dos registros e confirmação final da operação.
    """
    try:
        print("Obtendo dados tratados do Parse JSON...")
        df_dados = tabela_ambiental()

        if df_dados.empty:
            print("Nenhum dado encontrado para inserir.")
            return

        with engine.begin() as connection:
            df_dados = resolver_id_estacao(df_dados, connection)
            print(f"Inserindo {len(df_dados)} registros na tabela '{tabela_destino}'...")

            df_dados.to_sql(
                name=tabela_destino,
                con=connection,
                if_exists=modo_carga,
                index=False,
            )

        print("Carga realizada com sucesso!")

    except Exception as e:
        print(f"Erro durante a inserção dos dados: {e}")


if __name__ == "__main__":
    inserir_dados()