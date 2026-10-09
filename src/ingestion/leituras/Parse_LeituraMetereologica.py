"""Parsing e normalização das leituras meteorológicas.

Este módulo lê o arquivo JSON de registros meteorológicos, achata os campos
aninhados, converte os tipos necessários e prepara o DataFrame para a carga no
banco de dados.
"""

# 1. Biblioteca para manipulação de arquivos JSON
import json
import logging

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, get_path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Biblioteca para conexão com o banco de dados SQL Server Express e execução de queries  
from sqlalchemy.engine import Connection
from sqlalchemy import create_engine, text

# 4. Diretório para os arquivos JSON
# 5. criar função e ler o arquivo JSON de leituras meteorológicas
def ler_json(path_arquivo):
    """Lê um arquivo JSON de leituras meteorológicas.

    Args:
        path_arquivo: Caminho do arquivo JSON a ser lido.

    Returns:
        object: Conteúdo carregado do arquivo JSON.
    """
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo

# 6. Função para criar o DataFrame a partir do JSON de leituras meteorológicas
def tabela_metereologica() -> pd.DataFrame:
    """Cria e trata o DataFrame com as leituras meteorológicas.

    O processo inclui normalização dos dados aninhados, preservação de
    `estacao_id`, remoção de duplicatas, ordenação e conversão dos campos numéricos.

    Returns:
        pd.DataFrame: DataFrame pronto para persistência no banco de dados.
    """
    # 1. Normalização do JSON e seleção/renomeação das colunas
    parse_metereologica = ler_json(get_path("INGESTION_LEITURA_METEOROLOGICA"))

    registros = pd.json_normalize(parse_metereologica["leituras_meteorologicas"])
    if "estacao_id" not in registros.columns:
        raise KeyError("Campo obrigatório ausente no JSON meteorológico: estacao_id")

    df_metereologica = registros[[
            "estacao_id",
            "cidade",
            "estado",
            "timestamp",
            "dados_meteorologicos.temperatura_ar.valor",
            "dados_meteorologicos.condicao.description",
            "dados_meteorologicos.umidade.valor",
            "dados_meteorologicos.chuva.valor",
            "dados_meteorologicos.vento.velocidade"
        ]].rename(
            columns={
                "timestamp": "data_leitura",
                "dados_meteorologicos.temperatura_ar.valor": "temperatura_ar",
                "dados_meteorologicos.condicao.description": "condicao",
                "dados_meteorologicos.umidade.valor": "umidade",
                "dados_meteorologicos.chuva.valor": "chuva",
                "dados_meteorologicos.vento.velocidade": "vento"
            })

    # 3.2 Auditoria (itens 26-31): completude, unicidade, validade, tempo e consistencia.
    df_metereologica["estacao_id"] = (
        df_metereologica["estacao_id"].astype("string").str.strip()
    )
    # Tempestividade (item 30): converter para UTC antes de ordenar ou deduplicar.
    df_metereologica["data_leitura"] = pd.to_datetime(
        df_metereologica["data_leitura"], utc=True, errors="coerce"
    )

    colunas_numericas = ["temperatura_ar", "umidade", "chuva", "vento"]
    for col in colunas_numericas:
        df_metereologica[col] = pd.to_numeric(df_metereologica[col], errors="coerce")

    # Acuracia e validade (item 29): limites fisicos de temperatura, umidade, chuva e vento.
    campos_invalidos = pd.DataFrame(
        {
            "temperatura_ar": (df_metereologica["temperatura_ar"] < -50)
            | (df_metereologica["temperatura_ar"] > 60),
            "umidade": (df_metereologica["umidade"] < 0)
            | (df_metereologica["umidade"] > 100),
            "chuva": df_metereologica["chuva"] < 0,
            "vento": df_metereologica["vento"] < 0,
        },
        index=df_metereologica.index,
    )

    colunas_obrigatorias = [
        "estacao_id",
        "cidade",
        "estado",
        "data_leitura",
        "temperatura_ar",
        "condicao",
        "umidade",
        "chuva",
        "vento",
    ]
    campos_texto = ["estacao_id", "cidade", "estado", "condicao"]
    campos_vazios = df_metereologica[colunas_obrigatorias].isna()
    for coluna in campos_texto:
        campos_vazios[coluna] |= (
            df_metereologica[coluna].astype("string").str.strip().eq("").fillna(True)
        )

    campos_rejeicao = campos_vazios.copy()
    for coluna in campos_invalidos.columns:
        campos_rejeicao[coluna] |= campos_invalidos[coluna]

    rejeitadas = campos_rejeicao.any(axis=1)
    for indice, leitura in df_metereologica.loc[rejeitadas].iterrows():
        campos = campos_rejeicao.columns[campos_rejeicao.loc[indice]].tolist()
        valores = {campo: leitura[campo] for campo in campos}
        logging.error(
            "Leitura meteorológica rejeitada por campo obrigatório vazio ou inválido: "
            "estacao_id=%s, data_leitura=%s, campos=%s, valores=%s",
            leitura["estacao_id"],
            leitura["data_leitura"],
            campos,
            valores,
        )

    # Unicidade (item 27): a chave e estacao + instante UTC; mantem a primeira ocorrencia.
    df_validas = df_metereologica.loc[~rejeitadas].copy()
    chave = ["estacao_id", "data_leitura"]
    duplicadas = df_validas.duplicated(subset=chave, keep="first")
    colunas_comparacao = [
        coluna for coluna in df_validas.columns if coluna not in chave
    ]

    for estacao_id, data_leitura in (
        df_validas.loc[duplicadas, chave].drop_duplicates().itertuples(
            index=False, name=None
        )
    ):
        grupo = df_validas.loc[
            df_validas["estacao_id"].eq(estacao_id)
            & df_validas["data_leitura"].eq(data_leitura)
        ]
        if len(grupo[colunas_comparacao].drop_duplicates()) > 1:
            logging.warning(
                "Retransmissao meteorologica conflitante; mantendo primeira: "
                "estacao_id=%s, data_leitura=%s, ocorrencias=%s",
                estacao_id,
                data_leitura,
                len(grupo),
            )

    if duplicadas.any():
        logging.info(
            "Duplicatas removidas do lote meteorologico: quantidade=%s",
            int(duplicadas.sum()),
        )

    df_validas = df_validas.drop_duplicates(subset=chave, keep="first")
    # Tempestividade (item 30): a ordenacao final usa o instante UTC validado.
    return df_validas.sort_values(
        "data_leitura", ascending=False, kind="stable"
    ).reset_index(drop=True)



if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    configure_logging(Path(__file__).resolve().parents[3])
    df = tabela_metereologica()
    logging.info("Preview do DataFrame tratado:\n%s", df.head())
