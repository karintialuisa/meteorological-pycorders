# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

from src.Parse_JSON import DIR_JSON

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON e obter o arquivo JSON
# 5. 1. Caminho para o arquivo JSON de monitoramento ambiental
DIR_ambiental_JSON = DIR_PARSE / "ingestion" / "leituras" /"leituras_ambientais.json"
# 5. 2. Caminho para o arquivo JSON de monitoramento meteorológico
DIR_meteorologicas_JSON = DIR_PARSE / "ingestion" / "leituras" /"leituras_meteorologicas.json"

# 6. Agora vamos abrir e ler o arquivo
with open(DIR_ambiental_JSON, "r", encoding="utf-8") as arquivo: 
    parse_ambiental = json.load(arquivo)

with open(DIR_meteorologicas_JSON, "r", encoding="utf-8") as arquivo: 
    parse_meteorologicas = json.load(arquivo)

# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável

df_ambiental = pd.json_normalize(parse_ambiental['estacoes'])[
        ["id", 
        "estacao_id",
        "timestamp", 
        "localizacao.woeid"
        ]
    ].rename(columns={
                    "id": "id_ambiental",
                    "estacao_id": "id_estacao",
                    "timestamp": pd.to_datetime("timestamp").dt.date,
                    "localizacao.woeid": "woeid"}
)