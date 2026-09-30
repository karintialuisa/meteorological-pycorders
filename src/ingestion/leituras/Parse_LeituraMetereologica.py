# ======================================================================================================
# ASSUNTO: Conexão com o banco de dados SQL Server Express
# Preparação e criação do DataFrame para as tabelas leituras meteorológicas
# ======================================================================================================


# 1. Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from multiprocessing import connection
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Biblioteca para conexão com o banco de dados SQL Server Express e execução de queries  
from sqlalchemy.engine import Connection
from sqlalchemy import create_engine, text

# 4. Diretório para os arquivos JSON
DIR_LEITURA_METEREOLOGICA = Path(__file__).resolve().parent / "leituras_meteorologicas.json"

# 5. criar função e ler o arquivo JSON de leituras meteorológicas
def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo

# 6. Função para criar o DataFrame a partir do JSON de leituras meteorológicas
def tabela_metereologica() -> pd.DataFrame:
    """Carrega o arquivo JSON meteorológico, realiza todo o parse, limpeza e
    tratamento de tipos dos dados para corresponder à tabela leiturameteorologica.
    """
    # 1. Normalização do JSON e seleção/renomeação das colunas
    parse_metereologica = ler_json(DIR_LEITURA_METEREOLOGICA)

    df_metereologica = pd.json_normalize(
        parse_metereologica["leituras_meteorologicas"]
        )[[
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
        subset=["cidade", "estado", "data_leitura"], keep="first"
    ).reset_index(drop=True)   

    # =========================================================================
    # TRATAMENTO E CONVERSÃO DE TIPOS (DTYPES)
    # =========================================================================
    df_metereologica["data_leitura"] = pd.to_datetime(df_metereologica["data_leitura"])

    colunas_numericas = ["temperatura_ar", "umidade", "chuva", "vento"]
    for col in colunas_numericas:
        df_metereologica[col] = pd.to_numeric(df_metereologica[col], errors="coerce")


    return df_metereologica 



if __name__ == "__main__":
    df = tabela_metereologica()
    print("Preview do DataFrame tratado:")
    print(df.head())
