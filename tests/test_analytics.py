"""Testa leitura de JSON, estatísticas, outliers e filtros dos relatórios."""

import json

import pandas as pd

from src.analytics import Relatorios_estatisticos as relatorios


def test_carregar_json_accepts_object_and_list_shapes(tmp_path):
    object_file = tmp_path / "object.json"
    object_file.write_text(
        json.dumps({"leituras": [{"cidade": "Recife", "valor": 4}]}),
        encoding="utf-8",
    )
    list_file = tmp_path / "list.json"
    list_file.write_text(
        json.dumps([{"leituras": [{"cidade": "Natal", "valor": 6}]}]),
        encoding="utf-8",
    )

    assert relatorios.carregar_json(object_file, "leituras").loc[0, "valor"] == 4
    assert relatorios.carregar_json(list_file, "leituras").loc[0, "cidade"] == "Natal"


def test_carregar_json_returns_empty_dataframe_for_missing_or_invalid_input(
    tmp_path,
):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{", encoding="utf-8")

    assert relatorios.carregar_json(tmp_path / "missing.json", "leituras").empty
    assert relatorios.carregar_json(invalid_file, "leituras").empty


def test_calcular_estatisticas_counts_outliers_and_ignores_invalid_values():
    df = pd.DataFrame({"value": [1, 2, 3, 4, 100, "invalid"]})

    result = relatorios.calcular_estatisticas(
        df, {"value": "Indicador"}, "Teste"
    )

    assert result.loc[0, "Total Registros"] == 5
    assert result.loc[0, "Média"] == 22
    assert result.loc[0, "Mediana"] == 3
    assert result.loc[0, "IQR"] == 2
    assert result.loc[0, "Outliers"] == 1


def test_calcular_estatisticas_returns_empty_when_columns_have_no_values():
    result = relatorios.calcular_estatisticas(
        pd.DataFrame({"value": [None, "invalid"]}),
        {"value": "Indicador", "missing": "Ausente"},
        "Teste",
    )

    assert result.empty


def test_selecionar_cidade_e_estacao_filters_both_datasets(monkeypatch):
    water = pd.DataFrame(
        {
            "cidade": ["Alpha", "Beta", "Beta"],
            "estacao_id": [10, 20, 30],
            "value": [1, 2, 3],
        }
    )
    weather = pd.DataFrame({"cidade": ["Alpha", "Beta"], "value": [4, 5]})
    choices = iter(["2", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(choices))

    water_result, weather_result, city, station = (
        relatorios.selecionar_cidade_e_estacao(water, weather)
    )

    assert city == "Beta"
    assert station == 30
    assert water_result["estacao_id"].tolist() == [30]
    assert weather_result["cidade"].tolist() == ["Beta"]


def test_selecionar_cidade_e_estacao_keeps_all_when_zero_selected(monkeypatch):
    water = pd.DataFrame({"cidade": ["Beta"], "estacao_id": [20]})
    weather = pd.DataFrame({"cidade": ["Beta"]})
    choices = iter(["0", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(choices))

    water_result, weather_result, city, station = (
        relatorios.selecionar_cidade_e_estacao(water, weather)
    )

    assert city == "Todas as Cidades"
    assert station == "Todas as Estações"
    assert len(water_result) == len(weather_result) == 1


def test_main_stops_cleanly_when_no_json_data_is_available(monkeypatch):
    calls = []
    monkeypatch.setattr(relatorios, "configure_logging", lambda root: None)
    monkeypatch.setattr(relatorios, "get_path", lambda key: key)
    monkeypatch.setattr(
        relatorios,
        "carregar_json",
        lambda path, chave_lista: calls.append((path, chave_lista))
        or pd.DataFrame(),
    )

    relatorios.main()

    assert calls == [
        ("INGESTION_LEITURA_AMBIENTAL", "leituras_ambientais"),
        ("INGESTION_LEITURA_METEOROLOGICA", "leituras_meteorologicas"),
    ]