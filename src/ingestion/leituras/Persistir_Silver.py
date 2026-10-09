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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import PROJECT_ROOT, get_silver_dir


# Itens 35-36: a Silver aceita somente os datasets de leitura e grava Parquet/Snappy.
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
        ],
        "numericas": ["temperatura_agua", "ph", "oxigenio", "condutividade"],
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


def _ler_chaves_existentes(
    pasta_dataset: Path, colunas_chave: list[str]
) -> set[tuple[object, ...]]:
    chaves = set()
    for caminho in pasta_dataset.glob("data_leitura=*/part-00000.parquet"):
        existentes = pd.read_parquet(
            caminho, columns=colunas_chave, engine="pyarrow"
        )
        chaves.update(_chaves(existentes, colunas_chave))
    return chaves


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
    df: pd.DataFrame, dataset: str, contrato: dict
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
    consistencia_invalida = _mascara_vazia(preparado, contrato["relacoes"])

    if dataset == "qualidade_agua":
        acuracia_invalida = pd.Series(False, index=preparado.index)
        validade_invalida = (
            (preparado["ph"] < 0)
            | (preparado["ph"] > 14)
            | (preparado["oxigenio"] < 0)
            | (preparado["condutividade"] < 0)
            | _mascara_infinita(preparado, contrato["numericas"])
        ).fillna(False)
    else:
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

    metricas_dimensoes = {
        "completeness": metricas(incompletas),
        "uniqueness": metricas(pd.Series(False, index=preparado.index)),
        "accuracy": metricas(acuracia_invalida),
        "validity": metricas(validade_invalida),
        "timeliness": metricas(tempestividade_invalida),
        "consistency": metricas(consistencia_invalida),
    }
    return limpas, metricas_dimensoes


def persistir_silver(
    df: pd.DataFrame,
    dataset: str,
    diretorio_silver: str | Path | None = None,
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
    limpas, metricas = _resumo_qualidade(df, dataset, contrato)
    chave = contrato["chave"]
    duplicadas_lote = limpas.duplicated(subset=chave, keep="first")
    linhas_avaliadas_unicidade = len(limpas)
    duplicatas_no_lote = int(duplicadas_lote.sum())
    if duplicadas_lote.any():
        logging.warning(
            "Silver/%s: retransmissoes no lote removidas=%s",
            dataset,
            duplicatas_no_lote,
        )
    limpas = limpas.drop_duplicates(subset=chave, keep="first").copy()

    chaves_existentes = _ler_chaves_existentes(pasta_dataset, chave)
    duplicadas_persistidas = limpas.apply(
        lambda linha: tuple(
            _normalizar_valor_chave(coluna, linha[coluna]) for coluna in chave
        )
        in chaves_existentes,
        axis=1,
    )
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
                if list(existente.columns) != list(lote_novo.columns):
                    raise ValueError(
                        f"Schema Silver incompativel na particao {data_particao}"
                    )
                combinado = pd.concat([existente, lote_novo], ignore_index=True)
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