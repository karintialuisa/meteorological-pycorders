# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

DIR_JSON = DIR_PARSE / 'src' / "ingestion" / "monitoramento_ambiental.json"


#------------
# 5. Diretório para o arquivo JSON e obter o arquivo JSON
DIR_JSON = DIR_PARSE / "ingestion" / "monitoramento_ambiental.json"
#------------


# 6. Agora vamos abrir e ler o arquivo
with open(DIR_JSON, "r", encoding="utf-8") as arquivo: 
    parse_json = json.load(arquivo)
# print(parse_json)

#-----------------------------------------------------------------------------------------------------
# 6. Agora vamos abrir e ler o arquivo (21/09)

# NOVO JSON LOCALIZAÇÃO
with open(JSON_LOCALIZACAO, "r", encoding="utf-8") as arquivo: 
    parse_json_localizacao = json.load(arquivo)
print(parse_json_localizacao)

def ler_json(caminho_arquivo):
    with open(caminho_arquivo, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)

parse_json = ler_json(DIR_CIDADE)
parse_json_localizacao = ler_json(DIR_ESTADO)
parse_json_localizacao = ler_json(DIR_MUNICIPIO)

    
#-----------------------------------------------------------------------------------------------------
# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável
df_estacoes = pd.json_normalize(parse_json['estacoes'])[
        ["id", 
        "localizacao.city_name", 
        "localizacao.woeid"
        ]
    ].rename(columns={
                    "id": "estacao_id",
                    "localizacao.woeid": "estado_id",
                    "localizacao.city_name": "cidade"}
)
print(df_estacoes)

