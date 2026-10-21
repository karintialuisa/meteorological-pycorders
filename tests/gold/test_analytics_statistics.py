"""Aceite dos IDs 45-49 e 51: estatisticas e Z-Score sem dependencia de SQL."""

import math
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from src.gold import analytics_stat as analytics


def medicoes(valores, estacao=1, parametro="PH", unidade="pH"):
    return pd.DataFrame({
        "dataset": "qualidade_agua",
        "id_estacao": estacao,
        "codigo_parametro": parametro,
        "unidade_medida": unidade,
        "valor": valores,
    })


def test_five_statistics_match_known_sample():
    resultado = analytics.calcular_estatisticas(medicoes([1, 2, 3, 4])).iloc[0]

    assert resultado["media"] == pytest.approx(2.5)
    assert resultado["mediana"] == pytest.approx(2.5)
    assert resultado["desvio_padrao"] == pytest.approx(math.sqrt(5 / 3))
    assert resultado["variancia"] == pytest.approx(5 / 3)
    assert resultado["q1"] == pytest.approx(1.75)
    assert resultado["q3"] == pytest.approx(3.25)
    assert resultado["iqr"] == pytest.approx(1.5)
    assert resultado["n_validos"] == 4
    assert resultado["ddof"] == 1


@pytest.mark.parametrize("valores,mediana,iqr", [
    ([1, 2], 1.5, 0.5),
    ([1, 2, 3], 2, 1),
    ([-5, -5, 0, 5, 5], 0, 10),
    ([7, 7, 7], 7, 0),
])
def test_linear_quartiles_and_sample_dispersion(valores, mediana, iqr):
    resultado = analytics.calcular_estatisticas(medicoes(valores)).iloc[0]

    assert resultado["mediana"] == pytest.approx(mediana)
    assert resultado["iqr"] == pytest.approx(iqr)
    assert resultado["variancia"] == pytest.approx(pd.Series(valores).var(ddof=1))
    assert resultado["desvio_padrao"] == pytest.approx(pd.Series(valores).std(ddof=1))


def test_singleton_does_not_invent_zero_sample_variance():
    resultado = analytics.calcular_estatisticas(medicoes([7])).iloc[0]

    assert resultado["media"] == resultado["mediana"] == 7
    assert resultado["q1"] == resultado["q3"] == 7
    assert resultado["iqr"] == 0
    assert pd.isna(resultado["desvio_padrao"])
    assert pd.isna(resultado["variancia"])


def test_station_parameter_dataset_and_unit_are_separate_groups():
    entrada = pd.concat([
        medicoes([1, 3]),
        medicoes([10, 20], estacao=2),
        medicoes([100], parametro="TURBIDEZ", unidade="NTU"),
        medicoes([40]).assign(dataset="outro_dataset"),
        medicoes([50], unidade="outra_unidade"),
    ], ignore_index=True)

    resultado = analytics.calcular_estatisticas(entrada)

    assert len(resultado) == 5
    assert sorted(resultado["media"]) == [2, 15, 40, 50, 100]


def test_invalid_measures_are_counted_and_logged(caplog):
    entrada = medicoes(pd.Series([1, 3, None, True, False, "5", "erro", float("inf"),
                                  float("-inf"), float("nan")], dtype=object))

    resultado = analytics.calcular_estatisticas(entrada).iloc[0]

    assert resultado["media"] == 2
    assert resultado["n_validos"] == 2
    assert resultado["n_invalidos"] == 8
    assert "Medidas descartadas" in caplog.text


def test_empty_and_all_invalid_groups_have_no_statistics(caplog):
    assert analytics.calcular_estatisticas(medicoes([])).empty
    assert analytics.calcular_estatisticas(medicoes([None])).empty
    assert "n_validos=0" in caplog.text


def test_missing_columns_and_group_identifiers_are_rejected():
    with pytest.raises(ValueError, match="Colunas ausentes"):
        analytics.calcular_estatisticas(pd.DataFrame())
    with pytest.raises(ValueError, match="Identificacao"):
        analytics.calcular_estatisticas(medicoes([1]).assign(id_estacao=None))


def test_zscore_matches_sample_formula_and_preserves_input():
    entrada = medicoes([1, 2, 3, 4]).assign(id_leitura_origem=["a", "b", "c", "d"])
    original = entrada.copy(deep=True)
    entrada.index = [9, 9, 2, 2]

    resultado = analytics.calcular_z_scores(entrada)

    esperado = [(valor - 2.5) / math.sqrt(5 / 3) for valor in [1, 2, 3, 4]]
    assert resultado["z_score"].tolist() == pytest.approx(esperado)
    assert resultado["z_score"].sum() == pytest.approx(0)
    assert resultado["z_score"].std(ddof=1) == pytest.approx(1)
    assert resultado["id_leitura_origem"].tolist() == ["a", "b", "c", "d"]
    assert resultado["status_zscore"].eq("avaliado").all()
    assert not resultado["anomalia_zscore"].any()
    assert resultado["ddof"].eq(1).all()
    pd.testing.assert_frame_equal(entrada.reset_index(drop=True), original)


@pytest.mark.parametrize("extremo", [100, -100])
def test_zscore_detects_positive_and_negative_extremes(extremo):
    resultado = analytics.calcular_z_scores(medicoes([0] * 10 + [extremo]))

    assert resultado["z_score"].iloc[-1] == pytest.approx(math.copysign(10 / math.sqrt(11), extremo))
    assert resultado["anomalia_zscore"].tolist() == [False] * 10 + [True]


def test_zscore_threshold_is_strict_and_configurable():
    entrada = medicoes([-1, 0, 1])

    igual = analytics.calcular_z_scores(entrada, limiar=1)
    menor = analytics.calcular_z_scores(entrada, limiar=0.5)

    assert igual["z_score"].tolist() == [-1, 0, 1]
    assert igual["anomalia_zscore"].tolist() == [False, False, False]
    assert menor["anomalia_zscore"].tolist() == [True, False, True]
    assert menor["limiar_zscore"].eq(0.5).all()


@pytest.mark.parametrize("limiar", [0, -1, True, None, "3", float("nan"), float("inf")])
def test_zscore_rejects_invalid_thresholds(limiar):
    with pytest.raises(ValueError, match="Limiar"):
        analytics.calcular_z_scores(medicoes([1, 2]), limiar=limiar)


@pytest.mark.parametrize("valores,status", [
    ([7], "amostra_insuficiente"), ([7, 7, 7], "desvio_zero"),
])
def test_zscore_undefined_is_not_classified_as_normal(valores, status, caplog):
    resultado = analytics.calcular_z_scores(medicoes(valores))

    assert resultado["z_score"].isna().all()
    assert resultado["anomalia_zscore"].isna().all()
    assert str(resultado["anomalia_zscore"].dtype) == "boolean"
    assert resultado["status_zscore"].eq(status).all()
    assert status in caplog.text


def test_zscore_invalid_measures_remain_traceable_but_do_not_affect_baseline():
    valores = pd.Series([1, 3, None, True, "5", float("inf")], dtype=object)
    entrada = pd.concat([
        medicoes(valores), medicoes([None, None], estacao=2)
    ], ignore_index=True)

    resultado = analytics.calcular_z_scores(entrada)

    assert len(resultado) == 8
    assert resultado["z_score"].iloc[:2].tolist() == pytest.approx([-1 / math.sqrt(2), 1 / math.sqrt(2)])
    assert resultado["valor"].iloc[2:].isna().all()
    assert resultado["z_score"].iloc[2:].isna().all()
    assert resultado["anomalia_zscore"].iloc[2:].isna().all()
    assert resultado["status_zscore"].iloc[2:].eq("medida_invalida").all()
    assert resultado["n_validos"].tolist() == [2] * 6 + [0, 0]
    assert resultado["n_invalidos"].tolist() == [4] * 6 + [2, 2]


def test_zscore_all_invalid_and_empty_inputs_have_explicit_contract():
    invalido = analytics.calcular_z_scores(medicoes([None]))
    assert invalido["n_validos"].tolist() == [0]
    assert invalido["n_invalidos"].tolist() == [1]
    assert invalido["status_zscore"].tolist() == ["medida_invalida"]
    vazio = analytics.calcular_z_scores(medicoes([]))
    assert vazio.empty
    assert {"z_score", "anomalia_zscore", "status_zscore"}.issubset(vazio.columns)


def test_zscore_groups_are_isolated_even_with_repeated_indices():
    grupos = [
        medicoes([1, 3]), medicoes([100, 104], estacao=2),
        medicoes([5, 15], parametro="TURBIDEZ", unidade="NTU"),
        medicoes([20, 40]).assign(dataset="outro_dataset"),
        medicoes([6, 9], unidade="outra_unidade"),
    ]
    resultado = analytics.calcular_z_scores(pd.concat(grupos))

    assert len(resultado) == 10
    assert resultado["z_score"].tolist() == pytest.approx([-1 / math.sqrt(2), 1 / math.sqrt(2)] * 5)
    assert resultado["n_validos"].eq(2).all()


def test_zscore_rejects_nonfinite_result_instead_of_marking_normal(monkeypatch):
    referencia = analytics.calcular_estatisticas(medicoes([1, 2]))
    referencia["desvio_padrao"] = 1e-320
    monkeypatch.setattr(analytics, "calcular_estatisticas", lambda entrada: referencia)

    with pytest.raises(ValueError, match="Z-Score nao finito"):
        analytics.calcular_z_scores(medicoes([1, 2]))


@pytest.fixture
def gravar_silver(tmp_path):
    def gravar(valores=(1, 2, 3, 4), dataset="qualidade_agua", dia="2026-10-01",
               estacao=1, transformar=None, nome="part-00000.parquet"):
        contrato = analytics.CONTRATOS_DATASETS[dataset]
        dados = {
            "id_estacao": [estacao] * len(valores),
            "data_leitura": pd.date_range(dia, periods=len(valores), freq="h", tz="UTC"),
        }
        dados.update({coluna: list(valores) for coluna in contrato["numericas"]})
        if dataset == "qualidade_agua":
            dados["id_leitura_origem"] = [f"{dia}-{estacao}-{indice}" for indice in range(len(valores))]
        else:
            dados["id_cidade"] = [10] * len(valores)
            dados["condicao"] = ["Sol"] * len(valores)
        df = pd.DataFrame(dados)
        if transformar is not None:
            df = transformar(df)
        destino = tmp_path / "silver" / dataset / f"data_leitura={dia}" / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(destino, engine="pyarrow", index=False)
        return destino
    return gravar


def test_reads_all_nine_numeric_parameters_without_sql(gravar_silver, monkeypatch):
    gravar_silver()
    gravar_silver(dataset="leitura_meteorologica")
    monkeypatch.setattr("config.settings.create_db_engine", lambda: pytest.fail("SQL nao permitido"))

    resultado = analytics.calcular_estatisticas(analytics.ler_medicoes_silver())

    assert set(resultado["codigo_parametro"]) == set(analytics.PARAMETROS.values())
    assert len(resultado) == 9
    assert resultado["media"].eq(2.5).all()
    vento = resultado.loc[resultado["codigo_parametro"] == "VENTO"].iloc[0]
    assert vento["unidade_medida"] == "km/h"


def test_partition_aggregation_uses_observations_not_daily_means(gravar_silver):
    gravar_silver([1], dia="2026-10-01")
    gravar_silver([3, 3, 5], dia="2026-10-02")
    gravar_silver([100], estacao=2, nome="part-00001.parquet")

    resultado = analytics.calcular_estatisticas(analytics.ler_medicoes_silver())

    assert resultado.loc[resultado["id_estacao"] == 1, "media"].eq(3).all()
    assert resultado.loc[resultado["id_estacao"] == 2, "media"].eq(100).all()


def test_reader_preserves_environmental_event_identity_at_same_instant(gravar_silver):
    gravar_silver([1, 3], transformar=lambda df: df.assign(
        data_leitura=pd.Timestamp("2026-10-01", tz="UTC"),
        id_leitura_origem=["evento-a", "evento-b"],
    ))
    gravar_silver([2], dataset="leitura_meteorologica")

    entrada = analytics.ler_medicoes_silver()
    agua = entrada.loc[entrada["dataset"] == "qualidade_agua"]
    meteo = entrada.loc[entrada["dataset"] == "leitura_meteorologica"]

    assert len(agua) == 10
    assert set(agua["id_leitura_origem"]) == {"evento-a", "evento-b"}
    assert agua["data_leitura"].nunique() == 1
    assert meteo["id_leitura_origem"].isna().all()
    assert not meteo.duplicated(["id_estacao", "data_leitura", "codigo_parametro"]).any()
    assert analytics.calcular_estatisticas(agua)["media"].eq(2).all()


@pytest.mark.parametrize("invalido", [True, None, "5", float("inf")])
def test_invalid_measure_in_parquet_is_not_coerced_into_a_number(gravar_silver, invalido, caplog):
    gravar_silver([1, 3], transformar=lambda df: df.assign(ph=[invalido, invalido]))

    resultado = analytics.calcular_estatisticas(analytics.ler_medicoes_silver())

    assert len(resultado) == 4
    assert "PH" not in set(resultado["codigo_parametro"])
    assert resultado["media"].eq(2).all()
    assert "n_invalidos=2 n_validos=0" in caplog.text


def test_meteorological_duplicate_instants_are_rejected(gravar_silver):
    gravar_silver(dataset="leitura_meteorologica", valores=[1, 2], transformar=lambda df: df.assign(
        data_leitura=["2026-10-01T00:00:00Z", "2026-09-30T21:00:00-03:00"]
    ))
    with pytest.raises(ValueError, match="Chaves duplicadas"):
        analytics.ler_medicoes_silver()


def test_date_filter_includes_entire_utc_day_and_prunes_other_partitions(gravar_silver):
    gravar_silver([1], dia="2026-09-30")
    gravar_silver([2, 4], transformar=lambda df: df.assign(
        data_leitura=["2026-10-01T00:00:00Z", "2026-10-02T01:59:59+02:00"]
    ))
    fora = gravar_silver([100], dia="2026-10-02")
    fora.write_bytes(b"Nao e Parquet, mas esta fora do recorte")

    resultado = analytics.ler_medicoes_silver(data_inicio="2026-10-01", data_fim="2026-10-01")

    assert len(resultado) == 10
    assert set(resultado["valor"]) == {2, 4}
    assert str(resultado["data_leitura"].dtype).endswith(", UTC]")


@pytest.mark.parametrize("inicio,fim", [
    ("2026-10-03", "2026-10-01"), ("20261001", None),
    ("2026-02-30", None), (None, "nao-data"),
])
def test_invalid_date_arguments_fail_before_publication(inicio, fim, tmp_path):
    with pytest.raises(ValueError, match="Data"):
        analytics.gerar_relatorio_estatistico(
            saida=tmp_path / "report.csv", data_inicio=inicio, data_fim=fim
        )
    assert not (tmp_path / "report.csv").exists()


@pytest.mark.parametrize("transformar,mensagem", [
    (lambda df: df.drop(columns="turbidez"), "colunas ausentes"),
    (lambda df: df.assign(id_estacao=None), "identificador invalido"),
    (lambda df: df.assign(id_estacao=True), "identificador invalido"),
    (lambda df: df.assign(id_leitura_origem=" "), "id_leitura_origem invalido"),
    (lambda df: df.assign(data_leitura="erro"), "data_leitura invalida"),
    (lambda df: df.assign(data_leitura=123), "timestamp numerico"),
    (lambda df: df.assign(data_leitura="2026-10-02T00:00:00Z"), "fora da particao"),
    (lambda df: pd.concat([df, df], ignore_index=True), "Chaves duplicadas"),
])
def test_invalid_silver_is_not_silently_treated_as_empty(gravar_silver, transformar, mensagem):
    gravar_silver(transformar=transformar)
    with pytest.raises(ValueError, match=mensagem):
        analytics.ler_medicoes_silver()


def test_duplicate_keys_across_partitions_are_rejected(gravar_silver):
    gravar_silver([1], transformar=lambda df: df.assign(id_leitura_origem="mesma"))
    gravar_silver([2], dia="2026-10-02", transformar=lambda df: df.assign(id_leitura_origem="mesma"))
    with pytest.raises(ValueError, match="Chaves duplicadas"):
        analytics.ler_medicoes_silver()


def test_corrupt_parquet_preserves_previous_report(gravar_silver, tmp_path):
    arquivo = gravar_silver()
    arquivo.write_bytes(b"Parquet corrompido")
    saida = tmp_path / "report.csv"
    saida.write_bytes(b"relatorio anterior")

    with pytest.raises(ValueError, match="Falha ao ler Parquet"):
        analytics.gerar_relatorio_estatistico(saida=saida)

    assert saida.read_bytes() == b"relatorio anterior"


def test_csv_snapshot_is_deterministic_and_silver_is_unchanged(gravar_silver, tmp_path):
    origem = gravar_silver()
    original = origem.read_bytes()
    saida = tmp_path / "reports" / "report.csv"

    primeiro = analytics.gerar_relatorio_estatistico(saida=saida)
    conteudo = saida.read_bytes()
    segundo = analytics.gerar_relatorio_estatistico(saida=saida)

    pd.testing.assert_frame_equal(primeiro, segundo)
    assert saida.read_bytes() == conteudo
    assert conteudo.startswith(b"\xef\xbb\xbf")
    assert "dataset;id_estacao;codigo_parametro;unidade_medida;" in conteudo.decode("utf-8-sig")
    relido = pd.read_csv(saida, sep=";")
    assert len(relido) == 5
    assert relido["media"].eq(2.5).all()
    assert relido["periodo_inicio_utc"].eq("2026-10-01T00:00:00+00:00").all()
    assert relido["periodo_fim_exclusivo_utc"].eq("2026-10-02T00:00:00+00:00").all()
    assert origem.read_bytes() == original


def test_singleton_csv_uses_empty_fields_for_sample_dispersion(gravar_silver, tmp_path):
    gravar_silver([7])
    saida = tmp_path / "report.csv"
    analytics.gerar_relatorio_estatistico(saida=saida)
    relido = pd.read_csv(saida, sep=";", keep_default_na=False)
    assert relido["variancia"].eq("").all()
    assert relido["desvio_padrao"].eq("").all()


def test_all_invalid_or_missing_data_does_not_overwrite_report(gravar_silver, tmp_path):
    saida = tmp_path / "report.csv"
    saida.write_bytes(b"anterior")
    with pytest.raises(ValueError, match="Nenhuma leitura"):
        analytics.gerar_relatorio_estatistico(saida=saida)
    gravar_silver([None])
    with pytest.raises(ValueError, match="Nenhuma medida valida"):
        analytics.gerar_relatorio_estatistico(saida=saida)
    assert saida.read_bytes() == b"anterior"


def test_atomic_replace_failure_preserves_report_and_cleans_temporary_file(gravar_silver, tmp_path, monkeypatch):
    gravar_silver()
    saida = tmp_path / "report.csv"
    saida.write_bytes(b"anterior")

    def falhar(*args):
        raise OSError("Falha simulada na publicacao")

    monkeypatch.setattr(analytics.os, "replace", falhar)
    with pytest.raises(OSError, match="Falha simulada"):
        analytics.gerar_relatorio_estatistico(saida=saida)
    assert saida.read_bytes() == b"anterior"
    assert not list(tmp_path.glob(".report.*.tmp"))


def test_report_cannot_overwrite_silver(gravar_silver):
    origem = gravar_silver()
    with pytest.raises(ValueError, match="fora da Silver"):
        analytics.gerar_relatorio_estatistico(saida=origem)


def test_zscore_report_round_trip_replay_and_silver_preservation(gravar_silver, tmp_path, monkeypatch):
    origem = gravar_silver([1, 2, 3, 4])
    original = origem.read_bytes()
    gravar_silver([1, 3], dataset="leitura_meteorologica")
    saida = tmp_path / "z_scores.csv"
    descritivo = tmp_path / "estatisticas.csv"
    monkeypatch.setattr(analytics, "SAIDA_ZSCORE", saida)
    monkeypatch.setattr(analytics, "SAIDA_PADRAO", descritivo)
    analytics.gerar_relatorio_estatistico()
    anterior = descritivo.read_bytes()

    primeiro = analytics.gerar_relatorio_zscore(limiar=0.5)
    conteudo = saida.read_bytes()
    segundo = analytics.gerar_relatorio_zscore(limiar=0.5)

    pd.testing.assert_frame_equal(primeiro, segundo)
    assert len(primeiro) == 28
    assert saida.read_bytes() == conteudo
    assert conteudo.startswith(b"\xef\xbb\xbf")
    relido = pd.read_csv(saida, sep=";")
    assert relido["z_score"].tolist() == pytest.approx(primeiro["z_score"].tolist())
    assert relido["limiar_zscore"].eq(0.5).all()
    assert relido["ddof"].eq(1).all()
    assert relido["status_zscore"].eq("avaliado").all()
    assert set(relido["codigo_parametro"]) == set(analytics.PARAMETROS.values())
    assert relido.loc[relido["dataset"] == "leitura_meteorologica", "id_leitura_origem"].isna().all()
    assert relido["periodo_inicio_utc"].eq("2026-10-01T00:00:00+00:00").all()
    assert relido["periodo_fim_exclusivo_utc"].eq("2026-10-02T00:00:00+00:00").all()
    assert descritivo.read_bytes() == anterior
    assert origem.read_bytes() == original


@pytest.mark.parametrize("valores,status", [([7], "amostra_insuficiente"), ([7, 7], "desvio_zero")])
def test_zscore_report_publishes_valid_but_undefined_scores_as_blank(gravar_silver, tmp_path, valores, status):
    gravar_silver(valores)
    saida = tmp_path / "z_scores.csv"
    analytics.gerar_relatorio_zscore(saida=saida)

    relido = pd.read_csv(saida, sep=";", keep_default_na=False)
    assert relido["z_score"].eq("").all()
    assert relido["anomalia_zscore"].eq("").all()
    assert relido["status_zscore"].eq(status).all()


def test_zscore_report_preserves_invalid_measure_rows(gravar_silver, tmp_path):
    gravar_silver([1, 3], transformar=lambda df: df.assign(ph=["erro", "5"]))
    saida = tmp_path / "z_scores.csv"
    resultado = analytics.gerar_relatorio_zscore(saida=saida)

    invalidas = resultado.loc[resultado["codigo_parametro"] == "PH"]
    assert len(resultado) == 10
    assert invalidas["status_zscore"].eq("medida_invalida").all()
    assert invalidas["n_invalidos"].eq(2).all()
    assert invalidas["valor"].isna().all()
    assert "erro" not in saida.read_text(encoding="utf-8-sig")


def test_zscore_report_filters_utc_period_and_retains_natural_ids(gravar_silver, tmp_path):
    gravar_silver([100], dia="2026-09-30")
    gravar_silver([1, 3], transformar=lambda df: df.assign(
        data_leitura=["2026-10-01T00:00:00Z", "2026-10-02T01:59:59+02:00"],
        id_leitura_origem=["evento-a", "evento-b"],
    ))
    resultado = analytics.gerar_relatorio_zscore(
        saida=tmp_path / "z_scores.csv", data_inicio="2026-10-01", data_fim="2026-10-01"
    )

    assert len(resultado) == 10
    assert resultado["media"].eq(2).all()
    assert set(resultado["id_leitura_origem"]) == {"evento-a", "evento-b"}


@pytest.mark.parametrize("falha", ["ausente", "invalida", "corrompida", "publicacao"])
def test_zscore_report_failure_preserves_previous_csv(gravar_silver, tmp_path, monkeypatch, falha):
    saida = tmp_path / "z_scores.csv"
    saida.write_bytes(b"anterior")
    if falha != "ausente":
        arquivo = gravar_silver([None] if falha == "invalida" else [1, 2])
        if falha == "corrompida":
            arquivo.write_bytes(b"corrompido")
    if falha == "publicacao":
        def falhar(*args):
            raise OSError("Falha simulada")
        monkeypatch.setattr(analytics.os, "replace", falhar)

    with pytest.raises((ValueError, OSError)):
        analytics.gerar_relatorio_zscore(saida=saida)

    assert saida.read_bytes() == b"anterior"
    assert not list(tmp_path.glob(".z_scores.*.tmp"))


def test_zscore_report_rejects_destination_in_silver_and_bad_threshold(gravar_silver, tmp_path):
    arquivo = gravar_silver()
    with pytest.raises(ValueError, match="fora da Silver"):
        analytics.gerar_relatorio_zscore(saida=arquivo)
    with pytest.raises(ValueError, match="Limiar"):
        analytics.gerar_relatorio_zscore(saida=tmp_path / "z.csv", limiar=0)


@pytest.mark.parametrize("direto", [False, True])
def test_zscore_cli_supports_threshold_and_explicit_failure(gravar_silver, tmp_path, direto):
    gravar_silver([1, 2, 3, 4])
    raiz = Path(__file__).resolve().parents[2]
    comando = [sys.executable, str(raiz / "src" / "gold" / "analytics_stat.py")] if direto else [
        sys.executable, "-m", "src.gold.analytics_stat"
    ]
    saida = tmp_path / "z.csv"
    argumentos = ["--analise", "zscore", "--saida", str(saida), "--limiar", "0.5"]
    ambiente = dict(os.environ, LOGS_DIR=str(tmp_path / "logs"))
    resultado = subprocess.run(comando + argumentos, cwd=raiz, env=ambiente,
                               capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    relido = pd.read_csv(saida, sep=";")
    assert relido["anomalia_zscore"].tolist() == [True, False, False, True] * 5
    assert relido["limiar_zscore"].eq(0.5).all()
    anterior = saida.read_bytes()
    for extras in [["--limiar", "nan"], ["--data-inicio", "erro"]]:
        falha = subprocess.run(comando + argumentos + extras, cwd=raiz, env=ambiente,
                               capture_output=True, text=True)
        assert falha.returncode == 1
        assert saida.read_bytes() == anterior
    logs = (tmp_path / "logs" / "execucao_relatorio.log").read_text(encoding="utf-8")
    assert "Relatorio Z-Score publicado" in logs
    assert "avaliadas=20" in logs and "anomalias=10" in logs and "ERROR" in logs


@pytest.mark.parametrize("direto", [False, True])
def test_cli_publishes_csv_and_returns_failure_on_invalid_dates(gravar_silver, tmp_path, direto):
    gravar_silver()
    raiz = Path(__file__).resolve().parents[2]
    comando = [sys.executable, str(raiz / "src" / "gold" / "analytics_stat.py")] if direto else [
        sys.executable, "-m", "src.gold.analytics_stat"
    ]
    saida = tmp_path / "report.csv"
    ambiente = dict(os.environ, LOGS_DIR=str(tmp_path / "logs"))
    argumentos = ["--silver-dir", str(tmp_path / "silver"), "--saida", str(saida)]

    resultado = subprocess.run(comando + argumentos, cwd=raiz, env=ambiente,
                               capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert saida.exists()
    anterior = saida.read_bytes()
    falha = subprocess.run(comando + argumentos + ["--data-inicio", "erro"],
                           cwd=raiz, env=ambiente, capture_output=True, text=True)
    assert falha.returncode == 1
    assert saida.read_bytes() == anterior
    logs = (tmp_path / "logs" / "execucao_relatorio.log").read_text(encoding="utf-8")
    assert "INFO" in logs and "WARNING" in logs and "ERROR" in logs