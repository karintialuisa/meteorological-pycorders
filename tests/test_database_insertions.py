"""Testes de inserção com dados manuais e SQLite em memória.."""

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from src.config.settings import get_path
from src.database.dml import Insert_Leituras_ambiental as ambiental
from src.database.dml import Insert_Leituras_Meteorologica as meteorologica
from src.database.dml import Insert_Localizacao as localizacao


def test_caminho_json_e_lido_do_ambiente(monkeypatch, tmp_path):
    caminho_json = tmp_path / "leituras-teste.json"
    monkeypatch.setenv("CAMINHO_JSON_TESTE", str(caminho_json))

    assert get_path("CAMINHO_JSON_TESTE") == caminho_json


@pytest.fixture
def banco_teste():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(
            text(
                "CREATE TABLE estado ("
                "id INTEGER PRIMARY KEY, codigo_ibge INTEGER UNIQUE, "
                "sigla TEXT UNIQUE, nome TEXT UNIQUE)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE cidade ("
                "id INTEGER PRIMARY KEY, id_estado INTEGER NOT NULL, "
                "codigo_ibge INTEGER UNIQUE, nome TEXT NOT NULL, "
                "FOREIGN KEY (id_estado) REFERENCES estado(id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE estacao ("
                "id INTEGER PRIMARY KEY, nome TEXT NOT NULL, status INTEGER, "
                "id_cidade INTEGER NOT NULL, id_estado INTEGER NOT NULL, "
                "FOREIGN KEY (id_cidade) REFERENCES cidade(id), "
                "FOREIGN KEY (id_estado) REFERENCES estado(id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE qualidade_agua ("
                "id INTEGER PRIMARY KEY, id_estacao INTEGER NOT NULL, "
                "data_leitura TEXT NOT NULL, temperatura_agua REAL, "
                "ph REAL, oxigenio REAL, condutividade REAL, "
                "FOREIGN KEY (id_estacao) REFERENCES estacao(id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE leitura_meteorologica ("
                "id INTEGER PRIMARY KEY, id_cidade INTEGER NOT NULL, "
                "temperatura_ar REAL NOT NULL, umidade REAL NOT NULL, "
                "chuva REAL NOT NULL, vento REAL NOT NULL, "
                "condicao TEXT NOT NULL, data_leitura TEXT NOT NULL, "
                "FOREIGN KEY (id_cidade) REFERENCES cidade(id))"
            )
        )
    yield engine
    engine.dispose()


def inserir_localizacao_base(connection):
    connection.execute(
        text(
            "INSERT INTO estado (id, codigo_ibge, sigla, nome) "
            "VALUES (1, 35, 'SP', 'São Paulo')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO cidade (id, id_estado, codigo_ibge, nome) "
            "VALUES (10, 1, 3550308, 'São Paulo')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO estacao (id, nome, status, id_cidade, id_estado) "
            "VALUES (20, 'Estação manual', 1, 10, 1)"
        )
    )


def test_insere_estado_cidade_e_estacao(banco_teste, monkeypatch):
    monkeypatch.setattr(
        localizacao,
        "tabela_estado",
        lambda: pd.DataFrame(
            [{
                "codigo_ibge_estado": 35,
                "sigla_estado": "SP",
                "nome_estado": "São Paulo",
            }]
        ),
    )
    monkeypatch.setattr(
        localizacao,
        "tabela_cidade",
        lambda: pd.DataFrame(
            [{
                "codigo_ibge_cidade": 3550308,
                "nome_cidade": "São Paulo",
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
                "nome": "Estação manual",
                "status_estacao": 1,
                "codigo_ibge_cidade": 3550308,
                "codigo_ibge_estado": 35,
            }]
        ),
    )

    with banco_teste.begin() as connection:
        estado_ids = localizacao.inserir_localizacao(connection)
        localizacao.inserir_estacoes(connection, estado_ids)
        quantidades = {
            tabela: connection.execute(
                text(f"SELECT COUNT(*) FROM {tabela}")
            ).scalar_one()
            for tabela in ("estado", "cidade", "estacao")
        }

    assert quantidades == {"estado": 1, "cidade": 1, "estacao": 1}


def test_insere_leitura_ambiental_e_resolve_estacao(
    banco_teste, monkeypatch
):
    with banco_teste.begin() as connection:
        inserir_localizacao_base(connection)

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
            }]
        ),
    )
    monkeypatch.setattr(
        ambiental,
        "tabela_estacao",
        lambda cidades, estados: pd.DataFrame(
            [{"id": 900, "nome": "Estação manual"}]
        ),
    )
    monkeypatch.setattr(ambiental, "tabela_cidade", pd.DataFrame)
    monkeypatch.setattr(ambiental, "tabela_estado", pd.DataFrame)
    monkeypatch.setattr(
        ambiental, "create_db_engine", lambda: banco_teste
    )

    ambiental.inserir_dados()

    with banco_teste.connect() as connection:
        leitura = connection.execute(
            text(
                "SELECT id_estacao, temperatura_agua, ph "
                "FROM qualidade_agua"
            )
        ).one()

    assert leitura == (20, 21.5, 7.2)


def test_insere_leitura_meteorologica_e_resolve_cidade(
    banco_teste, monkeypatch
):
    with banco_teste.begin() as connection:
        inserir_localizacao_base(connection)

    monkeypatch.setattr(
        meteorologica,
        "tabela_metereologica",
        lambda: pd.DataFrame(
            [{
                "cidade": "São Paulo",
                "estado": "São Paulo",
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
        meteorologica, "create_db_engine", lambda: banco_teste
    )

    meteorologica.inserir_dados()

    with banco_teste.connect() as connection:
        leitura = connection.execute(
            text(
                "SELECT id_cidade, temperatura_ar, condicao "
                "FROM leitura_meteorologica"
            )
        ).one()

    assert leitura == (10, 24.0, "Nublado")