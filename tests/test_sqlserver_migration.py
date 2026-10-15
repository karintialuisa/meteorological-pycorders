"""ID44: backfill, cutover e exclusoes do legado homologados no DDL real."""

from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.database.dml.Migrar_Leituras import migrar_legado
from src.database.dml.Persistir_Medicoes import carregar_dataframe
from src.database.dml.Insert_Parametros import inserir_parametros
from sqlserver_support import RUN_TESTS, ROOT, disposable_engine


pytestmark = pytest.mark.skipif(not RUN_TESTS, reason="Habilite SQL Server em src/config/.env.test.")


@pytest.fixture
def engine():
    with disposable_engine(legacy=True) as target:
        with target.begin() as connection:
            connection.execute(text("INSERT INTO estado(codigo_ibge,sigla,nome) VALUES(99,'ZZ','Teste')"))
            connection.execute(text(
                "INSERT INTO cidade(id_estado,codigo_ibge,nome) SELECT id,9999999,'Teste' FROM estado"
            ))
            connection.execute(text(
                "INSERT INTO estacao(codigo_origem,nome,status,id_cidade,id_estado) "
                "SELECT 'HISTORY','Teste',1,id,id_estado FROM cidade"
            ))
        inserir_parametros(engine=target)
        yield target


def seed_history(engine):
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO qualidade_agua(id_leitura_origem,id_estacao,data_leitura,"
            "temperatura_agua,ph,oxigenio,condutividade,turbidez,criado_em) "
            "SELECT 'H-001',id,'2026-09-16T09:00:00-03:00',21.123,7.001,8.125,100.999,NULL,"
            "'2026-09-17T12:00:00Z' FROM estacao WHERE codigo_origem='HISTORY'"
        ))
        connection.execute(text(
            "INSERT INTO leitura_meteorologica(id_cidade,id_estacao,temperatura_ar,"
            "umidade,chuva,vento,condicao,data_leitura,criado_em) "
            "SELECT id_cidade,id,24.123,65.25,0.125,4.999,'Nublado','2026-09-16T12:00:00Z',"
            "'2026-09-17T12:00:00Z' FROM estacao WHERE codigo_origem='HISTORY'"
        ))


def snapshot(engine):
    with engine.connect() as connection:
        return (
            connection.execute(text("SELECT * FROM leituras ORDER BY id")).all(),
            connection.execute(text("SELECT * FROM leitura_itens ORDER BY id_leitura,id_parametro")).all(),
        )


def test_migration_reconciles_precision_nulls_timestamps_and_replay(engine):
    seed_history(engine)
    assert migrar_legado(engine) == {"qualidade_agua": 1, "leitura_meteorologica": 1}
    first = snapshot(engine)
    assert len(first[0]) == 2 and len(first[1]) == 9
    assert migrar_legado(engine) == {"qualidade_agua": 1, "leitura_meteorologica": 1}
    assert snapshot(engine) == first
    with engine.connect() as connection:
        values = connection.execute(text(
            "SELECT p.codigo,i.valor_numerico FROM leitura_itens i "
            "JOIN parametros p ON p.id=i.id_parametro JOIN leituras l ON l.id=i.id_leitura "
            "WHERE l.origem='qualidade_agua'"
        )).all()
        assert dict(values) == {
            "TEMP_AGUA": Decimal("21.123000"), "PH": Decimal("7.001000"),
            "OD": Decimal("8.125000"), "COND_ELETRICA": Decimal("100.999000"),
        }
        assert connection.execute(text(
            "SELECT COUNT(*) FROM leituras WHERE id_operador IS NULL "
            "AND data_leitura='2026-09-16T12:00:00Z' AND criado_em='2026-09-17T12:00:00Z'"
        )).scalar_one() == 2


def test_atomic_backfill_conflict_rolls_back_all_events(engine):
    seed_history(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO leituras(origem,chave_origem,id_estacao,data_leitura) "
            "SELECT 'leitura_meteorologica','HISTORY|2026-09-16T12:00:00.000000+00:00',"
            "id,'2026-09-16T13:00:00Z' FROM estacao"
        ))
    original = snapshot(engine)
    with pytest.raises(ValueError, match="conflitante"):
        migrar_legado(engine, arquivar=True)
    assert snapshot(engine) == original
    assert "qualidade_agua" in inspect(engine).get_table_names(schema="dbo")


def test_missing_parameter_rolls_back_header_and_first_item(engine):
    seed_history(engine)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM parametros WHERE codigo='PH'"))
    with pytest.raises(ValueError, match="parametro nao cadastrado"):
        migrar_legado(engine)
    assert snapshot(engine) == ([], [])


def test_technical_sql_failure_rolls_back_complete_backfill(engine):
    seed_history(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TRIGGER dbo.fail_backfill_item ON dbo.leitura_itens AFTER INSERT AS "
            "BEGIN SET NOCOUNT ON; IF EXISTS (SELECT 1 FROM inserted i "
            "JOIN parametros p ON p.id=i.id_parametro WHERE p.codigo='PH') "
            "THROW 51045,'Falha tecnica sintetica',1; END"
        ))
    with pytest.raises(DBAPIError, match="Falha tecnica sintetica"):
        migrar_legado(engine, arquivar=True)
    assert snapshot(engine) == ([], [])
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM qualidade_agua")).scalar_one() == 1
    assert "legado_qualidade_agua" not in inspect(engine).get_table_names(schema="dbo")


def test_archive_preserves_source_ids_blocks_writes_and_allows_cutover(engine):
    seed_history(engine)
    with engine.connect() as connection:
        original_ids = connection.execute(text("SELECT id,id_leitura_origem FROM qualidade_agua")).all()
    migrar_legado(engine, arquivar=True)
    first = snapshot(engine)
    migrar_legado(engine, arquivar=True)
    assert snapshot(engine) == first
    names = inspect(engine).get_table_names(schema="dbo")
    assert "qualidade_agua" not in names and "leitura_meteorologica" not in names
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id,id_leitura_origem FROM legado_qualidade_agua")).all() == original_ids
    for statement in (
        "UPDATE legado_qualidade_agua SET ph=8",
        "DELETE FROM legado_qualidade_agua",
        "INSERT INTO legado_qualidade_agua(id_leitura_origem,id_estacao,data_leitura,ph) "
        "SELECT 'BLOCK',id,'2026-09-16T12:00:00Z',7 FROM estacao",
    ):
        with pytest.raises(DBAPIError, match="somente leitura"):
            with engine.begin() as connection:
                connection.execute(text(statement))
    with engine.begin() as connection:
        # Zero-row cascades cannot prevent deletion of an unrelated station.
        connection.execute(text(
            "INSERT INTO estacao(codigo_origem,nome,id_cidade,id_estado) "
            "SELECT 'UNREFERENCED','Livre',id,id_estado FROM cidade"
        ))
        connection.execute(text(
            "INSERT INTO operadores(cpf_hash,nome_completo_cifrado,id_estacao) "
            "SELECT REPLICATE('a',64),'sintetico',id FROM estacao WHERE codigo_origem='UNREFERENCED'"
        ))
        connection.execute(text("DELETE FROM estacao WHERE codigo_origem='UNREFERENCED'"))
        assert connection.execute(text("SELECT COUNT(*) FROM operadores")).scalar_one() == 0
    accepted = carregar_dataframe(pd.DataFrame([{
        "id_leitura_origem": "POST-CUTOVER", "estacao_id": "HISTORY",
        "data_leitura": "2026-09-18T12:00:00Z", "ph": 7,
    }]), "qualidade_agua", engine)
    assert len(accepted) == 1
    assert len(snapshot(engine)[0]) == 3


def test_legacy_cascades_before_migration_respect_constraints(engine):
    seed_history(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO operadores(cpf_hash,nome_completo_cifrado,id_estacao) "
            "SELECT REPLICATE('b',64),'sintetico',id FROM estacao"
        ))
        connection.execute(text("DELETE FROM estacao"))
        for table in ("qualidade_agua", "leitura_meteorologica", "operadores"):
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
        assert connection.execute(text(
            "SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1"
        )).scalar_one() == 0


@pytest.mark.parametrize("table", ["cidade", "estado"])
def test_location_parent_deletes_are_blocked_and_preserve_rows(engine, table):
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {table}"))
    with engine.connect() as connection:
        assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM estacao")).scalar_one() == 1


def test_normalized_essential_queries_keep_event_granularity(engine):
    seed_history(engine)
    migrar_legado(engine, arquivar=True)
    query = (ROOT / "src" / "database" / "dql" / "consultas-essenciais.sql").read_text(encoding="utf-8")
    with engine.connect() as connection:
        cursor = connection.connection.driver_connection.cursor()
        try:
            cursor.execute(query)
            results = []
            while True:
                if cursor.description:
                    results.append([dict(zip([column[0] for column in cursor.description], row))
                                    for row in cursor.fetchall()])
                if not cursor.nextset():
                    break
        finally:
            cursor.close()
    assert len(results) == 4
    assert all(len(result) == 1 for result in results)
    assert results[0][0]["quantidade_leituras"] == 1
    assert results[1][0]["quantidade_leituras"] == 1
    assert results[2][0]["ph"] == Decimal("7.001000")
    assert results[2][0]["turbidez"] is None
    assert results[3][0]["quantidade_leituras"] == 1
    assert results[3][0]["chuva_acumulada"] == Decimal("0.125000")
