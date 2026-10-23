"""Leitura dos lotes JSONL brutos da API REST gravados na Bronze."""

import json
import logging
from pathlib import Path

from config.settings import get_api_raw_dir
from src.bronze.ingestion import CONTRATOS


def ler_registros_bronze(
    dataset: str, diretorio: str | Path | None = None
) -> list[dict]:
    """Retorna o campo `record` de todos os lotes do dataset, do mais antigo ao mais novo."""
    if dataset not in CONTRATOS:
        raise ValueError(f"Dataset nao suportado: {dataset}")
    raiz = Path(diretorio) if diretorio is not None else get_api_raw_dir()
    registros: list[dict] = []
    for arquivo in sorted(raiz.glob(f"api_{dataset}_*.jsonl")):
        with arquivo.open(encoding="utf-8") as linhas:
            for numero, linha in enumerate(linhas, start=1):
                if not linha.strip():
                    continue
                try:
                    registros.append(json.loads(linha)["record"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    logging.warning(
                        "Linha Bronze invalida ignorada: arquivo=%s linha=%s",
                        arquivo.name, numero,
                    )
    logging.info("Bronze/%s lida: registros=%s", dataset, len(registros))
    return registros
