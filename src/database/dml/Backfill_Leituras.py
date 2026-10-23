"""Reprocessamento historico dos JSONs configurados, sem sobrescrever eventos."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine, get_path
from src.database.dialect import require_sqlserver
from src.database.dml.Persistir_Medicoes import carregar_dataframe, consultar_medicoes_periodo
from src.silver.etl.Parse_LeituraAmbiental import tabela_ambiental
from src.silver.etl.Parse_LeituraMetereologica import tabela_metereologica
from src.silver.persistencia.Persistir_Silver import persistir_silver, reconstruir_particoes_silver


DATASETS = {
    "ambiental": ("qualidade_agua", "INGESTION_LEITURA_AMBIENTAL"),
    "meteorologica": ("leitura_meteorologica", "INGESTION_LEITURA_METEOROLOGICA"),
}


def validar_periodo(data_inicio: str, data_fim: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Converte datas ISO em limites UTC: inicio incluso e fim exclusivo."""
    try:
        inicio = date.fromisoformat(data_inicio)
        fim = date.fromisoformat(data_fim)
    except ValueError as error:
        raise ValueError("Informe datas validas no formato AAAA-MM-DD.") from error
    if inicio.isoformat() != data_inicio or fim.isoformat() != data_fim:
        raise ValueError("Informe datas validas no formato AAAA-MM-DD.")
    if inicio >= fim:
        raise ValueError("A data inicial deve ser anterior a data final exclusiva.")
    return pd.Timestamp(inicio, tz="UTC"), pd.Timestamp(fim, tz="UTC")


def reprocessar_periodo(
    dataset: str,
    data_inicio: str,
    data_fim: str,
    *,
    engine: Engine | None = None,
    reconstruir_silver: bool = False,
) -> dict[str, dict[str, int]]:
    """Reaplica leituras do periodo ao SQL e a Silver usando as regras atuais.

    A fonte e o JSON definido no .env, nao uma consulta a API ou migracao do
    legado. Replays preservam o SQL existente e permitem reparar Silver ausente.
    Conflitos continuam rejeitados, sem substituir os valores originais.
    reconstruir_silver substitui dias completos pela referencia SQL aceita,
    inclusive quando o JSON disponivel nao contem todo o historico do dia.
    """
    if dataset not in (*DATASETS, "ambos"):
        raise ValueError(f"Dataset de backfill desconhecido: {dataset}")
    if engine is not None:
        require_sqlserver(engine)
    inicio, fim = validar_periodo(data_inicio, data_fim)
    datasets = tuple(DATASETS) if dataset == "ambos" else (dataset,)
    resultado = {}
    target_engine = engine
    try:
        for nome in datasets:
            origem, chave_fonte = DATASETS[nome]
            fonte = get_path(chave_fonte)
            logging.info(
                "Backfill iniciado: dataset=%s inicio_utc=%s fim_exclusivo_utc=%s fonte=%s",
                nome, inicio.isoformat(), fim.isoformat(), fonte,
            )
            dados = tabela_ambiental() if nome == "ambiental" else tabela_metereologica()
            datas = pd.to_datetime(dados["data_leitura"], utc=True, errors="raise")
            selecionados = dados.loc[(datas >= inicio) & (datas < fim)].copy()
            aprovados = pd.DataFrame()
            gravadas_silver = 0
            if not selecionados.empty:
                if target_engine is None:
                    target_engine = create_db_engine()
                require_sqlserver(target_engine)
                aprovados = carregar_dataframe(selecionados, origem, target_engine)
                if not aprovados.empty and not reconstruir_silver:
                    silver = persistir_silver(aprovados, origem)
                    gravadas_silver = int(silver["linhas_gravadas"])
            rejeitados = len(selecionados) - len(aprovados)
            if reconstruir_silver and not rejeitados:
                if target_engine is None:
                    target_engine = create_db_engine()
                require_sqlserver(target_engine)
                silver = reconstruir_particoes_silver(
                    lambda: consultar_medicoes_periodo(target_engine, origem, inicio, fim),
                    origem, inicio, fim,
                )
                gravadas_silver = int(silver["linhas_gravadas"])
            elif reconstruir_silver:
                logging.error(
                    "Reconstrucao Silver cancelada: dataset=%s eventos_rejeitados=%s",
                    nome, rejeitados,
                )
            resultado[nome] = {
                "selecionados": len(selecionados),
                "aprovados": len(aprovados),
                "rejeitados": rejeitados,
                "gravados_silver": gravadas_silver,
            }
            log = logging.warning if rejeitados else logging.info
            log(
                "Backfill finalizado: dataset=%s selecionados=%s aprovados=%s "
                "rejeitados=%s gravados_silver=%s",
                nome, len(selecionados), len(aprovados), rejeitados, gravadas_silver,
            )
    finally:
        if engine is None and target_engine is not None:
            target_engine.dispose()
    return resultado


def main(argv: list[str] | None = None) -> int:
    """Executa backfill via CLI; rejeicoes na carga resultam em codigo de falha."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=(*DATASETS, "ambos"), required=True)
    parser.add_argument("--data-inicio", required=True, help="Data UTC inclusiva, AAAA-MM-DD.")
    parser.add_argument("--data-fim", required=True, help="Data UTC exclusiva, AAAA-MM-DD.")
    parser.add_argument(
        "--reconstruir-silver", action="store_true",
        help="Substitui as particoes diarias pela referencia SQL aceita (ID 71).",
    )
    args = parser.parse_args(argv)
    configure_logging(categoria="insercao")
    try:
        resultado = reprocessar_periodo(
            args.dataset, args.data_inicio, args.data_fim,
            reconstruir_silver=args.reconstruir_silver,
        )
    except ValueError as error:
        logging.error("Backfill interrompido: %s", error)
        return 1
    return 1 if any(item["rejeitados"] for item in resultado.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
