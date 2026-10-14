import logging
import unicodedata
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
COLUNAS_COMPARACAO_RETRANSMISSAO = [
    "id_cidade",
    "temperatura_ar",
    "umidade",
    "chuva",
    "vento",
    "condicao",
]


def _normalizar_localidade(valor: object) -> str:
    texto = "" if pd.isna(valor) else str(valor).strip().casefold()
    decomposicao = unicodedata.normalize("NFKD", texto)
    return "".join(
        caractere
        for caractere in decomposicao
        if not unicodedata.combining(caractere)
    )


def _normalizar_valor_retransmissao(coluna: str, valor: object) -> object:
    if pd.isna(valor):
        return None
    if coluna == "data_leitura":
        instante = pd.to_datetime(valor, utc=True, errors="coerce")
        return None if pd.isna(instante) else instante.isoformat()
    if coluna in COLUNAS_COMPARACAO_RETRANSMISSAO and coluna != "condicao":
        return round(float(valor), 3)
    return str(valor).strip()


def validar_unicidade_persistida(connection) -> None:
    """Rejeita chaves naturais meteorologicas repetidas ja persistidas."""
    # 3.2 Unicidade: valida retransmissoes historicas antes da nova carga.
    duplicada = connection.execute(
        text(
            "SELECT id_estacao, data_leitura FROM leitura_meteorologica "
            "GROUP BY id_estacao, data_leitura HAVING COUNT(*) > 1"
        )
    ).first()
    if duplicada is not None:
        raise ValueError(
            "3.2 Unicidade: leitura_meteorologica possui chaves naturais duplicadas."
        )


def filtrar_retransmissoes(
    df_leituras: pd.DataFrame, connection
) -> pd.DataFrame:
    """Remove retransmissoes por estacao e instante, inclusive ja persistidas."""
    chave = ["id_estacao", "data_leitura"]
    rejeicoes_consistencia = int(
        df_leituras.attrs.get("silver_consistency_rejections", 0)
    )
    df_leituras = df_leituras.copy()
    if df_leituras.empty:
        df_leituras.attrs["silver_consistency_rejections"] = rejeicoes_consistencia
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
    conflitos_lote = 0
    for id_estacao, data_leitura in (
        df_leituras.loc[duplicadas_lote, chave]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    ):
        grupo = df_leituras.loc[
            df_leituras["id_estacao"].eq(id_estacao)
            & df_leituras["data_leitura"].eq(data_leitura)
        ]
        primeira = grupo.iloc[0]
        quantidade_conflitante = sum(
            any(
                _normalizar_valor_retransmissao(coluna, leitura[coluna])
                != _normalizar_valor_retransmissao(coluna, primeira[coluna])
                for coluna in colunas_comparacao
            )
            for _, leitura in grupo.iloc[1:].iterrows()
        )
        if quantidade_conflitante:
            conflitos_lote += quantidade_conflitante
            logging.warning(
                "Retransmissao meteorologica conflitante no lote; "
                "rejeitando versoes divergentes e mantendo primeira: "
                "id_estacao=%s, data_leitura=%s, rejeitadas=%s",
                id_estacao,
                data_leitura,
                quantidade_conflitante,
            )
    if duplicadas_lote.any():
        logging.info(
            "Duplicatas meteorologicas removidas do lote: quantidade=%s",
            int(duplicadas_lote.sum()),
        )
    df_leituras = df_leituras.drop_duplicates(subset=chave, keep="first")
    rejeicoes_consistencia += conflitos_lote

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
                "SELECT id_estacao, data_leitura, id_cidade, temperatura_ar, "
                "umidade, chuva, vento, condicao "
                "FROM leitura_meteorologica WHERE "
                + " OR ".join(condicoes)
            )
            consulta_existentes.extend(connection.execute(consulta, parametros))
        else:
            ids_estacao = sorted({int(id_estacao) for id_estacao, _ in lote})
            consulta = text(
                "SELECT id_estacao, data_leitura, id_cidade, temperatura_ar, "
                "umidade, chuva, vento, condicao FROM leitura_meteorologica "
                "WHERE id_estacao IN :ids_estacao"
            ).bindparams(bindparam("ids_estacao", expanding=True))
            consulta_existentes.extend(
                connection.execute(consulta, {"ids_estacao": ids_estacao})
            )

    registros_existentes = {
        (
            int(row.id_estacao),
            pd.to_datetime(row.data_leitura, utc=True).isoformat(),
        ): row._mapping
        for row in consulta_existentes
    }
    novas = []
    conflitos_persistidos = 0
    ignoradas = 0
    for _, leitura in df_leituras.iterrows():
        chave_leitura = (
            int(leitura["id_estacao"]),
            pd.Timestamp(leitura["data_leitura"]).isoformat(),
        )
        existente = registros_existentes.get(chave_leitura)
        if existente is None:
            novas.append(True)
            continue

        novas.append(False)
        payload_conflitante = any(
            _normalizar_valor_retransmissao(coluna, leitura[coluna])
            != _normalizar_valor_retransmissao(coluna, existente[coluna])
            for coluna in COLUNAS_COMPARACAO_RETRANSMISSAO
        )
        if payload_conflitante:
            conflitos_persistidos += 1
            logging.warning(
                "Retransmissao meteorologica conflitante ignorada; "
                "mantendo registro existente: id_estacao=%s, data_leitura=%s",
                leitura["id_estacao"],
                leitura["data_leitura"],
            )
        else:
            ignoradas += 1

    if ignoradas:
        logging.info(
            "Retransmissoes meteorologicas ja persistidas ignoradas: quantidade=%s",
            ignoradas,
        )
    rejeicoes_consistencia += conflitos_persistidos
    resultado = df_leituras.loc[novas].reset_index(drop=True)
    resultado.attrs["silver_consistency_rejections"] = rejeicoes_consistencia
    return resultado

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
            "SELECT estacao.id AS id_estacao, estacao.id_cidade, "
            "estacao.id_estado AS id_estado_estacao, "
            "cidade.id_estado AS id_estado_cidade, "
            "cidade.nome AS nome_cidade, estado.nome AS nome_estado, "
            "estado.sigla AS sigla_estado "
            "FROM estacao "
            "JOIN cidade ON cidade.id = estacao.id_cidade "
            "JOIN estado ON estado.id = cidade.id_estado"
        ),
        connection,
    )

    rejeicoes_consistencia = int(
        df_leituras.attrs.get("silver_consistency_rejections", 0)
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

    divergente = pd.Series(False, index=df_leituras.index)
    divergente |= df_leituras["id_estado_estacao"].ne(
        df_leituras["id_estado_cidade"]
    )
    if "cidade" in df_leituras.columns:
        cidade_origem = df_leituras["cidade"].map(_normalizar_localidade)
        cidade_cadastro = df_leituras["nome_cidade"].map(_normalizar_localidade)
        cidade_informada = cidade_origem.ne("")
        divergente |= cidade_informada & cidade_origem.ne(cidade_cadastro)
    if "estado" in df_leituras.columns:
        estado_origem = df_leituras["estado"].map(_normalizar_localidade)
        estado_nome = df_leituras["nome_estado"].map(_normalizar_localidade)
        estado_sigla = df_leituras["sigla_estado"].map(_normalizar_localidade)
        estado_informado = estado_origem.ne("")
        divergente |= (
            estado_informado
            & estado_origem.ne(estado_nome)
            & estado_origem.ne(estado_sigla)
        )

    quantidade_divergente = int(divergente.sum())
    if quantidade_divergente:
        logging.warning(
            "Leituras meteorologicas rejeitadas por localizacao divergente "
            "do cadastro: quantidade=%s, estacoes=%s",
            quantidade_divergente,
            sorted(df_leituras.loc[divergente, "id_estacao"].unique().tolist()),
        )
        rejeicoes_consistencia += quantidade_divergente

    resultado = df_leituras.loc[~divergente].drop(
        columns=[
            "cidade",
            "estado",
            "nome_cidade",
            "nome_estado",
            "sigla_estado",
            "id_estado_estacao",
            "id_estado_cidade",
        ],
        errors="ignore",
    )
    resultado.attrs["silver_consistency_rejections"] = rejeicoes_consistencia
    return resultado


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
            validar_unicidade_persistida(connection)
            df_dados = filtrar_retransmissoes(df_dados, connection)
            rejeicoes_consistencia = int(
                df_dados.attrs.get("silver_consistency_rejections", 0)
            )
            if df_dados.empty:
                if rejeicoes_consistencia:
                    persistir_silver(
                        df_dados,
                        "leitura_meteorologica",
                        rejeicoes_consistencia=rejeicoes_consistencia,
                    )
                return

            # 3.2 Persistencia (itens 35-36): grava leituras limpas e enriquecidas na Silver.
            persistir_silver(
                df_dados,
                "leitura_meteorologica",
                rejeicoes_consistencia=rejeicoes_consistencia,
            )

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
    configure_logging(Path(__file__).resolve().parents[3], categoria="insercao")
    inserir_dados()