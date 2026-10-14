"""Persistencia governada das leituras na camada Silver."""

import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as parquet

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import PROJECT_ROOT, get_silver_dir


# Referencia: projeto_final.pdf, secao 3.2 (persistencia e compressao);
# features.csv IDs 35 (Parquet) e 36 (Snappy).
# Leituras temporais de parametros: projeto_final.pdf, secao 2; features.csv IDs 4-9.
# A Silver aceita somente os datasets de leitura e grava Parquet/Snappy.
CONTRATOS_DATASETS = {
    "qualidade_agua": {
        "chave": ["id_leitura_origem"],
        "obrigatorias": [
            "id_leitura_origem",
            "id_estacao",
            "data_leitura",
            "temperatura_agua",
            "ph",
            "oxigenio",
            "condutividade",
            "turbidez",
        ],
        "numericas": [
            "temperatura_agua",
            "ph",
            "oxigenio",
            "condutividade",
            "turbidez",
        ],
        "relacoes": ["id_estacao"],
    },
    "leitura_meteorologica": {
        "chave": ["id_estacao", "data_leitura"],
        "obrigatorias": [
            "id_estacao",
            "id_cidade",
            "data_leitura",
            "temperatura_ar",
            "umidade",
            "chuva",
            "vento",
            "condicao",
        ],
        "numericas": ["temperatura_ar", "umidade", "chuva", "vento"],
        "relacoes": ["id_estacao", "id_cidade"],
    },
}


def _mascara_vazia(df: pd.DataFrame, colunas: list[str]) -> pd.Series:
    mascara = df[colunas].isna().any(axis=1)
    for coluna in colunas:
        if pd.api.types.is_object_dtype(df[coluna]) or isinstance(
            df[coluna].dtype, pd.StringDtype
        ):
            mascara |= df[coluna].astype("string").str.strip().eq("").fillna(False)
    return mascara


def _mascara_infinita(df: pd.DataFrame, colunas: list[str]) -> pd.Series:
    infinitos = [float("inf"), float("-inf")]
    return pd.DataFrame(
        {coluna: df[coluna].isin(infinitos) for coluna in colunas},
        index=df.index,
    ).any(axis=1)


def _normalizar_valor_chave(coluna: str, valor: object) -> object:
    if coluna == "data_leitura":
        data = pd.Timestamp(valor)
        if data.tzinfo is None:
            data = data.tz_localize("UTC")
        else:
            data = data.tz_convert("UTC")
        return data.isoformat()
    if pd.api.types.is_number(valor):
        numero = float(valor)
        return int(numero) if numero.is_integer() else numero
    return str(valor).strip()


def _chaves(df: pd.DataFrame, colunas: list[str]):
    for valores in df[colunas].itertuples(index=False, name=None):
        yield tuple(
            _normalizar_valor_chave(coluna, valor)
            for coluna, valor in zip(colunas, valores)
        )


def _assinatura_payload(
    linha: pd.Series, colunas_payload: list[str], numericas: list[str]
) -> dict[str, object]:
    assinatura = {}
    for coluna in colunas_payload:
        valor = linha[coluna]
        if pd.isna(valor):
            assinatura[coluna] = None
        elif coluna == "data_leitura":
            assinatura[coluna] = _normalizar_valor_chave(coluna, valor)
        elif coluna in numericas:
            assinatura[coluna] = round(float(valor), 3)
        elif pd.api.types.is_number(valor):
            assinatura[coluna] = _normalizar_valor_chave(coluna, valor)
        else:
            assinatura[coluna] = str(valor).strip()
    return assinatura


def _ler_registros_existentes(
    pasta_dataset: Path,
    colunas_chave: list[str],
    colunas_payload: list[str],
    numericas: list[str],
) -> dict[tuple[object, ...], tuple[object, ...]]:
    registros = {}
    colunas = list(dict.fromkeys([*colunas_chave, *colunas_payload]))
    for caminho in pasta_dataset.glob("data_leitura=*/part-00000.parquet"):
        colunas_disponiveis = [
            coluna
            for coluna in colunas
            if coluna in parquet.ParquetFile(caminho).schema.names
        ]
        existentes = pd.read_parquet(
            caminho, columns=colunas_disponiveis, engine="pyarrow"
        )
        payload_disponivel = [
            coluna for coluna in colunas_payload if coluna in colunas_disponiveis
        ]
        for _, linha in existentes.iterrows():
            chave = tuple(
                _normalizar_valor_chave(coluna, linha[coluna])
                for coluna in colunas_chave
            )
            registros[chave] = _assinatura_payload(linha, payload_disponivel, numericas)
    return registros


def _gravar_parquet_atomico(df: pd.DataFrame, destino: Path) -> None:
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destino.parent,
            prefix=f".{destino.stem}.",
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
        df.to_parquet(
            temporario,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        os.replace(temporario, destino)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def _gravar_json_atomico(conteudo: dict, destino: Path) -> None:
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destino.parent,
            prefix=f".{destino.stem}.",
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(conteudo, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
        os.replace(temporario, destino)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def _resumo_qualidade(
    df: pd.DataFrame,
    dataset: str,
    contrato: dict,
    rejeicoes_consistencia: int = 0,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    linhas_recebidas = len(df)
    preparado = df.copy()
    preparado["data_leitura"] = pd.to_datetime(
        preparado["data_leitura"], errors="coerce", utc=True
    )
    for coluna in contrato["numericas"]:
        preparado[coluna] = pd.to_numeric(preparado[coluna], errors="coerce")

    incompletas = _mascara_vazia(preparado, contrato["obrigatorias"])
    tempestividade_invalida = preparado["data_leitura"].isna()
    # 3.2 Consistência: relações ausentes ou contraditórias são rejeitadas e auditadas antes da persistência.
    consistencia_invalida = _mascara_vazia(preparado, contrato["relacoes"])

    if dataset == "qualidade_agua":
        # 3.2 Acurácia e validade: aceita água de 0 °C a +50 °C, inclusive.
        acuracia_invalida = (
            (preparado["temperatura_agua"] < 0)
            | (preparado["temperatura_agua"] > 50)
        ).fillna(False)
        validade_invalida = (
            (preparado["ph"] < 0)
            | (preparado["ph"] > 14)
            | (preparado["oxigenio"] < 0)
            | (preparado["condutividade"] < 0)
            | (preparado["turbidez"] < 0)
            | _mascara_infinita(preparado, contrato["numericas"])
        ).fillna(False)
    else:
        # 3.2 Acurácia e validade: aceita ar de -50 °C a +60 °C, inclusive.
        acuracia_invalida = (
            (preparado["temperatura_ar"] < -50)
            | (preparado["temperatura_ar"] > 60)
        ).fillna(False)
        validade_invalida = (
            (preparado["umidade"] < 0)
            | (preparado["umidade"] > 100)
            | (preparado["chuva"] < 0)
            | (preparado["vento"] < 0)
            | _mascara_infinita(preparado, contrato["numericas"])
        ).fillna(False)

    rejeitadas = (
        incompletas
        | tempestividade_invalida
        | consistencia_invalida
        | acuracia_invalida
        | validade_invalida
    )
    limpas = preparado.loc[~rejeitadas].copy()

    def metricas(rejeicoes: pd.Series) -> dict[str, int]:
        quantidade_rejeitada = int(rejeicoes.sum())
        return {
            "linhas_avaliadas": linhas_recebidas,
            "linhas_aprovadas": linhas_recebidas - quantidade_rejeitada,
            "linhas_rejeitadas": quantidade_rejeitada,
        }

    metricas_consistencia = metricas(consistencia_invalida)
    metricas_consistencia["linhas_avaliadas"] += rejeicoes_consistencia
    metricas_consistencia["linhas_rejeitadas"] += rejeicoes_consistencia
    metricas_consistencia["linhas_aprovadas"] = (
        metricas_consistencia["linhas_avaliadas"]
        - metricas_consistencia["linhas_rejeitadas"]
    )
    metricas_dimensoes = {
        "completeness": metricas(incompletas),
        "uniqueness": metricas(pd.Series(False, index=preparado.index)),
        "accuracy": metricas(acuracia_invalida),
        "validity": metricas(validade_invalida),
        "timeliness": metricas(tempestividade_invalida),
        "consistency": metricas_consistencia,
    }
    return limpas, metricas_dimensoes


def persistir_silver(
    df: pd.DataFrame,
    dataset: str,
    diretorio_silver: str | Path | None = None,
    *,
    rejeicoes_consistencia: int = 0,
) -> dict[str, object]:
    """Mescla leituras por chave natural e grava particoes diarias na Silver.

    O manifesto registra apenas contagens de qualidade e caminhos tecnicos; nao
    serializa valores das leituras, dados pessoais, chaves ou outros segredos.
    """
    if dataset not in CONTRATOS_DATASETS:
        raise ValueError(f"Dataset Silver nao suportado: {dataset}")

    contrato = CONTRATOS_DATASETS[dataset]
    ausentes = sorted(set(contrato["obrigatorias"]) - set(df.columns))
    if ausentes:
        raise ValueError(
            f"Colunas obrigatorias ausentes para Silver/{dataset}: {ausentes}"
        )

    raiz = Path(diretorio_silver) if diretorio_silver is not None else get_silver_dir()
    if not raiz.is_absolute():
        raiz = PROJECT_ROOT / raiz
    pasta_dataset = raiz / dataset
    pasta_dataset.mkdir(parents=True, exist_ok=True)

    # 3.2 Auditoria (itens 26-31): mede qualidade antes de qualquer persistencia.
    limpas, metricas = _resumo_qualidade(
        df, dataset, contrato, rejeicoes_consistencia
    )
    chave = contrato["chave"]
    duplicadas_lote = limpas.duplicated(subset=chave, keep="first")
    linhas_avaliadas_unicidade = len(limpas)
    duplicatas_no_lote = int(duplicadas_lote.sum())
    payload = [coluna for coluna in limpas.columns if coluna not in chave]
    conflitos_payload = pd.Series(False, index=limpas.index)
    for valores_chave in (
        limpas.loc[duplicadas_lote, chave]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    ):
        mascara_grupo = pd.Series(True, index=limpas.index)
        for coluna, valor in zip(chave, valores_chave):
            mascara_grupo &= limpas[coluna].eq(valor)
        grupo = limpas.loc[mascara_grupo]
        assinatura_primeira = tuple(grupo.iloc[0][payload].tolist())
        for indice, linha in grupo.iloc[1:].iterrows():
            if tuple(linha[payload].tolist()) != assinatura_primeira:
                conflitos_payload.loc[indice] = True
    quantidade_conflitos_payload = int(conflitos_payload.sum())
    if quantidade_conflitos_payload:
        logging.warning(
            "Silver/%s: retransmissoes com payload conflitante rejeitadas=%s",
            dataset,
            quantidade_conflitos_payload,
        )
        metricas["consistency"]["linhas_rejeitadas"] += (
            quantidade_conflitos_payload
        )
        metricas["consistency"]["linhas_aprovadas"] -= (
            quantidade_conflitos_payload
        )
    if duplicadas_lote.any():
        logging.warning(
            "Silver/%s: retransmissoes no lote removidas=%s",
            dataset,
            duplicatas_no_lote,
        )
    limpas = limpas.drop_duplicates(subset=chave, keep="first").copy()

    colunas_payload = [coluna for coluna in limpas.columns if coluna not in chave]
    registros_existentes = _ler_registros_existentes(
        pasta_dataset, chave, colunas_payload, contrato["numericas"]
    )
    chaves_existentes = set(registros_existentes)
    duplicadas_persistidas = limpas.apply(
        lambda linha: tuple(
            _normalizar_valor_chave(coluna, linha[coluna]) for coluna in chave
        )
        in chaves_existentes,
        axis=1,
    )
    conflitos_persistidos = 0
    for _, linha in limpas.loc[duplicadas_persistidas].iterrows():
        chave_linha = tuple(
            _normalizar_valor_chave(coluna, linha[coluna]) for coluna in chave
        )
        assinatura = _assinatura_payload(
            linha, colunas_payload, contrato["numericas"]
        )
        assinatura_existente = registros_existentes[chave_linha]
        if any(
            assinatura[coluna] != valor
            for coluna, valor in assinatura_existente.items()
        ):
            conflitos_persistidos += 1
    if conflitos_persistidos:
        logging.warning(
            "Silver/%s: retransmissoes conflitantes contra Parquet rejeitadas=%s",
            dataset,
            conflitos_persistidos,
        )
        metricas["consistency"]["linhas_rejeitadas"] += conflitos_persistidos
        metricas["consistency"]["linhas_aprovadas"] -= conflitos_persistidos
    quantidade_persistidas_ignoradas = int(duplicadas_persistidas.sum())
    if quantidade_persistidas_ignoradas:
        logging.info(
            "Silver/%s: chaves ja persistidas ignoradas=%s",
            dataset,
            quantidade_persistidas_ignoradas,
        )
    novas = limpas.loc[~duplicadas_persistidas].copy()
    metricas["uniqueness"] = {
        "linhas_avaliadas": linhas_avaliadas_unicidade,
        "linhas_aprovadas": len(novas),
        "linhas_rejeitadas": linhas_avaliadas_unicidade - len(novas),
    }

    particoes_gravadas = []
    if not novas.empty:
        novas["_particao_data"] = novas["data_leitura"].dt.strftime("%Y-%m-%d")
        for data_particao, lote_novo in novas.groupby("_particao_data", sort=True):
            lote_novo = lote_novo.drop(columns="_particao_data")
            pasta_particao = pasta_dataset / f"data_leitura={data_particao}"
            pasta_particao.mkdir(parents=True, exist_ok=True)
            destino = pasta_particao / "part-00000.parquet"

            if destino.exists():
                existente = pd.read_parquet(destino, engine="pyarrow")
                colunas_combinadas = list(
                    dict.fromkeys([*existente.columns, *lote_novo.columns])
                )
                for coluna in colunas_combinadas:
                    if coluna not in existente:
                        existente[coluna] = float("nan")
                    if coluna not in lote_novo:
                        lote_novo[coluna] = float("nan")
                existente = existente[colunas_combinadas]
                lote_novo = lote_novo[colunas_combinadas]
                combinado = pd.concat([existente, lote_novo], ignore_index=True)
                for coluna in contrato["numericas"]:
                    combinado[coluna] = pd.to_numeric(
                        combinado[coluna], errors="coerce"
                    )
            else:
                combinado = lote_novo

            combinado = combinado.drop_duplicates(subset=chave, keep="first")
            combinado = combinado.sort_values(
                "data_leitura", ascending=True, kind="stable"
            ).reset_index(drop=True)
            # 3.2 Persistencia (itens 35-36): Parquet colunar com Snappy e troca atomica.
            _gravar_parquet_atomico(combinado, destino)
            particoes_gravadas.append(destino.relative_to(raiz).as_posix())
            chaves_existentes.update(_chaves(lote_novo, chave))

    metricas["timeliness"]["ordenacao_gravada"] = "data_leitura_utc_ascendente"
    execucao_id = uuid.uuid4().hex
    manifesto = {
        "execucao_id": execucao_id,
        "dataset": dataset,
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "formato": "parquet",
        "compressao": "snappy",
        "linhas_recebidas": len(df),
        "linhas_gravadas": len(novas),
        "particoes_gravadas": particoes_gravadas,
        "dimensoes_qualidade": metricas,
    }
    pasta_manifestos = raiz / "_audit" / dataset
    pasta_manifestos.mkdir(parents=True, exist_ok=True)
    caminho_manifesto = pasta_manifestos / f"{execucao_id}.json"
    # 3.2 Auditoria (itens 26-31): manifesto contem somente metricas agregadas.
    _gravar_json_atomico(manifesto, caminho_manifesto)

    logging.info(
        "Silver/%s concluida: recebidas=%s, gravadas=%s, manifesto=%s",
        dataset,
        len(df),
        len(novas),
        caminho_manifesto.relative_to(raiz).as_posix(),
    )
    return {
        "linhas_gravadas": len(novas),
        "particoes_gravadas": particoes_gravadas,
        "manifesto": caminho_manifesto,
    }