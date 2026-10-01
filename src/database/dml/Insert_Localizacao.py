"""Carga inicial de dados de localização no banco de dados.


Este módulo conecta ao SQL Server Express, lê as tabelas de localização
normalizadas a partir dos arquivos JSON e insere os dados nas tabelas de
estado, cidade e estação.
"""
import os

import urllib
import pandas as pd
# text recebe uma string SQL, como "DELETE FROM estado", e cria um objeto
# TextClause: uma instrução SQL reconhecida pelo SQLAlchemy. Ele apenas prepara
# o comando; a alteração só acontece quando connection.execute() o executa.
from sqlalchemy import create_engine, text

import sys
import urllib.parse
from pathlib import Path
# setamos o caminho para o sys.path, para ao executar o script possamos importar módulos do projeto corretamente.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text
from ingestion.localizacao.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estacao,
    tabela_estado,
)


# Localiza o diretório raiz do projeto para permitir importações e carregar o .env
BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(dotenv_path=BASE_DIR / ".env")

def get_env(chave: str) -> str:
    """Obtém obrigatoriamente a variável do arquivo .env.

    Lança erro se não for encontrada.
    """
    valor = os.getenv(chave)
    if not valor:
        raise KeyError(
            f"❌ Configuração ausente: A chave '{chave}' não foi encontrada no arquivo .env"
        )
    return valor


# Configurações da conexão obtidas estritamente do .env
servidor = get_env("DB_HOST")
database = get_env("DB_NAME")
trusted_connection = get_env("DB_TRUSTED_CONNECTION")

modo_carga = "append"  # Use "append" para preservar os dados atuais.

# Codifica a string ODBC para que ela possa ser usada pelo SQLAlchemy.
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection={trusted_connection};"
)

# Cria a engine reutilizada nas operações de leitura e escrita do banco.
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


def limpar_localizacao(connection):
    """Remove os registros de localização e reinicia os identificadores.

    Args:
        connection: Conexão ativa com o banco de dados SQL Server.
    """
    if modo_carga == "replace":
        connection.execute(text("DELETE FROM estacao"))
        connection.execute(text("DELETE FROM cidade"))
        connection.execute(text("DELETE FROM estado"))

        connection.execute(text("DBCC CHECKIDENT ('estacao', RESEED, 0)"))
        connection.execute(text("DBCC CHECKIDENT ('cidade', RESEED, 0)"))
        connection.execute(text("DBCC CHECKIDENT ('estado', RESEED, 0)"))


def inserir_localizacao(connection):
    """Insere os estados e cidades no banco, vinculando cada cidade ao estado.

    Args:
        connection: Conexão SQLAlchemy utilizada para executar as operações.

    Returns:
        pandas.DataFrame: Tabela com os IDs de estado e seus códigos IBGE.
    """
    df_estado = tabela_estado()
    df_estado["codigo_ibge_estado"] = pd.to_numeric(
        df_estado["codigo_ibge_estado"], errors="raise"
    ).astype("Int64")

    if modo_carga == "append":
        estados_existentes = pd.read_sql(
            text("SELECT codigo_ibge FROM estado"), connection
        )
        df_estado = df_estado[
            ~df_estado["codigo_ibge_estado"].isin(
                estados_existentes["codigo_ibge"]
            )
        ]

    if not df_estado.empty:
        df_estado.rename(
            columns={
                "codigo_ibge_estado": "codigo_ibge",
                "sigla_estado": "sigla",
                "nome_estado": "nome",
            }
        ).to_sql("estado", connection, if_exists="append", index=False)

    estado_ids = pd.read_sql(
        text("SELECT id, codigo_ibge, sigla FROM estado"), connection
    ).rename(
        columns={
            "id": "id_estado",
            "codigo_ibge": "codigo_ibge_estado",
            "sigla": "sigla_estado",
        }
    )

    df_cidade = tabela_cidade().merge(
        estado_ids[["id_estado", "sigla_estado"]],
        on="sigla_estado",
        how="left",
        validate="many_to_one",
    )

    if df_cidade["id_estado"].isna().any():
        raise ValueError("Cidade com estado não encontrado no banco")

    df_cidade["codigo_ibge_cidade"] = pd.to_numeric(
        df_cidade["codigo_ibge_cidade"], errors="raise"
    ).astype("Int64")

    df_cidade = df_cidade.rename(
        columns={"codigo_ibge_cidade": "codigo_ibge", "nome_cidade": "nome"}
    )[["id_estado", "codigo_ibge", "nome"]]

    if modo_carga == "append":
        cidades_existentes = pd.read_sql(
            text("SELECT codigo_ibge, id_estado FROM cidade"), connection
        )
        df_cidade = df_cidade.merge(
            cidades_existentes,
            on=["codigo_ibge", "id_estado"],
            how="left",
            indicator=True,
        )
        df_cidade = df_cidade[df_cidade["_merge"] == "left_only"].drop(
            columns=["_merge"]
        )

    if not df_cidade.empty:
        df_cidade.to_sql("cidade", connection, if_exists="append", index=False)

    return estado_ids


def inserir_estacoes(connection, estado_ids):
    """Insere as estações da rede, relacionando cada uma a cidade e ao estado.

    Args:
        connection: Conexão ativa com o banco de dados.
        estado_ids (pandas.DataFrame): DataFrame com os IDs de estado e os códigos
            IBGE relacionados.
    """
    df_estacao = tabela_estacao(tabela_cidade(), tabela_estado())

    cidade_ids = pd.read_sql(
        text("SELECT id, codigo_ibge, id_estado FROM cidade"), connection
    ).rename(columns={"id": "id_cidade", "codigo_ibge": "codigo_ibge_cidade"})

    cidade_ids["codigo_ibge_cidade"] = cidade_ids["codigo_ibge_cidade"].astype(
        "Int64"
    )
    df_estacao["codigo_ibge_cidade"] = pd.to_numeric(
        df_estacao["codigo_ibge_cidade"], errors="raise"
    ).astype("Int64")
    df_estacao["codigo_ibge_estado"] = pd.to_numeric(
        df_estacao["codigo_ibge_estado"], errors="raise"
    ).astype("Int64")

    df_estacao = df_estacao.merge(
        estado_ids[["id_estado", "codigo_ibge_estado"]],
        on="codigo_ibge_estado",
        how="left",
        validate="many_to_one",
    )
    df_estacao = df_estacao.merge(
        cidade_ids,
        on=["codigo_ibge_cidade", "id_estado"],
        how="left",
        validate="many_to_one",
    )

    if df_estacao[["id_estado", "id_cidade"]].isna().any().any():
        raise ValueError(
            "Estação com cidade ou estado não encontrado no banco"
        )

    df_estacao = df_estacao.rename(columns={"status_estacao": "status"})[
        ["nome", "status", "id_estado", "id_cidade"]
    ]

    if modo_carga == "append":
        estacoes_existentes = pd.read_sql(
            text("SELECT nome, id_estado, id_cidade FROM estacao"), connection
        )
        df_estacao = df_estacao.merge(
            estacoes_existentes,
            on=["nome", "id_estado", "id_cidade"],
            how="left",
            indicator=True,
        )
        df_estacao = df_estacao[df_estacao["_merge"] == "left_only"].drop(
            columns=["_merge"]
        )

    if not df_estacao.empty:
        df_estacao.to_sql(
            "estacao", connection, if_exists="append", index=False
        )


if __name__ == "__main__":
    with engine.begin() as connection:
        limpar_localizacao(connection)
        estado_ids = inserir_localizacao(connection)
        inserir_estacoes(connection, estado_ids)

    print("Dados inseridos com sucesso!")