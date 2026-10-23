"""Testes do consumo REST, do contrato de leituras e da persistência Bronze."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import URLError

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.bronze import ingestion


def leitura_ambiental():
    return {
        "id": "LEIT-AMB-000001",
        "estacao_id": "AMB-001",
        "timestamp": "2026-09-15T08:24:00-03:00",
        "qualidade_agua": {
            "temperatura": {"valor": 21.3, "unidade": "°C"},
            "ph": {"valor": 7.2, "unidade": "pH"},
            "oxigenio_dissolvido": {"valor": 6.8, "unidade": "mg/L"},
            "condutividade": {"valor": 145.2, "unidade": "µS/cm"},
            "turbidez": {"valor": 2.0, "unidade": "NTU"},
        },
        "cidade": "Porto Velho",
        "estado": "Rondônia",
    }


def leitura_meteorologica():
    return {
        "id": "LEIT-MET-000001",
        "estacao_id": "MET-RO-001",
        "timestamp": "2026-09-15T08:24:00-03:00",
        "dados_meteorologicos": {
            "temperatura_ar": {"valor": 22, "unidade": "°C"},
            "condicao": {"description": "Parcialmente nublado"},
            "umidade": {"valor": 78, "unidade": "%"},
            "chuva": {"valor": 0.0, "unidade": "mm"},
            "vento": {"velocidade": 8.5, "unidade": "km/h"},
        },
        "cidade": "Porto Velho",
        "estado": "Rondônia",
    }


def resultado_agritempo(id_estacao="901", dados_climaticos=None):
    if dados_climaticos is None:
        dados_climaticos = [
            {
                "id": 7001,
                "id_estacao": int(id_estacao),
                "data": "2026-09-01",
                "temperatura_minima": 18.2,
                "temperatura_minima_estimada": False,
                "temperatura_media": 23.0,
                "temperatura_maxima": 28.1,
                "temperatura_maxima_estimada": True,
                "precipitacao": 4.2,
            }
        ]
    return {
        "uf": "BA",
        "id_municipio": "2927408",
        "id_estacao": int(id_estacao),
        "capturado_em": "2026-10-14T13:12:43+00:00",
        "detalhes_estacao": {
            "id": int(id_estacao),
            "nome": "Estação de teste",
            "municipio": "Salvador",
            "uf": "BA",
            "latitude": -12.9,
            "longitude": -38.33,
        },
        "dados_climaticos": dados_climaticos,
    }


def resposta(payload):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return payload

    return Response()


def test_validar_registro_rejeita_campos_ausentes_e_tipos_incompativeis():
    registro = leitura_ambiental()
    assert ingestion.validar_registro("ambiental", registro) is None

    del registro["estacao_id"]
    assert "estacao_id" in ingestion.validar_registro("ambiental", registro)

    registro = leitura_ambiental()
    registro["qualidade_agua"]["ph"]["valor"] = "7.2"
    assert "numérico" in ingestion.validar_registro("ambiental", registro)

    registro_meteo = leitura_meteorologica()
    assert ingestion.validar_registro("meteorologica", registro_meteo) is None
    registro_meteo["dados_meteorologicos"]["vento"]["velocidade"] = True
    assert "numérico" in ingestion.validar_registro("meteorologica", registro_meteo)


def test_contrato_agritempo_exige_minima_maxima_e_extrai_somente_essas_medidas():
    documento = {
        "metadados": {
            "gerado_em": "2026-10-14T13:13:44+00:00",
            "data_inicial": "2026-05-01",
            "data_final": "2026-09-01",
            "total_consultas_configuradas": 1,
            "total_registros_acumulados": 2,
        },
        "resultados": [
            resultado_agritempo(),
            resultado_agritempo("902", dados_climaticos={}),
        ],
    }

    assert ingestion.validar_documento_agritempo(documento) == []
    leituras = ingestion.extrair_temperaturas_ar(documento["resultados"])

    assert leituras == [
        {
            "id_leitura_origem": "7001",
            "id_estacao": "901",
            "municipio": "Salvador",
            "uf": "BA",
            "data_leitura": "2026-09-01",
            "temperatura_ar_minima": 18.2,
            "temperatura_ar_maxima": 28.1,
            "temperatura_ar_minima_estimada": False,
            "temperatura_ar_maxima_estimada": True,
        }
    ]


@pytest.mark.parametrize(
    "alteracao,motivo",
    [
        (lambda item: item.pop("temperatura_minima"), "temperatura_minima ausente"),
        (lambda item: item.update(temperatura_maxima=17.0), "maior que temperatura_maxima"),
        (lambda item: item.update(temperatura_maxima="28.1"), "numérica entre -50 e 60"),
    ],
)
def test_contrato_agritempo_rejeita_leituras_de_temperatura_invalidas(
    alteracao, motivo
):
    resultado = resultado_agritempo()
    alteracao(resultado["dados_climaticos"][0])

    assert any(motivo in erro for erro in ingestion.validar_resultado_agritempo(resultado))


def test_ingerir_endpoint_grava_aprovados_em_lotes_append_only(
    monkeypatch, tmp_path, caplog
):
    """Audita rejeições e prova que lotes novos não alteram o histórico Bronze."""
    aprovado = leitura_ambiental()
    invalido = leitura_ambiental()
    invalido["qualidade_agua"]["ph"]["valor"] = "7.2"
    requisicoes = []
    payload = json.dumps({"leituras_ambientais": [aprovado, invalido]}).encode()
    monkeypatch.setattr(
        ingestion,
        "urlopen",
        lambda request, timeout: requisicoes.append((request, timeout))
        or resposta(payload),
    )
    limite = ingestion.LimiteRequisicoes(10)

    with caplog.at_level(logging.WARNING):
        primeiro = ingestion.ingerir_endpoint(
            "https://sensores.example/api/leituras",
            "ambiental",
            tmp_path,
            limite,
            token="segredo-de-teste",
            nome_fonte="estacoes-rio",
        )

    assert (primeiro.recebidos, primeiro.aprovados, primeiro.rejeitados) == (2, 1, 1)
    assert "Registro da API rejeitado" in caplog.text
    registro_auditado = next(
        record for record in caplog.records if "Auditoria de contrato" in record.message
    )
    momento_auditoria = registro_auditado.message.split("momento_utc=")[1]
    assert datetime.fromisoformat(momento_auditoria).utcoffset().total_seconds() == 0
    assert requisicoes[0][0].get_header("Authorization") == "Bearer segredo-de-teste"
    assert requisicoes[0][1] == 15
    linha = json.loads(primeiro.arquivo_bronze.read_text(encoding="utf-8"))
    assert linha["source"] == "estacoes-rio"
    assert linha["dataset"] == "ambiental"
    assert linha["record"] == aprovado
    assert datetime.fromisoformat(linha["ingested_at"]).utcoffset().total_seconds() == 0

    historico = primeiro.arquivo_bronze.read_bytes()
    segundo = ingestion.ingerir_endpoint(
        "https://sensores.example/api/leituras",
        "ambiental",
        tmp_path,
        limite,
    )
    assert segundo.arquivo_bronze != primeiro.arquivo_bronze
    assert primeiro.arquivo_bronze.read_bytes() == historico
    assert len(list(tmp_path.glob("api_*.jsonl"))) == 2


def test_gravar_bronze_adiciona_timestamp_utc_a_cada_registro(tmp_path):
    """Confirma que cada linha recebe seu próprio timestamp ISO 8601 UTC."""
    arquivo = ingestion._gravar_bronze(
        [leitura_ambiental(), leitura_ambiental()],
        "ambiental",
        "estacoes-rio",
        tmp_path,
    )

    linhas = [
        json.loads(linha)
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
    ]
    assert len(linhas) == 2
    assert all(
        datetime.fromisoformat(linha["ingested_at"]).utcoffset().total_seconds() == 0
        for linha in linhas
    )


@pytest.mark.parametrize("body", [b"", b"[]"])
def test_ingerir_endpoint_registra_resposta_vazia_sem_criar_arquivo(
    monkeypatch, tmp_path, caplog, body
):
    monkeypatch.setattr(ingestion, "urlopen", lambda *_args, **_kwargs: resposta(body))

    with caplog.at_level(logging.WARNING):
        resultado = ingestion.ingerir_endpoint(
            "https://sensores.example/api/leituras",
            "ambiental",
            tmp_path,
            ingestion.LimiteRequisicoes(10),
        )

    assert resultado.arquivo_bronze is None
    assert resultado.ok is True
    assert "Resposta" in caplog.text
    assert not list(tmp_path.iterdir())


def test_ingerir_endpoint_trata_queda_de_conexao(monkeypatch, tmp_path, caplog):
    def falhar(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr(ingestion, "urlopen", falhar)
    with caplog.at_level(logging.ERROR):
        resultado = ingestion.ingerir_endpoint(
            "https://sensores.example/api/leituras",
            "ambiental",
            tmp_path,
            ingestion.LimiteRequisicoes(10),
        )

    assert resultado.arquivo_bronze is None
    assert resultado.ok is False
    assert "Falha de conexão" in caplog.text
    assert not list(tmp_path.iterdir())


def test_ingerir_endpoint_rejeita_resposta_que_nao_e_json(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(ingestion, "urlopen", lambda *_args, **_kwargs: resposta(b"not json"))
    with caplog.at_level(logging.ERROR):
        resultado = ingestion.ingerir_endpoint(
            "https://sensores.example/api/leituras",
            "ambiental",
            tmp_path,
            ingestion.LimiteRequisicoes(10),
        )

    assert resultado.arquivo_bronze is None
    assert resultado.ok is False
    assert "Resposta fora do contrato JSON" in caplog.text


def test_limite_de_requisicoes_aguarda_a_janela_de_sessenta_segundos():
    agora = [0.0]
    esperas = []

    def dormir(segundos):
        esperas.append(segundos)
        agora[0] += segundos

    limite = ingestion.LimiteRequisicoes(
        2, relogio=lambda: agora[0], dormir=dormir
    )
    limite.aguardar_permissao()
    limite.aguardar_permissao()
    limite.aguardar_permissao()

    assert esperas == [60.0]


def test_ingestao_rejeita_url_nao_http(tmp_path):
    with pytest.raises(ValueError, match="HTTP ou HTTPS"):
        ingestion.ingerir_endpoint(
            "file:///tmp/readings.json",
            "ambiental",
            tmp_path,
            ingestion.LimiteRequisicoes(10),
        )