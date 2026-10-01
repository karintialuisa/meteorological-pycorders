"""Fornece fixtures de banco SQLite para testes isolados das cargas."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


@pytest.fixture
def banco_teste():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))

    with engine.begin() as connection:
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


@pytest.fixture
def connection(banco_teste):
    with banco_teste.begin() as active_connection:
        yield active_connection