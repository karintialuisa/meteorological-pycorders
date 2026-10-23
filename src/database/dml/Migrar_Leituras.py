"""Backfill explicito, reconciliado e transacional do legado para 3FN."""

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from src.database.dialect import require_sqlserver
from src.database.dml.Insert_Leituras import _normalizar_instante
from src.database.dml.Persistir_Medicoes import MAPEAMENTO, preparar_evento, persistir_evento
from src.database.dml.etl_lock import adquirir_lock_etl


def migrar_legado(engine, *, arquivar: bool = False) -> dict[str, int]:
    """Nao cria schema nem parametros. Toda a migracao usa uma transacao."""
    require_sqlserver(engine)
    contagens = {origem: 0 for origem in MAPEAMENTO}
    with engine.begin() as connection:
        adquirir_lock_etl(connection, "etl:leituras")
        adquirir_lock_etl(connection, "etl:leitura_itens")
        schema = inspect(connection)
        nomes = set(schema.get_table_names(schema="dbo"))
        for tabela, colunas in {
            "leituras": {"id", "origem", "chave_origem", "id_estacao", "id_operador", "data_leitura", "criado_em"},
            "leitura_itens": {"id_leitura", "id_parametro", "valor_numerico", "valor_texto"},
            "parametros": {"id", "codigo", "nome", "unidade_medida"},
        }.items():
            if tabela not in nomes or not colunas <= {
                coluna["name"] for coluna in schema.get_columns(tabela, schema="dbo")
            }:
                raise ValueError(f"preflight: destino 3FN incompativel: {tabela}")
        for tabela, relacoes in {
            "leituras": {("id_estacao", "estacao", "id"), ("id_operador", "operadores", "id")},
            "leitura_itens": {("id_leitura", "leituras", "id"), ("id_parametro", "parametros", "id")},
        }.items():
            fks = schema.get_foreign_keys(tabela, schema="dbo")
            encontradas = {
                (fk["constrained_columns"][0], fk["referred_table"].lower(), fk["referred_columns"][0])
                for fk in fks
                if len(fk["constrained_columns"]) == 1 and len(fk["referred_columns"]) == 1
            }
            if not relacoes <= encontradas:
                raise ValueError(f"preflight: FKs obrigatorias ausentes: {tabela}")
            for fk in fks:
                esperado = "CASCADE" if tabela == "leitura_itens" and fk["constrained_columns"] == ["id_leitura"] else "NO ACTION"
                acao = (fk.get("options", {}).get("ondelete") or "NO ACTION").upper().replace("_", " ")
                if acao != esperado:
                    raise ValueError(f"preflight: politica de exclusao incompativel: {tabela}")
        if set(schema.get_pk_constraint("leitura_itens", schema="dbo")["constrained_columns"]) != {"id_leitura", "id_parametro"}:
            raise ValueError("preflight: PK composta de itens ausente")
        unicas = [index for index in schema.get_indexes("leituras", schema="dbo") if index["unique"]]
        if not any(set(constraint["column_names"]) == {"origem", "chave_origem"} for constraint in unicas):
            raise ValueError("preflight: unicidade de leitura ausente")
        invalidas = connection.execute(text(
            "SELECT name FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1"
        )).scalars().all()
        if invalidas:
            raise ValueError("preflight: FKs desabilitadas ou nao confiaveis")
        eventos = []
        chaves = set()
        for origem in MAPEAMENTO:
            fonte = origem if origem in nomes else f"legado_{origem}"
            if fonte not in nomes:
                raise ValueError(f"preflight: tabela fonte ausente: {origem}")
            if origem in nomes and f"legado_{origem}" in nomes:
                raise ValueError(f"preflight: arquivo legado ja existe: {origem}")
            obrigatorias = {"id", "id_estacao", "data_leitura", "criado_em", *MAPEAMENTO[origem]}
            obrigatorias.add("id_leitura_origem" if origem == "qualidade_agua" else "id_cidade")
            colunas = {coluna["name"] for coluna in schema.get_columns(fonte, schema="dbo")}
            if not obrigatorias <= colunas:
                raise ValueError(f"preflight: schema incompativel: {fonte}")
            # Bloqueia alteracao da fonte durante preflight, backfill e cutover.
            lock = " WITH (TABLOCKX, HOLDLOCK)"
            registros = connection.execute(text(
                f"SELECT f.*, e.codigo_origem AS estacao_id, e.id_cidade AS cidade_estacao "
                f"FROM {fonte} f{lock} LEFT JOIN estacao e ON e.id=f.id_estacao"
            )).mappings().all()
            for registro in registros:
                if registro["estacao_id"] is None:
                    raise ValueError(f"preflight: estacao orfa em {fonte}")
                if origem == "leitura_meteorologica" and registro["id_cidade"] != registro["cidade_estacao"]:
                    raise ValueError("preflight: cidade meteorologica diverge da estacao")
                cabecalho, itens = preparar_evento(registro, origem)
                chave = (origem, cabecalho["chave_origem"])
                if chave in chaves:
                    raise ValueError("preflight: chave natural duplicada")
                chaves.add(chave)
                criado_em = _normalizar_instante(registro["criado_em"])
                eventos.append((cabecalho, itens, criado_em))
                contagens[origem] += 1

        for cabecalho, itens, criado_em in eventos:
            parametros = {"origem": cabecalho["origem"], "chave": cabecalho["chave_origem"]}
            anterior = connection.execute(text(
                "SELECT id FROM leituras WHERE origem=:origem AND chave_origem=:chave"
            ), parametros).scalar_one_or_none()
            persistir_evento(connection, cabecalho, itens)
            if anterior is None:
                connection.execute(text(
                    "UPDATE leituras SET criado_em=:criado_em "
                    "WHERE origem=:origem AND chave_origem=:chave"
                ), {**parametros, "criado_em": criado_em})
            destino = connection.execute(text(
                "SELECT l.id_estacao, l.data_leitura, l.criado_em, e.codigo_origem "
                "FROM leituras l JOIN estacao e ON e.id=l.id_estacao "
                "WHERE l.origem=:origem AND l.chave_origem=:chave"
            ), parametros).mappings().one()
            if (destino["codigo_origem"] != cabecalho["codigo_estacao"]
                    or _normalizar_instante(destino["data_leitura"]) != cabecalho["data_leitura"]
                    or _normalizar_instante(destino["criado_em"]) != criado_em):
                raise ValueError("reconciliacao: cabecalho diverge da fonte")
            valores = connection.execute(text(
                "SELECT p.codigo, i.valor_numerico, i.valor_texto "
                "FROM leitura_itens i JOIN parametros p ON p.id=i.id_parametro "
                "JOIN leituras l ON l.id=i.id_leitura "
                "WHERE l.origem=:origem AND l.chave_origem=:chave"
            ), parametros).mappings().all()
            esperado = {
                item["codigo_parametro"]: (item["valor_numerico"], item["valor_texto"])
                for item in itens
            }
            encontrado = {
                item["codigo"]: (
                    Decimal(str(item["valor_numerico"])) if item["valor_numerico"] is not None else None,
                    item["valor_texto"],
                ) for item in valores
            }
            if encontrado != esperado:
                raise ValueError("reconciliacao: valores divergentes")

        for consulta in (
            "SELECT COUNT(*) FROM leituras l LEFT JOIN estacao e ON e.id=l.id_estacao WHERE e.id IS NULL",
            "SELECT COUNT(*) FROM leituras l LEFT JOIN operadores o ON o.id=l.id_operador WHERE l.id_operador IS NOT NULL AND o.id IS NULL",
            "SELECT COUNT(*) FROM leitura_itens i LEFT JOIN leituras l ON l.id=i.id_leitura WHERE l.id IS NULL",
            "SELECT COUNT(*) FROM leitura_itens i LEFT JOIN parametros p ON p.id=i.id_parametro WHERE p.id IS NULL",
        ):
            if connection.execute(text(consulta)).scalar_one():
                raise ValueError("reconciliacao: registros orfaos no destino")

        if arquivar:
            for origem in MAPEAMENTO:
                arquivo = f"legado_{origem}"
                if origem in nomes:
                    connection.execute(text(f"EXEC sys.sp_rename 'dbo.{origem}', '{arquivo}'"))
                    connection.execute(text(
                        f"CREATE TRIGGER dbo.tr_{arquivo}_somente_leitura ON dbo.{arquivo} "
                        "AFTER INSERT, UPDATE, DELETE AS BEGIN "
                        "SET NOCOUNT ON; "
                        "IF EXISTS (SELECT 1 FROM inserted) OR EXISTS (SELECT 1 FROM deleted) "
                        "THROW 51044, 'Arquivo legado somente leitura', 1; END"
                    ))
    logging.info("Backfill reconciliado: contagens=%s arquivado=%s", contagens, arquivar)
    return contagens


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--confirm", action="store_true", required=True)
    parser.add_argument("--arquivar", action="store_true")
    args = parser.parse_args()
    configure_logging(categoria="insercao")
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            banco = connection.execute(text("SELECT DB_NAME()")).scalar_one()
        if banco != args.expected_database:
            raise ValueError("banco conectado difere do explicitamente autorizado")
        migrar_legado(engine, arquivar=args.arquivar)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
