import json
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Monitoramento ambiental",
    page_icon="💧",
    layout="wide",
)


DIR_LEITURAS = Path(__file__).resolve().parent / "ingestion" / "leituras"


@st.cache_data
def carregar_leituras() -> pd.DataFrame:
    """Lê o JSON ambiental e transforma os campos aninhados em colunas."""
    caminho = DIR_LEITURAS / "leituras_ambientais.json"
    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)["leituras_ambientais"]

    leituras = pd.json_normalize(dados).rename(
        columns={
            "qualidade_agua.temperatura.valor": "Temperatura (°C)",
            "qualidade_agua.ph.valor": "pH",
            "qualidade_agua.oxigenio_dissolvido.valor": "Oxigênio dissolvido (mg/L)",
            "qualidade_agua.condutividade.valor": "Condutividade (µS/cm)",
        }
    )
    leituras["timestamp"] = pd.to_datetime(leituras["timestamp"])
    return leituras.sort_values("timestamp", ascending=False).reset_index(drop=True)


def calcular_estatisticas(dados: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """Calcula média, mediana, quartis e IQR por grupo."""
    colunas_numericas = dados.select_dtypes(include="number").columns
    estatisticas = dados.groupby(grupo)[list(colunas_numericas)].agg(
        ["mean", "median", lambda serie: serie.quantile(0.25), lambda serie: serie.quantile(0.75)]
    )
    estatisticas.columns = [
        f"{coluna} - {medida}"
        for coluna, medida in estatisticas.columns
    ]

    for coluna in colunas_numericas:
        q1 = estatisticas[f"{coluna} - <lambda_0>"]
        q3 = estatisticas[f"{coluna} - <lambda_1>"]
        estatisticas[f"{coluna} - IQR"] = q3 - q1

    return estatisticas.reset_index()


try:
    leituras = carregar_leituras()
except (FileNotFoundError, json.JSONDecodeError) as erro:
    st.error(f"Não foi possível carregar as leituras: {erro}")
    st.stop()

st.title("Monitoramento ambiental")
st.caption("Leituras de qualidade da água agrupadas por estação, cidade e estado.")

with st.sidebar:
    st.header("Filtros")
    estados = st.multiselect(
        "Estado",
        options=sorted(leituras["estado"].dropna().unique()),
    )
    cidades_disponiveis = leituras[
        leituras["estado"].isin(estados)
    ] if estados else leituras
    cidades = st.multiselect(
        "Cidade",
        options=sorted(cidades_disponiveis["cidade"].dropna().unique()),
    )
    estacoes_disponiveis = cidades_disponiveis[
        cidades_disponiveis["cidade"].isin(cidades)
    ] if cidades else cidades_disponiveis
    estacoes = st.multiselect(
        "Estação",
        options=sorted(estacoes_disponiveis["estacao_id"].dropna().unique()),
    )

dados = leituras.copy()
if estados:
    dados = dados[dados["estado"].isin(estados)]
if cidades:
    dados = dados[dados["cidade"].isin(cidades)]
if estacoes:
    dados = dados[dados["estacao_id"].isin(estacoes)]

metricas = {
    "Leituras": len(dados),
    "Estações": dados["estacao_id"].nunique(),
    "Cidades": dados["cidade"].nunique(),
    "Estados": dados["estado"].nunique(),
}
colunas_metricas = st.columns(len(metricas))
for coluna, (rotulo, valor) in zip(colunas_metricas, metricas.items()):
    coluna.metric(rotulo, valor)

if dados.empty:
    st.warning("Nenhuma leitura corresponde aos filtros selecionados.")
    st.stop()

aba_resumo, aba_estatisticas, aba_dados = st.tabs(
    ["Resumo", "Estatísticas", "Dados"]
)

with aba_resumo:
    st.subheader("Leituras por estação")
    leituras_por_estacao = (
        dados.groupby(["estacao_id", "cidade", "estado"], as_index=False)
        .size()
        .rename(columns={"size": "Quantidade de leituras"})
        .sort_values("Quantidade de leituras", ascending=False)
    )
    st.dataframe(leituras_por_estacao, width="stretch", hide_index=True)

    st.subheader("Média das variáveis por estação")
    colunas_numericas = dados.select_dtypes(include="number").columns
    medias = dados.groupby("estacao_id")[list(colunas_numericas)].mean()
    st.bar_chart(medias)

with aba_estatisticas:
    st.subheader("Estatísticas por estação")
    st.caption("IQR é o intervalo interquartil: Q3 - Q1. Ele mostra a dispersão dos 50% centrais dos dados.")
    estatisticas = calcular_estatisticas(dados, "estacao_id")
    st.dataframe(
        estatisticas.round(2),
        width="stretch",
        hide_index=True,
    )

    st.subheader("Estatísticas por cidade")
    estatisticas_cidade = calcular_estatisticas(dados, "cidade")
    st.dataframe(
        estatisticas_cidade.round(2),
        width="stretch",
        hide_index=True,
    )

with aba_dados:
    st.subheader("Leituras filtradas")
    st.dataframe(
        dados.sort_values("timestamp", ascending=False),
        width="stretch",
        hide_index=True,
        column_config={
            "timestamp": st.column_config.DatetimeColumn("Data da leitura"),
        },
    )