"""Testa leitura de JSON, estatísticas, outliers e filtros dos relatórios."""

import json
import sys
from pathlib import Path
import pandas as pd
import pytest
from sqlalchemy import text

path = Path(__file__).resolve().parents[1] 
sys.path.append(str(path))  
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
    assert result.loc[0, "Desvio Padrão"] == 43.62
    assert result.loc[0, "Variância"] == 1902.5
    assert result.loc[0, "IQR"] == 2
    assert result.loc[0, "Outliers"] == 1
    assert result.loc[0, "Relatório"] == "Teste"
    assert result.loc[0, "Leituras"] == "Indicador"


def test_calcular_estatisticas_uses_zero_standard_deviation_for_one_reading():
    result = relatorios.calcular_estatisticas(
        pd.DataFrame({"value": [7]}), {"value": "Indicador"}, "Teste"
    )

    assert result.loc[0, "Total Registros"] == 1
    assert result.loc[0, "Média"] == 7
    assert result.loc[0, "Mediana"] == 7
    assert result.loc[0, "Desvio Padrão"] == 0.0
    assert result.loc[0, "Variância"] == 0.0
    assert result.loc[0, "IQR"] == 0
    assert result.loc[0, "Outliers"] == 0


def test_calcular_estatisticas_groups_each_parameter_by_station():
    readings = pd.DataFrame(
        {
            "estacao_id": [10, 10, 20, 20],
            "estacao": ["Norte", "Norte", "Sul", "Sul"],
            "temperature": [1, 3, 10, 14],
            "ph": [6, 8, 7, 9],
        }
    )

    result = relatorios.calcular_estatisticas(
        readings,
        {"temperature": "Temperatura", "ph": "pH"},
        "Teste",
    )

    assert result[["Estação ID", "Estação", "Leituras"]].values.tolist() == [
        [10, "Norte", "Temperatura"],
        [10, "Norte", "pH"],
        [20, "Sul", "Temperatura"],
        [20, "Sul", "pH"],
    ]
    norte_temperature = result.loc[
        (result["Estação ID"] == 10) & (result["Leituras"] == "Temperatura")
    ].iloc[0]
    sul_temperature = result.loc[
        (result["Estação ID"] == 20) & (result["Leituras"] == "Temperatura")
    ].iloc[0]

    assert norte_temperature["Média"] == 2
    assert norte_temperature["Mediana"] == 2
    assert norte_temperature["Desvio Padrão"] == 1.41
    assert norte_temperature["Variância"] == 2
    assert norte_temperature["IQR"] == 1
    assert sul_temperature["Média"] == 12
    assert sul_temperature["Variância"] == 8
    assert sul_temperature["IQR"] == 2


def test_calcular_estatisticas_returns_empty_when_columns_have_no_values():
    result = relatorios.calcular_estatisticas(
        pd.DataFrame({"value": [None, "invalid"]}),
        {"value": "Indicador", "missing": "Ausente"},
        "Teste",
    )

    assert result.empty


def test_identificar_outliers_iqr_returns_records_and_thresholds():
    readings = pd.DataFrame(
        {
            "ID": [1, 2, 3, 4, 5, 6],
            "Data/Hora": ["d1", "d2", "d3", "d4", "d5", "d6"],
            "temperatura": [-50, 1, 2, 3, 4, 100],
        }
    )

    result = relatorios.identificar_outliers_iqr(
        readings, {"temperatura": "Temperatura da água"}
    )

    assert result["ID"].tolist() == [1, 6]
    assert result["Indicador"].tolist() == [
        "Temperatura da água",
        "Temperatura da água",
    ]
    assert result["Valor da leitura"].tolist() == [-50, 100]
    assert result["Limite inferior"].tolist() == [-2.5, -2.5]
    assert result["Limite superior"].tolist() == [7.5, 7.5]


def test_identificar_outliers_iqr_returns_empty_for_values_inside_limits():
    result = relatorios.identificar_outliers_iqr(
        pd.DataFrame({"value": [1, 2, 3, 4]}), {"value": "Indicador"}
    )

    assert result.empty


def test_carregar_dados_sql_returns_station_context_and_measurements(banco_teste):
    with banco_teste.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO estado (id, codigo_ibge, sigla, nome) "
                "VALUES (1, 35, 'SP', 'Sao Paulo')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO cidade (id, id_estado, codigo_ibge, nome) "
                "VALUES (10, 1, 3550308, 'Sao Paulo')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO estacao (id, nome, status, id_cidade, id_estado) "
                "VALUES (20, 'Estacao Centro', 1, 10, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO qualidade_agua "
                "(id, id_estacao, data_leitura, temperatura_agua, ph, "
                "oxigenio, condutividade) "
                "VALUES (1, 20, '2026-01-01', 21.5, 7.2, 8.1, 120.0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO leitura_meteorologica "
                "(id, id_cidade, id_estacao, temperatura_ar, umidade, chuva, "
                "vento, condicao, data_leitura) "
                "VALUES (1, 10, 20, 24.0, 65.0, 0.0, 4.5, 'Nublado', "
                "'2026-01-01')"
            )
        )

    water, weather = relatorios.carregar_dados_sql(banco_teste)

    assert water.loc[0, "estacao_id"] == 20
    assert water.loc[0, "estacao"] == "Estacao Centro"
    assert water.loc[0, "temperatura_agua"] == 21.5
    assert weather.loc[0, "estacao_id"] == 20
    assert weather.loc[0, "estacao"] == "Estacao Centro"
    assert weather.loc[0, "temperatura_ar"] == 24.0


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


def test_main_stops_cleanly_when_no_sql_data_is_available(monkeypatch):
    monkeypatch.setattr(relatorios, "configure_logging", lambda root: None)
    monkeypatch.setattr(
        relatorios,
        "carregar_dados_sql",
        lambda: (pd.DataFrame(), pd.DataFrame()),
    )

    relatorios.main()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))