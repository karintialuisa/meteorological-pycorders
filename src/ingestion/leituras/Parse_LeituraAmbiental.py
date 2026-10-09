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

    O processo normaliza medições e timestamps, rejeita registros incompletos
    ou inválidos e deduplica por identificador de origem.

    Returns:
        pd.DataFrame: DataFrame pronto para inserção no banco de dados.
    """
    parse_ambiental = ler_json(get_path("INGESTION_LEITURA_AMBIENTAL"))
    registros = parse_ambiental.get("leituras_ambientais", [])
    df_origem = pd.json_normalize(registros)

    # 3.2 Auditoria (itens 26-31): completude, unicidade, validade, tempo e consistencia.
    colunas_medicao = {
        "qualidade_agua.temperatura.valor": "temperatura_agua",
        "qualidade_agua.ph.valor": "ph",
        "qualidade_agua.oxigenio_dissolvido.valor": "oxigenio",
        "qualidade_agua.condutividade.valor": "condutividade",
    }
    colunas_saida = [
        "id_leitura_origem",
        "estacao_id",
        *colunas_medicao.values(),
        "data_leitura",
    ]

    if not registros:
        logging.info(
            "Qualidade ambiental: recebidas=0, aceitas=0, rejeitadas=0, "
            "duplicatas_removidas=0, motivos={}",
        )
        return pd.DataFrame(columns=colunas_saida)

    timestamp_origem = df_origem.get(
        "timestamp", pd.Series(pd.NA, index=df_origem.index)
    )
    estacao_origem = df_origem.get(
        "estacao_id", pd.Series(pd.NA, index=df_origem.index)
    )
    id_origem = df_origem.get("id", pd.Series(pd.NA, index=df_origem.index))

    estacao_string = estacao_origem.apply(
        lambda valor: "" if pd.isna(valor) else str(valor).strip()
    )
    id_string = id_origem.apply(
        lambda valor: "" if pd.isna(valor) else str(valor).strip()
    )
    timestamp_string = timestamp_origem.apply(
        lambda valor: "" if pd.isna(valor) else str(valor).strip()
    )
    datas = pd.to_datetime(timestamp_origem, errors="coerce", utc=True)

    estacao_ausente = estacao_string.eq("")
    id_ausente = id_string.eq("")
    data_ausente = timestamp_string.eq("") | datas.isna()
    motivos_rejeicao = {
        "id de origem ausente": id_ausente,
        "estacao_id ausente": estacao_ausente,
        "timestamp ausente ou inválido": data_ausente,
    }

    for coluna_origem, coluna_destino in colunas_medicao.items():
        valores_origem = df_origem.get(
            coluna_origem, pd.Series(pd.NA, index=df_origem.index)
        )
        valores_numericos = pd.to_numeric(valores_origem, errors="coerce")
        df_origem[coluna_destino] = valores_numericos

        valor_ausente = valores_origem.isna() | (
            valores_origem.astype("string").str.strip().eq("").fillna(False)
        )
        valor_nao_numerico = valores_numericos.isna() & ~valor_ausente
        motivos_rejeicao[f"{coluna_destino} ausente"] = valor_ausente
        motivos_rejeicao[f"{coluna_destino} nao numerico"] = valor_nao_numerico

    motivos_rejeicao["ph fora do intervalo 0-14"] = (
        (df_origem["ph"] < 0) | (df_origem["ph"] > 14)
    ).fillna(False)
    motivos_rejeicao["oxigenio negativo"] = (df_origem["oxigenio"] < 0).fillna(
        False
    )
    motivos_rejeicao["condutividade negativa"] = (
        df_origem["condutividade"] < 0
    ).fillna(False)

    # Completude e validade (itens 26 e 28): rejeita leituras incompletas ou fora do dominio.
    rejeitar_completude = id_ausente | estacao_ausente | data_ausente
    rejeitar_qualidade = pd.DataFrame(
        {
            motivo: mascara
            for motivo, mascara in motivos_rejeicao.items()
            if motivo not in {
                "id de origem ausente",
                "estacao_id ausente",
                "timestamp ausente ou inválido",
            }
        }
    ).any(axis=1)
    rejeitar = rejeitar_completude | rejeitar_qualidade

    for indice in df_origem.index[rejeitar]:
        motivos = [
            motivo
            for motivo, mascara in motivos_rejeicao.items()
            if mascara.loc[indice]
        ]
        incompleta = rejeitar_completude.loc[indice]
        logging.warning(
            "Leitura ambiental rejeitada por %s: indice=%s, id=%s, "
            "estacao_id=%s, timestamp=%s, motivos=%s",
            "incompletude ou validade" if incompleta else "validade",
            indice,
            df_origem.at[indice, "id"] if "id" in df_origem else None,
            estacao_origem.loc[indice],
            timestamp_origem.loc[indice],
            ", ".join(motivos),
        )

    df_ambiental = df_origem.loc[~rejeitar].copy()
    df_ambiental["id_leitura_origem"] = id_string.loc[~rejeitar]
    df_ambiental["data_leitura"] = datas.loc[~rejeitar]
    df_ambiental["estacao_id"] = estacao_string.loc[~rejeitar]
    df_ambiental = df_ambiental[
        colunas_saida
    ]

    # Unicidade e consistencia (itens 27 e 31): conserva a primeira retransmissao por ID.
    duplicados = df_ambiental["id_leitura_origem"].duplicated(keep="first")
    for leitura_id in df_ambiental.loc[
        duplicados, "id_leitura_origem"
    ].unique():
        grupo = df_ambiental.loc[
            df_ambiental["id_leitura_origem"].eq(leitura_id)
        ]
        if len(grupo.drop(columns="id_leitura_origem").drop_duplicates()) > 1:
            logging.warning(
                "Retransmissão conflitante no lote; mantendo primeira leitura: "
                "id_leitura_origem=%s",
                leitura_id,
            )
    if duplicados.any():
        logging.info(
            "Duplicatas removidas do lote ambiental: quantidade=%s",
            int(duplicados.sum()),
        )
    quantidade_duplicatas = int(duplicados.sum())
    df_ambiental = df_ambiental.drop_duplicates(
        subset=["id_leitura_origem"], keep="first"
    ).reset_index(drop=True)

    # Tempestividade (item 30): ordena pelas datas ja normalizadas em UTC.
    df_ambiental = df_ambiental.sort_values(["data_leitura"], ascending=False)
    df_ambiental = df_ambiental.reset_index(drop=True)

    contagem_motivos = {
        motivo: int(mascara.sum())
        for motivo, mascara in motivos_rejeicao.items()
        if mascara.any()
    }
    logging.info(
        "Qualidade ambiental: recebidas=%s, aceitas=%s, rejeitadas=%s, "
        "duplicatas_removidas=%s, motivos=%s",
        len(df_origem),
        len(df_ambiental),
        int(rejeitar.sum()),
        quantidade_duplicatas,
        contagem_motivos,
    )

    return df_ambiental

if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    configure_logging(Path(__file__).resolve().parents[3])
    df = tabela_ambiental()
    logging.info("Preview do DataFrame tratado:\n%s", df.head())
