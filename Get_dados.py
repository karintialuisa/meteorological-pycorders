import json
from datetime import datetime
import requests

# 1. Lista de dicionários com UF e ID do Município configuráveis
CONFIGURACOES_BUSCA = [
    {"uf": "BA", "id_municipio": "2927408"},
    {"uf": "SP", "id_municipio": "3550308"},
    {"uf": "RJ", "id_municipio": "3304557"},
    {"uf": "MG", "id_municipio": "3170206"},
]

# Configurações de API e Período
TOKEN_BEARER = "b5876a54-6a44-3986-85f7-03f380448469"
DATA_INICIAL = "2026-05-01"
DATA_FINAL = "2026-09-01"
NOME_ARQUIVO_JSON = "dados_agritempo.json"

# Cabeçalhos padrão das requisições
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "access-control-allow-origin": "*",
    "authorization": f"Bearer {TOKEN_BEARER}",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "Referer": "https://www.agritempo.gov.br/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def buscar_estacoes(uf: str, id_municipio: str) -> list:
    """Busca as estações vinculadas ao município e UF."""
    url = "https://api.cnptia.embrapa.br/agritempo-dados/v1/estacao"
    params = {"uf": uf.upper(), "idMunicipio": id_municipio}

    try:
        response = requests.get(
            url, headers=HEADERS, params=params, timeout=15
        )
        if response.status_code == 200:
            return response.json()
        print(
            f"Erro ao buscar estações [{uf} - {id_municipio}]: Status"
            f" {response.status_code}"
        )
        return []
    except requests.RequestException as e:
        print(f"Falha na requisição de estações: {e}")
        return []


def buscar_dados_climaticos(id_estacao: str, data_inicio: str, data_fim: str) -> dict:
    """Busca o histórico de dados climáticos de uma estação específica."""
    url = f"https://api.cnptia.embrapa.br/agritempo-dados/v1/clima/{id_estacao}"
    params = {"dataInicial": data_inicio, "dataFinal": data_fim}

    try:
        response = requests.get(
            url, headers=HEADERS, params=params, timeout=15
        )
        if response.status_code == 200:
            return response.json()
        print(
            f"Erro ao buscar clima da estação {id_estacao}: Status"
            f" {response.status_code}"
        )
        return {}
    except requests.RequestException as e:
        print(f"Falha na requisição de clima: {e}")
        return {}


def processar_e_gerar_json():
    """Processa todas as buscas e gera o arquivo JSON final."""
    estrutura_final = {
        "metadados": {
            "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_inicial": DATA_INICIAL,
            "data_final": DATA_FINAL,
            "total_consultas_configuradas": len(CONFIGURACOES_BUSCA),
        },
        "resultados": [],
    }

    for item in CONFIGURACOES_BUSCA:
        uf = item["uf"]
        id_muni = item["id_municipio"]

        print(f"\n---> Consultando UF: {uf} | Município ID: {id_muni}")
        estacoes = buscar_estacoes(uf, id_muni)

        if not estacoes:
            print(f"Nenhuma estação encontrada para {uf} - {id_muni}.")
            continue

        for estacao in estacoes:
            # Extrai o ID da estação dinamicamente
            if isinstance(estacao, dict):
                id_estacao = estacao.get("id") or estacao.get("idEstacao")
            else:
                id_estacao = estacao

            if id_estacao:
                print(
                    f"  > Coletando clima para a Estação ID: {id_estacao}..."
                )
                clima = buscar_dados_climaticos(
                    str(id_estacao), DATA_INICIAL, DATA_FINAL
                )

                # Monta a estrutura do item
                registro = {
                    "uf": uf,
                    "id_municipio": id_muni,
                    "id_estacao": id_estacao,
                    "detalhes_estacao": estacao,
                    "dados_climaticos": clima,
                }

                estrutura_final["resultados"].append(registro)

    # Escreve o dicionário completo em um arquivo .json
    with open(NOME_ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(estrutura_final, f, ensure_ascii=False, indent=4)

    print("\n==================================================")
    print(
        f"Sucesso! {len(estrutura_final['resultados'])} registro(s) salvos em"
        f" '{NOME_ARQUIVO_JSON}'."
    )
    print("==================================================")


if __name__ == "__main__":
    processar_e_gerar_json()