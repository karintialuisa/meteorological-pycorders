import sys
import urllib.parse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# Permite importar o pacote ingestion ao executar este arquivo diretamente.
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Importa a função do módulo Parse_leituras_JSON
from Parse_leituras_JSON import tabela_ambiental
from ingestion.localizacao.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estacao,
    tabela_estado,
)

# Configurações da conexão com a instância local do SQL Server
servidor = r".\SQLEXPRESS"  # Ou 'localhost\SQLEXPRESS'
database = "monitoramento"
tabela_destino = "qualidade_agua"
modo_carga = "append"  # Mantém os dados existentes na tabela

# Codifica a string ODBC para utilização com SQLAlchemy
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

# Cria a engine de conexão com o banco
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


def resolver_id_estacao(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    """Troca o código da estação do JSON pelo id gerado no banco, usando o nome."""
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
    try:
        print("Obtendo dados tratados do Parse JSON...")
        df_dados = tabela_ambiental()

        if df_dados.empty:
            print("Nenhum dado encontrado para inserir.")
            return

        with engine.begin() as connection:
            df_dados = resolver_id_estacao(df_dados, connection)

            print(f"Inserindo {len(df_dados)} registros na tabela '{tabela_destino}'...")

            # O Pandas/SQLAlchemy identificará automaticamente os dtypes do DataFrame
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