"""Testa normalização dos dados e endpoints de consulta da API."""

import json
import pandas as pd
import pytest
import sys
from pathlib import Path
path = Path(__file__).resolve().parents[1] 
sys.path.append(str(path))  
from src.api import main as api

def write_json(path, content):
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_carregar_e_normalizar_handles_valid_missing_and_invalid_files(tmp_path):
    valid_path = write_json(
        tmp_path / "valid.json",
        {"leituras": [{"cidade": "Recife", "medicao": {"valor": 3}}]},
    )
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{", encoding="utf-8")

    valid = api.carregar_e_normalizar(valid_path, "leituras")

    assert valid.loc[0, "cidade"] == "Recife"
    assert valid.loc[0, "medicao.valor"] == 3
    assert api.carregar_e_normalizar(tmp_path / "missing.json", "leituras").empty
    assert api.carregar_e_normalizar(invalid_path, "leituras").empty


def test_home_reports_api_and_documentation():
    assert api.home() == {"status": "API Online", "documentacao": "/docs"}


def test_listar_cidades_combines_and_sorts_sources(monkeypatch):
    data = {
        "leituras_ambientais": [
            {"cidade": "Recife"},
            {"cidade": "Natal"},
        ],
        "leituras_meteorologicas": [
            {"cidade": "Recife"},
            {"cidade": "Maceio"},
        ],
    }
    monkeypatch.setattr(api, "get_path", lambda key: key)
    monkeypatch.setattr(
        api,
        "carregar_e_normalizar",
        lambda path, key: pd.DataFrame(data[key]),
    )

    assert api.listar_cidades() == ["Maceio", "Natal", "Recife"]


@pytest.mark.parametrize(
    "endpoint",
    [api.obter_leituras_ambientais, api.obter_leituras_meteorologicas],
)
def test_reading_endpoints_filter_city_case_insensitively(monkeypatch, endpoint):
    df = pd.DataFrame(
        [{"cidade": "Recife", "valor": 1}, {"cidade": "Natal", "valor": 2}]
    )
    monkeypatch.setattr(api, "get_path", lambda key: key)
    monkeypatch.setattr(api, "carregar_e_normalizar", lambda path, key: df)

    assert endpoint(cidade="rEcIfE") == [{"cidade": "Recife", "valor": 1}]
    assert endpoint(cidade=None) == [
        {"cidade": "Recife", "valor": 1},
        {"cidade": "Natal", "valor": 2},
    ]


@pytest.mark.parametrize(
    "endpoint",
    [api.obter_leituras_ambientais, api.obter_leituras_meteorologicas],
)
def test_reading_endpoints_return_empty_when_no_data(monkeypatch, endpoint):
    monkeypatch.setattr(api, "get_path", lambda key: key)
    monkeypatch.setattr(
        api, "carregar_e_normalizar", lambda path, key: pd.DataFrame()
    )

    assert endpoint(cidade=None) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))