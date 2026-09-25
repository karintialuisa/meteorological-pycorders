# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path
from time import strftime

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

from datetime import datetime

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON e obter o arquivo JSON
# 5. 1. Caminho para o arquivo JSON de monitoramento ambiental
DIR_ambiental_JSON = DIR_PARSE / "leituras_ambientais.json"

# 5. 2. Caminho para o arquivo JSON de monitoramento meteorológico
DIR_meteorologicas_JSON = DIR_PARSE / "leituras_meteorologicas.json"

# 6. Agora vamos abrir e ler o arquivo
def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo
 
parse_ambiental = ler_json(DIR_ambiental_JSON)

parse_meteorologicas = ler_json(DIR_meteorologicas_JSON)


# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável

def tabela_localizacao() -> pd.DataFrame:
    df_ambiental = pd.json_normalize(parse_ambiental['leituras_ambientais'])[
            [
            "estacao_id",
            "timestamp", 
            "qualidade_agua.temperatura.valor",
            "qualidade_agua.ph.valor",
            "qualidade_agua.oxigenio_dissolvido.valor",
            "qualidade_agua.condutividade.valor"
            ]
        ].rename(columns={
                        "estacao_id": "id_estacao",
                        "timestamp": "data_leitura",
                        "qualidade_agua.temperatura.valor": "qualidade_agua_temperatura_valor",
                        "qualidade_agua.ph.valor": "qualidade_agua_ph_valor",
                        "qualidade_agua.oxigenio_dissolvido.valor": "qualidade_agua_oxigenio_valor",
                        "qualidade_agua.condutividade.valor": "qualidade_agua_condutividade_valor"
                        })

    # 8. Remover duplicatas do DataFrame ambiental
    df_ambiental = df_ambiental.drop_duplicates().reset_index(drop=True)

    # Ordena por estação, data e horário mais recente
    df_ambiental = df_ambiental.sort_values(["data_leitura"], ascending=False)

    # Verifica estação + data
    duplicados = df_ambiental[
        df_ambiental.duplicated(
            subset=["id_estacao", "data_leitura"],
            keep=False
        )
    ]

    # Se houver duplicatas, manter apenas a primeira ocorrência (mais recente)
    if not duplicados.empty:
        df_ambiental = df_ambiental.drop_duplicates(
            subset=["id_estacao", "data_leitura"],
            keep="first"
        ).reset_index(drop=True)

    df_ambiental["data_leitura"] = pd.to_datetime(df_ambiental["data_leitura"]).dt.strftime("%d/%m/%Y %H:%M")
        
    print(df_ambiental)
    return df_ambiental


tabela_localizacao()
#Caso precise da cidade, nos relatorios, fazer merge com tabela de estações para obter a cidade correspondente