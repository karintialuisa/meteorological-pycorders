# 1. Importa a biblioteca padrão usada para abrir, ler e converter arquivos JSON.
import json
# 2. Importa Path para montar caminhos de arquivos de forma segura e independente do sistema operacional.
from pathlib import Path
# 3. Importa o pandas, usado para organizar os dados em tabelas chamadas DataFrames.
import pandas as pd
# 4. Importa logging, que permite registrar mensagens informativas e erros durante a execução.
import logging

# Configura o formato e o nível mínimo das mensagens que serão registradas no programa.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Cria um registrador identificado, facilitando localizar mensagens deste módulo.
logger = logging.getLogger("Parse_JSON_Log")

# Obtém a pasta onde este arquivo Python está salvo.
DIR_PARSE = Path(__file__).resolve().parent
# Monta o caminho completo do JSON que contém as leituras de qualidade da água.
DIR_JSON_AMBIENTAIS = DIR_PARSE / "ingestion" / "leituras" / "leituras_ambientais.json"
# Monta o caminho completo do JSON que contém as leituras meteorológicas.
DIR_JSON_METEOROLOGICAS = DIR_PARSE / "ingestion" / "leituras" / "leituras_meteorologicas.json"

# Criação da função para ler arquivos JSON ambientais
def ler_json_ambientais(path_json: Path) -> dict:
    # Recebe o caminho do arquivo ambiental, abre-o em modo leitura e interpreta seu conteúdo como JSON.
    with open(path_json, "r", encoding="utf-8") as arquivo: 
        parse_json_ambientais = json.load(arquivo)
    # Devolve os dados convertidos para estruturas Python, normalmente um dicionário.
    return parse_json_ambientais

# Criação da função para ler arquivos JSON meteorológicos
def ler_json_meteorologicas(path_json: Path) -> dict:
    # Recebe o caminho do arquivo meteorológico e abre-o garantindo a leitura correta de caracteres especiais.
    with open(path_json, "r", encoding="utf-8") as arquivo:
        # Converte o conteúdo JSON em estruturas Python para permitir seu processamento.
        parse_json_meteorologicas = json.load(arquivo)
    # Retorna os dados meteorológicos carregados.
    return parse_json_meteorologicas


# Carrega os dois arquivos JSON uma única vez para que seus dados possam ser reutilizados.
parse_json_ambientais = ler_json_ambientais(DIR_JSON_AMBIENTAIS)
parse_json_meteorologicas = ler_json_meteorologicas(DIR_JSON_METEOROLOGICAS)


# Transforma as leituras ambientais em uma tabela organizada e com nomes de colunas mais fáceis de entender.
def tabela_leituras_agua() -> pd.DataFrame:
    # Achata estruturas JSON aninhadas, seleciona os campos necessários e cria nomes amigáveis.
    df_leituras_agua = pd.json_normalize(parse_json_ambientais["leituras_ambientais"])[
        [
            "id",
            "estacao_id",
            "cidade",
            "estado",
            "qualidade_agua.temperatura.valor",
            "qualidade_agua.ph.valor",
            "qualidade_agua.oxigenio_dissolvido.valor",
            "qualidade_agua.condutividade.valor",
        ]
    ].rename(columns={
            # Substitui os caminhos longos das propriedades JSON por nomes curtos e descritivos.
            "qualidade_agua.temperatura.valor": "Temperatura_ºC",
            "qualidade_agua.ph.valor": "pH",
            "qualidade_agua.oxigenio_dissolvido.valor": "Oxigenio_Dissolvido_mg/L",
            "qualidade_agua.condutividade.valor": "Condutividade_µS/cm",
            

    })
    
    # Retorna o DataFrame com a coluna Data em formato de data.
    return print(df_leituras_agua)

# Executa a função para mostrar uma amostra da tabela de água.
tabela_agua = tabela_leituras_agua()


# Criação da função para transformar leituras meteorológicas em uma tabela organizada e com nomes de colunas mais amigáveis.
def tabela_leituras_meteorologicas() -> pd.DataFrame:

    # Achata os dados meteorológicos, mantém apenas as colunas úteis e renomeia-as para facilitar a leitura.
    df_leituras_meteorologicas = pd.json_normalize(parse_json_meteorologicas["leituras_meteorologicas"])[
        [
            "id",
            "estacao_id",
            "cidade",
            "estado",
            "dados_meteorologicos.temperatura_ar.valor",
            "dados_meteorologicos.umidade.valor",
            "dados_meteorologicos.condicao.description",
            "dados_meteorologicos.chuva.valor",
            "dados_meteorologicos.vento.velocidade",
        ]

    ].rename(columns={
        # Traduz os nomes técnicos dos campos aninhados para nomes curtos e compreensíveis.
        "dados_meteorologicos.temperatura_ar.valor": "Temperatura_Ar_ºC",
        "dados_meteorologicos.umidade.valor": "Umidade_Ar",
        "dados_meteorologicos.condicao.description": "Condicao_Tempo",
        "dados_meteorologicos.chuva.valor": "Chuva_mm",
        "dados_meteorologicos.vento.velocidade": "Vento_KM/H"
    }
    )
    # Exibe as primeiras linhas para validar visualmente o resultado do tratamento.
    return print("\nTabela de leitura meteorológica:  \n", df_leituras_meteorologicas.head())

# Executa a função para exibir uma amostra da tabela meteorológica.
tabela_leitura_meteorologica = tabela_leituras_meteorologicas()
# Cria uma tabela de referência com cada estação e seu respectivo estado.

# Cria a tabela de estados e guarda o resultado em uma variável chamada de df_estado.
def tabela_estado() -> pd.DataFrame:
    # Seleciona estação e estado, remove combinações repetidas e reorganiza os índices.
    df_estado = pd.json_normalize(parse_json_ambientais["leituras_ambientais"])[
        [
            "estacao_id",
            "estado",
        ]
    ].drop_duplicates().reset_index(drop=True)

    # Mostra uma amostra da tabela para facilitar a conferência dos dados.
    print("\n","Tabela de estado: \n", df_estado.head(), "\n")
    # Retorna o DataFrame pronto para ser usado em outras partes do programa.
    return df_estado


df_estado = tabela_estado()

# Cria a tabela de cidades e guarda o resultado em uma variável chamada de df_cidade.
def tabela_cidade() -> pd.DataFrame:

    # Seleciona estação e cidade, elimina registros repetidos e corrige a numeração das linhas.
    df_cidade = pd.json_normalize(parse_json_ambientais["leituras_ambientais"])[
        [
            "estacao_id",
            "cidade",
            
        ]
    ].drop_duplicates().reset_index(drop=True)

    # Exibe uma amostra para confirmar que a tabela foi criada corretamente.
    print("\n","Tabela de cidade: \n", df_cidade.head(), "\n")
    # Retorna a tabela de cidades para reutilização.
    return df_cidade

# Executa a função e armazena a tabela de cidades resultante.
df_cidade = tabela_cidade()

