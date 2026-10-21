"""Testes de persistencia e auditoria da camada Silver."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as parquet
import pytest

from src.silver.persistencia import Persistir_Silver as silver
from src.silver.persistencia.Persistir_Silver import persistir_silver


def _water_record(
    reading_id,
    timestamp,
    ph=7.0,
    oxygen=8.0,
    conductivity=100.0,
    temperature=20.0,
    turbidity=2.5,
):
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
    assert restored.loc[0, "turbidez"] == 2.5
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


def test_water_merge_evolves_legacy_partition_schema(tmp_path):
    partition = (
        tmp_path
        / "qualidade_agua"
        / "data_leitura=2026-05-20"
    )
    partition.mkdir(parents=True)
    legacy_record = _water_record("W-OLD", "2026-05-20T10:00:00Z")
    legacy_record.pop("turbidez")
    legacy_record["data_leitura"] = pd.to_datetime(
        legacy_record["data_leitura"], utc=True
    )
    pd.DataFrame([legacy_record]).to_parquet(
        partition / "part-00000.parquet", engine="pyarrow", index=False
    )

    result = persistir_silver(
        pd.DataFrame(
            [_water_record("W-NEW", "2026-05-20T12:00:00Z", turbidity=75.0)]
        ),
        "qualidade_agua",
        tmp_path,
    )

    restored = pd.read_parquet(
        partition / "part-00000.parquet", engine="pyarrow"
    ).set_index("id_leitura_origem")
    assert result["linhas_gravadas"] == 1
    assert pd.isna(restored.loc["W-OLD", "turbidez"])
    assert restored.loc["W-NEW", "turbidez"] == 75.0


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
            _water_record("W-turbidity", "2026-05-20T15:00:00Z", turbidity=-0.1),
        ]
    )

    result = persistir_silver(rows, "qualidade_agua", tmp_path)

    manifest = _manifest(result)
    dimensions = manifest["dimensoes_qualidade"]
    assert result["linhas_gravadas"] == 1
    assert dimensions["completeness"]["linhas_rejeitadas"] == 1
    assert dimensions["validity"]["linhas_rejeitadas"] == 2
    assert dimensions["accuracy"]["linhas_rejeitadas"] == 0
    assert dimensions["timeliness"]["linhas_rejeitadas"] == 0


def test_silver_rejects_water_temperatures_outside_domain_range(tmp_path):
    rows = pd.DataFrame(
        [
            _water_record("W-min", "2026-05-20T10:00:00Z", temperature=0),
            _water_record("W-max", "2026-05-20T11:00:00Z", temperature=50),
            _water_record("W-below", "2026-05-20T12:00:00Z", temperature=-0.1),
            _water_record("W-above", "2026-05-20T13:00:00Z", temperature=50.1),
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
    accuracy = _manifest(result)["dimensoes_qualidade"]["accuracy"]
    assert result["linhas_gravadas"] == 2
    assert set(restored["id_leitura_origem"]) == {"W-min", "W-max"}
    assert accuracy == {
        "linhas_avaliadas": 4,
        "linhas_aprovadas": 2,
        "linhas_rejeitadas": 2,
    }


def test_silver_rejects_air_temperatures_outside_agreed_range(tmp_path):
    rows = pd.DataFrame(
        [
            _weather_record(20, "2026-05-20T10:00:00Z", temperature=-50),
            _weather_record(21, "2026-05-20T11:00:00Z", temperature=60),
            _weather_record(22, "2026-05-20T12:00:00Z", temperature=-50.1),
            _weather_record(23, "2026-05-20T13:00:00Z", temperature=60.1),
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
    accuracy = _manifest(result)["dimensoes_qualidade"]["accuracy"]
    assert result["linhas_gravadas"] == 2
    assert set(restored["temperatura_ar"]) == {-50, 60}
    assert accuracy == {
        "linhas_avaliadas": 4,
        "linhas_aprovadas": 2,
        "linhas_rejeitadas": 2,
    }


def test_empty_silver_batch_writes_zero_count_manifest(tmp_path):
    columns = [
        "id_leitura_origem",
        "id_estacao",
        "data_leitura",
        "temperatura_agua",
        "ph",
        "oxigenio",
        "condutividade",
        "turbidez",
    ]

    result = persistir_silver(
        pd.DataFrame(columns=columns), "qualidade_agua", tmp_path
    )

    assert result["linhas_gravadas"] == 0
    assert result["manifesto"].is_file()
    assert not (tmp_path / "qualidade_agua" / "data_leitura=NaT").exists()


def _reconstruir(tmp_path, referencia, inicio="2026-05-20", fim="2026-05-21"):
    """Usa uma referencia sintetica completa no contrato da reconstrucao."""
    return silver.reconstruir_particoes_silver(
        lambda: referencia.copy(), "qualidade_agua",
        pd.Timestamp(inicio, tz="UTC"), pd.Timestamp(fim, tz="UTC"), tmp_path,
    )


def test_reconstruction_clears_existing_day_only_when_sql_reference_is_empty(tmp_path):
    dados = pd.DataFrame([_water_record("W-1", "2026-05-20T12:00:00Z")])
    persistir_silver(dados, "qualidade_agua", tmp_path)
    destino = tmp_path / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    resultado = _reconstruir(tmp_path, dados.iloc[:0])
    assert pd.read_parquet(destino).empty
    assert resultado["linhas_gravadas"] == 0
    assert _manifest(resultado)["particoes"][0]["linhas_anteriores"] == 1
    assert _manifest(resultado)["particoes"][0]["linhas_finais"] == 0
    assert _reconstruir(tmp_path, dados.iloc[:0])["linhas_gravadas"] == 0


@pytest.mark.parametrize("defeito", ["duplicada", "invalida", "fora", "coluna"])
def test_invalid_reference_preserves_all_partitions(tmp_path, defeito):
    dados = pd.DataFrame([_water_record("W-1", "2026-05-20T12:00:00Z")])
    persistir_silver(dados, "qualidade_agua", tmp_path)
    destino = tmp_path / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    anterior = destino.read_bytes()
    if defeito == "duplicada":
        dados = pd.concat([dados, dados], ignore_index=True)
    elif defeito == "invalida":
        dados["ph"] = 15
    elif defeito == "fora":
        dados["data_leitura"] = "2026-05-21T00:00:00Z"
    else:
        dados = dados.drop(columns="ph")
    with pytest.raises(ValueError):
        _reconstruir(tmp_path, dados)
    assert destino.read_bytes() == anterior


def test_reconstruction_rejects_key_collision_with_untouched_partition(tmp_path):
    dados = pd.DataFrame([_water_record("W-1", "2026-05-19T12:00:00Z")])
    persistir_silver(dados, "qualidade_agua", tmp_path)
    dados["data_leitura"] = "2026-05-20T12:00:00Z"
    with pytest.raises(ValueError, match="fora do periodo"):
        _reconstruir(tmp_path, dados)
    assert not (tmp_path / "qualidade_agua" / "data_leitura=2026-05-20").exists()


@pytest.mark.parametrize("somente_extra", [False, True])
def test_reconstruction_rejects_unexpected_partition_files(tmp_path, somente_extra):
    dados = pd.DataFrame([_water_record("W-1", "2026-05-20T12:00:00Z")])
    persistir_silver(dados, "qualidade_agua", tmp_path)
    extra = tmp_path / "qualidade_agua" / "data_leitura=2026-05-20" / "part-extra.parquet"
    dados.to_parquet(extra, index=False)
    if somente_extra:
        extra.with_name("part-00000.parquet").unlink()
        dados = dados.iloc[:0]
    with pytest.raises(ValueError, match="layout esperado"):
        _reconstruir(tmp_path, dados)


def test_failed_atomic_replace_preserves_previous_file_and_removes_temporary(tmp_path, monkeypatch):
    dados = pd.DataFrame([_water_record("W-1", "2026-05-20T12:00:00Z")])
    persistir_silver(dados, "qualidade_agua", tmp_path)
    destino = tmp_path / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    anterior = destino.read_bytes()
    dados["ph"] = 8

    def falhar(*_args):
        raise OSError("Falha na troca atomica")

    with monkeypatch.context() as patch:
        patch.setattr(silver.os, "replace", falhar)
        with pytest.raises(OSError, match="Falha na troca"):
            _reconstruir(tmp_path, dados)
    assert destino.read_bytes() == anterior
    assert not list(destino.parent.glob("*.tmp"))
    _reconstruir(tmp_path, dados)
    assert pd.read_parquet(destino)["ph"].tolist() == [8]


def test_reconstruction_resumes_after_failure_in_second_partition(tmp_path, monkeypatch):
    dados = pd.DataFrame([
        _water_record("W-1", "2026-05-20T12:00:00Z"),
        _water_record("W-2", "2026-05-21T12:00:00Z"),
    ])
    persistir_silver(dados, "qualidade_agua", tmp_path)
    dados["ph"] = 8
    gravar = silver._gravar_parquet_atomico

    def falhar_segundo(lote, destino):
        if "2026-05-21" in str(destino):
            raise OSError("Falha no segundo dia")
        gravar(lote, destino)

    with monkeypatch.context() as patch:
        patch.setattr(silver, "_gravar_parquet_atomico", falhar_segundo)
        with pytest.raises(OSError, match="segundo dia"):
            _reconstruir(tmp_path, dados, fim="2026-05-22")
    resultado = _reconstruir(tmp_path, dados, fim="2026-05-22")
    assert resultado["linhas_gravadas"] == 2
    for caminho in (tmp_path / "qualidade_agua").glob("data_leitura=*/*.parquet"):
        assert pd.read_parquet(caminho)["ph"].tolist() == [8]


def test_manifest_failure_is_explicit_and_reconstruction_can_be_replayed(tmp_path, monkeypatch):
    dados = pd.DataFrame([_water_record("W-1", "2026-05-20T12:00:00Z")])

    def falhar(*_args):
        raise OSError("Auditoria indisponivel")

    with monkeypatch.context() as patch:
        patch.setattr(silver, "_gravar_json_atomico", falhar)
        with pytest.raises(OSError, match="Auditoria indisponivel"):
            _reconstruir(tmp_path, dados)
    resultado = _reconstruir(tmp_path, dados)
    assert resultado["linhas_gravadas"] == 1
    assert _manifest(resultado)["particoes"][0]["linhas_finais"] == 1


def test_reconstruction_coordinates_with_normal_writer_in_another_process(tmp_path):
    """O escritor nao pode mesclar uma versao antiga enquanto outro a substitui."""
    dados = pd.DataFrame([_water_record("W-1", "2026-05-20T12:00:00Z")])
    novo = _water_record("W-2", "2026-05-20T13:00:00Z")
    pronto = tmp_path / "writer-ready"
    terminou = tmp_path / "writer-done"
    script = (
        "import json,sys; from pathlib import Path; import pandas as pd; "
        "from src.silver.persistencia.Persistir_Silver import persistir_silver; "
        "Path(sys.argv[2]).touch(); "
        "persistir_silver(pd.DataFrame([json.loads(sys.argv[4])]),'qualidade_agua',sys.argv[1]); "
        "Path(sys.argv[3]).touch()"
    )
    processo = None

    def consultar():
        nonlocal processo
        processo = subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), str(pronto), str(terminou), json.dumps(novo)],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        limite = time.monotonic() + 20
        while not pronto.exists():
            if processo.poll() is not None:
                pytest.fail(f"Escritor falhou: {processo.communicate()}")
            if time.monotonic() >= limite:
                pytest.fail("Escritor nao iniciou")
            time.sleep(0.05)
        time.sleep(0.2)
        assert not terminou.exists()
        return dados

    try:
        silver.reconstruir_particoes_silver(
            consultar, "qualidade_agua", pd.Timestamp("2026-05-20", tz="UTC"),
            pd.Timestamp("2026-05-21", tz="UTC"), tmp_path,
        )
        assert processo is not None
        saida, erro = processo.communicate(timeout=20)
        assert processo.returncode == 0, (saida, erro)
    finally:
        if processo is not None and processo.poll() is None:
            processo.kill()
            processo.communicate()
    destino = tmp_path / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    assert set(pd.read_parquet(destino)["id_leitura_origem"]) == {"W-1", "W-2"}
    assert terminou.exists()


def test_dataset_lock_timeout_is_explicit_and_release_allows_retry(tmp_path):
    pasta = tmp_path / "qualidade_agua"
    pasta.mkdir()
    with silver._bloquear_dataset(pasta):
        with pytest.raises(TimeoutError, match="Timeout ao reservar"):
            with silver._bloquear_dataset(pasta, timeout=0):
                pytest.fail("Lock simultaneo")
    with silver._bloquear_dataset(pasta, timeout=0):
        assert (pasta / ".silver.lock").exists()