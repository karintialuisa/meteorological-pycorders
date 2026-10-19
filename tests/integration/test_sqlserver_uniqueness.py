"""Replay, conflito e concorrencia das cargas reais no destino 3FN."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.database.dml import Insert_Leituras_ambiental as ambiental
from src.database.dml import Insert_Leituras_Meteorologica as meteorologica
from src.database.dml.Insert_Parametros import inserir_parametros
from sqlserver_support import RUN_TESTS, disposable_engine


pytestmark = pytest.mark.skipif(not RUN_TESTS, reason="Habilite SQL Server em src/config/.env.")


@pytest.fixture
def sqlserver_engine():
    with disposable_engine() as engine:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO estado(codigo_ibge,sigla,nome) VALUES(99,'ZZ','Estado teste')"))
            connection.execute(text(
                "INSERT INTO cidade(id_estado,codigo_ibge,nome) "
                "SELECT id,9999999,'Cidade teste' FROM estado"
            ))
            connection.execute(text(
                "INSERT INTO estacao(codigo_origem,nome,status,id_cidade,id_estado) "
                "SELECT 'TEST-001','Estacao teste',1,id,id_estado FROM cidade"
            ))
        inserir_parametros(engine=engine)
        yield engine


def batch(origem, **changes):
    common = {"estacao_id": "TEST-001", "data_leitura": "2026-10-12T12:00:00Z"}
    if origem == "qualidade_agua":
        values = {"id_leitura_origem": "WATER-001", "temperatura_agua": 21.5,
                  "ph": 7, "oxigenio": 8, "condutividade": 100, "turbidez": 2.5}
    else:
        values = {"cidade": "Ignorada", "estado": "Ignorado", "temperatura_ar": 24,
                  "umidade": 65, "chuva": 0, "vento": 4.5, "condicao": "Nublado"}
    return pd.DataFrame([{**common, **values, **changes}])


def configure(monkeypatch, engine, origem, provider):
    module, parser = (
        (ambiental, "tabela_ambiental") if origem == "qualidade_agua"
        else (meteorologica, "tabela_metereologica")
    )
    monkeypatch.setattr(module, "create_db_engine", lambda: engine)
    monkeypatch.setattr(module, parser, provider)
    return module


def snapshot(engine):
    with engine.connect() as connection:
        return (
            connection.execute(text("SELECT id,origem,chave_origem,data_leitura FROM leituras ORDER BY id")).all(),
            connection.execute(text(
                "SELECT id_leitura,id_parametro,valor_numerico,valor_texto "
                "FROM leitura_itens ORDER BY id_leitura,id_parametro"
            )).all(),
        )


def test_sqlserver_has_expected_natural_key_constraints(sqlserver_engine):
    with sqlserver_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO leituras(origem,chave_origem,id_estacao,data_leitura) "
            "SELECT 'qualidade_agua','DUP',id,'2026-10-12T12:00:00Z' FROM estacao"
        ))
    with pytest.raises(IntegrityError):
        with sqlserver_engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO leituras(origem,chave_origem,id_estacao,data_leitura) "
                "SELECT 'qualidade_agua','DUP',id,'2026-10-13T12:00:00Z' FROM estacao"
            ))


@pytest.mark.parametrize("origem", ["qualidade_agua", "leitura_meteorologica"])
def test_real_loader_replay_and_conflict_preserve_whole_event(sqlserver_engine, monkeypatch, caplog, origem):
    module = configure(monkeypatch, sqlserver_engine, origem, lambda: batch(origem))
    module.inserir_dados()
    original = snapshot(sqlserver_engine)
    module.inserir_dados()
    assert snapshot(sqlserver_engine) == original
    change = {"turbidez": 75} if origem == "qualidade_agua" else {"temperatura_ar": 31}
    configure(monkeypatch, sqlserver_engine, origem, lambda: batch(origem, **change))
    module.inserir_dados()
    assert snapshot(sqlserver_engine) == original
    assert "conflitante" in caplog.text
    assert len(original[0]) == 1 and len(original[1]) == 5


@pytest.mark.parametrize("origem", ["qualidade_agua", "leitura_meteorologica"])
def test_concurrent_complete_events_are_serialized(sqlserver_engine, monkeypatch, origem):
    module = configure(monkeypatch, sqlserver_engine, origem, lambda: batch(origem))
    # Silver tem seu proprio contrato de arquivos; aqui isolamos concorrencia SQL.
    monkeypatch.setattr(module, "persistir_silver", lambda *args: None)
    started, release = Event(), Event()
    event_globals = module.carregar_dataframe.__globals__["persistir_evento"].__globals__
    original = event_globals["adquirir_lock_etl"]
    first = True
    def hold_lock(connection, resource, timeout_ms=60000):
        nonlocal first
        original(connection, resource, timeout_ms)
        if resource == "etl:leituras" and first:
            first = False
            started.set()
            if not release.wait(30):
                raise TimeoutError("concorrencia nao liberou lock")
    monkeypatch.setitem(event_globals, "adquirir_lock_etl", hold_lock)
    with ThreadPoolExecutor(max_workers=4) as executor:
        initial = executor.submit(module.inserir_dados)
        try:
            assert started.wait(30)
            contenders = [executor.submit(module.inserir_dados) for _ in range(3)]
        finally:
            release.set()
        initial.result(timeout=60)
        for result in contenders:
            result.result(timeout=60)
    headers, items = snapshot(sqlserver_engine)
    assert len(headers) == 1 and len(items) == 5


def test_meteorological_offsets_are_equivalent(sqlserver_engine, monkeypatch):
    module = configure(monkeypatch, sqlserver_engine, "leitura_meteorologica",
                       lambda: batch("leitura_meteorologica"))
    module.inserir_dados()
    original = snapshot(sqlserver_engine)
    configure(monkeypatch, sqlserver_engine, "leitura_meteorologica",
              lambda: batch("leitura_meteorologica", data_leitura="2026-10-12T09:00:00-03:00"))
    module.inserir_dados()
    assert snapshot(sqlserver_engine) == original
