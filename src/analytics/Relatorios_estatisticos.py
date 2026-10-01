"""Geração de relatórios estatísticos para leituras ambientais e meteorológicas.

Este módulo carrega os arquivos JSON de leitura, normaliza os dados aninhados,
permite a seleção de uma cidade pelo terminal e calcula estatísticas descritivas
como mediana, quartis e IQR para cada variável monitorada.
"""

import json
import logging
from pathlib import Path
import pandas as pd
from tabulate import tabulate

BASE_DIR = Path(__file__).resolve().parents[1]
PASTA_LEITURAS = BASE_DIR / "ingestion" / "leituras"

CAMINHO_JSON_AGUA = PASTA_LEITURAS / "leituras_ambientais.json"
CAMINHO_JSON_METEO = PASTA_LEITURAS / "leituras_meteorologicas.json"

# Mapeamento dos caminhos achatados (colunas no Pandas) para nomes amigáveis no relatório
COLUNAS_ALVO_AGUA = {
    "qualidade_agua.temperatura.valor": "Temperatura da Água (°C)",
    "qualidade_agua.ph.valor": "pH da Água",
    "qualidade_agua.oxigenio_dissolvido.valor": "Oxigênio Dissolvido (mg/L)",
    "qualidade_agua.condutividade.valor": "Condutividade (µS/cm)",
}

COLUNAS_ALVO_METEOROLOGICAS = {
    "dados_meteorologicos.temperatura_ar.valor": "Temperatura (°C)",
    "dados_meteorologicos.umidade.valor": "Umidade (%)",
    "dados_meteorologicos.chuva.valor": "Precipitação (mm)",
    "dados_meteorologicos.vento.velocidade": "Velocidade do Vento (km/h)",
}

def carregar_json(caminho_arquivo: Path, chave_lista: str) -> pd.DataFrame:
    """Carrega um arquivo JSON e normaliza a estrutura em um DataFrame.

    Args:
        caminho_arquivo (Path): Caminho para o arquivo JSON a ser lido.
        chave_lista (str): Nome da chave que contém a lista de registros dentro
            do JSON.

    Returns:
        pd.DataFrame: DataFrame com os dados achatados e prontos para análise.
    """
    
    if not caminho_arquivo.exists():
        logging.warning(f"Arquivo não encontrado: {caminho_arquivo}")
        return pd.DataFrame()

    try:
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            conteudo = json.load(f)

        if isinstance(conteudo, list):
            df_normalizado = pd.json_normalize(
                conteudo,
                record_path=[chave_lista],
                errors="ignore"
            )
        else:
            df_normalizado = pd.json_normalize(
                [conteudo],
                record_path=[chave_lista],
                errors="ignore"
            )

        return df_normalizado

    except Exception as e:
        logging.error(f"Erro ao processar e achatar o arquivo '{caminho_arquivo.name}': {e}")
        return pd.DataFrame()


def calcular_estatisticas(df: pd.DataFrame, mapa_colunas: dict, nome_relatorio: str) -> pd.DataFrame:
    """Calcula estatísticas descritivas para as colunas informadas.

    Args:
        df (pd.DataFrame): DataFrame com os dados a serem avaliados.
        mapa_colunas (dict): Dicionário mapeando nomes originais das colunas para
            rótulos amigáveis exibidos no relatório.
        nome_relatorio (str): Nome do tipo de relatório, como "Qualidade da Água"
            ou "Meteorologia".

    Returns:
        pd.DataFrame: Tabela com mediana, quartis e IQR para cada variável.
    """

    relatorio = []

    for coluna_json, nome_amigavel in mapa_colunas.items():
        if coluna_json in df.columns:
            serie = pd.to_numeric(df[coluna_json], errors="coerce").dropna()

            if not serie.empty:
                mediana = serie.median()
                q1 = serie.quantile(0.25)
                q3 = serie.quantile(0.75)
                iqr = q3 - q1

                relatorio.append({
                    "Relatório": nome_relatorio,
                    "Variável": nome_amigavel,
                    "Total_Registros": len(serie),
                    "Mediana": round(mediana, 2),
                    "Q1 (25%)": round(q1, 2),
                    "Q3 (75%)": round(q3, 2),
                    "IQR": round(iqr, 2)
                })
        else:
            logging.warning(f"Campo '{coluna_json}' não encontrado no DataFrame.")

    return pd.DataFrame(relatorio)


def selecionar_e_filtrar_cidade(df_agua: pd.DataFrame, df_meteo: pd.DataFrame):
    """Mostra um menu interativo para escolher a cidade de interesse.

    Args:
        df_agua (pd.DataFrame): DataFrame das leituras ambientais.
        df_meteo (pd.DataFrame): DataFrame das leituras meteorológicas.

    Returns:
        tuple: DataFrames filtrados e o nome da cidade selecionada.
    """

    cidades_agua = set(df_agua["cidade"].dropna().unique()) if "cidade" in df_agua.columns else set()
    cidades_meteo = set(df_meteo["cidade"].dropna().unique()) if "cidade" in df_meteo.columns else set()
    
    # Consolida a lista única de cidades
    todas_cidades = sorted(list(cidades_agua.union(cidades_meteo)))

    if not todas_cidades:
        print("⚠️ Nenhuma coluna 'cidade' foi identificada nos dados.")
        return df_agua, df_meteo, "Todas as Cidades"

    print("\n" + "=" * 50)
    print("      FILTRO DE CIDADES DISPONÍVEIS")
    print("=" * 50)
    print(" [0] TODAS AS CIDADES (Visão Geral)")
    for index, cidade in enumerate(todas_cidades, start=1):
        print(f" [{index}] {cidade}")
    print("=" * 50)

    while True:
        opcao = input("Digite o número da cidade desejada: ").strip()
        if opcao == "0":
            return df_agua, df_meteo, "Todas as Cidades"
        elif opcao.isdigit() and 1 <= int(opcao) <= len(todas_cidades):
            cidade_escolhida = todas_cidades[int(opcao) - 1]
            
            # Aplica os filtros
            df_agua_filtrado = df_agua[df_agua["cidade"] == cidade_escolhida] if "cidade" in df_agua.columns else df_agua
            df_meteo_filtrado = df_meteo[df_meteo["cidade"] == cidade_escolhida] if "cidade" in df_meteo.columns else df_meteo
            
            return df_agua_filtrado, df_meteo_filtrado, cidade_escolhida
        else:
            print("⚠️ Opção inválida! Digite um número da lista acima.")


def main():
    """Executa o fluxo principal de geração dos relatórios estatísticos.

    O processo inclui carregamento dos dados, seleção interativa da cidade,
    cálculo das estatísticas por variável e impressão dos resultados em tabela.
    """

    logging.info("Iniciando a geração dos Relatórios Estatísticos...")

    # 1. CARREGA OS DATAFRAMES
    df_agua = carregar_json(CAMINHO_JSON_AGUA, chave_lista="leituras_ambientais")
    df_meteo = carregar_json(CAMINHO_JSON_METEO, chave_lista="leituras_meteorologicas")

    if df_agua.empty and df_meteo.empty:
        logging.warning("Nenhum dado pôde ser carregado dos arquivos JSON.")
        return

    # 2. SELEÇÃO INTERATIVA DE FILTRO POR CIDADE VIA TERMINAL
    df_agua, df_meteo, nome_filtro_cidade = selecionar_e_filtrar_cidade(df_agua, df_meteo)

    print(f"\n📌 Exibindo estatísticas para: [ {nome_filtro_cidade} ]\n")

    # 3. PROCESSA E IMPRIME LEITURAS AMBIENTAIS
    if not df_agua.empty:
        relatorio_agua = calcular_estatisticas(df_agua, COLUNAS_ALVO_AGUA, "Qualidade da Água")
        if not relatorio_agua.empty:
            print("=" * 80)
            print(f"📊 RELATÓRIO: LEITURAS AMBIENTAIS - {nome_filtro_cidade}")
            print("=" * 80)
            print(tabulate(relatorio_agua, headers="keys", tablefmt="fancy_grid", showindex=False))
            print("\n")
            logging.info(f"--- RELATÓRIO AMBIENTAL ({nome_filtro_cidade}) ---\n{relatorio_agua.to_string(index=False)}\n")

    # 4. PROCESSA E IMPRIME LEITURAS METEOROLÓGICAS
    if not df_meteo.empty:
        relatorio_meteo = calcular_estatisticas(df_meteo, COLUNAS_ALVO_METEOROLOGICAS, "Meteorologia")
        if not relatorio_meteo.empty:
            print("=" * 80)
            print(f"🌤️ RELATÓRIO: LEITURAS METEOROLÓGICAS - {nome_filtro_cidade}")
            print("=" * 80)
            print(tabulate(relatorio_meteo, headers="keys", tablefmt="fancy_grid", showindex=False))
            print("\n")
            logging.info(f"--- RELATÓRIO METEOROLÓGICO ({nome_filtro_cidade}) ---\n{relatorio_meteo.to_string(index=False)}\n")


if __name__ == "__main__":
    main()