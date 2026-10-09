"""Locks cooperativos para serializar cargas ETL no SQL Server."""

from sqlalchemy import text


def adquirir_lock_etl(connection, recurso: str, timeout_ms: int = 60000) -> None:
    """Adquire lock exclusivo até o fim da transação atual no SQL Server.

    Em outros bancos, não aplica lock; eles continuam úteis para testes locais,
    mas não oferecem a proteção contra concorrência do SQL Server. No SQL
    Server, o lock coordena somente escritores que usem o mesmo recurso.
    """
    if connection.dialect.name != "mssql":
        return
    if not connection.in_transaction():
        raise RuntimeError("O lock ETL exige uma transação ativa")

    resultado = connection.execute(
        text(
            "DECLARE @resultado int; "
            "EXEC @resultado = sys.sp_getapplock "
            "@Resource = :recurso, @LockMode = 'Exclusive', "
            "@LockOwner = 'Transaction', @LockTimeout = :timeout_ms; "
            "SELECT @resultado"
        ),
        {"recurso": recurso, "timeout_ms": timeout_ms},
    ).scalar_one()

    if resultado < 0:
        raise TimeoutError(
            f"Nao foi possivel adquirir o lock ETL {recurso!r}: {resultado}"
        )