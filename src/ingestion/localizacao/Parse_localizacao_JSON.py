"""Parsing e normalização dos dados de localização do projeto.

Este módulo lê os arquivos JSON de estados, cidades e estações, transforma as
estruturas aninhadas em DataFrames tabulares e prepara os dados para a carga
no banco de dados.
"""

# 1 . Biblioteca para manipulação de arquivos JSON
import json
import logging

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, get_path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
# 6. Função para ler arquivo JSON
def ler_json(path_arquivo):
    """Lê um arquivo JSON e retorna o conteúdo em memória.

    Args:
        path_arquivo: Caminho do arquivo JSON a ser carregado.

    Returns:
        object: Estrutura Python contida no JSON.
    """
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo

# 7. Tabela Estado
def tabela_estado() -> pd.DataFrame:
    """Gera o DataFrame com os dados de estados.

    Returns:
        pd.DataFrame: Tabela contendo código IBGE, sigla e nome dos estados.
    """
    parse_estado = ler_json(get_path("INGESTION_LOCALIZACAO_ESTADOS"))
    df_estado = pd.json_normalize(parse_estado)[
        ["ibge", "sigla", "nome"]
    ].rename(columns={
        "ibge": "codigo_ibge_estado",
        "sigla": "sigla_estado",
        "nome": "nome_estado",
    })
    df_estado = df_estado.drop_duplicates().reset_index(drop=True)
    return df_estado

# 8. Tabela Cidade
def tabela_cidade() -> pd.DataFrame:
    """Gera o DataFrame com os dados de cidades.

    Returns:
        pd.DataFrame: Tabela contendo código IBGE, nome da cidade e sigla do estado.
    """
    parse_cidade = ler_json(get_path("INGESTION_LOCALIZACAO_MUNICIPIOS"))
    df_cidade = pd.json_normalize(parse_cidade)[
        ["ibge", 
         "cidade", 
         "sigla_estado"
        ]
    ].rename(columns={
        "ibge": "codigo_ibge_cidade",
        "cidade": "nome_cidade"
    })

    df_cidade = df_cidade.drop_duplicates().reset_index(drop=True)
    return df_cidade

# 9. Tabela Estação (localiza os códigos IBGE para buscar as FKs no banco)
def tabela_estacao(df_cidade: pd.DataFrame, df_estado: pd.DataFrame) -> pd.DataFrame:
    """Gera o DataFrame com os dados de estações meteorológicas.

    Args:
        df_cidade (pd.DataFrame): DataFrame com os dados de cidades.
        df_estado (pd.DataFrame): DataFrame com os dados de estados.

    Returns:
        pd.DataFrame: Tabela preparada com os códigos IBGE de cidade e estado e
            os metadados da estação.
    """
    parse_estacao = ler_json(get_path("INGESTION_LOCALIZACAO_ESTACOES"))
    
    df_estacao = pd.json_normalize(parse_estacao['estacoes_ambientais'])[
        [
            "id",
            "tipo",
            "nome", 
            "descricao",
            "status", 
            "localizacao.estado",
            "localizacao.city_name"
        ]
    ].rename(columns={        
        "status": "status_estacao",
        "localizacao.estado": "sigla_estado",
        "localizacao.city_name": "cidade_estacao"
    })
    df_estacao["estacao_id"] = df_estacao["id"]

    # Conversão de status (1 = ativa, 0 = inativa)
    df_estacao["status_estacao"] = df_estacao["status_estacao"].apply(lambda x: 1 if x == "ativa" else 0)

    # Concatena nome + descrição
    df_estacao["nome"] = (
        df_estacao["nome"].fillna("") + " - " + df_estacao["descricao"].fillna("")
    ).str.strip()

    # Prefixo [Desativado] se inativa
    df_estacao["nome"] = df_estacao.apply(
        lambda row: "[Desativado] " + row["nome"] if row["status_estacao"] == 0 else row["nome"], 
        axis=1
    )

    # Remove coluna de descrição
    df_estacao = df_estacao.drop(columns=["descricao"])

    # --- MERGES ---
    
    # A sigla identifica o estado; o ID usado como FK será consultado no banco.
    df_estacao = df_estacao.merge(
        df_estado[["sigla_estado", "codigo_ibge_estado", "nome_estado"]],
        on="sigla_estado",
        how="left",
        validate="many_to_one",
    )

    # Nome e UF juntos evitam associar municípios homônimos de outros estados.
    df_estacao = df_estacao.merge(
        df_cidade[["nome_cidade", "sigla_estado", "codigo_ibge_cidade"]],
        left_on=["cidade_estacao", "sigla_estado"],
        right_on=["nome_cidade", "sigla_estado"],
        how="left",
        validate="many_to_one",
    )

    # Uma FK obrigatória não pode ser resolvida se faltar um dos códigos.
    if df_estacao[["codigo_ibge_estado", "codigo_ibge_cidade"]].isna().any().any():
        raise ValueError("Estação com cidade ou estado não encontrado nos arquivos JSON")

    # Códigos IBGE identificam os registros; IDs de FK vêm do banco na inserção.
    colunas_finais = [
        "id",
        "estacao_id",
        "tipo",
        "nome",
        "status_estacao",
        "cidade_estacao",
        "nome_cidade",
        "codigo_ibge_cidade",
        "sigla_estado",
        "nome_estado",
        "codigo_ibge_estado",
    ]
    
    df_estacao_final = df_estacao[colunas_finais]

    return df_estacao_final

# Execução principal
if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    configure_logging(Path(__file__).resolve().parents[3])
    logging.info("%s LISTA DE TABELAS %s", "=" * 30, "=" * 30)
    
    df_est = tabela_estado()
    df_cid = tabela_cidade()
    
    logging.info("Tabela de Cidade:\n%s", df_cid.head())
    logging.info("Tabela de Estado:\n%s", df_est.head())
    
    df_estacao_final = tabela_estacao(df_cid, df_est)
    logging.info(
        "Tabela final Estação com códigos IBGE de Cidade e Estado:\n%s",
        df_estacao_final.to_string(index=False),
    )
