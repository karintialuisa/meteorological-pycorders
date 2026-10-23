import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import requests
from uuid import uuid4

import sys
path = Path(__file__).parents[2]
sys.path.append(str(path))
from config.settings import PROJECT_ROOT, configure_logging, get_agritempo_raw_dir
from src.bronze.ingestion import (
    LimiteRequisicoes,
    extrair_temperaturas_ar,
    validar_documento_agritempo,
)

# 1. Lista de dicionários com UF e ID do Município configuráveis
CONFIGURACOES_BUSCA = [
    {"uf": "BA", "id_municipio": "2927408"},
    {"uf": "SP", "id_municipio": "3550308"},
    {"uf": "RJ", "id_municipio": "3304557"},
    {"uf": "MG", "id_municipio": "3170206"},
]

# Configurações de API e Período
DATA_INICIAL = "2026-05-01"
DATA_FINAL = "2026-09-01"
NOME_ARQUIVO_JSON = "dados_agritempo.json"
LIMITE_REQUISICOES = LimiteRequisicoes(
    int(os.getenv("API_REQUESTS_PER_MINUTE", "30"))
)

# Cabeçalhos padrão das requisições
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "access-control-allow-origin": "*",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "Referer": "https://www.agritempo.gov.br/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def obter_headers() -> dict:
    """Monta os cabeçalhos da API usando o bearer armazenado no .env."""
    token = os.getenv("AGRITEMPO_BEARER_TOKEN")
    if not token:
        raise RuntimeError(
            "Configure AGRITEMPO_BEARER_TOKEN em src/config/.env."
        )
    return {**HEADERS, "authorization": f"Bearer {token}"}


def _registrar_requisicao() -> None:
    LIMITE_REQUISICOES.aguardar_permissao()


def buscar_estacoes(uf: str, id_municipio: str) -> list:
    """Busca as estações vinculadas ao município e UF."""
    url = "https://api.cnptia.embrapa.br/agritempo-dados/v1/estacao"
    params = {"uf": uf.upper(), "idMunicipio": id_municipio}

    try:
        _registrar_requisicao()
        response = requests.get(
            url, headers=obter_headers(), params=params, timeout=15
        )
        if response.status_code == 200:
            return response.json()
        logging.error(
            f"Erro ao buscar estações [{uf} - {id_municipio}]: Status"
            f" {response.status_code}"
        )
        return []
    except requests.RequestException as e:
        logging.exception("Falha na requisição de estações: %s", e)
        return []


def buscar_dados_climaticos(id_estacao: str, data_inicio: str, data_fim: str) -> dict:
    """Busca o histórico de dados climáticos de uma estação específica."""
    url = f"https://api.cnptia.embrapa.br/agritempo-dados/v1/clima/{id_estacao}"
    params = {"dataInicial": data_inicio, "dataFinal": data_fim}

    try:
        _registrar_requisicao()
        response = requests.get(
            url, headers=obter_headers(), params=params, timeout=15
        )
        if response.status_code == 200:
            return response.json()
        logging.error(
            f"Erro ao buscar clima da estação {id_estacao}: Status"
            f" {response.status_code}"
        )
        return {}
    except requests.RequestException as e:
        logging.exception("Falha na requisição de clima: %s", e)
        return {}


def salvar_resultados_append(registros_novos: list[dict]) -> tuple[Path, int]:
    """Acrescenta resultados ao JSON existente sem descartar o histórico."""
    caminho = get_agritempo_raw_dir() / NOME_ARQUIVO_JSON
    caminho.parent.mkdir(parents=True, exist_ok=True)

    documento_existente = {}
    if caminho.exists():
        with caminho.open("r", encoding="utf-8") as arquivo:
            documento_existente = json.load(arquivo)
        if not isinstance(documento_existente, dict):
            raise ValueError(f"Estrutura inválida no arquivo existente: {caminho}")

    resultados_existentes = documento_existente.get("resultados", [])
    if not isinstance(resultados_existentes, list):
        raise ValueError(f"Campo resultados inválido no arquivo existente: {caminho}")

    resultados = [*resultados_existentes, *registros_novos]
    metadados = documento_existente.get("metadados", {})
    if not isinstance(metadados, dict):
        raise ValueError(f"Campo metadados inválido no arquivo existente: {caminho}")
    metadados = {
        **metadados,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "data_inicial": DATA_INICIAL,
        "data_final": DATA_FINAL,
        "total_consultas_configuradas": len(CONFIGURACOES_BUSCA),
        "total_registros_acumulados": len(resultados),
    }
    documento_final = {
        **documento_existente,
        "metadados": metadados,
        "resultados": resultados,
    }
    erros_contrato = validar_documento_agritempo(documento_final)
    if erros_contrato:
        raise ValueError(
            "JSON Agritempo fora do contrato: " + "; ".join(erros_contrato[:10])
        )

    temporario = caminho.with_name(f".{caminho.name}.{uuid4().hex}.tmp")
    try:
        with temporario.open("x", encoding="utf-8") as arquivo:
            json.dump(documento_final, arquivo, ensure_ascii=False, indent=4)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)

    return caminho, len(resultados)


def processar_e_gerar_json():
    """Processa buscas e acrescenta os novos resultados ao JSON existente."""
    registros_novos = []

    for item in CONFIGURACOES_BUSCA:
        uf = item["uf"]
        id_muni = item["id_municipio"]

        logging.info("Consultando UF=%s município=%s", uf, id_muni)
        estacoes = buscar_estacoes(uf, id_muni)

        if not estacoes:
            logging.warning("Nenhuma estação encontrada: UF=%s município=%s", uf, id_muni)
            continue

        for estacao in estacoes:
            # Extrai o ID da estação dinamicamente
            if isinstance(estacao, dict):
                id_estacao = estacao.get("id") or estacao.get("idEstacao")
            else:
                id_estacao = estacao

            if id_estacao:
                logging.info("Coletando clima para estação=%s", id_estacao)
                clima = buscar_dados_climaticos(
                    str(id_estacao), DATA_INICIAL, DATA_FINAL
                )

                # Monta a estrutura do item
                registro = {
                    "uf": uf,
                    "id_municipio": id_muni,
                    "id_estacao": id_estacao,
                    "capturado_em": datetime.now(timezone.utc).isoformat(),
                    "detalhes_estacao": estacao,
                    "dados_climaticos": clima,
                }

                registros_novos.append(registro)

    temperaturas_ar = extrair_temperaturas_ar(registros_novos)
    caminho, total_acumulado = salvar_resultados_append(registros_novos)

    logging.info(
        "Coleta Agritempo concluída: novos=%s total_acumulado=%s observacoes_temperatura_ar=%s arquivo=%s",
        len(registros_novos),
        total_acumulado,
        len(temperaturas_ar),
        caminho,
    )


def main() -> int:
    configure_logging(PROJECT_ROOT, categoria="tratamento")
    if not os.getenv("AGRITEMPO_BEARER_TOKEN"):
        logging.error("Configure AGRITEMPO_BEARER_TOKEN em src/config/.env.")
        return 1
    try:
        processar_e_gerar_json()
    except (OSError, ValueError, json.JSONDecodeError):
        logging.exception("Falha ao persistir resultados da API Agritempo.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())