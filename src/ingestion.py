"""Fachada de ingestao Bronze para a estrutura do projeto integrador."""

from src.bronze.ingestion import (
    LimiteRequisicoes,
    ingerir_endpoint,
    main,
    validar_registro,
)

__all__ = ["LimiteRequisicoes", "ingerir_endpoint", "validar_registro", "main"]


if __name__ == "__main__":
    raise SystemExit(main())