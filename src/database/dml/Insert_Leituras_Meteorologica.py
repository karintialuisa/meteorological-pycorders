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
from sqlalchemy import bindparam, text
from database.dml.etl_lock import adquirir_lock_etl
from database.dml.Insert_Leituras_ambiental import resolver_id_estacao
from ingestion.leituras.Parse_LeituraMetereologica import tabela_metereologica
from ingestion.leituras.Persistir_Silver import persistir_silver


tabeladestino = "leitura_meteorologica"
modocarga = "append"
TAMANHO_LOTE_CHAVES = 400


def filtrar_retransmissoes(
    df_leituras: pd.DataFrame, connection
) -> pd.DataFrame:
    """Remove retransmissoes por estacao e instante, inclusive ja persistidas."""
    chave = ["id_estacao", "data_leitura"]
    df_leituras = df_leituras.copy()
    if df_leituras.empty:
        return df_leituras

    df_leituras["data_leitura"] = pd.to_datetime(
        df_leituras["data_leitura"], utc=True, errors="coerce"
    )
    sem_chave = df_leituras[chave].isna().any(axis=1)
    if sem_chave.any():
        logging.warning(
            "Leituras meteorologicas rejeitadas por chave incompleta: quantidade=%s",
            int(sem_chave.sum()),
        )
        df_leituras = df_leituras.loc[~sem_chave].copy()
    if df_leituras.empty:
        return df_leituras

    duplicadas_lote = df_leituras.duplicated(subset=chave, keep="first")
    colunas_comparacao = [
        coluna for coluna in df_leituras.columns if coluna not in chave
    ]
    for id_estacao, data_leitura in (
        df_leituras.loc[duplicadas_lote, chave]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    ):
        grupo = df_leituras.loc[
            df_leituras["id_estacao"].eq(id_estacao)
            & df_leituras["data_leitura"].eq(data_leitura)
        ]
        if len(grupo[colunas_comparacao].drop_duplicates()) > 1:
            logging.warning(
                "Retransmissao meteorologica conflitante no lote; "
                "mantendo primeira: id_estacao=%s, data_leitura=%s",
                id_estacao,
                data_leitura,
            )
    if duplicadas_lote.any():
        logging.info(
            "Duplicatas meteorologicas removidas do lote: quantidade=%s",
            int(duplicadas_lote.sum()),
        )
    df_leituras = df_leituras.drop_duplicates(subset=chave, keep="first")

    consulta_existentes = []
    chaves = list(df_leituras[chave].itertuples(index=False, name=None))
    for inicio in range(0, len(chaves), TAMANHO_LOTE_CHAVES):
        lote = chaves[inicio : inicio + TAMANHO_LOTE_CHAVES]
        if connection.dialect.name == "mssql":
            condicoes = []
            parametros = {}
            for indice, (id_estacao, data_leitura) in enumerate(lote):
                nome_estacao = f"estacao_{indice}"
                nome_data = f"data_{indice}"
                timestamp = pd.Timestamp(data_leitura)
                expressao_data = f"CONVERT(datetimeoffset, :{nome_data}, 127)"
                condicoes.append(
                    f"(id_estacao = :{nome_estacao} AND "
                    f"data_leitura = {expressao_data})"
                )
                parametros[nome_estacao] = int(id_estacao)
                parametros[nome_data] = timestamp.isoformat()

            consulta = text(
                "SELECT id_estacao, data_leitura FROM leitura_meteorologica WHERE "
                + " OR ".join(condicoes)
            )
            consulta_existentes.extend(connection.execute(consulta, parametros))
        else:
            ids_estacao = sorted({int(id_estacao) for id_estacao, _ in lote})
            consulta = text(
                "SELECT id_estacao, data_leitura FROM leitura_meteorologica "
                "WHERE id_estacao IN :ids_estacao"
            ).bindparams(bindparam("ids_estacao", expanding=True))
            consulta_existentes.extend(
                connection.execute(consulta, {"ids_estacao": ids_estacao})
            )

    chaves_existentes = {
        (
            int(row.id_estacao),
            pd.to_datetime(row.data_leitura, utc=True).isoformat(),
        )
        for row in consulta_existentes
    }
    novas = df_leituras.apply(
        lambda leitura: (
            int(leitura["id_estacao"]),
            pd.Timestamp(leitura["data_leitura"]).isoformat(),
        )
        not in chaves_existentes,
        axis=1,
    )
    ignoradas = int((~novas).sum())
    if ignoradas:
        logging.info(
            "Retransmissoes meteorologicas ja persistidas ignoradas: quantidade=%s",
            ignoradas,
        )
    return df_leituras.loc[novas].reset_index(drop=True)

def resolver_id_cidade(df_leituras: pd.DataFrame, connection) -> pd.DataFrame:
    """Resolve a cidade a partir da estação já cadastrada no banco.

    Args:
        df_leituras (pd.DataFrame): DataFrame contendo as leituras meteorológicas.
        connection: Conexão ativa com o banco de dados SQL Server.

    Returns:
        pd.DataFrame: DataFrame enriquecido com o id_cidade do banco.
    """
    if "id_estacao" not in df_leituras.columns:
        raise KeyError("Coluna id_estacao ausente no DataFrame meteorológico")

    cidades_estacoes_banco = pd.read_sql(
        text(
            "SELECT id AS id_estacao, id_cidade "
            "FROM estacao"
        ),
        connection,
    )

    df_leituras = df_leituras.merge(
        cidades_estacoes_banco,
        on="id_estacao",
        how="left",
        validate="many_to_one",
    )

    sem_cidade = df_leituras.loc[df_leituras["id_cidade"].isna(), "id_estacao"]
    if not sem_cidade.empty:
        raise ValueError(
            "Estações sem cidade cadastrada no banco: "
            f"{sorted(sem_cidade.unique())}"
        )

    return df_leituras.drop(columns=["cidade", "estado"], errors="ignore")


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
            df_dados = resolver_id_estacao(df_dados, connection)
            df_dados = resolver_id_cidade(df_dados, connection)

            # 3.2 Auditoria (item 27): lock transacional antes do check-and-insert.
            adquirir_lock_etl(connection, "etl:leitura_meteorologica")
            df_dados = filtrar_retransmissoes(df_dados, connection)
            if df_dados.empty:
                return

            # 3.2 Persistencia (itens 35-36): grava leituras limpas e enriquecidas na Silver.
            persistir_silver(df_dados, "leitura_meteorologica")

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

    except Exception:
        logging.exception("Erro ao inserir dados")
        raise


if __name__ == "__main__":
    configure_logging(Path(__file__).resolve().parents[3])
    inserir_dados()