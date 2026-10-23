"""Testes das dimensoes de qualidade avaliadas antes da persistencia Silver."""

import json

import pandas as pd

from src.silver.persistencia.Persistir_Silver import persistir_silver


def _water_record(
    reading_id,
    timestamp,
    *,
    temperature=20.0,
    ph=7.0,
    oxygen=8.0,
    conductivity=100.0,
    turbidity=2.5,
):
    """Cria uma leitura de água válida que pode ser alterada para cada cenário."""
    return {
        "id_leitura_origem": reading_id,
        "id_estacao": 20,
        "data_leitura": timestamp,
        "temperatura_agua": temperature,
        "ph": ph,
        "oxigenio": oxygen,
        "condutividade": conductivity,
        "turbidez": turbidity,
    }


def _weather_record(station_id, timestamp, *, temperature=24.0, humidity=65.0):
    """Cria uma leitura meteorológica válida com os campos exigidos pela Silver."""
    return {
        "id_estacao": station_id,
        "id_cidade": 10,
        "data_leitura": timestamp,
        "temperatura_ar": temperature,
        "umidade": humidity,
        "chuva": 0.0,
        "vento": 4.5,
        "condicao": "Nublado",
    }


def _manifest(result):
    """Carrega o manifesto de qualidade gerado por uma gravação Silver."""
    return json.loads(result["manifesto"].read_text(encoding="utf-8"))


def test_water_quality_rejects_incomplete_invalid_and_out_of_range_rows(tmp_path):
    """Mantém apenas leitura válida e verifica dimensões por tipo de rejeição."""
    rows = pd.DataFrame(
        [
            _water_record("W-valid", "2026-05-20T10:00:00Z"),
            _water_record("W-missing", "2026-05-20T11:00:00Z", oxygen=None),
            _water_record("W-date", "not-a-date"),
            _water_record("W-temperature", "2026-05-20T13:00:00Z", temperature=50.1),
            _water_record("W-ph", "2026-05-20T14:00:00Z", ph=14.1),
            _water_record("W-infinite", "2026-05-20T15:00:00Z", turbidity=float("inf")),
        ]
    )

    result = persistir_silver(rows, "qualidade_agua", tmp_path)

    partition = (
        tmp_path
        / "qualidade_agua"
        / "data_leitura=2026-05-20"
        / "part-00000.parquet"
    )
    restored = pd.read_parquet(partition, engine="pyarrow")
    dimensions = _manifest(result)["dimensoes_qualidade"]
    assert result["linhas_gravadas"] == 1
    assert restored["id_leitura_origem"].tolist() == ["W-valid"]
    assert dimensions["completeness"]["linhas_rejeitadas"] == 2
    assert dimensions["timeliness"]["linhas_rejeitadas"] == 1
    assert dimensions["accuracy"]["linhas_rejeitadas"] == 1
    assert dimensions["validity"]["linhas_rejeitadas"] == 2


def test_weather_quality_rejects_invalid_timestamp_and_domain_values(tmp_path):
    """Verifica rejeições meteorológicas por completude, tempo e domínio."""
    rows = pd.DataFrame(
        [
            _weather_record(20, "2026-05-20T10:00:00Z"),
            _weather_record(21, "invalid-timestamp"),
            _weather_record(22, "2026-05-20T12:00:00Z", temperature=60.1),
            _weather_record(23, "2026-05-20T13:00:00Z", humidity=100.1),
            {
                **_weather_record(24, "2026-05-20T14:00:00Z"),
                "condicao": " ",
            },
        ]
    )

    result = persistir_silver(rows, "leitura_meteorologica", tmp_path)

    partition = (
        tmp_path
        / "leitura_meteorologica"
        / "data_leitura=2026-05-20"
        / "part-00000.parquet"
    )
    restored = pd.read_parquet(partition, engine="pyarrow")
    dimensions = _manifest(result)["dimensoes_qualidade"]
    assert result["linhas_gravadas"] == 1
    assert restored["id_estacao"].tolist() == [20]
    assert dimensions["completeness"]["linhas_rejeitadas"] == 2
    assert dimensions["timeliness"]["linhas_rejeitadas"] == 1
    assert dimensions["accuracy"]["linhas_rejeitadas"] == 1
    assert dimensions["validity"]["linhas_rejeitadas"] == 1
