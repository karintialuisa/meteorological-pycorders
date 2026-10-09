"""Testes de persistencia e auditoria da camada Silver."""

import json

import pandas as pd
import pyarrow.parquet as parquet

from src.ingestion.leituras.Persistir_Silver import persistir_silver


def _water_record(reading_id, timestamp, ph=7.0, oxygen=8.0, conductivity=100.0):
    return {
        "id_leitura_origem": reading_id,
        "id_estacao": 20,
        "data_leitura": timestamp,
        "temperatura_agua": 20.0,
        "ph": ph,
        "oxigenio": oxygen,
        "condutividade": conductivity,
    }


def _weather_record(station_id, timestamp, temperature=24.0, condition="Nublado"):
    return {
        "id_estacao": station_id,
        "id_cidade": 10,
        "data_leitura": timestamp,
        "temperatura_ar": temperature,
        "umidade": 65.0,
        "chuva": 0.0,
        "vento": 4.5,
        "condicao": condition,
    }


def _manifest(result):
    return json.loads(result["manifesto"].read_text(encoding="utf-8"))


def test_water_round_trip_partition_snappy_and_idempotent_merge(tmp_path):
    rows = pd.DataFrame(
        [
            _water_record("W-1", "2026-05-20T10:00:00-03:00"),
            _water_record("W-1", "2026-05-20T13:00:00Z", ph=8.0),
            _water_record("W-2", "2026-05-21T10:00:00Z"),
        ]
    )

    first = persistir_silver(rows, "qualidade_agua", tmp_path)

    assert first["linhas_gravadas"] == 2
    first_partition = (
        tmp_path
        / "qualidade_agua"
        / "data_leitura=2026-05-20"
        / "part-00000.parquet"
    )
    parquet_file = parquet.ParquetFile(first_partition)
    restored = pd.read_parquet(first_partition, engine="pyarrow")
    assert parquet_file.metadata.row_group(0).column(0).compression == "SNAPPY"
    parquet_file.close()
    assert restored["id_leitura_origem"].tolist() == ["W-1"]
    assert restored.loc[0, "ph"] == 7.0
    assert "__index_level_0__" not in restored.columns

    repeated = persistir_silver(rows, "qualidade_agua", tmp_path)
    assert repeated["linhas_gravadas"] == 0

    later = pd.DataFrame(
        [_water_record("W-3", "2026-05-20T16:00:00Z")]
    )
    merged = persistir_silver(later, "qualidade_agua", tmp_path)
    restored = pd.read_parquet(first_partition, engine="pyarrow")
    assert merged["linhas_gravadas"] == 1
    assert set(restored["id_leitura_origem"]) == {"W-1", "W-3"}
    assert (tmp_path / "qualidade_agua" / "data_leitura=2026-05-21").is_dir()


def test_weather_uses_utc_natural_key_and_writes_quality_manifest(tmp_path):
    rows = pd.DataFrame(
        [
            _weather_record(
                20,
                "2026-05-20T10:00:00-03:00",
                temperature=24.0,
                condition="SENTINELA_CONFIDENCIAL",
            ),
            _weather_record(
                20,
                "2026-05-20T13:00:00Z",
                temperature=29.0,
                condition="Conflito",
            ),
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
    assert result["linhas_gravadas"] == 1
    assert restored["temperatura_ar"].tolist() == [24.0]
    assert str(restored["data_leitura"].dt.tz) == "UTC"
    assert parquet.ParquetFile(partition).metadata.row_group(0).column(0).compression == "SNAPPY"

    manifest = _manifest(result)
    assert set(manifest["dimensoes_qualidade"]) == {
        "completeness",
        "uniqueness",
        "accuracy",
        "validity",
        "timeliness",
        "consistency",
    }
    assert manifest["dimensoes_qualidade"]["uniqueness"] == {
        "linhas_avaliadas": 2,
        "linhas_aprovadas": 1,
        "linhas_rejeitadas": 1,
    }
    manifest_text = result["manifesto"].read_text(encoding="utf-8")
    assert "SENTINELA_CONFIDENCIAL" not in manifest_text
    assert "cpf" not in manifest_text.lower()
    assert "nome_completo" not in manifest_text.lower()


def test_quality_manifest_counts_invalid_and_incomplete_rows(tmp_path):
    rows = pd.DataFrame(
        [
            _water_record("W-valid", "2026-05-20T12:00:00Z"),
            _water_record("W-ph", "2026-05-20T13:00:00Z", ph=14.1),
            _water_record("W-missing", "2026-05-20T14:00:00Z", oxygen=None),
        ]
    )

    result = persistir_silver(rows, "qualidade_agua", tmp_path)

    manifest = _manifest(result)
    dimensions = manifest["dimensoes_qualidade"]
    assert result["linhas_gravadas"] == 1
    assert dimensions["completeness"]["linhas_rejeitadas"] == 1
    assert dimensions["validity"]["linhas_rejeitadas"] == 1
    assert dimensions["accuracy"]["linhas_rejeitadas"] == 0
    assert dimensions["timeliness"]["linhas_rejeitadas"] == 0


def test_empty_silver_batch_writes_zero_count_manifest(tmp_path):
    columns = [
        "id_leitura_origem",
        "id_estacao",
        "data_leitura",
        "temperatura_agua",
        "ph",
        "oxigenio",
        "condutividade",
    ]

    result = persistir_silver(
        pd.DataFrame(columns=columns), "qualidade_agua", tmp_path
    )

    assert result["linhas_gravadas"] == 0
    assert result["manifesto"].is_file()
    assert not (tmp_path / "qualidade_agua" / "data_leitura=NaT").exists()