# ============================================================
# ASSUNTO: Conexão com o banco de dados SQL Server Express
# Inserção de dados na tabela Cidade, estado, estacao
# ============================================================


import urllib
import pandas as pd
# text recebe uma string SQL, como "DELETE FROM estado", e cria um objeto
# TextClause: uma instrução SQL reconhecida pelo SQLAlchemy. Ele apenas prepara
# o comando; a alteração só acontece quando connection.execute() o executa.
from sqlalchemy import create_engine, text

import sys
from pathlib import Path
parse_dir = Path(__file__).resolve().parents[2]
sys.path.append(str(parse_dir))


from ingestion.localizacao.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estado,
    tabela_estacao
)

# Configurações da conexão com a instância local do SQL Server.
servidor = r'.\SQLEXPRESS'  # Ou 'localhost\SQLEXPRESS' ou o IP do seu servidor
database = 'monitoramento'
modo_carga = "append"  # Use "append" para preservar os dados atuais.
 
# Codifica a string ODBC para que ela possa ser usada pelo SQLAlchemy.
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

 
# Cria a engine reutilizada nas operações de leitura e escrita do banco.
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


def limpar_localizacao(connection):
    """Remove os dados de localização e reinicia os IDs no modo replace."""
    if modo_carga == "replace":
        # A exclusão segue a ordem das foreign keys: filha antes da tabela pai.
        # text() prepara o comando e connection.execute() envia esse comando ao SQL Server. Sem o comando execute(), text() não consulta nem altera o banco.
        connection.execute(text("DELETE FROM estacao"))
        connection.execute(text("DELETE FROM cidade"))
        connection.execute(text("DELETE FROM estado"))

        # DELETE não reinicia o contador IDENTITY; RESEED 0 faz o próximo ID ser 1.
        # DBCC CHECKIDENT também é uma instrução SQL, por isso usa text().
        connection.execute(text("DBCC CHECKIDENT ('estacao', RESEED, 0)"))
        connection.execute(text("DBCC CHECKIDENT ('cidade', RESEED, 0)"))
        connection.execute(text("DBCC CHECKIDENT ('estado', RESEED, 0)"))


def inserir_localizacao(connection):
    """Insere estados e cidades, relacionando cidades aos IDs dos estados."""
    df_estado = tabela_estado()
    # O JSON usa texto para IBGE; a coluna do banco e a comparação usam inteiro.
    df_estado["codigo_ibge_estado"] = pd.to_numeric(
        df_estado["codigo_ibge_estado"], errors="raise"
    ).astype("Int64")
    if modo_carga == "append":
        # No modo append, mantém somente estados que ainda não estão cadastrados.
        # SELECT consulta o banco e read_sql transforma o resultado em DataFrame.
        estados_existentes = pd.read_sql(
            text("SELECT codigo_ibge FROM estado"), connection
        )
        df_estado = df_estado[
            ~df_estado["codigo_ibge_estado"].isin(
                estados_existentes["codigo_ibge"]
            )
        ]
    if not df_estado.empty:
        df_estado.rename(columns={
            "codigo_ibge_estado": "codigo_ibge",
            "sigla_estado": "sigla",
            "nome_estado": "nome",
        }).to_sql("estado", connection, if_exists="append", index=False)

    # Recupera os IDs gerados pelo banco para criar as foreign keys das cidades.
    # A instrução SELECT é preparada por text() e executada por read_sql().
    estado_ids = pd.read_sql(
        text("SELECT id, codigo_ibge, sigla FROM estado"), connection
    ).rename(columns={"id": "id_estado", "codigo_ibge": "codigo_ibge_estado", "sigla": "sigla_estado"})
    df_cidade = tabela_cidade().merge(
        estado_ids[["id_estado", "sigla_estado"]], on="sigla_estado", how="left", validate="many_to_one"
    )
    if df_cidade["id_estado"].isna().any():
        raise ValueError("Cidade com estado não encontrado no banco")
    # O JSON pode fornecer o código IBGE como texto; o banco usa tipo inteiro.
    df_cidade["codigo_ibge_cidade"] = pd.to_numeric(
        df_cidade["codigo_ibge_cidade"], errors="raise"
    ).astype("Int64")
    df_cidade = df_cidade.rename(columns={"codigo_ibge_cidade": "codigo_ibge", "nome_cidade": "nome"})[
        ["id_estado", "codigo_ibge", "nome"]
    ]
    if modo_carga == "append":
        # No modo append, evita inserir cidades já existentes.
        # Consulta somente as colunas usadas para identificar uma cidade existente.
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
    """Resolve os códigos IBGE em IDs do banco antes de inserir as estações."""
    df_estacao = tabela_estacao(tabela_cidade(), tabela_estado())
    cidade_ids = pd.read_sql(
        text("SELECT id, codigo_ibge, id_estado FROM cidade"), connection
    ).rename(columns={"id": "id_cidade", "codigo_ibge": "codigo_ibge_cidade"})
    cidade_ids["codigo_ibge_cidade"] = cidade_ids["codigo_ibge_cidade"].astype("Int64")
    df_estacao["codigo_ibge_cidade"] = pd.to_numeric(
        df_estacao["codigo_ibge_cidade"], errors="raise"
    ).astype("Int64")
    df_estacao["codigo_ibge_estado"] = pd.to_numeric(
        df_estacao["codigo_ibge_estado"], errors="raise"
    ).astype("Int64")
    # O IDENTITY de cada tabela é gerado pelo SQL Server, não pelo JSON.
    df_estacao = df_estacao.merge(
        estado_ids[["id_estado", "codigo_ibge_estado"]],
        on="codigo_ibge_estado", how="left", validate="many_to_one",
    )
    df_estacao = df_estacao.merge(
        cidade_ids,
        on=["codigo_ibge_cidade", "id_estado"], how="left", validate="many_to_one",
    )
    if df_estacao[["id_estado", "id_cidade"]].isna().any().any():
        raise ValueError("Estação com cidade ou estado não encontrado no banco")
    df_estacao = df_estacao.rename(columns={"status_estacao": "status"})[
        ["nome", "status", "id_estado", "id_cidade"]
    ]
    if modo_carga == "append":
        # No modo append, evita duplicar estações já cadastradas.
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
        df_estacao.to_sql("estacao", connection, if_exists="append", index=False)


if __name__ == "__main__":
    # Uma transação reverte as alterações se alguma FK não puder ser resolvida.
    with engine.begin() as connection:
        limpar_localizacao(connection)
        estado_ids = inserir_localizacao(connection)
        inserir_estacoes(connection, estado_ids)

    print("Dados inseridos com sucesso!")