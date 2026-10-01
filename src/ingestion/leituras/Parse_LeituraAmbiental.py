"""Parsing e normalização das leituras ambientais.

Este módulo lê as leituras de qualidade da água em formato JSON, achata os
campos aninhados e prepara um DataFrame pronto para inserção no banco.
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

# 4. Diretório para os arquivos JSON
# 5. criar função e ler o arquivo JSON de leituras meteorológicas
def ler_json(path_arquivo):
    """Lê um arquivo JSON de leituras ambientais.

    Args:
        path_arquivo: Caminho do arquivo JSON a ser lido.

    Returns:
        object: Conteúdo carregado do arquivo JSON.
    """
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo

# 6. Função para criar o DataFrame a partir do JSON de leituras meteorológicas
def tabela_ambiental() -> pd.DataFrame:
    """Cria e trata o DataFrame com as leituras ambientais.

    O processo inclui normalização dos dados aninhados, remoção de registros
    duplicados por estação e data e conversão da coluna de tempo para datetime.

    Returns:
        pd.DataFrame: DataFrame pronto para inserção no banco de dados.
    """
    # 1. Normalização do JSON e seleção/renomeação das colunas
    parse_ambiental = ler_json(get_path("INGESTION_LEITURA_AMBIENTAL"))

    df_ambiental = pd.json_normalize(
        parse_ambiental["leituras_ambientais"]
        )[[
            "estacao_id",
            "timestamp", 
            "qualidade_agua.temperatura.valor",
            "qualidade_agua.ph.valor",
            "qualidade_agua.oxigenio_dissolvido.valor",
            "qualidade_agua.condutividade.valor",
        ]].rename(
            columns={
            # Substitui os caminhos longos das propriedades JSON por nomes curtos e descritivos.
            "timestamp": "data_leitura",
            "qualidade_agua.temperatura.valor": "temperatura_agua",
            "qualidade_agua.ph.valor": "ph",
            "qualidade_agua.oxigenio_dissolvido.valor": "oxigenio",
            "qualidade_agua.condutividade.valor": "condutividade"
            })

    df_ambiental = df_ambiental.drop_duplicates().reset_index(drop=True)

    # Ordenação para priorizar o registro mais recente em caso de duplicatas
    df_ambiental = df_ambiental.sort_values(["data_leitura"], ascending=False)

    # Tratamento de duplicatas mantendo apenas o registro mais recente por cidade/data
    df_ambiental = df_ambiental.drop_duplicates(
        subset=["estacao_id", "data_leitura"],
        keep="first"
    ).reset_index(drop=True)   

    df_ambiental["data_leitura"] = pd.to_datetime(
        df_ambiental["data_leitura"], utc=True
    )

    return df_ambiental 

if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    configure_logging(Path(__file__).resolve().parents[3])
    df = tabela_ambiental()
    logging.info("Preview do DataFrame tratado:\n%s", df.head())
