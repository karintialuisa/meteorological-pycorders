"""Carga ambiental no modelo 3FN e na Silver, sem dual-write."""

import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, create_db_engine
from database.dml.Persistir_Medicoes import carregar_dataframe
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


def validar_unicidade_persistida(connection) -> None:
    """Rejeita dados existentes sem ID ou com ID de leitura repetido."""
    # 3.2 Unicidade: valida o legado antes de processar novas retransmissoes.
    sem_identidade = connection.execute(
        text(
            "SELECT 1 FROM qualidade_agua "
            "WHERE id_leitura_origem IS NULL "
            "OR LTRIM(RTRIM(id_leitura_origem)) = ''"
        )
    ).first()
    if sem_identidade is not None:
        raise ValueError(
            "3.2 Unicidade: qualidade_agua possui id_leitura_origem nulo ou vazio."
        )

    duplicada = connection.execute(
        text(
            "SELECT id_leitura_origem FROM qualidade_agua "
            "GROUP BY id_leitura_origem HAVING COUNT(*) > 1"
        )
    ).first()
    if duplicada is not None:
        raise ValueError(
            "3.2 Unicidade: qualidade_agua possui id_leitura_origem duplicado."
        )


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
        "temperatura_agua, ph, oxigenio, condutividade, turbidez "
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
        "turbidez",
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
    leituras = df_leituras.copy()
    leituras["estacao_id"] = leituras["estacao_id"].astype("string").str.strip()
    result = leituras.merge(
        estacoes, left_on="estacao_id", right_on="codigo_origem",
        how="left", validate="many_to_one",
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
            validar_unicidade_persistida(connection)
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
    configure_logging(categoria="insercao")
    inserir_dados()
