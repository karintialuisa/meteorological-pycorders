"""Regressoes de carga 3FN, atomicidade, replay e reparacao Silver."""

from decimal import Decimal

import pandas as pd
import pytest
from unittest.mock import MagicMock
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.database.dml import Insert_Leituras_ambiental as ambiental
from src.database.dml import Insert_Leituras_Meteorologica as meteorologica
from src.database.dml import Insert_Localizacao as localizacao
from src.database.dml.Insert_Parametros import inserir_parametros
from src.database.dml.Migrar_Leituras import migrar_legado
from src.database.dml import Migrar_Leituras as migracao
from src.database.dml import Persistir_Medicoes as persistencia
from src.database.dml.Persistir_Medicoes import carregar_dataframe
from src.silver.persistencia.Exportar_Cadastros import exportar_cadastros


def seed_location(engine):
    with engine.begin() as connection:
        connection.execute(text("SET IDENTITY_INSERT dbo.estado ON"))
        connection.execute(text(
            "INSERT INTO dbo.estado(id,codigo_ibge,sigla,nome) VALUES(1,35,'SP','Sao Paulo')"
        ))
        connection.execute(text("SET IDENTITY_INSERT dbo.estado OFF"))
        connection.execute(text("SET IDENTITY_INSERT dbo.cidade ON"))
        connection.execute(text(
            "INSERT INTO dbo.cidade(id,id_estado,codigo_ibge,nome) VALUES(10,1,3550308,'Sao Paulo')"
        ))
        connection.execute(text("SET IDENTITY_INSERT dbo.cidade OFF"))
        connection.execute(text("SET IDENTITY_INSERT dbo.estacao ON"))
        connection.execute(text(
            "INSERT INTO dbo.estacao(id,codigo_origem,nome,status,id_cidade,id_estado) "
            "VALUES(20,'AMB-001','Nome alteravel',1,10,1)"
        ))
        connection.execute(text("SET IDENTITY_INSERT dbo.estacao OFF"))
    inserir_parametros(engine=engine)


def test_exported_cadastros_preserve_reading_ids_and_refresh(banco_teste):
    seed_location(banco_teste)
    destinos = exportar_cadastros(banco_teste)
    estados = pd.read_parquet(destinos["estados"])
    cidades = pd.read_parquet(destinos["cidades"])
    estacoes = pd.read_parquet(destinos["estacoes"])
    assert estados["id_estado"].tolist() == [1]
    assert estados["codigo_ibge_estado"].tolist() == [35]
    assert cidades["id_cidade"].tolist() == [10]
    assert cidades["codigo_ibge_cidade"].tolist() == [3550308]
    assert estacoes["id_estacao"].tolist() == [20]
    dimensao = estacoes.merge(cidades, on="id_cidade", validate="many_to_one").merge(
        estados, on="id_estado", validate="many_to_one"
    )
    for origem, registro in (("qualidade_agua", water()), ("leitura_meteorologica", meteo())):
        leituras = carregar_dataframe(pd.DataFrame([registro]), origem, banco_teste)
        localizadas = leituras.merge(
            dimensao[["id_estacao", "nome_cidade", "sigla_estado"]],
            on="id_estacao", validate="many_to_one",
        )
        assert len(localizadas) == len(leituras) == 1
        assert localizadas["nome_cidade"].tolist() == ["Sao Paulo"]
        assert localizadas["sigla_estado"].tolist() == ["SP"]
    with banco_teste.begin() as connection:
        connection.execute(text("UPDATE estacao SET nome='Nome atualizado' WHERE id=20"))
    assert exportar_cadastros(banco_teste) == destinos
    assert pd.read_parquet(destinos["estacoes"])["nome_estacao"].tolist() == ["Nome atualizado"]
    assert len(list(destinos["estacoes"].parent.glob("*.parquet"))) == 3


def test_exported_cadastros_require_populated_database(banco_teste):
    from config.settings import get_silver_dir

    with pytest.raises(ValueError, match="vazio no banco"):
        exportar_cadastros(banco_teste)
    assert not (get_silver_dir() / "cadastros").exists()


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


def test_load_progress_reports_counts_without_database(monkeypatch, caplog):
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = MagicMock(id=20, id_cidade=10)
    monkeypatch.setattr(persistencia, "require_sqlserver", lambda engine: None)
    monkeypatch.setattr(persistencia, "_validar_legado_inativo", lambda connection: None)
    persistir = MagicMock()
    monkeypatch.setattr(persistencia, "persistir_evento", persistir)
    monkeypatch.setattr(persistencia, "monotonic", lambda: 10.0)
    registros = [meteo() for _ in range(101)] + [meteo(umidade=101)]

    with caplog.at_level("INFO"):
        aprovados = carregar_dataframe(pd.DataFrame(registros), "leitura_meteorologica", engine)

    assert len(aprovados) == persistir.call_count == 101
    progresso = [record.message for record in caplog.records if "Progresso SQL:" in record.message]
    assert len(progresso) == 3
    assert "processados=1/102" in progresso[0]
    assert "processados=100/102" in progresso[1]
    assert "processados=102/102 (100.0%) aceitos=101 rejeitados=1" in progresso[2]
    assert "restante_estimado=0.0s" in progresso[2]
    assert "conectando e validando legado" in caplog.text
    assert "Carga SQL concluida" in caplog.text


def test_load_progress_reports_elapsed_interval(monkeypatch, caplog):
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = MagicMock(id=20, id_cidade=10)
    monkeypatch.setattr(persistencia, "require_sqlserver", lambda engine: None)
    monkeypatch.setattr(persistencia, "_validar_legado_inativo", lambda connection: None)
    monkeypatch.setattr(persistencia, "persistir_evento", MagicMock())
    instantes = iter([0.0, 0.0, 1.0, 6.0, 7.0, 7.0])
    monkeypatch.setattr(persistencia, "monotonic", lambda: next(instantes))

    with caplog.at_level("INFO"):
        carregar_dataframe(pd.DataFrame([meteo()] * 3), "leitura_meteorologica", engine)

    progresso = [record.message for record in caplog.records if "Progresso SQL:" in record.message]
    assert len(progresso) == 3
    assert "processados=2/3" in progresso[1]
    assert "decorrido=6.0s" in progresso[1]
    assert "restante_estimado=3.0s" in progresso[1]


def test_meteorological_loader_logs_stages(monkeypatch, caplog):
    dados = pd.DataFrame([meteo()])
    monkeypatch.setattr(meteorologica, "tabela_metereologica", lambda: dados)
    monkeypatch.setattr(meteorologica, "create_db_engine", MagicMock())
    monkeypatch.setattr(meteorologica, "carregar_dataframe", lambda *args: dados)
    silver = MagicMock()
    monkeypatch.setattr(meteorologica, "persistir_silver", silver)

    with caplog.at_level("INFO"):
        meteorologica.inserir_dados()

    silver.assert_called_once_with(dados, "leitura_meteorologica")
    assert "lendo e tratando JSON Bronze" in caplog.text
    assert "Tratamento meteorologico concluido: leituras=1" in caplog.text
    assert "Persistencia Silver iniciada" in caplog.text
    assert "Persistencia Silver concluida" in caplog.text
    assert "aceitos=1 rejeitados=0 tempo_total=" in caplog.text


def test_station_code_resolution_does_not_depend_on_name(banco_teste, caplog):
    seed_location(banco_teste)
    with banco_teste.begin() as connection:
        connection.execute(text("SET IDENTITY_INSERT dbo.estacao ON"))
        connection.execute(text(
            "INSERT INTO dbo.estacao(id,codigo_origem,nome,status,id_cidade,id_estado) "
            "VALUES(21,'AMB-002','Nome alteravel',1,10,1)"
        ))
        connection.execute(text("SET IDENTITY_INSERT dbo.estacao OFF"))
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
    assert value == (Decimal("2.8") if origem == "qualidade_agua" else Decimal("24"))


def test_meteorological_offsets_have_same_natural_key(banco_teste):
    seed_location(banco_teste)
    carregar_dataframe(pd.DataFrame([meteo(), meteo(data_leitura="2026-05-20T09:00:00-03:00")]),
                       "leitura_meteorologica", banco_teste)
    assert counts(banco_teste) == (1, 5, 0, 0)


def test_progress_counts_insertion_replay_and_rejection(banco_teste):
    seed_location(banco_teste)
    chamadas = []
    output = carregar_dataframe(
        pd.DataFrame([meteo(), meteo(), meteo(vento=-1)]),
        "leitura_meteorologica", banco_teste,
        progresso=lambda atual, total: chamadas.append((atual, total)),
    )
    assert chamadas == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert len(output) == 2
    assert counts(banco_teste) == (1, 5, 0, 0)


def test_meteorological_progress_initial_interval_and_final(capsys):
    for atual in range(251):
        meteorologica.exibir_progresso(atual, 250)
    assert capsys.readouterr().out.splitlines() == [
        f"Meteorologia: {atual}/250 leituras processadas"
        for atual in (0, 100, 200, 250)
    ]


def test_meteorological_loader_wires_progress(
    banco_teste, monkeypatch, capsys
):
    seed_location(banco_teste)
    monkeypatch.setattr(meteorologica, "tabela_metereologica", lambda: pd.DataFrame([meteo()]))
    monkeypatch.setattr(meteorologica, "create_db_engine", lambda: banco_teste)
    meteorologica.inserir_dados()
    assert capsys.readouterr().out.splitlines() == [
        "Meteorologia: 0/1 leituras processadas",
        "Meteorologia: 1/1 leituras processadas",
    ]


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
            "CREATE TRIGGER dbo.fail_second ON dbo.leitura_itens AFTER INSERT AS "
            "BEGIN SET NOCOUNT ON; "
            "IF EXISTS (SELECT 1 FROM inserted i JOIN dbo.parametros p "
            "ON p.id=i.id_parametro WHERE p.codigo='PH') "
            "BEGIN; THROW 51000, 'falha tecnica', 1; END; END"
        ))
<<<<<<< HEAD
    chamadas = []
    with pytest.raises(IntegrityError, match="falha tecnica"):
        carregar_dataframe(
            pd.DataFrame([water()]), "qualidade_agua", banco_teste,
            progresso=lambda atual, total: chamadas.append((atual, total)),
        )
    assert chamadas == [(0, 1)]
=======
    with pytest.raises(DBAPIError, match="falha tecnica"):
        carregar_dataframe(pd.DataFrame([water()]), "qualidade_agua", banco_teste)
>>>>>>> origin/feature/wagner2
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
    from config.settings import get_silver_dir
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
    with banco_teste.begin() as connection:
        connection.execute(text("ALTER TABLE dbo.qualidade_agua DROP COLUMN temperatura_agua"))
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
        connection.execute(text("DROP TABLE dbo.qualidade_agua"))
        connection.execute(text(
            "CREATE TABLE dbo.qualidade_agua (id BIGINT IDENTITY(1,1) PRIMARY KEY, "
            "id_leitura_origem VARCHAR(100), id_estacao BIGINT, data_leitura VARCHAR(40), "
            "temperatura_agua NUMERIC(8,3), ph NUMERIC(5,3), oxigenio NUMERIC(10,3), "
            "condutividade NUMERIC(12,3), turbidez NUMERIC(12,3), criado_em VARCHAR(40))"
        ))
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


def test_limpar_localizacao_preserves_records_in_append_mode(banco_teste):
    with banco_teste.begin() as connection:
        connection.execute(text(
            "INSERT INTO dbo.estado(codigo_ibge,sigla,nome) VALUES(35,'SP','Sao Paulo')"
        ))
        localizacao.limpar_localizacao(connection)
        assert connection.execute(text("SELECT COUNT(*) FROM dbo.estado")).scalar_one() == 1
