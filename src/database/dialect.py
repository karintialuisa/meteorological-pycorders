"""Validacoes do backend relacional suportado pela aplicacao."""


def require_sqlserver(target) -> None:
    """Falha antes do SQL quando engine ou connection nao usam SQL Server."""
    dialect = getattr(target, "dialect", None)
    if dialect is None:
        dialect = getattr(getattr(target, "engine", None), "dialect", None)
    if dialect is None:
        raise TypeError("engine ou connection SQLAlchemy obrigatoria")
    if dialect.name != "mssql":
        raise RuntimeError(
            f"Backend nao suportado: {dialect.name}; use SQL Server Express (mssql+pyodbc)"
        )
