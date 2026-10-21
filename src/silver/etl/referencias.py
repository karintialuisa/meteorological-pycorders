"""Cadastros e resolucao de chaves da Silver sem depender do banco relacional."""

import logging
from pathlib import Path

import pandas as pd

from config.settings import get_silver_dir
from src.silver.etl.Parse_localizacao_JSON import (
    tabela_cidade,
    tabela_estacao,
    tabela_estado,
)
from src.silver.persistencia.Persistir_Silver import (
    CONTRATOS_DATASETS,
    _gravar_parquet_atomico,
)


def _inteiro(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="raise").astype("int64")


def construir_cadastros_silver() -> dict[str, pd.DataFrame]:
    """Deriva estados, cidades e estacoes dos JSONs com IDs sequenciais estaveis."""
    estados_origem = tabela_estado()
    cidades_origem = tabela_cidade()
    estacoes_origem = tabela_estacao(cidades_origem, estados_origem)

    estados = estados_origem.copy()
    estados["codigo_ibge_estado"] = _inteiro(estados["codigo_ibge_estado"])
    estados = estados.sort_values("codigo_ibge_estado").reset_index(drop=True)
    estados.insert(0, "id_estado", range(1, len(estados) + 1))

    cidades = cidades_origem.merge(
        estados[["id_estado", "sigla_estado"]],
        on="sigla_estado", how="left", validate="many_to_one",
    )
    if cidades["id_estado"].isna().any():
        raise ValueError("Cidade com estado nao encontrado nos JSONs")
    cidades["codigo_ibge_cidade"] = _inteiro(cidades["codigo_ibge_cidade"])
    cidades = cidades.sort_values("codigo_ibge_cidade").reset_index(drop=True)
    cidades.insert(0, "id_cidade", range(1, len(cidades) + 1))
    cidades = cidades[["id_cidade", "id_estado", "codigo_ibge_cidade", "nome_cidade"]]

    estacoes = estacoes_origem.copy()
    estacoes["codigo_ibge_cidade"] = _inteiro(estacoes["codigo_ibge_cidade"])
    estacoes = estacoes.merge(
        cidades[["id_cidade", "codigo_ibge_cidade"]],
        on="codigo_ibge_cidade", how="left", validate="many_to_one",
    )
    estacoes = estacoes.rename(
        columns={"id": "codigo_origem", "nome": "nome_estacao"}
    ).sort_values("codigo_origem").reset_index(drop=True)
    estacoes.insert(0, "id_estacao", range(1, len(estacoes) + 1))
    estacoes = estacoes[
        ["id_estacao", "codigo_origem", "nome_estacao", "status_estacao", "id_cidade"]
    ]
    return {"estados": estados, "cidades": cidades, "estacoes": estacoes}


def carregar_estacoes_silver(diretorio_silver: str | Path | None = None) -> pd.DataFrame:
    """Le o cadastro Silver existente ou o gera dos JSONs na primeira execucao."""
    raiz = Path(diretorio_silver) if diretorio_silver is not None else get_silver_dir()
    destino = raiz / "cadastros" / "estacoes.parquet"
    if destino.is_file():
        estacoes = pd.read_parquet(destino, engine="pyarrow")
    else:
        cadastros = construir_cadastros_silver()
        for nome, tabela in cadastros.items():
            _gravar_parquet_atomico(tabela, raiz / "cadastros" / f"{nome}.parquet")
        logging.info("Cadastros Silver gerados dos JSONs em %s", raiz / "cadastros")
        estacoes = cadastros["estacoes"]
    ausentes = {"id_estacao", "codigo_origem", "id_cidade"} - set(estacoes.columns)
    if ausentes:
        raise ValueError(f"Cadastro Silver de estacoes incompleto: {sorted(ausentes)}")
    estacoes = estacoes[["id_estacao", "codigo_origem", "id_cidade"]].copy()
    estacoes["codigo_origem"] = estacoes["codigo_origem"].astype("string").str.strip()
    return estacoes


def resolver_referencias(
    leituras: pd.DataFrame, dataset: str, estacoes: pd.DataFrame
) -> pd.DataFrame:
    """Troca `estacao_id` de origem pelas chaves Silver; rejeita estacoes sem cadastro."""
    if leituras.empty:
        return leituras.iloc[0:0].copy()
    preparado = leituras.copy()
    preparado["estacao_id"] = preparado["estacao_id"].astype("string").str.strip()
    resolvido = preparado.merge(
        estacoes, left_on="estacao_id", right_on="codigo_origem",
        how="left", validate="many_to_one",
    )
    sem_cadastro = resolvido["id_estacao"].isna()
    if sem_cadastro.any():
        logging.warning(
            "Silver/%s: leituras rejeitadas por estacao sem cadastro=%s",
            dataset, int(sem_cadastro.sum()),
        )
    resolvido = resolvido.loc[~sem_cadastro].copy()
    for coluna in ("id_estacao", "id_cidade"):
        resolvido[coluna] = resolvido[coluna].astype("int64")
    return resolvido[CONTRATOS_DATASETS[dataset]["obrigatorias"]].reset_index(drop=True)
