# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON e obter o arquivo JSON
DIR_JSON = DIR_PARSE / "ingestion" / "monitoramento_ambiental.json"

# 6. Agora vamos abrir e ler o arquivo
with open(DIR_JSON, "r", encoding="utf-8") as arquivo: 
    parse_json = json.load(arquivo)

# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável
df_estacoes = pd.json_normalize(parse_json['estacoes'])

print('DataFrame de estações carregado: \n', df_estacoes)