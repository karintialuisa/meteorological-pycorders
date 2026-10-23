"""Testa a fronteira de dialeto sem abrir conexoes."""

from types import SimpleNamespace

import pytest

from src.database.dialect import require_sqlserver


def test_require_sqlserver_accepts_mssql_engine_and_connection():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="mssql"))
    connection = SimpleNamespace(engine=engine)

    require_sqlserver(engine)
    require_sqlserver(connection)


@pytest.mark.parametrize("dialect", ["postgresql", "mysql", "oracle"])
def test_require_sqlserver_rejects_other_dialects(dialect):
    engine = SimpleNamespace(dialect=SimpleNamespace(name=dialect))

    with pytest.raises(RuntimeError, match="use SQL Server Express"):
        require_sqlserver(engine)


def test_require_sqlserver_rejects_unknown_handle():
    with pytest.raises(TypeError, match="SQLAlchemy"):
        require_sqlserver(object())
