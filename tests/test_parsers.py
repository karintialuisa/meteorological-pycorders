"""Testa parsing, normalização, deduplicação e validação dos dados JSON."""

import json
import sys
from pathlib import Path
path = Path(__file__).resolve().parents[1] 
sys.path.append(str(path))  

import pandas as pd
import pytest

from src.ingestion.localizacao import Parse_localizacao_JSON as localizacao
from src.ingestion.leituras import Parse_LeituraAmbiental as ambiental
from src.ingestion.leituras import Parse_LeituraMetereologica as meteorologica


def save_json(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_tabela_estado_and_cidade_normalize_and_remove_duplicates(
    monkeypatch, tmp_path
):
    state_path = save_json(
        tmp_path,
        "states.json",
        [
            {"ibge": 35, "sigla": "SP", "nome": "Sao Paulo"},
            {"ibge": 35, "sigla": "SP", "nome": "Sao Paulo"},
        ],
    )
    city_path = save_json(
        tmp_path,
        "cities.json",
        [
            {"ibge": 3550308, "cidade": "Sao Paulo", "sigla_estado": "SP"},
            {"ibge": 3550308, "cidade": "Sao Paulo", "sigla_estado": "SP"},
        ],
    )
    paths = {
        "INGESTION_LOCALIZACAO_ESTADOS": state_path,
        "INGESTION_LOCALIZACAO_MUNICIPIOS": city_path,
    }
    monkeypatch.setattr(localizacao, "get_path", paths.__getitem__)

    states = localizacao.tabela_estado()
    cities = localizacao.tabela_cidade()

    assert states.to_dict("records") == [
        {"codigo_ibge_estado": 35, "sigla_estado": "SP", "nome_estado": "Sao Paulo"}
    ]
    assert cities.to_dict("records") == [
        {"codigo_ibge_cidade": 3550308, "nome_cidade": "Sao Paulo", "sigla_estado": "SP"}
    ]


def test_tabela_estacao_resolves_geography_and_status(monkeypatch, tmp_path):
    station_path = save_json(
        tmp_path,
        "stations.json",
        {
            "estacoes_ambientais": [
                {
                    "id": 7,
                    "tipo": "monitoramento_ambiental",
                    "nome": "Rio",
                    "descricao": "Centro",
                    "status": "ativa",
                    "localizacao": {"estado": "SP", "city_name": "Sao Paulo"},
                },
                {
                    "id": 8,
                    "tipo": "monitoramento_ambiental",
                    "nome": "Lago",
                    "descricao": "Sul",
                    "status": "inativa",
                    "localizacao": {"estado": "SP", "city_name": "Sao Paulo"},
                },
            ]
        },
    )
    monkeypatch.setattr(localizacao, "get_path", lambda key: station_path)
    cities = pd.DataFrame(
        [{"nome_cidade": "Sao Paulo", "sigla_estado": "SP", "codigo_ibge_cidade": 3550308}]
    )
    states = pd.DataFrame(
        [{"sigla_estado": "SP", "codigo_ibge_estado": 35, "nome_estado": "Sao Paulo"}]
    )

    result = localizacao.tabela_estacao(cities, states)

    assert result["nome"].tolist() == ["Rio - Centro", "[Desativado] Lago - Sul"]
    assert result["estacao_id"].tolist() == [7, 8]
    assert result["tipo"].tolist() == [
        "monitoramento_ambiental",
        "monitoramento_ambiental",
    ]
    assert result["status_estacao"].tolist() == [1, 0]
    assert result["codigo_ibge_cidade"].tolist() == [3550308, 3550308]


def test_tabela_estacao_rejects_unmatched_location(monkeypatch, tmp_path):
    station_path = save_json(
        tmp_path,
        "stations.json",
        {
            "estacoes_ambientais": [
                {
                    "id": 7,
                    "tipo": "monitoramento_ambiental",
                    "nome": "Rio",
                    "descricao": "Centro",
                    "status": "ativa",
                    "localizacao": {"estado": "RJ", "city_name": "Niteroi"},
                }
            ]
        },
    )
    monkeypatch.setattr(localizacao, "get_path", lambda key: station_path)

    with pytest.raises(ValueError, match="cidade ou estado"):
        localizacao.tabela_estacao(
            pd.DataFrame(columns=["nome_cidade", "sigla_estado", "codigo_ibge_cidade"]),
            pd.DataFrame(columns=["sigla_estado", "codigo_ibge_estado", "nome_estado"]),
        )


def test_tabela_ambiental_normalizes_deduplicates_and_parses_dates(
    monkeypatch, tmp_path, caplog
):
    records = [
        {
            "id": "LEIT-AMB-000001",
            "estacao_id": 7,
            "timestamp": "2026-01-01T10:00:00Z",
            "qualidade_agua": {
                "temperatura": {"valor": 20},
                "ph": {"valor": 7},
                "oxigenio_dissolvido": {"valor": 8},
                "condutividade": {"valor": 100},
            },
        },
        {
            "id": "LEIT-AMB-000002",
            "estacao_id": 7,
            "timestamp": "2026-01-02T10:00:00Z",
            "qualidade_agua": {
                "temperatura": {"valor": 21},
                "ph": {"valor": 7.1},
                "oxigenio_dissolvido": {"valor": 8.2},
                "condutividade": {"valor": 101},
            },
        },
        {
            "id": "LEIT-AMB-000002",
            "estacao_id": 7,
            "timestamp": "2026-01-02T10:00:00Z",
            "qualidade_agua": {
                "temperatura": {"valor": 22},
                "ph": {"valor": 7.1},
                "oxigenio_dissolvido": {"valor": 8.2},
                "condutividade": {"valor": 101},
            },
        },
        {
            "id": "LEIT-AMB-000003",
            "estacao_id": 7,
            "timestamp": "2026-01-02T10:00:00Z",
            "qualidade_agua": {
                "temperatura": {"valor": 19},
                "ph": {"valor": 7.0},
                "oxigenio_dissolvido": {"valor": 8.0},
                "condutividade": {"valor": 99},
            },
        },
    ]
    path = save_json(tmp_path, "water.json", {"leituras_ambientais": records})
    monkeypatch.setattr(ambiental, "get_path", lambda key: path)

    result = ambiental.tabela_ambiental()

    assert len(result) == 3
    assert str(result.loc[0, "data_leitura"].tz) == "UTC"
    assert result.loc[0, "temperatura_agua"] == 21
    assert set(result["id_leitura_origem"]) == {
        "LEIT-AMB-000001",
        "LEIT-AMB-000002",
        "LEIT-AMB-000003",
    }
    assert result["temperatura_agua"].tolist().count(21) == 1
    assert {"ph", "oxigenio", "condutividade"}.issubset(result.columns)
    assert any("Retransmissão conflitante no lote" in rec.message for rec in caplog.records)


def test_tabela_ambiental_rejects_incomplete_readings_and_logs_reasons(
    monkeypatch, tmp_path, caplog
):
    def record(reading_id, station_id=7, timestamp="2026-01-01T10:00:00Z"):
        return {
            "id": reading_id,
            "estacao_id": station_id,
            "timestamp": timestamp,
            "qualidade_agua": {
                "temperatura": {"valor": 20},
                "ph": {"valor": 7},
                "oxigenio_dissolvido": {"valor": 8},
                "condutividade": {"valor": 100},
            },
        }

    records = [
        record("valid"),
        record("no-station", station_id=None),
        record("blank-station", station_id="  "),
        record("no-timestamp", timestamp=None),
        record("invalid-timestamp", timestamp="data-invalida"),
    ]
    path = save_json(tmp_path, "water.json", {"leituras_ambientais": records})
    monkeypatch.setattr(ambiental, "get_path", lambda key: path)

    result = ambiental.tabela_ambiental()

    assert len(result) == 1
    assert result["estacao_id"].notna().all()
    assert result["estacao_id"].astype(str).str.strip().ne("").all()
    assert result["data_leitura"].notna().all()
    assert str(result.loc[0, "data_leitura"].tz) == "UTC"
    rejected = [
        record
        for record in caplog.records
        if "rejeitada por incompletude" in record.message
    ]
    assert len(rejected) == 4
    assert any("estacao_id ausente" in record.message for record in rejected)
    assert any(
        "timestamp ausente ou inválido" in record.message
        for record in rejected
    )


def test_tabela_ambiental_rejects_records_without_required_keys(
    monkeypatch, tmp_path, caplog
):
    path = save_json(
        tmp_path,
        "water.json",
        {"leituras_ambientais": [{"qualidade_agua": {}}]},
    )
    monkeypatch.setattr(ambiental, "get_path", lambda key: path)

    result = ambiental.tabela_ambiental()

    assert result.empty
    assert len(caplog.records) == 1
    assert "estacao_id ausente" in caplog.records[0].message
    assert "timestamp ausente ou inválido" in caplog.records[0].message
    assert "id de origem ausente" in caplog.records[0].message


def test_tabela_metereologica_normalizes_numeric_fields_and_deduplicates(
    monkeypatch, tmp_path
):
    def record(timestamp, temperature):
        return {
            "cidade": "Recife",
            "estado": "Pernambuco",
                "estacao_id": "MET-RECIFE-01",
            "timestamp": timestamp,
            "dados_meteorologicos": {
                "temperatura_ar": {"valor": temperature},
                "condicao": {"description": "Nublado"},
                "umidade": {"valor": "70"},
                "chuva": {"valor": "0"},
                "vento": {"velocidade": "5.2"},
            },
        }

    path = save_json(
        tmp_path,
        "weather.json",
        {
            "leituras_meteorologicas": [
                record("2026-01-01T10:00:00-03:00", "bad"),
                record("2026-01-02T10:00:00-04:00", "25"),
                record("2026-01-02T10:00:00-04:00", "25"),
            ]
        },
    )
    monkeypatch.setattr(meteorologica, "get_path", lambda key: path)

    result = meteorologica.tabela_metereologica()

    assert len(result) == 2
    assert result["estacao_id"].tolist() == ["MET-RECIFE-01", "MET-RECIFE-01"]
    assert str(result["data_leitura"].dt.tz) == "UTC"
    assert pd.isna(result.loc[result["data_leitura"].dt.day == 1, "temperatura_ar"]).all()
    latest = result.loc[result["data_leitura"].dt.day == 2].iloc[0]
    assert latest["temperatura_ar"] == 25
    assert latest["umidade"] == 70
    assert latest["vento"] == 5.2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))