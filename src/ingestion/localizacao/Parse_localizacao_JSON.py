# ======================================================================================================
# ASSUNTO: Conexão com o banco de dados SQL Server Express
# Preparação e criação do DataFrame para as tabelas de localização (Cidade, Estado, Estação)
# ============================================================

# 1. Biblioteca para manipulação de arquivos JSON
import json

# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório base para arquivos de parsing JSON
DIR_PARSE = Path(__file__).resolve().parent

# 5. Diretório para os arquivos JSON
DIR_CIDADE = DIR_PARSE / "municipio.json"
DIR_ESTADO = DIR_PARSE / "estado.json"
DIR_ESTACAO = DIR_PARSE / "estacoes.json"

# 6. Função para ler arquivo JSON
def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo

# 7. Tabela Estado
def tabela_estado() -> pd.DataFrame:
    parse_estado = ler_json(DIR_ESTADO)
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
    parse_cidade = ler_json(DIR_CIDADE)
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
    parse_estacao = ler_json(DIR_ESTACAO)
    
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
        
        "status": "status_estacao",
        "localizacao.estado": "sigla_estado",
        "localizacao.city_name": "cidade_estacao"
    })

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
    print(30*"=", "LISTA DE TABELAS", 30*"=", "\n")
    
    df_est = tabela_estado()
    df_cid = tabela_cidade()
    
    print("Tabela de Cidade:\n", df_cid.head())
    print("\nTabela de Estado:\n", df_est.head())
    
    df_estacao_final = tabela_estacao(df_cid, df_est)
    print("\nTabela final Estação com códigos IBGE de Cidade e Estado:\n", df_estacao_final.to_string(index=False))