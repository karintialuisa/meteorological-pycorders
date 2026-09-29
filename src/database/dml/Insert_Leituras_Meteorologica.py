# ============================================================
# ASSUNTO: Conexão com o banco de dados SQL Server Express
# Inserção de dados na tabela leituras meteorologica
# ============================================================

import sys
import urllib.parse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# Permite importar o pacote ingestion ao executar este arquivo diretamente
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Importa a função do módulo Parse_leituras_JSON
from src.ingestion.leituras.Parse_LeituraMetereologica import tabela_meteorologica

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
    """Associa o nome da cidade trazido do JSON ao id numérico (id_cidade) da tabela cidade do banco."""
    if "cidade" not in df_leituras.columns:
        raise KeyError("A coluna 'cidade' não foi encontrada no DataFrame vindo de tabela_meteorologica().")

    # 1. Busca cidades cadastradas no SQL Server mapeando para id_cidade
    cidades_banco = pd.read_sql(
        text("SELECT id AS id_cidade, nome FROM cidade"), connection
    )

    # 2. Merge com a tabela de cidades do banco
    df_leituras = df_leituras.merge(
        cidades_banco,
        left_on="cidade",
        right_on="nome",
        how="left",
    )

    # 3. Verifica se alguma cidade no JSON não possui id_cidade correspondente no banco
    sem_cidade = df_leituras.loc[df_leituras["id_cidade"].isna(), "cidade"]
    if not sem_cidade.empty:
        raise ValueError(
            f"Cidades encontradas no JSON sem cadastro no banco: {sorted(sem_cidade.unique())}"
        )


    # 5. Remove colunas auxiliares que não fazem parte da tabela de destino
    df_leituras = df_leituras.drop(columns=["cidade", "nome"], errors="ignore")

    return df_leituras


def inserir_dados():
    try:
        print("Obtendo dados do Parse JSON...")
        df_dados = tabela_meteorologica()

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