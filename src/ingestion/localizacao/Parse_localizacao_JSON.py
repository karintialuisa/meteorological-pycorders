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
DIR_ESTACAO = DIR_PARSE / "estacoes.json"

# 5. criar função e ler o arquivo JSON de cidade

def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo
 
parse_cidade = ler_json(DIR_CIDADE)
parse_estado = ler_json(DIR_ESTADO)
parse_estacao = ler_json(DIR_ESTACAO)

# 7. Converter o JSON em um DataFrame do pandas e renomear as colunas para um formato mais amigável
# não incluída a coluna id por conta da remoção da duplicidade nos dados e o id será gerado automaticamente no banco de dados

def tabela_localizacao() -> pd.DataFrame:
    global df_estado
    df_estado = pd.json_normalize(parse_estado)[
            [
            "ibge", 
            "sigla",
            "nome"
            ]
        ].rename(columns={                    
                        "ibge": "codigo_ibge"
                        })

    df_cidade = pd.json_normalize(parse_cidade)[
            [
            "ibge", 
            "sigla_estado",
            "cidade"
            ]
        ].rename(columns={
                        "ibge": "codigo_ibge_cidade",
                        "sigla_estado": "sigla_estado",
                        "cidade": "nome_cidade"
                        })
    
    # 8. [Tabela Estado] Criar um DataFrame de estado e remover duplicatas
    df_estado = df_estado[['codigo_ibge', 'sigla', 'nome']].drop_duplicates().reset_index(drop=True)

    # 9. [Tabela Cidade] Criar um DataFrame de cidade e remover duplicatas
    # df_cidade = df_cidade[['codigo_ibge_cidade', 'sigla_estado', 'nome_cidade']].drop_duplicates().reset_index(drop=True)

    # 10. [Tabela Estado, Tabela Cidade] Exibir os DataFrames resultantes para verificação e juntá-los com base no ID da estação
    # df_localizacao = df_cidade.merge(df_estado, left_on="sigla_estado", right_on="sigla")
    return df_estado

def tabela_estacao(df_localizacao: pd.DataFrame) -> pd.DataFrame:
    df_estacao = pd.json_normalize(parse_estacao['estacoes_ambientais'])[
            [
            "id",
            "nome", 
            "descricao",
            "status", 
            "localizacao.estado",
            "localizacao.city_name"
            ]
            ].rename(columns={
                        "id": "id_estacao",
                        "status": "status_estacao",
                        "localizacao.estado": "estado_estacao",
                        "localizacao.city_name": "cidade_estacao"
                        })

    # 12. [Tabela estacao] Conversões 

    # 12.1 Conversão flag ativo para 0 ou 1
    df_estacao["status_estacao"] = df_estacao["status_estacao"].apply(lambda x: 1 if x == "ativa" else 0)

    # 12.2 Junta nome + descrição  
    # fillna para evitar valores nulos na concatenação  
    # strip para remover espaços em branco extras após a concatenação
    df_estacao["nome"] = (
        df_estacao["nome"].fillna("") + " - " + df_estacao["descricao"].fillna("")
    ).str.strip()

    # 12.3 Adiciona o prefixo "[Desativado]" ao nome da estação se o status for desativado
    df_estacao["nome"] = df_estacao.apply(lambda row: "[Desativado] " + row["nome"] if row["status_estacao"] == 0 else row["nome"], axis=1)

    # 12.3 Remove a coluna descrição
    df_estacao = df_estacao.drop(columns=["descricao"])


    # 10. [Tabela localizacao, Tabela estacao] Exibir os DataFrames resultantes para verificação e juntá-los com base no ID da estação
    # para codigo IBGE de cidade e estado
    df_estacao_localizacao = df_estacao.merge(df_localizacao, left_on="cidade_estacao", right_on="nome_cidade")

    print(f"\n Tabela merge - estacao e localizacao")
    print(df_estacao_localizacao)
    return df_estacao_localizacao

if __name__ == "__main__":
    tabela_estacao(tabela_localizacao())
