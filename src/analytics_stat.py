"""Entrada compatível com o modulo analitico Gold do projeto."""

from src.gold.analytics_stat import (
    calcular_anomalias,
    calcular_estatisticas,
    calcular_iqr_flags,
    calcular_z_scores,
    gerar_modelo_estrela,
    gerar_relatorio_anomalias,
    gerar_relatorio_estatistico,
    gerar_relatorio_zscore,
    ler_medicoes_silver,
    main,
)

__all__ = [
    "calcular_anomalias",
    "calcular_estatisticas",
    "calcular_iqr_flags",
    "calcular_z_scores",
    "gerar_modelo_estrela",
    "gerar_relatorio_anomalias",
    "gerar_relatorio_estatistico",
    "gerar_relatorio_zscore",
    "ler_medicoes_silver",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())