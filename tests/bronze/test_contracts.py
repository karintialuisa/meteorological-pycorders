"""Testes dos data contracts Pydantic da Bronze."""

import copy

import pytest

from src.bronze.contracts import validar_contrato

AMBIENTAL = {
    "id": "a1",
    "estacao_id": "E1",
    "timestamp": "2026-10-01T10:00:00Z",
    "qualidade_agua": {
        "temperatura": {"valor": 20},
        "ph": {"valor": 7.1},
        "oxigenio_dissolvido": {"valor": 8},
        "condutividade": {"valor": 100},
        "turbidez": {"valor": 3},
    },
}
METEOROLOGICA = {
    "id": "m1",
    "estacao_id": "E1",
    "timestamp": "2026-10-01T10:00:00+00:00",
    "cidade": "Recife",
    "estado": "PE",
    "dados_meteorologicos": {
        "temperatura_ar": {"valor": 30},
        "umidade": {"valor": 60},
        "chuva": {"valor": 0},
        "vento": {"velocidade": 10},
        "condicao": {"description": "sol"},
    },
}


def test_valid_records_are_accepted_and_extra_fields_are_kept():
    ambiental = copy.deepcopy(AMBIENTAL)
    ambiental["extra"] = 1
    assert validar_contrato("ambiental", ambiental) is None
    assert validar_contrato("meteorologica", METEOROLOGICA) is None


@pytest.mark.parametrize(
    "mutacao,trecho",
    [
        (lambda r: r.pop("estacao_id"), "campo obrigatório ausente ou inválido: estacao_id"),
        (lambda r: r.update(id="  "), "campo obrigatório ausente ou inválido: id"),
        (lambda r: r.update(timestamp="ontem"), "ISO 8601"),
        (lambda r: r.update(timestamp="2026-10-01T10:00:00"), "fuso horário"),
        (lambda r: r["qualidade_agua"]["ph"].update(valor="7"), "qualidade_agua.ph.valor deve ser numérico"),
        (lambda r: r["qualidade_agua"]["ph"].update(valor=True), "numérico"),
        (lambda r: r["qualidade_agua"]["ph"].update(valor=float("inf")), "finito"),
        (lambda r: r["qualidade_agua"].pop("turbidez"), "qualidade_agua.turbidez"),
    ],
)
def test_ambiental_rejections_use_audit_messages(mutacao, trecho):
    registro = copy.deepcopy(AMBIENTAL)
    mutacao(registro)
    assert trecho in validar_contrato("ambiental", registro)


def test_meteorologica_requires_texts_and_nested_condition():
    registro = copy.deepcopy(METEOROLOGICA)
    registro["cidade"] = ""
    assert "cidade" in validar_contrato("meteorologica", registro)

    registro = copy.deepcopy(METEOROLOGICA)
    registro["dados_meteorologicos"]["condicao"]["description"] = None
    assert "dados_meteorologicos.condicao.description" in validar_contrato(
        "meteorologica", registro
    )

    registro = copy.deepcopy(METEOROLOGICA)
    registro["dados_meteorologicos"]["vento"] = {}
    assert "dados_meteorologicos.vento.velocidade" in validar_contrato(
        "meteorologica", registro
    )
