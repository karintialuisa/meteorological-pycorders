"""Backfill por periodo com JSON real, SQL isolado e Silver temporaria."""

import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as parquet
import pytest
from sqlalchemy import text

from src.database.dml import Backfill_Leituras as backfill
from src.database.dml.Insert_Parametros import inserir_parametros
from src.silver.etl import Parse_LeituraAmbiental as ambiental
from src.silver.etl import Parse_LeituraMetereologica as meteorologica
from sqlserver_support import RUN_TESTS, disposable_engine


@pytest.fixture
def fontes_historicas(tmp_path, monkeypatch):
    """Configura JSONs sinteticos e Silver temporaria para ambos os bancos."""
    fontes = {
        "INGESTION_LEITURA_AMBIENTAL": tmp_path / "water.json",
        "INGESTION_LEITURA_METEOROLOGICA": tmp_path / "weather.json",
    }
    monkeypatch.setattr(backfill, "get_path", fontes.__getitem__)
    monkeypatch.setattr(ambiental, "get_path", fontes.__getitem__)
    monkeypatch.setattr(meteorologica, "get_path", fontes.__getitem__)
    datas = [
        "2026-05-19T23:59:59Z",
        "2026-05-19T21:00:00-03:00",
        "2026-05-20T12:00:00Z",
        "2026-05-21T00:00:00Z",
    ]
    agua = []
    meteo = []
    for indice, instante in enumerate(datas):
        comum = {"estacao_id": "AMB-001", "timestamp": instante}
        agua.append({
            **comum, "id": f"W-{indice}",
            "qualidade_agua": {
                "temperatura": {"valor": 20},
                "ph": {"valor": 7},
                "oxigenio_dissolvido": {"valor": 8},
                "condutividade": {"valor": 100},
                "turbidez": {"valor": 3},
            },
        })
        meteo.append({
            **comum, "cidade": "Sao Paulo", "estado": "SP",
            "dados_meteorologicos": {
                "temperatura_ar": {"valor": 24},
                "umidade": {"valor": 65},
                "chuva": {"valor": 0},
                "vento": {"velocidade": 4},
                "condicao": {"description": "Nublado"},
            },
        })
    fontes["INGESTION_LEITURA_AMBIENTAL"].write_text(
        json.dumps({"leituras_ambientais": agua}), encoding="utf-8",
    )
    fontes["INGESTION_LEITURA_METEOROLOGICA"].write_text(
        json.dumps({"leituras_meteorologicas": meteo}), encoding="utf-8",
    )
    return tmp_path / "silver"


@pytest.fixture
def historico(fontes_historicas, banco_teste):
    """Prepara os relacionamentos no SQL Server descartavel."""
    with banco_teste.begin() as connection:
        connection.execute(text(
            "SET IDENTITY_INSERT dbo.estado ON; "
            "INSERT INTO dbo.estado(id,codigo_ibge,sigla,nome) VALUES(1,35,'SP','Sao Paulo'); "
            "SET IDENTITY_INSERT dbo.estado OFF"
        ))
        connection.execute(text(
            "SET IDENTITY_INSERT dbo.cidade ON; "
            "INSERT INTO dbo.cidade(id,id_estado,codigo_ibge,nome) VALUES(10,1,3550308,'Sao Paulo'); "
            "SET IDENTITY_INSERT dbo.cidade OFF"
        ))
        connection.execute(text(
            "SET IDENTITY_INSERT dbo.estacao ON; "
            "INSERT INTO dbo.estacao(id,codigo_origem,nome,status,id_cidade,id_estado) "
            "VALUES(20,'AMB-001','Estacao',1,10,1); "
            "SET IDENTITY_INSERT dbo.estacao OFF"
        ))
    inserir_parametros(engine=banco_teste)
    return fontes_historicas


def _eventos(engine):
    """Consulta identidade e valores para comprovar preservacao no replay."""
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT l.id,l.origem,l.chave_origem,l.data_leitura,i.id_parametro,"
            "i.valor_numerico,i.valor_texto FROM leituras l "
            "JOIN leitura_itens i ON i.id_leitura=l.id ORDER BY l.id,i.id_parametro"
        )).all()


@pytest.mark.parametrize("dataset,origem", [
    ("ambiental", "qualidade_agua"),
    ("meteorologica", "leitura_meteorologica"),
])
def test_backfill_filters_utc_replays_and_preserves_outside_period(
    historico, banco_teste, dataset, origem,
):
    """Executa parsers/carga/Silver reais e verifica fronteiras e idempotencia."""
    _verificar_backfill(historico, banco_teste, dataset, origem)


@pytest.mark.skipif(
    not RUN_TESTS, reason="Habilite SQL Server descartavel em src/config/.env.",
)
@pytest.mark.parametrize("dataset,origem", [
    ("ambiental", "qualidade_agua"),
    ("meteorologica", "leitura_meteorologica"),
])
def test_backfill_sqlserver_disposable(fontes_historicas, dataset, origem, monkeypatch):
    """Homologa o mesmo fluxo no DDL real, com limpeza pelo lifecycle seguro."""
    with disposable_engine() as engine:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO estado(codigo_ibge,sigla,nome) VALUES(99,'ZZ','Estado teste')"
            ))
            connection.execute(text(
                "INSERT INTO cidade(id_estado,codigo_ibge,nome) "
                "SELECT id,9999999,'Cidade teste' FROM estado"
            ))
            connection.execute(text(
                "INSERT INTO estacao(codigo_origem,nome,status,id_cidade,id_estado) "
                "SELECT 'AMB-001','Estacao teste',1,id,id_estado FROM cidade"
            ))
        inserir_parametros(engine=engine)
        _verificar_backfill(fontes_historicas, engine, dataset, origem)
        _verificar_reconstrucao(fontes_historicas, engine, dataset, origem, monkeypatch)


def _verificar_backfill(historico, banco_teste, dataset, origem):
    """Verifica replay e reconstrução usando SQL Server descartável."""
    backfill.reprocessar_periodo(dataset, "2026-05-19", "2026-05-20", engine=banco_teste)
    fora = historico / origem / "data_leitura=2026-05-19" / "part-00000.parquet"
    bytes_fora = fora.read_bytes()
    eventos_fora = _eventos(banco_teste)

    resultado = backfill.reprocessar_periodo(
        dataset, "2026-05-20", "2026-05-21", engine=banco_teste,
    )

    assert resultado[dataset] == {
        "selecionados": 2, "aprovados": 2, "rejeitados": 0, "gravados_silver": 2,
    }
    destino = historico / origem / "data_leitura=2026-05-20" / "part-00000.parquet"
    linhas = pd.read_parquet(destino)
    assert linhas["data_leitura"].tolist() == [
        pd.Timestamp("2026-05-20T00:00:00Z"),
        pd.Timestamp("2026-05-20T12:00:00Z"),
    ]
    assert not (historico / origem / "data_leitura=2026-05-21").exists()
    assert fora.read_bytes() == bytes_fora
    assert _eventos(banco_teste)[:5] == eventos_fora
    eventos = _eventos(banco_teste)
    bytes_destino = destino.read_bytes()

    repetido = backfill.reprocessar_periodo(
        dataset, "2026-05-20", "2026-05-21", engine=banco_teste,
    )
    assert repetido[dataset]["gravados_silver"] == 0
    assert _eventos(banco_teste) == eventos
    assert destino.read_bytes() == bytes_destino

    destino.unlink()
    reparado = backfill.reprocessar_periodo(
        dataset, "2026-05-20", "2026-05-21", engine=banco_teste,
    )
    assert reparado[dataset]["gravados_silver"] == 2
    assert _eventos(banco_teste) == eventos
    assert fora.read_bytes() == bytes_fora


def test_backfill_both_datasets(historico, banco_teste):
    resultado = backfill.reprocessar_periodo(
        "ambos", "2026-05-20", "2026-05-21", engine=banco_teste,
    )
    assert set(resultado) == {"ambiental", "meteorologica"}
    assert all(item["aprovados"] == 2 for item in resultado.values())


def _verificar_reconstrucao(historico, engine, dataset, origem, monkeypatch):
    """Repara duplicatas, valores e linhas extras sem depender de JSON completo."""
    backfill.reprocessar_periodo(dataset, "2026-05-19", "2026-05-22", engine=engine)
    pasta = historico / origem
    destino = pasta / "data_leitura=2026-05-20" / "part-00000.parquet"
    fora = {
        caminho: caminho.read_bytes() for caminho in pasta.glob("data_leitura=*/part-00000.parquet")
        if caminho != destino
    }
    eventos = _eventos(engine)
    referencia = pd.read_parquet(destino)
    extras = referencia.iloc[[0]].copy()
    if dataset == "ambiental":
        extras["id_leitura_origem"] = "W-INDEVIDA"
        coluna = "ph"
        parser_nome = "tabela_ambiental"
    else:
        extras["data_leitura"] = pd.Timestamp("2026-05-20T13:00:00Z")
        coluna = "temperatura_ar"
        parser_nome = "tabela_metereologica"
    corrompido = pd.concat([referencia, referencia, extras], ignore_index=True)
    corrompido[coluna] = 8
    corrompido.to_parquet(destino, index=False)
    parser = getattr(backfill, parser_nome)
    monkeypatch.setattr(backfill, parser_nome, lambda: parser().iloc[[1]].copy())

    for _ in range(2):
        resultado = backfill.reprocessar_periodo(
            dataset, "2026-05-20", "2026-05-21", engine=engine, reconstruir_silver=True,
        )
        assert resultado[dataset] == {
            "selecionados": 1, "aprovados": 1, "rejeitados": 0, "gravados_silver": 2,
        }
        pd.testing.assert_frame_equal(pd.read_parquet(destino), referencia)
        assert _eventos(engine) == eventos
        assert all(caminho.read_bytes() == conteudo for caminho, conteudo in fora.items())
    manifestos = [
        json.loads(caminho.read_text(encoding="utf-8"))
        for caminho in (historico / "_audit" / origem).glob("*.json")
    ]
    reconstrucoes = [item for item in manifestos if item.get("modo") == "reconstrucao_sql"]
    assert sorted(item["particoes"][0]["linhas_anteriores"] for item in reconstrucoes) == [2, 5]
    assert all(item["particoes"][0]["linhas_finais"] == 2 for item in reconstrucoes)


@pytest.mark.parametrize("dataset,origem", [
    ("ambiental", "qualidade_agua"),
    ("meteorologica", "leitura_meteorologica"),
])
def test_backfill_reconstruction_matches_sql_with_partial_json(
    historico, banco_teste, dataset, origem, monkeypatch,
):
    _verificar_reconstrucao(historico, banco_teste, dataset, origem, monkeypatch)


def test_backfill_reconstruction_reads_sql_even_when_json_period_is_empty(
    historico, banco_teste, monkeypatch,
):
    backfill.reprocessar_periodo("ambos", "2026-05-20", "2026-05-21", engine=banco_teste)
    original = _eventos(banco_teste)
    for parser_nome in ("tabela_ambiental", "tabela_metereologica"):
        dados = getattr(backfill, parser_nome)().iloc[:0]
        monkeypatch.setattr(backfill, parser_nome, lambda dados=dados: dados.copy())
    resultado = backfill.reprocessar_periodo(
        "ambos", "2026-05-20", "2026-05-21", engine=banco_teste, reconstruir_silver=True,
    )
    assert all(item["selecionados"] == 0 and item["gravados_silver"] == 2 for item in resultado.values())
    assert _eventos(banco_teste) == original


@pytest.mark.parametrize("dataset,origem", [
    ("ambiental", "qualidade_agua"),
    ("meteorologica", "leitura_meteorologica"),
])
def test_backfill_empty_sql_reference_clears_stale_partition_with_typed_schema(
    historico, banco_teste, dataset, origem, monkeypatch,
):
    backfill.reprocessar_periodo(dataset, "2026-05-20", "2026-05-21", engine=banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text("DELETE FROM leituras"))
    parser_nome = "tabela_ambiental" if dataset == "ambiental" else "tabela_metereologica"
    vazios = getattr(backfill, parser_nome)().iloc[:0]
    monkeypatch.setattr(backfill, parser_nome, lambda: vazios.copy())
    resultado = backfill.reprocessar_periodo(
        dataset, "2026-05-20", "2026-05-21", engine=banco_teste, reconstruir_silver=True,
    )
    destino = historico / origem / "data_leitura=2026-05-20" / "part-00000.parquet"
    assert resultado[dataset]["gravados_silver"] == 0
    assert pd.read_parquet(destino).empty
    assert not any(pa.types.is_null(campo.type) for campo in parquet.read_schema(destino))
    assert _eventos(banco_teste) == []


def test_backfill_invalid_sql_reference_preserves_previous_silver(
    historico, banco_teste, monkeypatch,
):
    backfill.reprocessar_periodo("ambiental", "2026-05-20", "2026-05-21", engine=banco_teste)
    destino = historico / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    anterior = destino.read_bytes()
    with banco_teste.begin() as connection:
        connection.execute(text(
            "DELETE FROM leitura_itens WHERE id_parametro IN "
            "(SELECT id FROM parametros WHERE codigo='PH')"
        ))
    vazios = backfill.tabela_ambiental().iloc[:0]
    monkeypatch.setattr(backfill, "tabela_ambiental", lambda: vazios.copy())
    with pytest.raises(ValueError, match="Referencia SQL rejeitada"):
        backfill.reprocessar_periodo(
            "ambiental", "2026-05-20", "2026-05-21", engine=banco_teste, reconstruir_silver=True,
        )
    assert destino.read_bytes() == anterior


def test_backfill_reconstruction_refuses_active_legacy_even_with_empty_json(
    historico, banco_teste, monkeypatch,
):
    backfill.reprocessar_periodo("ambiental", "2026-05-20", "2026-05-21", engine=banco_teste)
    destino = historico / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    anterior = destino.read_bytes()
    with banco_teste.begin() as connection:
        connection.execute(text(
            "INSERT INTO qualidade_agua(id_leitura_origem,id_estacao,data_leitura) "
            "VALUES('LEGADO',20,'2026-05-20T12:00:00+00:00')"
        ))
    vazios = backfill.tabela_ambiental().iloc[:0]
    monkeypatch.setattr(backfill, "tabela_ambiental", lambda: vazios.copy())
    with pytest.raises(ValueError, match="legado ativo"):
        backfill.reprocessar_periodo(
            "ambiental", "2026-05-20", "2026-05-21", engine=banco_teste, reconstruir_silver=True,
        )
    assert destino.read_bytes() == anterior


def test_backfill_conflict_cancels_reconstruction(historico, banco_teste, monkeypatch, caplog):
    backfill.reprocessar_periodo("ambiental", "2026-05-20", "2026-05-21", engine=banco_teste)
    destino = historico / "qualidade_agua" / "data_leitura=2026-05-20" / "part-00000.parquet"
    anterior = destino.read_bytes()
    parser = backfill.tabela_ambiental

    def conflitantes():
        dados = parser()
        dados["ph"] = 8
        return dados

    monkeypatch.setattr(backfill, "tabela_ambiental", conflitantes)
    resultado = backfill.reprocessar_periodo(
        "ambiental", "2026-05-20", "2026-05-21", engine=banco_teste, reconstruir_silver=True,
    )
    assert resultado["ambiental"]["rejeitados"] == 2
    assert destino.read_bytes() == anterior
    assert "Reconstrucao Silver cancelada" in caplog.text


def test_backfill_empty_period_does_not_connect(historico, monkeypatch):
    def conexao_inesperada():
        pytest.fail("Periodo sem leituras nao deve abrir conexao.")
    monkeypatch.setattr(backfill, "create_db_engine", conexao_inesperada)
    resultado = backfill.reprocessar_periodo("ambos", "2025-01-01", "2025-01-02")
    assert all(item["selecionados"] == 0 for item in resultado.values())


def test_backfill_recovers_after_silver_failure(historico, banco_teste, monkeypatch):
    writer = backfill.persistir_silver

    def falha_silver(*_args):
        raise OSError("Falha de escrita simulada")
    monkeypatch.setattr(backfill, "persistir_silver", falha_silver)
    with pytest.raises(OSError, match="Falha de escrita"):
        backfill.reprocessar_periodo(
            "ambiental", "2026-05-20", "2026-05-21", engine=banco_teste,
        )
    eventos = _eventos(banco_teste)
    assert len(eventos) == 10
    monkeypatch.setattr(backfill, "persistir_silver", writer)
    resultado = backfill.reprocessar_periodo(
        "ambiental", "2026-05-20", "2026-05-21", engine=banco_teste,
    )
    assert resultado["ambiental"]["gravados_silver"] == 2
    assert _eventos(banco_teste) == eventos


@pytest.mark.parametrize("inicio,fim", [
    ("invalid", "2026-05-21"),
    ("2026-02-30", "2026-05-21"),
    ("20260520", "2026-05-21"),
    ("2026-05-20", "2026-05-20"),
    ("2026-05-21", "2026-05-20"),
])
def test_backfill_rejects_invalid_period_before_reading_source(monkeypatch, inicio, fim):
    monkeypatch.setattr(backfill, "get_path", lambda _key: pytest.fail("Leitura inesperada"))
    with pytest.raises(ValueError):
        backfill.reprocessar_periodo("ambos", inicio, fim)


def test_backfill_rejects_unknown_dataset():
    with pytest.raises(ValueError, match="Dataset de backfill desconhecido"):
        backfill.reprocessar_periodo("desconhecido", "2026-05-20", "2026-05-21")


def test_backfill_conflict_is_reported_and_original_is_preserved(
    historico, banco_teste, caplog, monkeypatch,
):
    backfill.reprocessar_periodo("ambiental", "2026-05-20", "2026-05-21", engine=banco_teste)
    original = _eventos(banco_teste)
    parser = backfill.tabela_ambiental

    def dados_conflitantes():
        dados = parser()
        dados["ph"] = 8
        return dados
    monkeypatch.setattr(backfill, "tabela_ambiental", dados_conflitantes)
    resultado = backfill.reprocessar_periodo(
        "ambiental", "2026-05-20", "2026-05-21", engine=banco_teste,
    )
    assert resultado["ambiental"]["rejeitados"] == 2
    assert "conflitante" in caplog.text
    assert _eventos(banco_teste) == original


@pytest.mark.parametrize("rejeitados,codigo", [(0, 0), (1, 1)])
def test_cli_returns_failure_for_rejected_events(monkeypatch, rejeitados, codigo):
    monkeypatch.setattr(backfill, "configure_logging", lambda **_kwargs: None)
    monkeypatch.setattr(
        backfill, "reprocessar_periodo",
        lambda *_args, **_kwargs: {"ambiental": {"rejeitados": rejeitados}},
    )
    assert backfill.main([
        "--dataset", "ambiental", "--data-inicio", "2026-05-20", "--data-fim", "2026-05-21",
    ]) == codigo


def test_cli_logs_invalid_period_and_returns_failure(monkeypatch, caplog):
    monkeypatch.setattr(backfill, "configure_logging", lambda **_kwargs: None)
    assert backfill.main([
        "--dataset", "ambos", "--data-inicio", "2026-05-21", "--data-fim", "2026-05-20",
    ]) == 1
    assert "Backfill interrompido" in caplog.text


def test_cli_enables_reconstruction_only_when_requested(monkeypatch):
    monkeypatch.setattr(backfill, "configure_logging", lambda **_kwargs: None)
    opcoes = {}

    def executar(*_args, **kwargs):
        opcoes.update(kwargs)
        return {"ambiental": {"rejeitados": 0}}

    monkeypatch.setattr(backfill, "reprocessar_periodo", executar)
    assert backfill.main([
        "--dataset", "ambiental", "--data-inicio", "2026-05-20",
        "--data-fim", "2026-05-21", "--reconstruir-silver",
    ]) == 0
    assert opcoes == {"reconstruir_silver": True}
