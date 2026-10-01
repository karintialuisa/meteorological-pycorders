import logging
"""Carga das leituras meteorológicas no banco de dados.

Este módulo lê os dados tratados do JSON meteorológico, resolve os IDs de cidade
correspondentes no banco e realiza a inserção dos registros na tabela
leitura_meteorologica.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, create_db_engine
import pandas as pd
from sqlalchemy import text
from ingestion.leituras.Parse_LeituraMetereologica import tabela_metereologica


tabeladestino = "leitura_meteorologica"
modocarga = "append"

def resolver_id_cidade(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    """Resolve o identificador da cidade com base no nome e estado.

    Args:
        df_leituras (pd.DataFrame): DataFrame contendo as leituras meteorológicas.
        connection: Conexão ativa com o banco de dados SQL Server.

    Returns:
        pd.DataFrame: DataFrame enriquecido com o id_cidade do banco.
    """
    colunas_necessarias = {"cidade", "estado"}
    colunas_ausentes = colunas_necessarias.difference(df_leituras.columns)
    if colunas_ausentes:
        raise KeyError(
            "Colunas ausentes no DataFrame meteorológico: "
            f"{sorted(colunas_ausentes)}"
        )

    cidades_banco = pd.read_sql(
        text(
            "SELECT c.id AS id_cidade, c.nome AS nome_cidade, "
            "e.nome AS nome_estado "
            "FROM cidade AS c "
            "INNER JOIN estado AS e ON e.id = c.id_estado"
        ),
        connection,
    )

    df_leituras = df_leituras.merge(
        cidades_banco,
        left_on=["cidade", "estado"],
        right_on=["nome_cidade", "nome_estado"],
        how="left",
        validate="many_to_one",
    )

    sem_cidade = df_leituras.loc[df_leituras["id_cidade"].isna(), "cidade"]
    if not sem_cidade.empty:
        raise ValueError(
            f"Cidades encontradas no JSON sem cadastro no banco: {sorted(sem_cidade.unique())}"
        )

    return df_leituras.drop(
        columns=["cidade", "estado", "nome_cidade", "nome_estado"]
    )


def inserir_dados():
    """Executa o processo completo de carga dos dados meteorológicos.

    A função carrega os dados tratados, resolve os identificadores do banco,
    insere os registros na tabela e imprime o resultado da operação.
    """
    try:
        logging.info("Obtendo dados do Parse JSON...")
        df_dados = tabela_metereologica()

        if df_dados.empty:
            logging.info("Nenhum dado encontrado para inserir.")
            return

        with create_db_engine().begin() as connection:
            df_dados = resolver_id_cidade(df_dados, connection)
            logging.info(
                "Inserindo %s registros na tabela '%s'...",
                len(df_dados),
                tabeladestino,
            )

            df_dados.to_sql(
                name=tabeladestino,
                con=connection,
                if_exists=modocarga,
                index=False,
            )

        logging.info("Carga realizada com sucesso!")

    except Exception as e:
        logging.exception("Erro ao inserir dados: %s", e)


if __name__ == "__main__":
    configure_logging(Path(__file__).resolve().parents[3])
    inserir_dados()