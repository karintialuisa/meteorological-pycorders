"""Testa resolução geográfica e cargas de dados usando SQLite em memória."""

import pandas as pd
import pytest
from sqlalchemy import text
import sys
from pathlib import Path
path = Path(__file__).resolve().parents[1] 
sys.path.append(str(path))  
from src.database.dml import Insert_Leituras_ambiental as ambiental
from src.database.dml import Insert_Leituras_Meteorologica as meteorologica
from src.database.dml import Insert_Localizacao as localizacao

def seed_location(engine):
    with engine.begin() as connection:
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


@pytest.mark.parametrize(
    "module, loader_name",
    [
        (ambiental, "tabela_ambiental"),
        (meteorologica, "tabela_metereologica"),
    ],
)
def test_empty_readings_skip_database_connection(monkeypatch, module, loader_name):
    monkeypatch.setattr(module, loader_name, pd.DataFrame)
    monkeypatch.setattr(
        module,
        "create_db_engine",
        lambda: pytest.fail("não deve abrir conexão sem leituras"),
    )

    module.inserir_dados()


def test_resolver_id_cidade_rejects_city_not_in_database(banco_teste):
    readings = pd.DataFrame(
        [{"cidade": "Atlantis", "estado": "Oceano", "temperatura_ar": 20}]
    )

    with banco_teste.connect() as connection:
        with pytest.raises(ValueError, match="sem cadastro no banco"):
            meteorologica.resolver_id_cidade(readings, connection)


def test_resolver_id_estacao_filters_station_not_in_database(
    banco_teste, monkeypatch, caplog
):
    monkeypatch.setattr(
        ambiental,
        "tabela_estacao",
        lambda cidades, estados: pd.DataFrame(
            [{"id": 900, "nome": "Estação ausente"}]
        ),
    )
    readings = pd.DataFrame(
        [{"estacao_id": 900, "data_leitura": "2026-01-01T00:00:00Z"}]
    )

    with banco_teste.connect() as connection:
        result = ambiental.resolver_id_estacao(readings, connection)

    assert result.empty
    assert any(
        "rejeitada por estação sem correspondência" in record.message
        for record in caplog.records
    )


def test_ambiental_load_resolves_station_and_persists_reading(
    banco_teste, monkeypatch, caplog
):
    seed_location(banco_teste)
    monkeypatch.setattr(
        ambiental,
        "tabela_ambiental",
        lambda: pd.DataFrame(
            [{
                "estacao_id": 900,
                "data_leitura": "2026-05-20T12:00:00+00:00",
                "temperatura_agua": 21.5,
                "ph": 7.2,
                "oxigenio": 8.1,
                "condutividade": 120.0,
            }, {
                "estacao_id": 901,
                "data_leitura": "2026-05-20T12:00:00+00:00",
                "temperatura_agua": 19.0,
                "ph": 7.0,
                "oxigenio": 8.0,
                "condutividade": 110.0,
            }]
        ),
    )
    monkeypatch.setattr(
        ambiental,
        "tabela_estacao",
        lambda cidades, estados: pd.DataFrame(
            [{"id": 900, "nome": "Estacao Centro"}]
        ),
    )
    monkeypatch.setattr(ambiental, "tabela_cidade", pd.DataFrame)
    monkeypatch.setattr(ambiental, "tabela_estado", pd.DataFrame)
    monkeypatch.setattr(ambiental, "create_db_engine", lambda: banco_teste)

    ambiental.inserir_dados()

    with banco_teste.connect() as connection:
        reading = connection.execute(
            text(
                "SELECT id_estacao, temperatura_agua, ph "
                "FROM qualidade_agua"
            )
        ).one()

    assert reading == (20, 21.5, 7.2)
    assert any(
        "rejeitada por estação sem correspondência" in record.message
        for record in caplog.records
    )


def test_ambiental_load_skips_insert_when_all_stations_are_unresolved(
    banco_teste, monkeypatch
):
    seed_location(banco_teste)
    monkeypatch.setattr(
        ambiental,
        "tabela_ambiental",
        lambda: pd.DataFrame(
            [{
                "estacao_id": 901,
                "data_leitura": "2026-05-20T12:00:00+00:00",
                "temperatura_agua": 19.0,
                "ph": 7.0,
                "oxigenio": 8.0,
                "condutividade": 110.0,
            }]
        ),
    )
    monkeypatch.setattr(
        ambiental,
        "tabela_estacao",
        lambda cidades, estados: pd.DataFrame(
            [{"id": 901, "nome": "Estação ausente"}]
        ),
    )
    monkeypatch.setattr(ambiental, "tabela_cidade", pd.DataFrame)
    monkeypatch.setattr(ambiental, "tabela_estado", pd.DataFrame)
    monkeypatch.setattr(ambiental, "create_db_engine", lambda: banco_teste)

    ambiental.inserir_dados()

    with banco_teste.connect() as connection:
        total = connection.execute(
            text("SELECT COUNT(*) FROM qualidade_agua")
        ).scalar_one()

    assert total == 0


def test_meteorological_load_resolves_city_and_persists_reading(
    banco_teste, monkeypatch
):
    seed_location(banco_teste)
    monkeypatch.setattr(
        meteorologica,
        "tabela_metereologica",
        lambda: pd.DataFrame(
            [{
                "estacao_id": 900,
                "cidade": "Sao Paulo",
                "estado": "Sao Paulo",
                "data_leitura": "2026-05-20T12:00:00",
                "temperatura_ar": 24.0,
                "umidade": 65.0,
                "chuva": 0.0,
                "vento": 4.5,
                "condicao": "Nublado",
            }]
        ),
    )
    monkeypatch.setattr(
        meteorologica,
        "resolver_id_estacao",
        lambda readings, connection: readings.assign(id_estacao=20).drop(
            columns=["estacao_id"]
        ),
    )
    monkeypatch.setattr(
        meteorologica, "create_db_engine", lambda: banco_teste
    )

    meteorologica.inserir_dados()

    with banco_teste.connect() as connection:
        reading = connection.execute(
            text(
                "SELECT id_cidade, id_estacao, temperatura_ar, condicao "
                "FROM leitura_meteorologica"
            )
        ).one()

    assert reading == (10, 20, 24.0, "Nublado")


def test_location_loading_is_idempotent_for_existing_records(
    banco_teste, monkeypatch
):
    monkeypatch.setattr(
        localizacao,
        "tabela_estado",
        lambda: pd.DataFrame(
            [{
                "codigo_ibge_estado": 35,
                "sigla_estado": "SP",
                "nome_estado": "Sao Paulo",
            }]
        ),
    )
    monkeypatch.setattr(
        localizacao,
        "tabela_cidade",
        lambda: pd.DataFrame(
            [{
                "codigo_ibge_cidade": 3550308,
                "nome_cidade": "Sao Paulo",
                "sigla_estado": "SP",
            }]
        ),
    )
    monkeypatch.setattr(
        localizacao,
        "tabela_estacao",
        lambda cidades, estados: pd.DataFrame(
            [{
                "id": 900,
                "nome": "Estacao Centro",
                "status_estacao": 1,
                "codigo_ibge_cidade": 3550308,
                "codigo_ibge_estado": 35,
            }]
        ),
    )

    for _ in range(2):
        with banco_teste.begin() as connection:
            estado_ids = localizacao.inserir_localizacao(connection)
            localizacao.inserir_estacoes(connection, estado_ids)

    with banco_teste.connect() as connection:
        counts = {
            table: connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()
            for table in ("estado", "cidade", "estacao")
        }

    assert counts == {"estado": 1, "cidade": 1, "estacao": 1}


def test_limpar_localizacao_preserves_records_in_append_mode(connection):
    connection.execute(
        text(
            "INSERT INTO estado (id, codigo_ibge, sigla, nome) "
            "VALUES (1, 35, 'SP', 'Sao Paulo')"
        )
    )

    localizacao.limpar_localizacao(connection)

    assert connection.execute(text("SELECT COUNT(*) FROM estado")).scalar_one() == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))