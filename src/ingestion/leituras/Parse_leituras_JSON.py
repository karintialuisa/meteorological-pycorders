# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON e obter o arquivo JSON
# 5. 1. Caminho para o arquivo JSON de monitoramento ambiental
DIR_ambiental_JSON = DIR_PARSE / "leituras_ambientais.json"
# 5. 2. Caminho para o arquivo JSON de monitoramento meteorológico
DIR_meteorologicas_JSON = DIR_PARSE / "leituras_meteorologicas.json"

# 6. Agora vamos abrir e ler o arquivo
with open(DIR_ambiental_JSON, "r", encoding="utf-8") as arquivo: 
    parse_ambiental = json.load(arquivo)

with open(DIR_meteorologicas_JSON, "r", encoding="utf-8") as arquivo: 
    parse_meteorologicas = json.load(arquivo)

# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável

{
      "id": "LEIT-AMB-000001",
      "estacao_id": "AMB-001-capital",
      "timestamp": "2026-09-15T08:24:00-03:00",
      "qualidade_agua": {
        "temperatura": {
          "valor": 21.3,
          "unidade": "°C"
        },
        "ph": {
          "valor": 7.2,
          "unidade": "pH"
        },
        "oxigenio_dissolvido": {
          "valor": 6.8,
          "unidade": "mg/L"
        },
        "condutividade": {
          "valor": 145.2,
          "unidade": "µS/cm"
        }
      }
    }

df_ambiental = pd.json_normalize(parse_ambiental['leituras_ambientais'])[
        ["id", 
        "estacao_id",
        "timestamp", 
        "qualidade_agua.temperatura.valor",
        "qualidade_agua.ph.valor",
        "qualidade_agua.oxigenio_dissolvido.valor",
        "qualidade_agua.condutividade.valor"
        ]
    ].rename(columns={
                    "id": "id_ambiental",
                    "estacao_id": "id_estacao",
                    "timestamp": "data_leitura",
                    "qualidade_agua.temperatura.valor": "qualidade_agua_temperatura_valor",
                    "qualidade_agua.ph.valor": "qualidade_agua_ph_valor",
                    "qualidade_agua.oxigenio_dissolvido.valor": "qualidade_agua_oxigenio_valor",
                    "qualidade_agua.condutividade.valor": "qualidade_agua_condutividade_valor"
                    })


# 8. Converter a coluna de timestamp para o formato de data apenas (sem hora)
df_ambiental["data_leitura"] = pd.to_datetime(df_ambiental["data_leitura"]).dt.date

print(df_ambiental)

