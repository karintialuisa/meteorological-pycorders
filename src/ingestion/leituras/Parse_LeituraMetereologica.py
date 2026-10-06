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

    df_metereologica = df_metereologica.drop_duplicates().reset_index(drop=True)

    # Ordenação para priorizar o registro mais recente em caso de duplicatas
    df_metereologica = df_metereologica.sort_values(["data_leitura"], ascending=False)

    # Tratamento de duplicatas mantendo apenas o registro mais recente por cidade/data
    df_metereologica = df_metereologica.drop_duplicates(
        subset=["estacao_id", "cidade", "estado", "data_leitura"], keep="first"
    ).reset_index(drop=True)   

    # =========================================================================
    # TRATAMENTO E CONVERSÃO DE TIPOS (DTYPES)
    # =========================================================================
    df_metereologica["data_leitura"] = pd.to_datetime(
        df_metereologica["data_leitura"], utc=True
    )

    colunas_numericas = ["temperatura_ar", "umidade", "chuva", "vento"]
    for col in colunas_numericas:
        df_metereologica[col] = pd.to_numeric(df_metereologica[col], errors="coerce")


    return df_metereologica 



if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    configure_logging(Path(__file__).resolve().parents[3])
    df = tabela_metereologica()
    logging.info("Preview do DataFrame tratado:\n%s", df.head())
