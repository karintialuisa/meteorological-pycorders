import os
import sys
import urllib.parse
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text
from ingestion.leituras.Parse_LeituraMetereologica import tabela_metereologica


# Obtenção do arquivo .env que possui as variáveis armazenadas
BASE_DIR = Path(__file__).resolve().parents[3]

# Carregamento do arquivo .env
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

tabeladestino = "leitura_meteorologica"
modocarga = "append"



params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection={trusted_connection};"
)

engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


def resolver_id_cidade(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
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

        print("Carga realizada com sucesso!")

    except Exception as e:
        print(f"Erro ao inserir dados: {e}")


if __name__ == "__main__":
    inserir_dados()