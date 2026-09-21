# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON de cidade e estado
DIR_CIDADE = DIR_PARSE / "ingestion" / "municipio.json"

DIR_ESTADO = DIR_PARSE / "ingestion" / "estado.json"

# 6. Abrir e ler o arquivo JSON de cidade
with open(DIR_CIDADE, "r", encoding="utf-8") as arquivo: 
    parse_cidade = json.load(arquivo)

with open(DIR_ESTADO, "r", encoding="utf-8") as arquivo: 
    parse_estado = json.load(arquivo)

# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável
df_estado = pd.json_normalize(parse_estado)[
        ["id", 
        "ibge", 
        "sigla",
        "nome"
        ]
    ].rename(columns={
                    "id":"id_estado",
                    "ibge": "codigo_ibge_estado",
                    "sigla": "sigla_estado",
                    "nome": "nome_estado"
                    })

df_cidade = pd.json_normalize(parse_cidade)[
        ["id", 
        "ibge", 
        "sigla_estado",
        "cidade"
        ]
    ].rename(columns={
        "id":"id_cidade",
                    "ibge": "codigo_ibge_cidade",
                    "sigla_estado": "sigla_estado",
                    "cidade": "nome_cidade"
                    })

# 8. Criar um DataFrame de estado e remover duplicatas

df_estado = df_estado[['id_estado', 'codigo_ibge_estado', 'sigla_estado', 'nome_estado']].drop_duplicates().reset_index(drop=True)
df_cidade = df_cidade[['id_cidade', 'codigo_ibge_cidade', 'sigla_estado', 'nome_cidade']].drop_duplicates().reset_index(drop=True)

# 10. Exibir os DataFrames resultantes para verificação e juntá-los com base no ID da estação
df_localizacao = df_cidade.merge(df_estado, on="sigla_estado", how="left")

#df_estacoes_merge = df_estacoes[['estacao_id','cidade']].drop_duplicates().reset_index(drop=True)

print(f"\nTabela de Localização (Cidades e Estados) : ")
print(df_localizacao.head())