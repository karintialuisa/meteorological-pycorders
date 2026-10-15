"""Regressoes de carga 3FN, atomicidade, replay e reparacao Silver."""

import pandas as pd
import pytest
from unittest.mock import MagicMock
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.database.dml import Insert_Leituras_ambiental as ambiental
from src.database.dml import Insert_Leituras_Meteorologica as meteorologica
from src.database.dml import Insert_Localizacao as localizacao
from src.database.dml.Insert_Parametros import inserir_parametros
from src.database.dml.Migrar_Leituras import migrar_legado
from src.database.dml import Migrar_Leituras as migracao
from src.database.dml.Persistir_Medicoes import carregar_dataframe


def seed_location(engine):
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO estado(id,codigo_ibge,sigla,nome) VALUES(1,35,'SP','Sao Paulo')"
        ))
        connection.execute(text(
            "INSERT INTO cidade(id,id_estado,codigo_ibge,nome) VALUES(10,1,3550308,'Sao Paulo')"
        ))
        connection.execute(text(
            "INSERT INTO estacao(id,codigo_origem,nome,status,id_cidade,id_estado) "
            "VALUES(20,'AMB-001','Nome alteravel',1,10,1)"
        ))
    inserir_parametros(engine=engine)


def water(**changes):
    return {
        "id_leitura_origem": "W-001", "estacao_id": "AMB-001",
        "data_leitura": "2026-05-20T12:00:00Z",
        "temperatura_agua": 21.5, "ph": 7.2, "oxigenio": 8.1,
        "condutividade": 120, "turbidez": 2.8, **changes,
    }


def meteo(**changes):
    return {
        "estacao_id": "AMB-001", "cidade": "Ignorada", "estado": "Ignorado",
        "data_leitura": "2026-05-20T12:00:00Z", "temperatura_ar": 24,
        "umidade": 65, "chuva": 0, "vento": 4.5, "condicao": "Nublado", **changes,
    }


def counts(engine):
    with engine.connect() as connection:
        return tuple(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                     for table in ("leituras", "leitura_itens", "qualidade_agua", "leitura_meteorologica"))


@pytest.mark.parametrize("module,parser", [(ambiental, "tabela_ambiental"), (meteorologica, "tabela_metereologica")])
def test_empty_readings_skip_database_connection(monkeypatch, module, parser):
    monkeypatch.setattr(module, parser, pd.DataFrame)
    monkeypatch.setattr(module, "create_db_engine", lambda: pytest.fail("conexao inesperada"))
    module.inserir_dados()


def test_station_code_resolution_does_not_depend_on_name(banco_teste, caplog):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text(
            "INSERT INTO estacao(id,codigo_origem,nome,status,id_cidade,id_estado) "
            "VALUES(21,'AMB-002','Nome alteravel',1,10,1)"
        ))
    with banco_teste.connect() as connection:
        result = ambiental.resolver_id_estacao(pd.DataFrame([
            water(), water(estacao_id="AMB-002"), water(estacao_id="AUSENTE"),
        ]), connection)
    assert result["id_estacao"].tolist() == [20, 21]
    assert "sem correspondência" in caplog.text


def test_city_resolution_uses_station_relationship(banco_teste):
    seed_location(banco_teste)
    with banco_teste.connect() as connection:
        assert meteorologica.resolver_id_cidade(pd.DataFrame([
            {"id_estacao": 20, "cidade": "Ignorada", "estado": "Ignorado"}
        ]), connection)["id_cidade"].tolist() == [10]
        with pytest.raises(ValueError, match="sem cidade"):
            meteorologica.resolver_id_cidade(pd.DataFrame([{"id_estacao": 999}]), connection)


@pytest.mark.parametrize("module,parser,registro,origem", [
    (ambiental, "tabela_ambiental", water(), "qualidade_agua"),
    (meteorologica, "tabela_metereologica", meteo(), "leitura_meteorologica"),
])
def test_loaders_use_only_3fn_and_replay_preserves_ids(banco_teste, monkeypatch, module, parser, registro, origem):
    seed_location(banco_teste)
    monkeypatch.setattr(module, parser, lambda: pd.DataFrame([registro]))
    monkeypatch.setattr(module, "create_db_engine", lambda: banco_teste)
    module.inserir_dados()
    with banco_teste.connect() as connection:
        first = connection.execute(text("SELECT id,chave_origem,data_leitura FROM leituras")).all()
    module.inserir_dados()
    assert counts(banco_teste) == (1, 5, 0, 0)
    with banco_teste.connect() as connection:
        assert connection.execute(text("SELECT id,chave_origem,data_leitura FROM leituras")).all() == first
        assert connection.execute(text("SELECT origem FROM leituras")).scalar_one() == origem


@pytest.mark.parametrize("registro,origem", [(water(turbidez=75), "qualidade_agua"), (meteo(temperatura_ar=31), "leitura_meteorologica")])
def test_conflicting_replay_keeps_first_whole_event(banco_teste, caplog, registro, origem):
    seed_location(banco_teste)
    first = water() if origem == "qualidade_agua" else meteo()
    carregar_dataframe(pd.DataFrame([first]), origem, banco_teste)
    assert carregar_dataframe(pd.DataFrame([registro]), origem, banco_teste).empty
    assert counts(banco_teste) == (1, 5, 0, 0)
    assert "conflitante" in caplog.text
    with banco_teste.connect() as connection:
        value = connection.execute(text(
            "SELECT valor_numerico FROM leitura_itens i JOIN parametros p ON p.id=i.id_parametro "
            "WHERE p.codigo=:codigo"
        ), {"codigo": "TURBIDEZ" if origem == "qualidade_agua" else "TEMP_AR"}).scalar_one()
    assert value == (2.8 if origem == "qualidade_agua" else 24)


def test_meteorological_offsets_have_same_natural_key(banco_teste):
    seed_location(banco_teste)
    carregar_dataframe(pd.DataFrame([meteo(), meteo(data_leitura="2026-05-20T09:00:00-03:00")]),
                       "leitura_meteorologica", banco_teste)
    assert counts(banco_teste) == (1, 5, 0, 0)


def test_silver_output_uses_only_approved_columns_and_normalized_values(banco_teste):
    seed_location(banco_teste)
    output = carregar_dataframe(pd.DataFrame([
        meteo(cpf="nao-exportar", nome_completo="nao-exportar", condicao=" Nublado ")
    ]), "leitura_meteorologica", banco_teste)
    assert set(output.columns) == {
        "id_estacao", "id_cidade", "data_leitura", "temperatura_ar",
        "umidade", "chuva", "vento", "condicao",
    }
    assert output["condicao"].tolist() == ["Nublado"]


@pytest.mark.parametrize("registro,origem", [
    (water(estacao_id="AUSENTE"), "qualidade_agua"),
    (water(operador_cpf_hash="a"*64), "qualidade_agua"),
    (water(ph=15), "qualidade_agua"),
    (water(oxigenio=-1), "qualidade_agua"),
    (water(condutividade=-1), "qualidade_agua"),
    (water(turbidez=-1), "qualidade_agua"),
    (water(temperatura_agua=float("inf")), "qualidade_agua"),
    (water(ph=7.1234567), "qualidade_agua"),
    (meteo(umidade=101), "leitura_meteorologica"),
    (meteo(chuva=-1), "leitura_meteorologica"),
    (meteo(vento=-1), "leitura_meteorologica"),
    (meteo(vento=float("nan")), "leitura_meteorologica"),
    (meteo(chuva=None), "leitura_meteorologica"),
    (meteo(umidade=None), "leitura_meteorologica"),
    (meteo(data_leitura="2026-01-01"), "leitura_meteorologica"),
])
def test_invalid_events_are_logged_and_leave_no_partial_rows(banco_teste, caplog, registro, origem):
    seed_location(banco_teste)
    assert carregar_dataframe(pd.DataFrame([registro]), origem, banco_teste).empty
    assert counts(banco_teste) == (0, 0, 0, 0)
    assert "Evento rejeitado" in caplog.text


def test_failure_on_second_item_rolls_back_header_and_first_item(banco_teste, caplog):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text("DELETE FROM parametros WHERE codigo='PH'"))
    assert carregar_dataframe(pd.DataFrame([water()]), "qualidade_agua", banco_teste).empty
    assert counts(banco_teste) == (0, 0, 0, 0)
    assert "parametro nao cadastrado" in caplog.text


def test_sql_failure_propagates_and_rolls_back_event(banco_teste):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text(
            "CREATE TRIGGER fail_second BEFORE INSERT ON leitura_itens "
            "WHEN NEW.id_parametro=(SELECT id FROM parametros WHERE codigo='PH') "
            "BEGIN SELECT RAISE(ABORT,'falha tecnica'); END"
        ))
    with pytest.raises(IntegrityError, match="falha tecnica"):
        carregar_dataframe(pd.DataFrame([water()]), "qualidade_agua", banco_teste)
    assert counts(banco_teste) == (0, 0, 0, 0)


def test_silver_failure_is_explicit_and_replay_repairs_it(banco_teste, monkeypatch):
    seed_location(banco_teste)
    monkeypatch.setattr(ambiental, "tabela_ambiental", lambda: pd.DataFrame([water()]))
    monkeypatch.setattr(ambiental, "create_db_engine", lambda: banco_teste)
    original = ambiental.persistir_silver
    def fail(*args):
        raise OSError("disco indisponivel")
    monkeypatch.setattr(ambiental, "persistir_silver", fail)
    with pytest.raises(OSError):
        ambiental.inserir_dados()
    assert counts(banco_teste) == (1, 5, 0, 0)
    monkeypatch.setattr(ambiental, "persistir_silver", original)
    ambiental.inserir_dados()
    from src.config.settings import get_silver_dir
    assert list(get_silver_dir().glob("qualidade_agua/data_leitura=*/part-00000.parquet"))


def test_database_rejects_duplicate_event_identity(banco_teste):
    seed_location(banco_teste)
    carregar_dataframe(pd.DataFrame([water()]), "qualidade_agua", banco_teste)
    with pytest.raises(IntegrityError):
        with banco_teste.begin() as connection:
            connection.execute(text(
                "INSERT INTO leituras(origem,chave_origem,id_estacao,data_leitura) "
                "VALUES('qualidade_agua','W-001',20,'2026-01-01T00:00:00Z')"
            ))


def test_backfill_nulls_precision_and_idempotence(banco_teste):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text("ALTER TABLE qualidade_agua ADD criado_em TEXT"))
        connection.execute(text("ALTER TABLE leitura_meteorologica ADD criado_em TEXT"))
        connection.execute(text(
            "INSERT INTO qualidade_agua(id_leitura_origem,id_estacao,data_leitura,"
            "temperatura_agua,ph,turbidez,criado_em) VALUES"
            "('W-HISTORY',20,'2026-05-20T09:00:00-03:00',21.123,7.001,NULL,'2026-05-21T12:00:00Z')"
        ))
    assert migrar_legado(banco_teste) == {"qualidade_agua": 1, "leitura_meteorologica": 0}
    with banco_teste.connect() as connection:
        first = connection.execute(text("SELECT * FROM leituras")).all()
    migrar_legado(banco_teste)
    assert counts(banco_teste) == (1, 2, 1, 0)
    with banco_teste.connect() as connection:
        assert connection.execute(text("SELECT * FROM leituras")).all() == first


def test_load_requires_archived_history_before_cutover(banco_teste):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text(
            "INSERT INTO qualidade_agua(id_leitura_origem,id_estacao,data_leitura,ph) "
            "VALUES('HISTORY',20,'2026-01-01T00:00:00Z',7)"
        ))
    with pytest.raises(ValueError, match="migracao e arquivamento"):
        carregar_dataframe(pd.DataFrame([water()]), "qualidade_agua", banco_teste)
    assert counts(banco_teste) == (0, 0, 1, 0)


def test_backfill_conflict_rolls_back_all_preceding_events(banco_teste):
    seed_location(banco_teste)
    carregar_dataframe(pd.DataFrame([water()]), "qualidade_agua", banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text("ALTER TABLE qualidade_agua ADD criado_em TEXT"))
        connection.execute(text("ALTER TABLE leitura_meteorologica ADD criado_em TEXT"))
        connection.execute(text(
            "INSERT INTO qualidade_agua(id_leitura_origem,id_estacao,data_leitura,ph,criado_em) VALUES"
            "('FIRST',20,'2026-05-20T12:00:00Z',7,'2026-05-21T12:00:00Z'),"
            "('W-001',20,'2026-05-20T12:00:00Z',8,'2026-05-21T12:00:00Z')"
        ))
    with pytest.raises(ValueError, match="conflitante"):
        migrar_legado(banco_teste)
    assert counts(banco_teste) == (1, 5, 2, 0)


def test_backfill_incompatible_schema_is_rejected_before_writes(banco_teste):
    seed_location(banco_teste)
    with pytest.raises(ValueError, match="schema incompativel"):
        migrar_legado(banco_teste)
    assert counts(banco_teste) == (0, 0, 0, 0)


@pytest.mark.parametrize("changes,duplicate,reason", [
    ({}, True, "chave natural duplicada"),
    ({"station": 999}, False, "estacao orfa"),
    ({"ph": 15}, False, "fora do dominio"),
    ({"date": "nao-e-data"}, False, "data_leitura invalida"),
    ({"key": None}, False, "id_leitura_origem obrigatorio"),
])
def test_backfill_preflight_rejects_bad_historical_data(banco_teste, changes, duplicate, reason):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text("DROP TABLE qualidade_agua"))
        connection.execute(text(
            "CREATE TABLE qualidade_agua (id INTEGER PRIMARY KEY, id_leitura_origem TEXT, "
            "id_estacao INTEGER, data_leitura TEXT, temperatura_agua NUMERIC, ph NUMERIC, "
            "oxigenio NUMERIC, condutividade NUMERIC, turbidez NUMERIC, criado_em TEXT)"
        ))
        connection.execute(text("ALTER TABLE leitura_meteorologica ADD criado_em TEXT"))
        insert = text(
            "INSERT INTO qualidade_agua(id_leitura_origem,id_estacao,data_leitura,ph,criado_em) "
            "VALUES(:key,:station,:date,:ph,'2026-05-21T12:00:00Z')"
        )
        values = {"key": "HISTORY", "station": 20, "date": "2026-05-20T12:00:00Z", "ph": 7, **changes}
        connection.execute(insert, values)
        if duplicate:
            connection.execute(insert, values)
    with pytest.raises(ValueError, match=reason):
        migrar_legado(banco_teste)
    assert counts(banco_teste) == (0, 0, 2 if duplicate else 1, 0)


@pytest.mark.parametrize("args,exit_code", [
    (["--help"], 0), ([], 2), (["--expected-database", "monitoramento_lgpd_test"], 2),
])
def test_migration_cli_requires_explicit_target_and_confirmation(monkeypatch, args, exit_code):
    monkeypatch.setattr("sys.argv", ["migrar", *args])
    monkeypatch.setattr(migracao, "create_db_engine", lambda: pytest.fail("conexao inesperada"))
    monkeypatch.setattr(migracao, "configure_logging", lambda **kwargs: pytest.fail("log antes de parse"))
    with pytest.raises(SystemExit) as error:
        migracao.main()
    assert error.value.code == exit_code


def test_migration_cli_rejects_wrong_database_and_disposes_engine(monkeypatch):
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = "outro_banco"
    monkeypatch.setattr("sys.argv", ["migrar", "--expected-database", "monitoramento_lgpd_test", "--confirm"])
    monkeypatch.setattr(migracao, "create_db_engine", lambda: engine)
    monkeypatch.setattr(migracao, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(migracao, "migrar_legado", lambda *args, **kwargs: pytest.fail("migracao indevida"))
    with pytest.raises(ValueError, match="difere"):
        migracao.main()
    engine.dispose.assert_called_once()


def test_location_loading_is_idempotent_for_existing_records(banco_teste, monkeypatch):
    monkeypatch.setattr(localizacao, "tabela_estado", lambda: pd.DataFrame([
        {"codigo_ibge_estado": 35, "sigla_estado": "SP", "nome_estado": "Sao Paulo"}]))
    monkeypatch.setattr(localizacao, "tabela_cidade", lambda: pd.DataFrame([
        {"codigo_ibge_cidade": 3550308, "nome_cidade": "Sao Paulo", "sigla_estado": "SP"}]))
    monkeypatch.setattr(localizacao, "tabela_estacao", lambda cidades, estados: pd.DataFrame([
        {"id": "AMB-001", "nome": "Estacao Centro", "status_estacao": 1,
         "codigo_ibge_cidade": 3550308, "codigo_ibge_estado": 35}]))
    for _ in range(2):
        with banco_teste.begin() as connection:
            ids = localizacao.inserir_localizacao(connection)
            localizacao.inserir_estacoes(connection, ids)
    with banco_teste.connect() as connection:
        assert [connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in ("estado", "cidade", "estacao")] == [1, 1, 1]


def test_limpar_localizacao_preserves_records_in_append_mode(connection):
    connection.execute(text("INSERT INTO estado(id,codigo_ibge,sigla,nome) VALUES(1,35,'SP','Sao Paulo')"))
    localizacao.limpar_localizacao(connection)
    assert connection.execute(text("SELECT COUNT(*) FROM estado")).scalar_one() == 1
