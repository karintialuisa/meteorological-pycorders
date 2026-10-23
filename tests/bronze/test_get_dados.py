"""Testes para autenticação Agritempo e persistência cumulativa do JSON."""

import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.bronze import agritempo as get_dados


def resultado_agritempo(id_estacao, id_leitura, temperatura_minima, temperatura_maxima):
    return {
        "uf": "BA",
        "id_municipio": "2927408",
        "id_estacao": id_estacao,
        "capturado_em": "2026-10-14T13:12:43+00:00",
        "detalhes_estacao": {
            "id": id_estacao,
            "nome": "Estação de teste",
            "municipio": "Salvador",
            "uf": "BA",
            "latitude": -12.9,
            "longitude": -38.33,
        },
        "dados_climaticos": [
            {
                "id": id_leitura,
                "id_estacao": id_estacao,
                "data": "2026-09-01",
                "temperatura_minima": temperatura_minima,
                "temperatura_minima_estimada": False,
                "temperatura_media": 23.0,
                "temperatura_maxima": temperatura_maxima,
                "temperatura_maxima_estimada": True,
            }
        ],
    }


def test_obter_headers_usa_bearer_do_ambiente(monkeypatch):
    monkeypatch.setenv("AGRITEMPO_BEARER_TOKEN", "token-de-teste")

    assert get_dados.obter_headers()["authorization"] == "Bearer token-de-teste"


def test_obter_headers_rejeita_bearer_ausente(monkeypatch):
    monkeypatch.delenv("AGRITEMPO_BEARER_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="AGRITEMPO_BEARER_TOKEN"):
        get_dados.obter_headers()


def test_salvar_resultados_acumula_no_mesmo_json(monkeypatch, tmp_path):
    monkeypatch.setattr(get_dados, "get_agritempo_raw_dir", lambda: tmp_path)
    registro_antigo = resultado_agritempo(901, 7001, 18.2, 28.1)
    registro_novo = resultado_agritempo(902, 7002, 19.0, 29.0)

    caminho_primeira_execucao, total_primeiro = get_dados.salvar_resultados_append(
        [registro_antigo]
    )
    caminho_segunda_execucao, total_segundo = get_dados.salvar_resultados_append(
        [registro_novo]
    )

    documento = json.loads(caminho_segunda_execucao.read_text(encoding="utf-8"))
    assert caminho_segunda_execucao == caminho_primeira_execucao
    assert total_primeiro == 1
    assert total_segundo == 2
    assert documento["resultados"] == [registro_antigo, registro_novo]
    assert documento["metadados"]["total_registros_acumulados"] == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_resultado_fora_do_contrato_nao_altera_json_existente(monkeypatch, tmp_path):
    monkeypatch.setattr(get_dados, "get_agritempo_raw_dir", lambda: tmp_path)
    caminho, _ = get_dados.salvar_resultados_append(
        [resultado_agritempo(901, 7001, 18.2, 28.1)]
    )
    conteudo_anterior = caminho.read_bytes()
    leitura_invalida = resultado_agritempo(902, 7002, 30.0, 20.0)

    with pytest.raises(ValueError, match="fora do contrato"):
        get_dados.salvar_resultados_append([leitura_invalida])

    assert caminho.read_bytes() == conteudo_anterior


def test_json_existente_invalido_nao_e_substituido(monkeypatch, tmp_path):
    monkeypatch.setattr(get_dados, "get_agritempo_raw_dir", lambda: tmp_path)
    caminho = tmp_path / get_dados.NOME_ARQUIVO_JSON
    conteudo_invalido = "não é JSON"
    caminho.write_text(conteudo_invalido, encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        get_dados.salvar_resultados_append([{"id_estacao": "E-3"}])

    assert caminho.read_text(encoding="utf-8") == conteudo_invalido