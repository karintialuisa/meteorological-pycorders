import json
from pathlib import Path
import pandas as pd

# 1. Diretório base do script
DIR_PARSE = Path(__file__).resolve().parent

# 2. Caminho para o arquivo JSON de monitoramento ambiental
DIR_AMBIENTAL_JSON = DIR_PARSE / "leituras_ambientais.json"


def ler_json(path_arquivo: Path) -> dict:
    """Lê um arquivo JSON e retorna seu conteúdo como dicionário."""
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo


def tabela_ambiental() -> pd.DataFrame:
    """Carrega o arquivo JSON ambiental, realiza todo o parse, limpeza e 
    tratamento de tipos dos dados para corresponder à tabela SQL Server.
    """
    parse_ambiental = ler_json(DIR_AMBIENTAL_JSON)

    # 1. Normalização do JSON e seleção/renomeação de colunas idênticas às do banco de dados
    df_ambiental = pd.json_normalize(parse_ambiental["leituras_ambientais"])[
        [
            "estacao_id",
            "timestamp",
            "qualidade_agua.temperatura.valor",
            "qualidade_agua.ph.valor",
            "qualidade_agua.oxigenio_dissolvido.valor",
            "qualidade_agua.condutividade.valor",
        ]
    ].rename(
        columns={
           
            "timestamp": "data_leitura",
            "qualidade_agua.temperatura.valor": "temperatura_agua",
            "qualidade_agua.ph.valor": "ph",
            "qualidade_agua.oxigenio_dissolvido.valor": "oxigenio",
            "qualidade_agua.condutividade.valor": "condutividade",
        }
    )

    # 2. Remoção de duplicatas exatas
    df_ambiental = df_ambiental.drop_duplicates().reset_index(drop=True)

    # 3. Ordenação para priorizar o registro mais recente em caso de duplicatas
    df_ambiental = df_ambiental.sort_values(["data_leitura"], ascending=False)

    # 4. Tratamento de duplicatas mantendo apenas o registro mais recente por estação/data
    df_ambiental = df_ambiental.drop_duplicates(
        subset=["estacao_id", "data_leitura"], keep="first"
    ).reset_index(drop=True)

    # =========================================================================
    # TRATAMENTO E CONVERSÃO DE TIPOS (DTYPES)
    # =========================================================================

    # Data de leitura convertida para datetime nativo - compatível com o datetime do SQL
    df_ambiental["data_leitura"] = pd.to_datetime(df_ambiental["data_leitura"]).dt.strftime("%Y-%m-%d %H:%M")
    
 
        
    
    return df_ambiental



#Caso precise da cidade, nos relatorios, fazer 'merge com tabela de estações para obter a cidade correspondente

if __name__ == "__main__":
    df = tabela_ambiental()