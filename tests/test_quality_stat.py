"""Testes das flags de qualidade e do esquema estrela Gold."""

import pandas as pd
import pyarrow.parquet as pq

from src.gold.analytics_stat import (
    calcular_anomalias,
    calcular_iqr_flags,
    construir_modelo_estrela,
    gerar_modelo_estrela,
)


def _medicoes(valores):
    return pd.DataFrame(
        {
            "dataset": ["qualidade_agua"] * len(valores),
            "id_estacao": [12] * len(valores),
            "codigo_parametro": ["PH"] * len(valores),
            "unidade_medida": ["pH"] * len(valores),
            "id_leitura_origem": [f"r{indice}" for indice in range(len(valores))],
            "data_leitura": pd.date_range(
                "2026-10-01", periods=len(valores), freq="D", tz="UTC"
            ),
            "valor": valores,
        }
    )


def test_iqr_flags_outlier_per_parameter_group():
    result = calcular_iqr_flags(_medicoes([1, 2, 3, 4, 100]))

    assert result["anomalia_iqr"].tolist() == [False, False, False, False, True]
    assert result.loc[4, "limite_superior_iqr"] == 7.0


def test_combined_quality_alert_uses_iqr_and_zscore_without_changing_rows():
    result = calcular_anomalias(_medicoes([1, 2, 3, 4, 100]))

    assert len(result) == 5
    assert result["alerta_qualidade"].tolist() == [False, False, False, False, True]
    assert result.loc[4, "anomalia_iqr"]
    assert not result.loc[4, "anomalia_zscore"]


def test_star_schema_has_geography_and_valid_surrogate_keys(tmp_path):
    cadastros = tmp_path / "cadastros"
    cadastros.mkdir()
    pd.DataFrame(
        [{
            "id_estacao": 12,
            "codigo_origem": "S-12",
            "nome_estacao": "Estacao Rio Claro",
            "status_estacao": 1,
            "id_cidade": 20,
        }]
    ).to_parquet(cadastros / "estacoes.parquet", index=False)
    pd.DataFrame(
        [{
            "id_cidade": 20,
            "id_estado": 3,
            "codigo_ibge_cidade": 1234567,
            "nome_cidade": "Rio Claro",
        }]
    ).to_parquet(cadastros / "cidades.parquet", index=False)
    pd.DataFrame(
        [{"id_estado": 3, "sigla_estado": "SP", "nome_estado": "Sao Paulo"}]
    ).to_parquet(cadastros / "estados.parquet", index=False)

    result = construir_modelo_estrela(
        _medicoes([1, 2, 3, 4, 100]), diretorio_cadastros=cadastros
    )
    fato = result["Fato_Medicoes"]
    estacao = result["Dim_Estacao"].iloc[0]

    assert estacao["nome_cidade"] == "Rio Claro"
    assert estacao["sigla_estado"] == "SP"
    assert fato["sk_estacao"].eq(result["Dim_Estacao"].iloc[0]["sk_estacao"]).all()
    assert fato["sk_parametro"].isin(result["Dim_Parametro"]["sk_parametro"]).all()
    assert fato["sk_tempo"].isin(result["Dim_Tempo"]["sk_tempo"]).all()
    assert fato["media_movel"].iloc[-1] == 22.0
    assert fato["alerta_qualidade"].iloc[-1]
    assert {"ano", "mes", "dia", "trimestre", "dia_semana", "dia_util"}.issubset(
        result["Dim_Tempo"].columns
    )


def test_star_schema_publishes_four_snappy_parquet_files(tmp_path, monkeypatch):
    silver = tmp_path / "silver"
    cadastros = silver / "cadastros"
    cadastros.mkdir(parents=True)
    pd.DataFrame(
        [{"id_estacao": 12, "codigo_origem": "S-12", "nome_estacao": "Rio Claro"}]
    ).to_parquet(cadastros / "estacoes.parquet", index=False)
    monkeypatch.setattr(
        "src.gold.analytics_stat.ler_medicoes_silver",
        lambda *_args: _medicoes([1, 2, 3, 4, 100]),
    )

    destinos = gerar_modelo_estrela(silver_dir=silver, gold_dir=tmp_path / "gold")

    assert set(destinos) == {
        "Fato_Medicoes", "Dim_Estacao", "Dim_Tempo", "Dim_Parametro"
    }
    for path in destinos.values():
        assert path.is_file()
        assert pd.read_parquet(path).shape[0] > 0
        metadata = pq.ParquetFile(path).metadata
        assert metadata.row_group(0).column(0).compression == "SNAPPY"
