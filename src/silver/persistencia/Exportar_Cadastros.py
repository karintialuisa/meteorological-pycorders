"""Exporta os cadastros SQL para Parquet preservando as chaves das leituras."""

import logging
from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine, get_silver_dir
from src.database.dialect import require_sqlserver
from src.silver.persistencia.Persistir_Silver import _gravar_parquet_atomico


CONSULTAS = {
    "estados": (
        "SELECT id AS id_estado, codigo_ibge AS codigo_ibge_estado, "
        "sigla AS sigla_estado, nome AS nome_estado FROM estado ORDER BY id"
    ),
    "cidades": (
        "SELECT id AS id_cidade, id_estado, codigo_ibge AS codigo_ibge_cidade, "
        "nome AS nome_cidade FROM cidade ORDER BY id"
    ),
    "estacoes": (
        "SELECT id AS id_estacao, codigo_origem, nome AS nome_estacao, "
        "status AS status_estacao, id_cidade FROM estacao ORDER BY id"
    ),
}


def exportar_cadastros(engine=None) -> dict[str, Path]:
    """Atualiza snapshots dos cadastros sem modificar o banco ou as leituras."""
    engine_propria = engine is None
    if engine_propria:
        engine = create_db_engine()
    require_sqlserver(engine)
    try:
        with engine.connect() as connection:
            tabelas = {
                nome: pd.read_sql(text(consulta), connection)
                for nome, consulta in CONSULTAS.items()
            }
        for nome, tabela in tabelas.items():
            if tabela.empty:
                raise ValueError(
                    f"Cadastro {nome} vazio no banco; carregue a localizacao antes de exportar."
                )
            for coluna in tabela.columns:
                if coluna.startswith("id_"):
                    tabela[coluna] = tabela[coluna].astype("int64")

        pasta = get_silver_dir() / "cadastros"
        pasta.mkdir(parents=True, exist_ok=True)
        destinos = {}
        for nome, tabela in tabelas.items():
            destino = pasta / f"{nome}.parquet"
            _gravar_parquet_atomico(tabela, destino)
            destinos[nome] = destino
            logging.info("Cadastro %s: %s registros em %s", nome, len(tabela), destino)
        return destinos
    finally:
        if engine_propria:
            engine.dispose()


if __name__ == "__main__":
    configure_logging(categoria="tratamento")
    exportar_cadastros()