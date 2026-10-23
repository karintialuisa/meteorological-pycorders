"""Carga idempotente do catalogo de parametros medidos."""

import logging
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from config.settings import configure_logging, create_db_engine
from src.database.dialect import require_sqlserver
from src.database.dml.etl_lock import adquirir_lock_etl


# Referencia: projeto_final.pdf, secao 3.3 (Parametros - Tabela de Dominio);
# features.csv ID 39. A turbidez esta no dominio mesmo sem medicao no JSON atual.
CATALOGO_PARAMETROS = (
    {"codigo": "TEMP_AGUA", "nome": "Temperatura da agua", "unidade_medida": "Celsius"},
    {"codigo": "TEMP_AR", "nome": "Temperatura do ar", "unidade_medida": "Celsius"},
    {"codigo": "PH", "nome": "Potencial hidrogenionico", "unidade_medida": "pH"},
    {"codigo": "OD", "nome": "Oxigenio dissolvido", "unidade_medida": "mg/L"},
    {"codigo": "COND_ELETRICA", "nome": "Condutividade eletrica", "unidade_medida": "uS/cm"},
    {"codigo": "TURBIDEZ", "nome": "Turbidez da agua", "unidade_medida": "NTU"},
    {"codigo": "UMIDADE", "nome": "Umidade relativa do ar", "unidade_medida": "%"},
    {"codigo": "CHUVA", "nome": "Precipitacao", "unidade_medida": "mm"},
    {"codigo": "VENTO", "nome": "Velocidade do vento", "unidade_medida": "km/h"},
    {"codigo": "CONDICAO_METEO", "nome": "Condicao meteorologica", "unidade_medida": "descricao"},
)

_COMPRIMENTOS_MAXIMOS = {"codigo": 50, "nome": 150, "unidade_medida": 50}


def _validar_parametros(
    parametros: Iterable[Mapping[str, object]],
) -> list[dict[str, str]]:
    """Valida campos obrigatorios, nulos, comprimentos e codigos repetidos."""
    registros = []
    codigos_vistos = set()

    for indice, parametro in enumerate(parametros):
        if not isinstance(parametro, Mapping):
            raise TypeError(f"Parametro no indice {indice} deve ser um mapeamento")

        registro = {}
        for campo, tamanho_maximo in _COMPRIMENTOS_MAXIMOS.items():
            valor = parametro.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(
                    f"Parametro no indice {indice} possui campo obrigatorio ausente ou vazio: {campo}"
                )
            valor_normalizado = valor.strip()
            if len(valor_normalizado) > tamanho_maximo:
                raise ValueError(
                    f"Campo {campo} do parametro no indice {indice} excede {tamanho_maximo} caracteres"
                )
            registro[campo] = valor_normalizado

        registro["codigo"] = registro["codigo"].upper()
        if registro["codigo"] in codigos_vistos:
            raise ValueError(
                f"Codigo de parametro repetido no lote: {registro['codigo']}"
            )
        codigos_vistos.add(registro["codigo"])
        registros.append(registro)

    return registros


def inserir_parametros(
    parametros: Iterable[Mapping[str, object]] = CATALOGO_PARAMETROS,
    engine=None,
) -> tuple[int, int]:
    """Insere ou atualiza parametros por codigo; retorna (inseridos, atualizados)."""
    registros = _validar_parametros(parametros)
    target_engine = engine or create_db_engine()
    require_sqlserver(target_engine)
    table_name = "dbo.parametros"
    inseridos = 0
    atualizados = 0

    with target_engine.begin() as connection:
        adquirir_lock_etl(connection, "etl:parametros")

        for parametro in registros:
            existente = connection.execute(
                text(
                    f"SELECT id, nome, unidade_medida FROM {table_name} "
                    "WHERE codigo = :codigo"
                ),
                {"codigo": parametro["codigo"]},
            ).mappings().one_or_none()

            if existente is None:
                connection.execute(
                    text(
                        f"INSERT INTO {table_name} (codigo, nome, unidade_medida) "
                        "VALUES (:codigo, :nome, :unidade_medida)"
                    ),
                    parametro,
                )
                inseridos += 1
                continue

            alteracoes = {
                campo: parametro[campo]
                for campo in ("nome", "unidade_medida")
                if existente[campo] != parametro[campo]
            }
            if alteracoes:
                assignments = ", ".join(
                    f"{campo} = :{campo}" for campo in alteracoes
                )
                connection.execute(
                    text(
                        f"UPDATE {table_name} SET {assignments} WHERE id = :id"
                    ),
                    {**alteracoes, "id": existente["id"]},
                )
                atualizados += 1

    logging.info(
        "Carga de parametros concluida: recebidos=%s inseridos=%s atualizados=%s",
        len(registros),
        inseridos,
        atualizados,
    )
    return inseridos, atualizados


if __name__ == "__main__":
    configure_logging(categoria="insercao")
    resultado = inserir_parametros()
    logging.info("Resultado da carga de parametros: inseridos=%s atualizados=%s", *resultado)