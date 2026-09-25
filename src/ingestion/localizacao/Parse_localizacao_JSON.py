# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON de cidade e estado
DIR_CIDADE = DIR_PARSE / "municipio.json"

DIR_ESTADO = DIR_PARSE / "estado.json"

# 5. criar função e ler o arquivo JSON de cidade

def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo
 
parse_cidade = ler_json(DIR_CIDADE)

parse_estado = ler_json(DIR_ESTADO)

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
df_localizacao = df_cidade.merge(df_estado, on="sigla_estado")

# 11. Remover as colunas de ID após a junção
df_localizacao = df_localizacao.drop(columns=["id_estado","id_cidade"])

print(f"\nTabela de Localização (Cidades e Estados) : ")
print(df_localizacao)