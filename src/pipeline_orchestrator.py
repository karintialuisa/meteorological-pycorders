"""Executa Bronze -> Silver -> Gold; a carga SQL 3FN e uma etapa paralela opcional."""

import argparse
import logging
from pathlib import Path

import pandas as pd

from config.settings import configure_logging
from src.bronze.leitor_bronze import ler_registros_bronze
from src.database.database_manager import (
    carregar_dataframe,
    create_db_engine,
    inserir_parametros,
)
from src.gold.analytics_stat import (
    gerar_modelo_estrela,
    gerar_relatorio_anomalias,
    gerar_relatorio_estatistico,
    gerar_relatorio_zscore,
)
from src.silver.etl.referencias import carregar_estacoes_silver, resolver_referencias
from src.silver.quality_governance import (
    persistir_silver,
    tabela_ambiental,
    tabela_metereologica,
)

# Dataset Bronze -> (dataset Silver, parser)
DATASETS = {
    "ambiental": ("qualidade_agua", tabela_ambiental),
    "meteorologica": ("leitura_meteorologica", tabela_metereologica),
}


def _processar_dataset(
    bronze: str, estacoes: pd.DataFrame, diretorio_bronze, engine
) -> int:
    silver, parser = DATASETS[bronze]
    registros = ler_registros_bronze(bronze, diretorio_bronze)
    if not registros:
        logging.info("Bronze/%s sem registros; Silver nao alterada", bronze)
        return 0
    leituras = parser(registros)
    aprovadas = resolver_referencias(leituras, silver, estacoes)
    if not aprovadas.empty:
        persistir_silver(aprovadas, silver)
    if engine is not None and not leituras.empty:
        carregar_dataframe(leituras, silver, engine)
    logging.info(
        "Bronze -> Silver: dataset=%s validadas=%s gravadas=%s",
        silver, len(leituras), len(aprovadas),
    )
    return len(aprovadas)


def executar_pipeline(
    *,
    apenas_gold: bool = False,
    carregar_sql: bool = False,
    engine=None,
    diretorio_bronze: str | Path | None = None,
    diretorio_gold: str | Path | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> dict[str, object]:
    """Le os lotes JSONL da Bronze, projeta a Silver e publica os produtos Gold.

    `carregar_sql` replica as leituras validadas no modelo 3FN, que precisa ter
    estacoes e parametros cadastrados. `apenas_gold` regenera so a Gold.
    """
    resultados: dict[str, object] = {}
    if not apenas_gold:
        engine_propria = carregar_sql and engine is None
        if carregar_sql:
            engine = engine or create_db_engine()
            inserir_parametros(engine=engine)
        try:
            estacoes = carregar_estacoes_silver()
            for bronze, (silver, _) in DATASETS.items():
                resultados[silver] = _processar_dataset(
                    bronze, estacoes, diretorio_bronze, engine if carregar_sql else None
                )
        finally:
            if engine_propria:
                engine.dispose()

    kwargs = {"data_inicio": data_inicio, "data_fim": data_fim}
    gold = Path(diretorio_gold) if diretorio_gold is not None else None
    saidas = (
        {}
        if gold is None
        else {
            "estatisticas": gold / "estatisticas_descritivas.csv",
            "zscore": gold / "z_scores.csv",
            "anomalias": gold / "alertas_qualidade.csv",
        }
    )
    resultados["estatisticas"] = gerar_relatorio_estatistico(
        saida=saidas.get("estatisticas"), **kwargs
    )
    resultados["zscore"] = gerar_relatorio_zscore(saida=saidas.get("zscore"), **kwargs)
    resultados["anomalias"] = gerar_relatorio_anomalias(
        saida=saidas.get("anomalias"), **kwargs
    )
    resultados["modelo_estrela"] = gerar_modelo_estrela(gold_dir=gold, **kwargs)
    return resultados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apenas-gold",
        action="store_true",
        help="Regenera relatorios e esquema estrela usando a Silver existente",
    )
    parser.add_argument(
        "--carregar-sql",
        action="store_true",
        help="Tambem grava as leituras validadas no modelo relacional 3FN",
    )
    parser.add_argument("--data-inicio", help="Primeiro dia UTC inclusivo (YYYY-MM-DD)")
    parser.add_argument("--data-fim", help="Ultimo dia UTC inclusivo (YYYY-MM-DD)")
    argumentos = parser.parse_args(argv)
    configure_logging(categoria="execucao")
    try:
        resultados = executar_pipeline(
            apenas_gold=argumentos.apenas_gold,
            carregar_sql=argumentos.carregar_sql,
            data_inicio=argumentos.data_inicio,
            data_fim=argumentos.data_fim,
        )
    except Exception:
        logging.exception("Falha na execucao do pipeline")
        return 1
    logging.info("Pipeline concluido: produtos=%s", sorted(resultados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
