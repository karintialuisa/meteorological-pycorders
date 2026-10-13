"""3.2 Validacao opt-in de unicidade em uma instancia SQL Server descartavel.

Configure RUN_SQLSERVER_UNIQUENESS_TESTS=1,
SQLSERVER_UNIQUENESS_TEST_DISPOSABLE=1 e
SQLSERVER_UNIQUENESS_TEST_URL e SQLSERVER_UNIQUENESS_TEST_EXPECTED_SERVER antes
de executar este modulo. A instancia deve ser isolada; os scripts DDL do projeto
usam o nome fixo de banco monitoramento.
"""

from concurrent.futures import ThreadPoolExecutor
import os
import re
from threading import Event, Lock
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from src.database.dml import Insert_Leituras_ambiental as ambiental
from src.database.dml import Insert_Leituras_Meteorologica as meteorologica


TEST_URL = os.getenv("SQLSERVER_UNIQUENESS_TEST_URL")
EXPECTED_SERVER = os.getenv("SQLSERVER_UNIQUENESS_TEST_EXPECTED_SERVER")
RUN_TESTS = os.getenv("RUN_SQLSERVER_UNIQUENESS_TESTS") == "1"
DISPOSABLE_CONFIRMED = os.getenv("SQLSERVER_UNIQUENESS_TEST_DISPOSABLE") == "1"
pytestmark = pytest.mark.skipif(
    not (RUN_TESTS and TEST_URL),
    reason=(
        "Defina RUN_SQLSERVER_UNIQUENESS_TESTS=1 e "
        "SQLSERVER_UNIQUENESS_TEST_URL para habilitar os testes opt-in."
    ),
)


def _database_name(connection_url: str) -> str:
    url = make_url(connection_url)
    if url.database:
        return url.database

    odbc_connect = url.query.get("odbc_connect", "")
    match = re.search(
        r"(?:^|;)\s*(?:DATABASE|INITIAL CATALOG)\s*=\s*([^;]+)",
        odbc_connect,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


@pytest.fixture(scope="module")
def sqlserver_engine():
    if not DISPOSABLE_CONFIRMED:
        pytest.fail(
            "Confirme que a instância SQL Server é descartável definindo "
            "SQLSERVER_UNIQUENESS_TEST_DISPOSABLE=1; nenhum dado foi alterado."
        )
    if not EXPECTED_SERVER:
        pytest.fail(
            "Defina SQLSERVER_UNIQUENESS_TEST_EXPECTED_SERVER com o valor de "
            "SERVERPROPERTY('ServerName') da instância descartável."
        )
    if _database_name(TEST_URL).casefold() != "monitoramento":
        pytest.fail(
            "A URL de teste precisa apontar para o banco monitoramento em "
            "uma instância isolada; nenhum dado foi alterado."
        )

    engine = create_engine(TEST_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            database = connection.execute(text("SELECT DB_NAME()")).scalar_one()
            if database.casefold() != "monitoramento":
                pytest.fail(
                    "A conexão não selecionou o banco monitoramento; "
                    "nenhum dado foi alterado."
                )
            server_name = connection.execute(
                text("SELECT CONVERT(nvarchar(128), SERVERPROPERTY('ServerName'))")
            ).scalar_one()
            if server_name.casefold() != EXPECTED_SERVER.casefold():
                pytest.fail(
                    "A instância SQL Server conectada não corresponde a "
                    "SQLSERVER_UNIQUENESS_TEST_EXPECTED_SERVER; "
                    "nenhum dado foi alterado."
                )

            tables = set(
                connection.execute(
                    text(
                        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                        "WHERE TABLE_SCHEMA = 'dbo'"
                    )
                ).scalars()
            )
            required = {
                "estado",
                "cidade",
                "estacao",
                "qualidade_agua",
                "leitura_meteorologica",
            }
            missing = required - tables
            if missing:
                pytest.fail(
                    "Aplique os scripts DDL na instância descartável antes dos "
                    f"testes; tabelas ausentes: {sorted(missing)}."
                )
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def synthetic_station(sqlserver_engine):
    token = uuid4().hex
    state_name = f"ITEM27-STATE-{token}"
    city_name = f"ITEM27-CITY-{token}"
    station_code = f"ITEM27-{token}"
    station_name = f"ITEM27-STATION-{token}"

    with sqlserver_engine.begin() as connection:
        for _ in range(20):
            state_sigla = uuid4().hex[:2].upper()
            exists = connection.execute(
                text("SELECT 1 FROM dbo.estado WHERE sigla = :sigla"),
                {"sigla": state_sigla},
            ).first()
            if exists is None:
                break
        else:
            pytest.fail("Não foi possível reservar uma sigla sintética de estado.")

        for _ in range(20):
            state_code = 100_000_000 + int(uuid4().hex[:8], 16) % 1_000_000_000
            exists = connection.execute(
                text("SELECT 1 FROM dbo.estado WHERE codigo_ibge = :codigo"),
                {"codigo": state_code},
            ).first()
            if exists is None:
                break
        else:
            pytest.fail("Não foi possível reservar um código sintético de estado.")

        for _ in range(20):
            city_code = 1_000_000 + int(uuid4().hex[:8], 16) % 900_000_000
            exists = connection.execute(
                text("SELECT 1 FROM dbo.cidade WHERE codigo_ibge = :codigo"),
                {"codigo": city_code},
            ).first()
            if exists is None:
                break
        else:
            pytest.fail("Não foi possível reservar um código sintético de cidade.")

        state_id = connection.execute(
            text(
                "INSERT INTO dbo.estado (codigo_ibge, sigla, nome) "
                "OUTPUT INSERTED.id VALUES (:codigo, :sigla, :nome)"
            ),
            {"codigo": state_code, "sigla": state_sigla, "nome": state_name},
        ).scalar_one()
        city_id = connection.execute(
            text(
                "INSERT INTO dbo.cidade (id_estado, codigo_ibge, nome) "
                "OUTPUT INSERTED.id VALUES (:estado, :codigo, :nome)"
            ),
            {"estado": state_id, "codigo": city_code, "nome": city_name},
        ).scalar_one()
        station_id = connection.execute(
            text(
                "INSERT INTO dbo.estacao "
                "(codigo_origem, nome, status, id_cidade, id_estado) "
                "OUTPUT INSERTED.id "
                "VALUES (:codigo, :nome, 1, :cidade, :estado)"
            ),
            {
                "codigo": station_code,
                "nome": station_name,
                "cidade": city_id,
                "estado": state_id,
            },
        ).scalar_one()

    station = {
        "id": int(station_id),
        "codigo_origem": station_code,
        "nome": station_name,
        "id_cidade": int(city_id),
    }
    try:
        yield station
    finally:
        with sqlserver_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM dbo.qualidade_agua WHERE id_estacao = :id"),
                {"id": station["id"]},
            )
            connection.execute(
                text(
                    "DELETE FROM dbo.leitura_meteorologica "
                    "WHERE id_estacao = :id"
                ),
                {"id": station["id"]},
            )
            connection.execute(
                text("DELETE FROM dbo.estacao WHERE id = :id"),
                {"id": station["id"]},
            )
            connection.execute(
                text("DELETE FROM dbo.cidade WHERE id = :id"),
                {"id": station["id_cidade"]},
            )
            connection.execute(
                text("DELETE FROM dbo.estado WHERE id = :id"),
                {"id": state_id},
            )


def _water_batch(station, reading_id: str, temperature: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id_leitura_origem": reading_id,
                "estacao_id": station["codigo_origem"],
                "data_leitura": pd.Timestamp("2026-10-12T12:00:00Z"),
                "temperatura_agua": temperature,
                "ph": 7.0,
                "oxigenio": 8.0,
                "condutividade": 100.0,
            }
        ]
    )


def _weather_batch(station, temperature: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "estacao_id": station["codigo_origem"],
                "cidade": "Synthetic test city",
                "estado": "Synthetic test state",
                "data_leitura": "2026-10-12T12:00:00Z",
                "temperatura_ar": temperature,
                "umidade": 65.0,
                "chuva": 0.0,
                "vento": 4.5,
                "condicao": "Nublado",
            }
        ]
    )


def _configure_water_loader(monkeypatch, engine, station, batch_provider):
    monkeypatch.setattr(ambiental, "create_db_engine", lambda: engine)
    monkeypatch.setattr(ambiental, "tabela_ambiental", batch_provider)
    monkeypatch.setattr(
        ambiental,
        "tabela_estacao",
        lambda cidades, estados: pd.DataFrame(
            [{"id": station["codigo_origem"], "nome": station["nome"]}]
        ),
    )
    monkeypatch.setattr(ambiental, "tabela_cidade", pd.DataFrame)
    monkeypatch.setattr(ambiental, "tabela_estado", pd.DataFrame)
    monkeypatch.setattr(
        ambiental, "persistir_silver", lambda *args, **kwargs: None
    )


def _configure_weather_loader(monkeypatch, engine, station, batch_provider):
    monkeypatch.setattr(meteorologica, "create_db_engine", lambda: engine)
    monkeypatch.setattr(meteorologica, "tabela_metereologica", batch_provider)
    monkeypatch.setattr(
        meteorologica,
        "resolver_id_estacao",
        lambda readings, connection: readings.assign(
            id_estacao=station["id"]
        ).drop(columns=["estacao_id"]),
    )
    monkeypatch.setattr(
        meteorologica, "persistir_silver", lambda *args, **kwargs: None
    )


def _hold_first_loader_lock_until_contender_arrives(
    monkeypatch, loader_module, expected_resource: str
):
    original_acquire_lock = loader_module.adquirir_lock_etl
    call_order_lock = Lock()
    calls = 0
    first_lock_acquired = Event()
    second_lock_attempted = Event()
    release_first_loader = Event()

    def acquire_lock(connection, resource: str, timeout_ms: int = 60000):
        nonlocal calls
        assert resource == expected_resource
        with call_order_lock:
            calls += 1
            call_number = calls

        if call_number == 1:
            original_acquire_lock(connection, resource, timeout_ms)
            first_lock_acquired.set()
            if not release_first_loader.wait(timeout=30):
                raise TimeoutError("Timeout aguardando a segunda carga chegar ao lock")
            return

        second_lock_attempted.set()
        return original_acquire_lock(connection, resource, timeout_ms)

    monkeypatch.setattr(loader_module, "adquirir_lock_etl", acquire_lock)
    return first_lock_acquired, second_lock_attempted, release_first_loader


def test_sqlserver_has_expected_natural_key_constraints(sqlserver_engine):
    with sqlserver_engine.connect() as connection:
        constraints = connection.execute(
            text(
                "SELECT kc.name, t.name, c.name, ic.key_ordinal "
                "FROM sys.key_constraints AS kc "
                "JOIN sys.tables AS t ON t.object_id = kc.parent_object_id "
                "JOIN sys.schemas AS s ON s.schema_id = t.schema_id "
                "JOIN sys.index_columns AS ic "
                "ON ic.object_id = t.object_id AND ic.index_id = kc.unique_index_id "
                "JOIN sys.columns AS c "
                "ON c.object_id = t.object_id AND c.column_id = ic.column_id "
                "WHERE s.name = 'dbo' AND kc.name IN "
                "('uq_qualidade_agua_id_leitura_origem', "
                "'uq_leitura_meteorologica_estacao_data')"
            )
        ).all()
        keys = {}
        for name, table, column, ordinal in constraints:
            keys.setdefault(name, []).append((ordinal, table, column))

        assert {
            name: [(table, column) for _, table, column in sorted(columns)]
            for name, columns in keys.items()
        } == {
            "uq_qualidade_agua_id_leitura_origem": [
                ("qualidade_agua", "id_leitura_origem")
            ],
            "uq_leitura_meteorologica_estacao_data": [
                ("leitura_meteorologica", "id_estacao"),
                ("leitura_meteorologica", "data_leitura"),
            ],
        }
        nullable = connection.execute(
            text(
                "SELECT is_nullable FROM sys.columns "
                "WHERE object_id = OBJECT_ID('dbo.qualidade_agua') "
                "AND name = 'id_leitura_origem'"
            )
        ).scalar_one()
        assert nullable is False


def test_sqlserver_water_loader_ignores_sequential_replays(
    sqlserver_engine, synthetic_station, monkeypatch
):
    reading_id = f"ITEM27-WATER-{uuid4().hex}"
    batches = iter(
        [
            _water_batch(synthetic_station, reading_id, 21.5),
            _water_batch(synthetic_station, reading_id, 29.0),
        ]
    )
    _configure_water_loader(
        monkeypatch, sqlserver_engine, synthetic_station, lambda: next(batches)
    )

    ambiental.inserir_dados()
    ambiental.inserir_dados()

    with sqlserver_engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT COUNT(*), MIN(temperatura_agua) FROM dbo.qualidade_agua "
                "WHERE id_leitura_origem = :reading_id"
            ),
            {"reading_id": reading_id},
        ).one()
    assert result == (1, 21.5)


def test_sqlserver_weather_loader_ignores_sequential_replays(
    sqlserver_engine, synthetic_station, monkeypatch
):
    batches = iter(
        [
            _weather_batch(synthetic_station, 24.0),
            _weather_batch(synthetic_station, 31.0),
        ]
    )
    _configure_weather_loader(
        monkeypatch, sqlserver_engine, synthetic_station, lambda: next(batches)
    )

    meteorologica.inserir_dados()
    meteorologica.inserir_dados()

    with sqlserver_engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT COUNT(*), MIN(temperatura_ar) "
                "FROM dbo.leitura_meteorologica "
                "WHERE id_estacao = :station_id "
                "AND data_leitura = '2026-10-12T12:00:00+00:00'"
            ),
            {"station_id": synthetic_station["id"]},
        ).one()
    assert result == (1, 24.0)


def test_sqlserver_rejects_direct_duplicate_natural_keys(
    sqlserver_engine, synthetic_station
):
    water_id = f"ITEM27-DIRECT-WATER-{uuid4().hex}"
    water_insert = text(
        "INSERT INTO dbo.qualidade_agua "
        "(id_leitura_origem, id_estacao, data_leitura) "
        "VALUES (:reading_id, :station_id, '2026-10-12T13:00:00+00:00')"
    )
    with pytest.raises(IntegrityError):
        with sqlserver_engine.begin() as connection:
            connection.execute(
                water_insert,
                {"reading_id": water_id, "station_id": synthetic_station["id"]},
            )
            connection.execute(
                water_insert,
                {"reading_id": water_id, "station_id": synthetic_station["id"]},
            )

    weather_insert = text(
        "INSERT INTO dbo.leitura_meteorologica "
        "(id_cidade, id_estacao, temperatura_ar, umidade, chuva, vento, "
        "condicao, data_leitura) "
        "VALUES (:city_id, :station_id, 24, 65, 0, 4.5, 'Nublado', "
        "'2026-10-12T14:00:00+00:00')"
    )
    with pytest.raises(IntegrityError):
        with sqlserver_engine.begin() as connection:
            parameters = {
                "city_id": synthetic_station["id_cidade"],
                "station_id": synthetic_station["id"],
            }
            connection.execute(weather_insert, parameters)
            connection.execute(weather_insert, parameters)


@pytest.mark.parametrize("dataset", ["water", "weather"])
def test_sqlserver_cooperating_concurrent_loads_are_idempotent(
    dataset, sqlserver_engine, synthetic_station, monkeypatch
):
    def provide_batch():
        if dataset == "water":
            return _water_batch(
                synthetic_station,
                f"ITEM27-CONCURRENT-{synthetic_station['id']}",
                22.0,
            )
        return _weather_batch(synthetic_station, 25.0)

    if dataset == "water":
        _configure_water_loader(
            monkeypatch, sqlserver_engine, synthetic_station, provide_batch
        )
        loader = ambiental.inserir_dados
        lock_module = ambiental
        lock_resource = "etl:qualidade_agua"
        query = text(
            "SELECT COUNT(*) FROM dbo.qualidade_agua "
            "WHERE id_leitura_origem = :reading_id"
        )
        parameters = {
            "reading_id": f"ITEM27-CONCURRENT-{synthetic_station['id']}"
        }
    else:
        _configure_weather_loader(
            monkeypatch, sqlserver_engine, synthetic_station, provide_batch
        )
        loader = meteorologica.inserir_dados
        lock_module = meteorologica
        lock_resource = "etl:leitura_meteorologica"
        query = text(
            "SELECT COUNT(*) FROM dbo.leitura_meteorologica "
            "WHERE id_estacao = :station_id "
            "AND data_leitura = '2026-10-12T12:00:00+00:00'"
        )
        parameters = {"station_id": synthetic_station["id"]}

    first_lock_acquired, second_lock_attempted, release_first_loader = (
        _hold_first_loader_lock_until_contender_arrives(
            monkeypatch, lock_module, lock_resource
        )
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(loader) for _ in range(2)]
        try:
            assert first_lock_acquired.wait(timeout=30)
            assert second_lock_attempted.wait(timeout=30)
        finally:
            release_first_loader.set()
        for future in futures:
            future.result(timeout=90)

    with sqlserver_engine.connect() as connection:
        count = connection.execute(query, parameters).scalar_one()
    assert count == 1