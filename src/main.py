# 1 . Biblioteca para manipulação de arquivos JSON
import json
# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path
# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd
# 4. Import logging para registro de mensagens de depuração e erro
import logging

# 5. Configuração da função do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Parse_JSON_Log")

# 6. Obtenção do diretório do arquivo atual, por meio da constante DIR_PARSE e a função Path(__file__) e obter posteriormente o caminho para o arquivo JSON das leituras ambientais da qualidade da água.
DIR_PARSE = Path(__file__).resolve().parent
DIR_JSON_AMBIENTAIS = DIR_PARSE / "ingestion" / "leituras" / "leituras_ambientais.json"


def ler_json(path_json: Path) -> dict:
    # 7. Agora vamos abrir e ler o arquivo
    with open(DIR_JSON_AMBIENTAIS, "r", encoding="utf-8") as arquivo: 
        parse_json = json.load(arquivo)
    return parse_json

# Função sendo chamada para abertura do arquivo e leitura do arquivo JSON
parse_json = ler_json(DIR_JSON_AMBIENTAIS)


# Funcão criada para transformar as leituras de água em um DataFrame do pandas com o rename das colunas para ficarem mais amigáveis
def tabela_leituras_agua() -> pd.DataFrame:
    df_leituras_agua = pd.json_normalize(parse_json["leituras_ambientais"])[
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
            "qualidade_agua.temperatura.valor": "Temperatura",
            "qualidade_agua.ph.valor": "pH",
            "qualidade_agua.oxigenio_dissolvido.valor": "Oxigenio_Dissolvido",
            "qualidade_agua.condutividade.valor": "Condutividade",

    })
    return print(df_leituras_agua)

tabela_agua = tabela_leituras_agua()
