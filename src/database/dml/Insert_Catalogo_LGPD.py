"""Registra metadados dos campos pessoais do cadastro de operadores."""

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import configure_logging, create_db_engine


# 3.2 LGPD (item 32): inventaria CPF e nome completo com classificacao,
# finalidade, protecao e politica de acesso.
METADADOS_CATALOGO = (
    {
        "schema_name": "dbo",
        "tabela": "operadores",
        "campo_logico": "cpf",
        "coluna_armazenada": "cpf_hash",
        "classificacao": "Dado pessoal",
        "finalidade": "Cadastro e identificacao de operadores de campo",
        "protecao": "HMAC-SHA-256",
        "politica_acesso": "Chave HMAC restrita ao processo autorizado; digest nao reversivel",
    },
    {
        "schema_name": "dbo",
        "tabela": "operadores",
        "campo_logico": "nome_completo",
        "coluna_armazenada": "nome_completo_cifrado",
        "classificacao": "Dado pessoal",
        "finalidade": "Cadastro e identificacao de operadores de campo",
        "protecao": "Fernet",
        "politica_acesso": "Descriptografia somente por processo autorizado com a chave",
    },
)


def inserir_catalogo_lgpd(engine=None) -> int:
    """Insere ou atualiza as definicoes do catalogo de forma idempotente."""
    target_engine = engine or create_db_engine()
    query = text(
        "SELECT id FROM catalogo_dados "
        "WHERE schema_name = :schema_name AND tabela = :tabela "
        "AND campo_logico = :campo_logico"
    )
    insert = text(
        "INSERT INTO catalogo_dados (schema_name, tabela, campo_logico, "
        "coluna_armazenada, classificacao, finalidade, protecao, politica_acesso) "
        "VALUES (:schema_name, :tabela, :campo_logico, :coluna_armazenada, "
        ":classificacao, :finalidade, :protecao, :politica_acesso)"
    )
    update = text(
        "UPDATE catalogo_dados SET coluna_armazenada = :coluna_armazenada, "
        "classificacao = :classificacao, finalidade = :finalidade, "
        "protecao = :protecao, politica_acesso = :politica_acesso "
        "WHERE id = :id"
    )

    with target_engine.begin() as connection:
        for metadata in METADADOS_CATALOGO:
            existing_id = connection.execute(query, metadata).scalar_one_or_none()
            if existing_id is None:
                connection.execute(insert, metadata)
            else:
                connection.execute(update, {**metadata, "id": existing_id})

    return len(METADADOS_CATALOGO)


if __name__ == "__main__":
    configure_logging()
    inserted = inserir_catalogo_lgpd()
    print(f"Catalogo LGPD atualizado: {inserted} campos.")