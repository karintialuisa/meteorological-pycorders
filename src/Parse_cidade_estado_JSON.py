# 1 . Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para o arquivo JSON de cidade e estado
DIR_CIDADE = DIR_PARSE / "ingestion" / "localizacao" / "municipio.json"

DIR_ESTADO = DIR_PARSE / "ingestion" / "localizacao" / "estado.json"


def ler_json(DIR_JSON: Path): 
    try:
        with open(DIR_JSON, "r", encoding="utf-8") as arquivo: 
            parse_json = json.load(arquivo)
        return parse_json
    except Exception as e:
        erro = print(f"Erro ao ler o arquivo JSON - {e}")
        return {erro}



def parse_json_cidade_estado(parse_json_estado: dict, parse_json_cidade: dict) -> tuple[pd.DataFrame, pd.DataFrame]:

    try:
        # 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável
        df_estado = pd.json_normalize(parse_json_estado)[
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

        df_cidade = pd.json_normalize(parse_json_cidade)[
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

        print(f"\nTabela das Cidades : ")
        print(df_cidade.head())
        print(f"\nTabela dos Estados : ")
        print(df_estado.head())

        return df_estado, df_cidade
    
    except KeyError as e:
            print(
                f"❌ Erro de Chave: Uma das colunas esperadas não foi encontrada no JSON: {e}"
            )
            # Retorna DataFrames vazios em caso de erro para evitar quebrar o fluxo de inserção no DB
            return pd.DataFrame(), pd.DataFrame()

    except (TypeError, AttributeError) as e:
        print(
            f"❌ Erro de Tipo: O formato do JSON recebido não é válido para normalização: {e}"
        )
        # Retorna DataFrames vazios em caso de erro para evitar quebrar o fluxo de inserção no DB
        return pd.DataFrame(), pd.DataFrame()

    except Exception as e:
        print(f"❌ Ocorreu um erro inesperado ao processar os JSONs: {e}")
        raise  # Re-envia o erro para caso tenha algum outro inesperado ocorrido


def parse_json_estacao(parse_json_estacao: dict) -> pd.DataFrame:

if __name__ == "__main__":

    #################### CHAMADA DE FUNÇOES LEITURA DOS JSON ##################
    parse_json_cidade = ler_json(DIR_CIDADE)
    parse_json_estado = ler_json(DIR_ESTADO)
    ################################################################

    #################### CHAMADA DA FUNÇÃO DE PARSING ##################
    df_estado, df_cidade = parse_json_cidade_estado(parse_json_estado, parse_json_cidade)