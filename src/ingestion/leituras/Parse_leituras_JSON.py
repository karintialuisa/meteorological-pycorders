import json
from pathlib import Path
import pandas as pd

# 1. Diretório base do script
DIR_PARSE = Path(__file__).resolve().parent

# 2. Caminho para o arquivo JSON de meteorologia
DIR_METEOROLOGIA_JSON = DIR_PARSE / "leituras_meteorologicas.json"


def ler_json(path_arquivo: Path) -> dict:
    """Lê um arquivo JSON e retorna seu conteúdo como dicionário."""
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo


def tabela_meteorologica() -> pd.DataFrame:
    """Carrega o arquivo JSON meteorológico, realiza todo o parse, limpeza e
    tratamento de tipos dos dados para corresponder à tabela leiturameteorologica.
    """
    parse_meteo = ler_json(DIR_METEOROLOGIA_JSON)

    # 1. Normalização do JSON e seleção/renomeação das colunas
    df_meteo = pd.json_normalize(parse_meteo["leituras_meteorologicas"])[
        [
            "cidade",
            "timestamp",
            "dados_meteorologicos.temperatura_ar.valor",
            "dados_meteorologicos.umidade.valor",
            "dados_meteorologicos.chuva.valor",
            "dados_meteorologicos.vento.velocidade",
            "dados_meteorologicos.condicao.description",
        ]
    ].rename(
        columns={
            "timestamp": "data_leitura",
            "dados_meteorologicos.temperatura_ar.valor": "temperatura_ar",
            "dados_meteorologicos.umidade.valor": "umidade",
            "dados_meteorologicos.chuva.valor": "chuva",
            "dados_meteorologicos.vento.velocidade": "vento",
            "dados_meteorologicos.condicao.description": "condicao",
        }
    )

    # 2. Remoção de duplicatas exatas
    df_meteo = df_meteo.drop_duplicates().reset_index(drop=True)

    # 3. Ordenação para priorizar o registro mais recente em caso de duplicatas
    df_meteo = df_meteo.sort_values(["data_leitura"], ascending=False)

    # 4. Tratamento de duplicatas mantendo apenas o registro mais recente por cidade/data
    df_meteo = df_meteo.drop_duplicates(
        subset=["cidade", "data_leitura"], keep="first"
    ).reset_index(drop=True)

    # =========================================================================
    # TRATAMENTO E CONVERSÃO DE TIPOS (DTYPES)
    # =========================================================================
    df_meteo["data_leitura"] = pd.to_datetime(df_meteo["data_leitura"])

    colunas_numericas = ["temperatura_ar", "umidade", "chuva", "vento"]
    for col in colunas_numericas:
        df_meteo[col] = pd.to_numeric(df_meteo[col], errors="coerce")

    return df_meteo


if __name__ == "__main__":
    df = tabela_meteorologica()
    print("Preview do DataFrame tratado:")
    print(df.head())