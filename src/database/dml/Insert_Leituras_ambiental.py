
"""Carga das leituras ambientais no banco de dados.

Este módulo lê os dados de qualidade da água tratados em JSON, resolve os IDs
de estação no banco e insere os registros na tabela qualidade_agua.
"""
import logging

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, text


sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import PROJECT_ROOT, configure_logging, create_db_engine
from database.dml.etl_lock import adquirir_lock_etl

from ingestion.leituras.Parse_LeituraAmbiental import tabela_ambiental
from ingestion.leituras.Persistir_Silver import persistir_silver
from ingestion.localizacao.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estacao,
    tabela_estado,
)

BASE_DIR = PROJECT_ROOT

tabela_destino = "qualidade_agua"
modo_carga = "append"
TAMANHO_LOTE_CONSULTA = 1000


def filtrar_retransmissoes(
    df_leituras: pd.DataFrame, connection
) -> pd.DataFrame:
    """Remove IDs já persistidos e audita retransmissões conflitantes."""
    df_leituras = df_leituras.copy()
    quantidade_recebida = len(df_leituras)
    if "id_leitura_origem" not in df_leituras:
        logging.error("Carga ambiental rejeitada: coluna id_leitura_origem ausente.")
        return df_leituras.iloc[0:0].copy()

    ids = df_leituras["id_leitura_origem"].apply(
        lambda valor: "" if pd.isna(valor) else str(valor).strip()
    )
    sem_id = ids.eq("")
    for leitura in df_leituras.loc[sem_id].to_dict("records"):
        logging.warning(
            "Leitura ambiental rejeitada por falta de identidade idempotente: "
            "estacao_id=%s, data_leitura=%s",
            leitura.get("estacao_id"),
            leitura.get("data_leitura"),
        )
    df_leituras = df_leituras.loc[~sem_id].copy()
    df_leituras["id_leitura_origem"] = ids.loc[~sem_id]
    if df_leituras.empty:
        logging.info(
            "Deduplicação ambiental: recebidos=%s, novos=0, "
            "retransmissoes_ignoradas=0, rejeitadas_sem_id=%s",
            quantidade_recebida,
            int(sem_id.sum()),
        )
        return df_leituras

    duplicados_lote = df_leituras["id_leitura_origem"].duplicated(keep="first")
    retransmissoes_lote = int(duplicados_lote.sum())
    if duplicados_lote.any():
        for leitura_id in df_leituras.loc[
            duplicados_lote, "id_leitura_origem"
        ].unique():
            grupo = df_leituras.loc[
                df_leituras["id_leitura_origem"].eq(leitura_id)
            ]
            if len(grupo.drop(columns="id_leitura_origem").drop_duplicates()) > 1:
                logging.warning(
                    "Retransmissão conflitante no lote; mantendo primeira leitura: "
                    "id_leitura_origem=%s",
                    leitura_id,
                )
        df_leituras = df_leituras.drop_duplicates(
            subset=["id_leitura_origem"], keep="first"
        )

    consulta = text(
        "SELECT id_leitura_origem, id_estacao, data_leitura, "
        "temperatura_agua, ph, oxigenio, condutividade "
        "FROM qualidade_agua WHERE id_leitura_origem IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    existentes = {}
    leitura_ids = df_leituras["id_leitura_origem"].tolist()
    for inicio in range(0, len(leitura_ids), TAMANHO_LOTE_CONSULTA):
        lote_ids = leitura_ids[inicio : inicio + TAMANHO_LOTE_CONSULTA]
        for row in connection.execute(consulta, {"ids": lote_ids}):
            existentes[row.id_leitura_origem] = row._mapping

    colunas_comparacao = [
        "id_estacao",
        "data_leitura",
        "temperatura_agua",
        "ph",
        "oxigenio",
        "condutividade",
    ]

    def normalizar(coluna, valor):
        if pd.isna(valor):
            return None
        if coluna == "data_leitura":
            data = pd.to_datetime(valor, errors="coerce", utc=True)
            return None if pd.isna(data) else data.isoformat()
        if coluna == "id_estacao":
            return int(valor)
        return round(float(valor), 3)

    inserir = []
    retransmissoes = 0
    for leitura in df_leituras.to_dict("records"):
        existente = existentes.get(leitura["id_leitura_origem"])
        if existente is None:
            inserir.append(leitura)
            continue

        retransmissoes += 1
        conflitante = any(
            normalizar(coluna, leitura.get(coluna))
            != normalizar(coluna, existente[coluna])
            for coluna in colunas_comparacao
        )
        if conflitante:
            logging.warning(
                "Retransmissão conflitante ignorada; mantendo registro existente: "
                "id_leitura_origem=%s",
                leitura["id_leitura_origem"],
            )
        else:
            logging.info(
                "Retransmissão ignorada: id_leitura_origem=%s",
                leitura["id_leitura_origem"],
            )

    logging.info(
        "Deduplicação ambiental: recebidos=%s, novos=%s, "
        "retransmissoes_ignoradas=%s, rejeitadas_sem_id=%s",
        quantidade_recebida,
        len(inserir),
        retransmissoes + retransmissoes_lote,
        int(sem_id.sum()),
    )
    if not inserir:
        return df_leituras.iloc[0:0].copy()
    return pd.DataFrame(inserir, columns=df_leituras.columns).reset_index(drop=True)



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
    df_estacao["id"] = df_estacao["id"].astype("string").str.strip()
    if df_estacao["id"].isna().any() or df_estacao["id"].eq("").any():
        raise ValueError("Código de estação ausente em estacoes.json")
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
    df_leituras["estacao_id"] = (
        df_leituras["estacao_id"].astype("string").str.strip()
    )

    df_leituras = df_leituras.merge(
        df_estacao[["id", "id_estacao"]],
        left_on="estacao_id",
        right_on="id",
        how="left",
        validate="many_to_one",
    )

    sem_estacao = df_leituras.loc[df_leituras["id_estacao"].isna()]
    for leitura in sem_estacao.to_dict("records"):
        logging.warning(
            "Leitura ambiental rejeitada por estação sem correspondência: "
            "id_leitura_origem=%s, estacao_id=%s, data_leitura=%s",
            leitura.get("id_leitura_origem"),
            leitura.get("estacao_id"),
            leitura.get("data_leitura"),
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

            # 3.2 Auditoria (item 27): serializa cargas cooperantes antes do check-and-insert.
            adquirir_lock_etl(connection, "etl:qualidade_agua")
            df_dados = filtrar_retransmissoes(df_dados, connection)
            if df_dados.empty:
                return

            # 3.2 Persistencia (itens 35-36): grava leituras limpas e enriquecidas na Silver.
            persistir_silver(df_dados, "qualidade_agua")

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

    except Exception:
        logging.exception("Erro durante a inserção dos dados")
        raise


if __name__ == "__main__":
    configure_logging(BASE_DIR)
    inserir_dados()