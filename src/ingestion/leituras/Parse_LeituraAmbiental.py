"""Parsing e normalização das leituras ambientais.

Este módulo lê as leituras de qualidade da água em formato JSON, achata os
campos aninhados e prepara um DataFrame pronto para inserção no banco.
"""

# 1. Biblioteca para manipulação de arquivos JSON
import json
import logging
# 2. Biblioteca para manipulação de caminhos de arquivos
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, get_path

# 3. Biblioteca para manipulação de dados em formato tabular (DataFrames)
import pandas as pd

# 4. Diretório para os arquivos JSON
# 5. criar função e ler o arquivo JSON de leituras meteorológicas
def ler_json(path_arquivo):
    """Lê um arquivo JSON de leituras ambientais.

    Args:
        path_arquivo: Caminho do arquivo JSON a ser lido.

    Returns:
        object: Conteúdo carregado do arquivo JSON.
    """
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = json.load(arquivo)
    return conteudo

# 6. Função para criar o DataFrame a partir do JSON de leituras meteorológicas
def tabela_ambiental() -> pd.DataFrame:
    """Cria e trata o DataFrame com as leituras ambientais.

    O processo inclui normalização dos dados aninhados, rejeição individual de
    registros incompletos e deduplicação por estação/data antes da persistência.

    Returns:
        pd.DataFrame: DataFrame pronto para inserção no banco de dados.
    """
    parse_ambiental = ler_json(get_path("INGESTION_LEITURA_AMBIENTAL"))
    registros = parse_ambiental.get("leituras_ambientais", [])
    df_origem = pd.json_normalize(registros)

    if df_origem.empty:
        logging.warning(
            "Leitura ambiental rejeitada por incompletude: indice=%s, "
            "id=%s, estacao_id=%s, timestamp=%s, motivos=%s",
            0,
            None,
            None,
            None,
            "estacao_id ausente, timestamp ausente ou inválido",
        )
        return pd.DataFrame(columns=[
            "estacao_id",
            "temperatura_agua",
            "ph",
            "oxigenio",
            "condutividade",
            "data_leitura",
        ])

    timestamp_origem = df_origem.get(
        "timestamp", pd.Series(pd.NA, index=df_origem.index)
    )
    estacao_origem = df_origem.get(
        "estacao_id", pd.Series(pd.NA, index=df_origem.index)
    )

    estacao_string = estacao_origem.apply(
        lambda valor: "" if pd.isna(valor) else str(valor).strip()
    )
    timestamp_string = timestamp_origem.apply(
        lambda valor: "" if pd.isna(valor) else str(valor).strip()
    )
    datas = pd.to_datetime(timestamp_origem, errors="coerce", utc=True)

    estacao_ausente = estacao_string.eq("")
    data_ausente = timestamp_string.eq("") | datas.isna()
    rejeitar = estacao_ausente | data_ausente

    for indice in df_origem.index[rejeitar]:
        motivos = []
        if estacao_ausente.loc[indice]:
            motivos.append("estacao_id ausente")
        if data_ausente.loc[indice]:
            motivos.append("timestamp ausente ou inválido")
        logging.warning(
            "Leitura ambiental rejeitada por incompletude: indice=%s, "
            "id=%s, estacao_id=%s, timestamp=%s, motivos=%s",
            indice,
            df_origem.at[indice, "id"] if "id" in df_origem else None,
            estacao_origem.loc[indice],
            timestamp_origem.loc[indice],
            ", ".join(motivos),
        )

    colunas_origem = [
        "estacao_id",
        "qualidade_agua.temperatura.valor",
        "qualidade_agua.ph.valor",
        "qualidade_agua.oxigenio_dissolvido.valor",
        "qualidade_agua.condutividade.valor",
    ]
    df_ambiental = df_origem.loc[~rejeitar].copy()
    for coluna in colunas_origem:
        if coluna not in df_ambiental:
            df_ambiental[coluna] = pd.NA

    df_ambiental["data_leitura"] = datas.loc[~rejeitar]
    df_ambiental["estacao_id"] = (
        df_ambiental["estacao_id"].apply(
            lambda valor: "" if pd.isna(valor) else str(valor).strip()
        )
    )
    df_ambiental = df_ambiental[colunas_origem + ["data_leitura"]].rename(
        columns={
            "qualidade_agua.temperatura.valor": "temperatura_agua",
            "qualidade_agua.ph.valor": "ph",
            "qualidade_agua.oxigenio_dissolvido.valor": "oxigenio",
            "qualidade_agua.condutividade.valor": "condutividade",
        }
    )

    df_ambiental = df_ambiental.drop_duplicates().reset_index(drop=True)
    df_ambiental = df_ambiental.sort_values(["data_leitura"], ascending=False)
    df_ambiental = df_ambiental.drop_duplicates(
        subset=["estacao_id", "data_leitura"],
        keep="first",
    ).reset_index(drop=True)

    return df_ambiental

if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    configure_logging(Path(__file__).resolve().parents[3])
    df = tabela_ambiental()
    logging.info("Preview do DataFrame tratado:\n%s", df.head())
