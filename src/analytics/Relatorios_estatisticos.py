"""Geração de relatórios estatísticos para leituras ambientais e meteorológicas.

Este módulo carrega os arquivos JSON de leitura, normaliza os dados aninhados,
permite a seleção de uma cidade pelo terminal e calcula estatísticas descritivas
como mediana, quartis e IQR para cada variável monitorada.
"""

import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from tabulate import tabulate

# Localiza o diretório raiz do projeto para permitir importações e carregar o .env
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))
load_dotenv(dotenv_path=BASE_DIR / ".env")


def get_env(chave: str) -> str:
    """Obtém obrigatoriamente a variável do arquivo .env.

    Lança erro se não for encontrada.
    """
    valor = os.getenv(chave)
    if not valor:
        raise KeyError(
            f"❌ Configuração ausente: A chave '{chave}' não foi encontrada no arquivo .env"
        )
    return valor


# Caminhos dos arquivos lidos estritamente do .env
DIR_JSON_AGUA = BASE_DIR / get_env("INGESTION_LEITURA_AMBIENTAL")
DIR_JSON_METEO = BASE_DIR / get_env("INGESTION_LEITURA_METEOROLOGICA")

# Mapeamento dos caminhos achatados (colunas no Pandas) para nomes amigáveis no relatório
COLUNAS_AGUA = {
    "qualidade_agua.temperatura.valor": "Temperatura da Água (°C)",
    "qualidade_agua.ph.valor": "pH da Água",
    "qualidade_agua.oxigenio_dissolvido.valor": "Oxigênio Dissolvido (mg/L)",
    "qualidade_agua.condutividade.valor": "Condutividade (µS/cm)",
}

COLUNAS_METEOROLOGICAS = {
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
                conteudo, record_path=[chave_lista], errors="ignore"
            )
        else:
            df_normalizado = pd.json_normalize(
                [conteudo], record_path=[chave_lista], errors="ignore"
            )

        return df_normalizado

    except Exception as e:
        logging.error(
            f"Erro ao processar e achatar o arquivo '{caminho_arquivo.name}': {e}"
        )
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
                media = serie.mean()
                mediana = serie.median()
                std = serie.std()
                q1 = serie.quantile(0.25)
                q3 = serie.quantile(0.75)
                iqr = q3 - q1

                # Cálculo de Outliers via Regra do IQR (Limite Inferior e Superior)
                limite_inf = q1 - 1.5 * iqr
                limite_sup = q3 + 1.5 * iqr
                outliers = serie[
                    (serie < limite_inf) | (serie > limite_sup)
                ].count()

                relatorio.append(
                    {
                        "Relatório": nome_relatorio,
                        "Leituras": nome_amigavel,
                        "Total Registros": len(serie),
                        "Média": round(media, 2),
                        "Mediana": round(mediana, 2),
                        "Desvio Padrão": round(std, 2)
                        if pd.notna(std)
                        else 0.0,
                        "IQR": round(iqr, 2),
                        "Outliers": int(outliers),
                    }
                )
        else:
            logging.warning(
                f"Campo '{coluna_json}' não encontrado no DataFrame."
            )

    return pd.DataFrame(relatorio)


def selecionar_cidade_e_estacao(
    df_agua: pd.DataFrame, df_meteo: pd.DataFrame
):
    """Filtra os DataFrames em 2 níveis: Cidade -> Estação."""
    col_cidade = "cidade"
    col_estacao = "estacao" if "estacao" in df_agua.columns else "estacao_id"

    # --- 1. FILTRO DE CIDADES ---
    cidades_agua = (
        set(df_agua[col_cidade].dropna().unique())
        if col_cidade in df_agua.columns
        else set()
    )
    cidades_meteo = (
        set(df_meteo[col_cidade].dropna().unique())
        if col_cidade in df_meteo.columns
        else set()
    )
    todas_cidades = sorted(list(cidades_agua.union(cidades_meteo)))

    if not todas_cidades:
        print("⚠️ Nenhuma coluna de cidade foi identificada nos dados.")
        return (
            df_agua,
            df_meteo,
            "Todas as Cidades",
            "Todas as Estações",
        )

    print("\n" + "=" * 50)
    print("      1. SELEÇÃO DE CIDADE")
    print("=" * 50)
    print(" [0] TODAS AS CIDADES (Visão Geral)")
    for idx, cidade in enumerate(todas_cidades, start=1):
        print(f" [{idx}] {cidade}")
    print("=" * 50)

    cidade_escolhida = "Todas as Cidades"
    while True:
        opcao_cidade = input("Digite o número da CIDADE desejada: ").strip()
        if opcao_cidade == "0":
            break
        elif opcao_cidade.isdigit() and 1 <= int(opcao_cidade) <= len(
            todas_cidades
        ):
            cidade_escolhida = todas_cidades[int(opcao_cidade) - 1]
            if col_cidade in df_agua.columns:
                df_agua = df_agua[df_agua[col_cidade] == cidade_escolhida]
            if col_cidade in df_meteo.columns:
                df_meteo = df_meteo[df_meteo[col_cidade] == cidade_escolhida]
            break
        else:
            print("⚠️ Opção inválida! Digite um número da lista acima.")

    # --- 2. FILTRO DE ESTAÇÕES DA CIDADE SELECIONADA ---
    estacoes_agua = (
        set(df_agua[col_estacao].dropna().unique())
        if col_estacao in df_agua.columns
        else set()
    )
    estacoes_meteo = (
        set(df_meteo[col_estacao].dropna().unique())
        if col_estacao in df_meteo.columns
        else set()
    )
    todas_estacoes = sorted(list(estacoes_agua.union(estacoes_meteo)))

    estacao_escolhida = "Todas as Estações"
    if todas_estacoes:
        print("\n" + "=" * 50)
        print(f"      2. SELEÇÃO DE ESTAÇÃO ({cidade_escolhida})")
        print("=" * 50)
        print(" [0] TODAS AS ESTAÇÕES DESSA CIDADE")
        for idx, estacao in enumerate(todas_estacoes, start=1):
            print(f" [{idx}] {estacao}")
        print("=" * 50)

        while True:
            opcao_estacao = input(
                "Digite o número da ESTAÇÃO desejada: "
            ).strip()
            if opcao_estacao == "0":
                break
            elif opcao_estacao.isdigit() and 1 <= int(opcao_estacao) <= len(
                todas_estacoes
            ):
                estacao_escolhida = todas_estacoes[int(opcao_estacao) - 1]
                if col_estacao in df_agua.columns:
                    df_agua = df_agua[
                        df_agua[col_estacao] == estacao_escolhida
                    ]
                if col_estacao in df_meteo.columns:
                    df_meteo = df_meteo[
                        df_meteo[col_estacao] == estacao_escolhida
                    ]
                break
            else:
                print("⚠️ Opção inválida! Digite um número da lista acima.")

    return df_agua, df_meteo, cidade_escolhida, estacao_escolhida


def main():
    """Executa o fluxo principal de geração dos relatórios estatísticos.

    O processo inclui carregamento dos dados, seleção interativa da cidade,
    cálculo das estatísticas por variável e impressão dos resultados em tabela.
    """

    logging.info("Iniciando a geração dos Relatórios Estatísticos...")

    # 1. CARREGA OS DATAFRAMES
    df_agua = carregar_json(DIR_JSON_AGUA, chave_lista="leituras_ambientais")
    df_meteo = carregar_json(
        DIR_JSON_METEO, chave_lista="leituras_meteorologicas"
    )

    if df_agua.empty and df_meteo.empty:
        logging.warning("Nenhum dado pôde ser carregado dos arquivos JSON.")
        return

    # 2. SELEÇÃO DINÂMICA DE CIDADE E ESTAÇÃO
    df_agua, df_meteo, nome_cidade, nome_estacao = (
        selecionar_cidade_e_estacao(df_agua, df_meteo)
    )

    print(
        f"\n📌 Exibindo estatísticas para Cidade: [ {nome_cidade} ] | Estação: [ {nome_estacao} ]\n"
    )

    # 3. PROCESSA E IMPRIME LEITURAS AMBIENTAIS
    if not df_agua.empty:
        relatorio_agua = calcular_estatisticas(
            df_agua, COLUNAS_AGUA, "Qualidade da Água"
        )
        if not relatorio_agua.empty:
            print("=" * 90)
            print(
                f"📊 RELATÓRIO: LEITURAS AMBIENTAIS - Cidade: {nome_cidade} | Estação: {nome_estacao}"
            )
            print("=" * 90)
            print(
                tabulate(
                    relatorio_agua,
                    headers="keys",
                    tablefmt="fancy_grid",
                    showindex=False,
                )
            )
            print("\n")
            logging.info(
                f"--- RELATÓRIO AMBIENTAL ({nome_cidade} - {nome_estacao}) ---\n{relatorio_agua.to_string(index=False)}\n"
            )

    # 4. PROCESSA E IMPRIME LEITURAS METEOROLÓGICAS
    if not df_meteo.empty:
        relatorio_meteo = calcular_estatisticas(
            df_meteo, COLUNAS_METEOROLOGICAS, "Meteorologia"
        )
        if not relatorio_meteo.empty:
            print("=" * 90)
            print(
                f"🌤️️  RELATÓRIO: LEITURAS METEOROLÓGICAS - Cidade: {nome_cidade} | Estação: {nome_estacao}"
            )
            print("=" * 90)
            print(
                tabulate(
                    relatorio_meteo,
                    headers="keys",
                    tablefmt="fancy_grid",
                    showindex=False,
                )
            )
            print("\n")
            logging.info(
                f"--- RELATÓRIO METEOROLÓGICO ({nome_cidade} - {nome_estacao}) ---\n{relatorio_meteo.to_string(index=False)}\n"
            )


if __name__ == "__main__":
    main()