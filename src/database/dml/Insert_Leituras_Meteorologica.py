"""Carga das leituras meteorológicas no banco de dados.

Este módulo lê os dados tratados do JSON meteorológico, resolve os IDs de cidade
correspondentes no banco e realiza a inserção dos registros na tabela
leitura_meteorologica.
"""

import sys
import urllib.parse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# Permite importar o pacote ingestion ao executar este arquivo diretamente
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Importa a função do módulo Parse_leituras_JSON
from ingestion.leituras.Parse_LeituraMetereologica import tabela_metereologica

# Configurações da conexão com a instância local do SQL Server
servidor = r".\SQLEXPRESS"  # Ou 'localhost\SQLEXPRESS'
database = "monitoramento"
tabeladestino = "leitura_meteorologica"
modocarga = "append"  # Mantém os dados existentes na tabela

# Codifica a string ODBC para utilização com SQLAlchem
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

# Cria a engine de conexão com o banco
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


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

    # 1. Busca as cidades e seus estados usando os IDs gerados pelo SQL Server.
    cidades_banco = pd.read_sql(
        text(
            "SELECT c.id AS id_cidade, c.nome AS nome_cidade, "
            "e.nome AS nome_estado "
            "FROM cidade AS c "
            "INNER JOIN estado AS e ON e.id = c.id_estado"
        ),
        connection,
    )

    # 2. Cidade e estado evitam vínculos incorretos entre municípios homônimos.
    df_leituras = df_leituras.merge(
        cidades_banco,
        left_on=["cidade", "estado"],
        right_on=["nome_cidade", "nome_estado"],
        how="left",
        validate="many_to_one",
    )

    # 3. Verifica se alguma cidade no JSON não possui id_cidade correspondente no banco
    sem_cidade = df_leituras.loc[df_leituras["id_cidade"].isna(), "cidade"]
    if not sem_cidade.empty:
        raise ValueError(
            f"Cidades encontradas no JSON sem cadastro no banco: {sorted(sem_cidade.unique())}"
        )


    # 5. Remove colunas auxiliares que não fazem parte da tabela de destino
    df_leituras = df_leituras.drop(
        columns=["cidade", "estado", "nome_cidade", "nome_estado"]
    )

    return df_leituras


def inserir_dados():
    """Executa o processo completo de carga dos dados meteorológicos.

    A função carrega os dados tratados, resolve os identificadores do banco,
    insere os registros na tabela e imprime o resultado da operação.
    """
    try:
        print("Obtendo dados do Parse JSON...")
        df_dados = tabela_metereologica()

        if df_dados.empty:
            print("Nenhum dado encontrado para inserir.")
            return

        with engine.begin() as connection:
            df_dados = resolver_id_cidade(df_dados, connection)

            print(f"Inserindo {len(df_dados)} registros na tabela '{tabeladestino}'...")

            df_dados.to_sql(
                name=tabeladestino,
                con=connection,
                if_exists=modocarga,
                index=False,
            )


    except Exception as e:
        print(f"Erro ao inserir dados: {e}")


if __name__ == "__main__":
    inserir_dados()