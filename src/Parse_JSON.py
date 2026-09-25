# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON e obter o arquivo JSON
<<<<<<< HEAD
DIR_ESTADO = DIR_PARSE / "ingestion" / "estado.json"

# DIR_JSON = DIR_PARSE / "ingestion" / "monitoramento_ambiental.json"
def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = arquivo.read()
    return print(conteudo)

=======
# 5. 1. Caminho para o arquivo JSON de monitoramento ambiental
DIR_JSON = DIR_PARSE / "ingestion" / "monitoramento_ambiental.json" # remover depois de substituir
>>>>>>> 1fa58ccc070dcda5581e72dfd8511de250d7d292

# 6. Agora vamos abrir e ler o arquivo
with open(DIR_JSON, "r", encoding="utf-8") as arquivo: 
    parse_json = json.load(arquivo)

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

# 7.1. Criar um DataFrame de estado

df_estado = df_estacoes[['estado_id']].drop_duplicates().reset_index(drop=True)

df_estado['estado'] = df_estado['estado_id']

# 7.2 Criar um DataFrame de cidade

df_cidade = df_estacoes[['cidade', 'estado_id']].drop_duplicates().reset_index(drop=True)

# 7.3 Criar um DataFrame de estação

df_estacoes_merge = df_estacoes[['estacao_id','cidade']].drop_duplicates().reset_index(drop=True)


# 8. Converter o objeto JSON de leituras em um DataFrame do pandas
df_leituras = pd.json_normalize(parse_json['leituras'])

# 9. Extrair a data a partir do timestamp dentro da chave leituras
df_leituras['data'] = pd.to_datetime(df_leituras["timestamp"]).dt.date

# 10. Exibir os DataFrames resultantes para verificação e juntá-los com base no ID da estação
df_leituras = df_leituras.merge(df_estacoes)

# 11. Vamos criar a tabela de água para obter os dados dentro da leitura referente a análise da água
# 12. Tabela de leituras de água criada e renomeada com colunas amigáveis, as colunas antes eram os caminhos completos dentro do JSON e selecionamos algumas e renomemaos para facilitar a análise posterior
tabela_agua = df_leituras[
    [
        "id",
        "estacao_id",
        "cidade",
        "estado_id",
        "data",
        "qualidade_agua.temperatura.valor",
        "qualidade_agua.ph.valor",
        "qualidade_agua.oxigenio_dissolvido.valor",
        "qualidade_agua.condutividade.valor"
    ]
].rename(columns={
    "id": "leitura_id",
    "qualidade_agua.temperatura.valor": "Temperatura_Agua",
    "qualidade_agua.ph.valor": "ph",
    "qualidade_agua.oxigenio_dissolvido.valor": "Oxigenio_Dissolvido",
    "qualidade_agua.condutividade.valor": "Condutividade"
})


# 13. Tabela de leituras meteorológicas criada e renomeada com colunas amigáveis, as colunas antes eram os caminhos completos dentro do JSON e selecionamos algumas e renomemaos para facilitar a análise posterior
tabela_meteorologica = df_leituras[
    [
        "id",
        "estacao_id",
        "cidade",
        "estado_id",
        "data",
        "dados_meteorologicos.temperatura_ar.valor",
        "dados_meteorologicos.umidade.valor",
        "dados_meteorologicos.vento.velocidade",
        "dados_meteorologicos.condicao.description",
        "dados_meteorologicos.chuva.valor"
    ]
].rename(columns={
    "id": "leitura_id",
    "dados_meteorologicos.temperatura_ar.valor": "Temperatura_Ar",
    "dados_meteorologicos.umidade.valor": "Umidade",
    "dados_meteorologicos.vento.velocidade": "Vento",
    "dados_meteorologicos.condicao.description": "Condicao",
    "dados_meteorologicos.chuva.valor": "Chuva"
})

# 14. Exibir as primeiras linhas de cada tabela para verificação, sendo as seguintes tabelas, Estação, Água e Meteorológica
print("\n", 30*"=","TABELAS TRATADAS",30*"=", "\n")
print(f"\nTabela de Estações/Merge : ")
print(df_estacoes_merge.head())
print(f"\nTabela de Estados: ")
print(df_estado.head())
print(f"\nTabela de Cidades: ")
print(df_cidade.head())
print(f"\nTabela de Água: ")
print(tabela_agua.head())
print(f"\nTabela Meteorológica: ")
print(tabela_meteorologica.head())
