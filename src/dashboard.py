import pandas as pd
import streamlit as st
from datetime import datetime, date

from config.settings import create_db_engine

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitoramento Ambiental e Meteorológico",
    page_icon="🌊",
    layout="wide",
)

# --- CSS PERSONALIZADO PARA AS TABELAS COM QUEBRA DE LINHA ---
st.markdown("""
    <style>
    .tabela-customizada {
        width: 100%;
        border-collapse: collapse;
        font-family: sans-serif;
        font-size: 14px;
        margin-bottom: 20px;
    }
    .tabela-customizada th {
        background-color: #f0f2f6;
        color: #31333F;
        font-weight: 600;
        text-align: left;
        padding: 10px;
        border-bottom: 2px solid #e6e9ef;
    }
    .tabela-customizada td {
        padding: 10px;
        border-bottom: 1px solid #e6e9ef;
        word-wrap: break-word;
        white-space: normal;
        vertical-align: middle;
    }
    @media (prefers-color-scheme: dark) {
        .tabela-customizada th {
            background-color: #262730;
            color: #FAFAFA;
            border-bottom: 2px solid #41444C;
        }
        .tabela-customizada td {
            border-bottom: 1px solid #41444C;
            color: #FAFAFA;
        }
    }
    </style>
""", unsafe_allow_html=True)

st.header("📊 Dashboard de Leituras Ambientais e Meteorológicas")


# --- CONEXÃO COM O SQL SERVER EXPRESS ---
@st.cache_resource
def get_database_engine():
    return create_db_engine()


engine = get_database_engine()


# --- FUNÇÃO GENÉRICA PARA EXECUTAR QUERIES COM CACHE ---
@st.cache_data(ttl=60)
def carregar_dados(query: str):
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


# --- FILTROS NA SIDEBAR ---
st.sidebar.header("🔍 Filtros")

# 1. BUSCAR TODAS AS CIDADES COM DADOS
try:
    query_cidades_com_dados = """
        SELECT DISTINCT c.nome AS cidade, e.sigla AS estado
        FROM cidade c
        JOIN estado e ON c.id_estado = e.id
        WHERE c.id IN (
            SELECT DISTINCT est.id_cidade 
            FROM qualidade_agua q
            JOIN estacao est ON q.id_estacao = est.id
            
            UNION
            
            SELECT DISTINCT id_cidade 
            FROM leitura_meteorologica
        )
        ORDER BY c.nome
    """
    df_cidades = carregar_dados(query_cidades_com_dados)
    lista_cidades = ["Todas"] + (df_cidades["cidade"] + " - " + df_cidades["estado"]).tolist() if not df_cidades.empty else ["Todas"]

except Exception as err:
    st.error(f"Erro ao carregar lista de cidades: {err}")
    lista_cidades = ["Todas"]

# Renderiza o filtro de Cidade primeiro
cidade_selecionada = st.sidebar.selectbox("Selecione a Cidade", options=lista_cidades)
filtro_cidade = cidade_selecionada.split(" - ")[0] if cidade_selecionada != "Todas" else None


# 2. BUSCAR APENAS AS ESTAÇÕES DA CIDADE SELECIONADA (DEPENDENCIA)
try:
    query_estacoes_com_dados = """
        SELECT DISTINCT est.nome AS estacao
        FROM estacao est
        JOIN cidade c ON est.id_cidade = c.id
        WHERE est.id IN (SELECT DISTINCT id_estacao FROM qualidade_agua)
    """
    if filtro_cidade:
        query_estacoes_com_dados += f" AND c.nome = '{filtro_cidade}'"
    
    query_estacoes_com_dados += " ORDER BY est.nome"
    
    df_estacoes = carregar_dados(query_estacoes_com_dados)
    lista_estacoes = ["Todas"] + df_estacoes["estacao"].tolist() if not df_estacoes.empty else ["Todas"]

except Exception as err:
    st.error(f"Erro ao carregar lista de estações: {err}")
    lista_estacoes = ["Todas"]

# Renderiza o filtro de Estação dependendo da seleção da Cidade
estacao_selecionada = st.sidebar.selectbox("Selecione a Estação (Água)", options=lista_estacoes)
filtro_estacao = estacao_selecionada if estacao_selecionada != "Todas" else None


# 3. FILTRO DE PERÍODO DE DATAS
st.sidebar.subheader("📅 Período")
hoje = date.today()
data_padrao_inicio = date(2026, 9, 15)
data_padrao_fim = date(2026, 9, 26)

periodo_selecionado = st.sidebar.date_input(
    "Selecione o Intervalo",
    value=(data_padrao_inicio, data_padrao_fim),
    format="DD/MM/YYYY"
)

if isinstance(periodo_selecionado, tuple) and len(periodo_selecionado) == 2:
    data_inicio, data_fim = periodo_selecionado
else:
    data_inicio = periodo_selecionado[0] if isinstance(periodo_selecionado, tuple) else periodo_selecionado
    data_fim = data_padrao_fim


# --- MONTAGEM DAS QUERIES SQL DINÂMICAS ---

condicoes_agua = []
condicoes_meteo = []

# Filtro por Cidade
if filtro_cidade:
    condicoes_agua.append(f"c.nome = '{filtro_cidade}'")
    condicoes_meteo.append(f"c.nome = '{filtro_cidade}'")

# Filtro por Estação (apenas para a qualidade da água)
if filtro_estacao:
    condicoes_agua.append(f"e.nome = '{filtro_estacao}'")

# Filtro por Período de Datas
if data_inicio and data_fim:
    str_inicio = data_inicio.strftime('%Y-%m-%d')
    str_fim = data_fim.strftime('%Y-%m-%d')
    condicoes_agua.append(f"q.data_leitura >= '{str_inicio} 00:00:00' AND q.data_leitura <= '{str_fim} 23:59:59'")
    condicoes_meteo.append(f"m.data_leitura >= '{str_inicio} 00:00:00' AND m.data_leitura <= '{str_fim} 23:59:59'")


# 1. Query Qualidade da Água
query_agua = """
    SELECT 
        q.id AS [ID],
        e.nome AS [Estação],
        c.nome AS [Cidade],
        est.sigla AS [UF],
        FORMAT(q.data_leitura, 'dd/MM/yyyy HH:mm') AS [Data/Hora],
        CAST(q.temperatura_agua AS FLOAT) AS [Temperatura],
        CAST(q.ph AS FLOAT) AS [pH],
        CAST(q.oxigenio AS FLOAT) AS [Oxigênio],
        CAST(q.condutividade AS FLOAT) AS [Condutividade]
    FROM qualidade_agua q
    JOIN estacao e ON q.id_estacao = e.id
    JOIN cidade c ON e.id_cidade = c.id
    JOIN estado est ON e.id_estado = est.id
"""
if condicoes_agua:
    query_agua += " WHERE " + " AND ".join(condicoes_agua)
query_agua += " ORDER BY q.data_leitura DESC"


# 2. Query Meteorológica
query_meteo = """
    SELECT 
        m.id AS [ID],
        c.nome AS [Cidade],
        e.sigla AS [UF],
        FORMAT(m.data_leitura, 'dd/MM/yyyy HH:mm') AS [Data/Hora],
        CAST(m.temperatura_ar AS FLOAT) AS [Temperatura],
        CAST(m.umidade AS FLOAT) AS [Umidade],
        CAST(m.chuva AS FLOAT) AS [Chuva],
        CAST(m.vento AS FLOAT) AS [Vento],
        m.condicao AS [Condição do Tempo]
    FROM leitura_meteorologica m
    JOIN cidade c ON m.id_cidade = c.id
    JOIN estado e ON c.id_estado = e.id
"""
if condicoes_meteo:
    query_meteo += " WHERE " + " AND ".join(condicoes_meteo)
query_meteo += " ORDER BY m.data_leitura DESC"


# --- CARREGAR DATAFRAMES ---
try:
    df_agua = carregar_dados(query_agua)
    df_meteo = carregar_dados(query_meteo)
except Exception as err:
    st.error(f"Erro ao consultar o banco de dados: {err}")
    df_agua, df_meteo = pd.DataFrame(), pd.DataFrame()

# --- ABA DE EXIBIÇÃO ---
aba1, aba2 = st.tabs(["💧 Qualidade da Água", "🌤️ Meteorologia"])

with aba1:
    st.subheader("Leituras da Qualidade da Água")
    if not df_agua.empty:
        # Métricas Estatísticas para Água
        temp_agua = df_agua['Temperatura'].dropna()
        ph_agua = df_agua['pH'].dropna()
        ox_agua = df_agua['Oxigênio'].dropna()
        cond_agua = df_agua['Condutividade'].dropna()

        # Cálculo de IQR (Q3 - Q1)
        iqr_temp = temp_agua.quantile(0.75) - temp_agua.quantile(0.25) if not temp_agua.empty else 0
        iqr_ph = ph_agua.quantile(0.75) - ph_agua.quantile(0.25) if not ph_agua.empty else 0
        iqr_ox = ox_agua.quantile(0.75) - ox_agua.quantile(0.25) if not ox_agua.empty else 0
        iqr_cond = cond_agua.quantile(0.75) - cond_agua.quantile(0.25) if not cond_agua.empty else 0

        # Exibição dos cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Média Temp. Água", f"{temp_agua.mean():.2f} °C")
            st.caption(f"**Mediana:** {temp_agua.median():.2f} °C | **Desv. Padrão:** {temp_agua.std():.2f} | **IQR:** {iqr_temp:.2f}")

        with col2:
            st.metric("Média pH", f"{ph_agua.mean():.2f}")
            st.caption(f"**Mediana:** {ph_agua.median():.2f} | **Desv. Padrão:** {ph_agua.std():.2f} | **IQR:** {iqr_ph:.2f}")

        with col3:
            st.metric("Média Oxigênio", f"{ox_agua.mean():.2f} mg/L")
            st.caption(f"**Mediana:** {ox_agua.median():.2f} mg/L | **Desv. Padrão:** {ox_agua.std():.2f} | **IQR:** {iqr_ox:.2f}")

        with col4:
            st.metric("Média Condutividade", f"{cond_agua.mean():.2f} µS/cm")
            st.caption(f"**Mediana:** {cond_agua.median():.2f} µS/cm | **Desv. Padrão:** {cond_agua.std():.2f} | **IQR:** {iqr_cond:.2f}")

        st.markdown("---")
        st.caption("*Temperatura: °C | Chuva: mm | Vento: Km/h | Condutividade: µS/cm | Oxigênio: mg/L")
        
        # Formatação para exibição na Tabela (2 casas decimais)
        df_agua_exibicao = df_agua.copy()
        colunas_float_agua = ["Temperatura", "pH", "Oxigênio", "Condutividade"]
        for col in colunas_float_agua:
            df_agua_exibicao[col] = df_agua_exibicao[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")

        st.markdown(
            df_agua_exibicao.to_html(classes="tabela-customizada", index=False, escape=False),
            unsafe_allow_html=True
        )

        metrica_agua = st.selectbox(
            "Métrica para o Gráfico (Água):",
            [
                "pH",
                "Temperatura",
                "Oxigênio",
                "Condutividade",
            ],
        )
        st.line_chart(df_agua, x="Data/Hora", y=metrica_agua)
    else:
        st.info("Nenhum registro de qualidade da água encontrado para o filtro selecionado.")

with aba2:
    st.subheader("Leituras Meteorológicas")
    if not df_meteo.empty:
        # Métricas Estatísticas para Clima
        temp_ar = df_meteo['Temperatura'].dropna()
        umidade = df_meteo['Umidade'].dropna()
        chuva = df_meteo['Chuva'].dropna()
        vento = df_meteo['Vento'].dropna()

        # Cálculo de IQR
        iqr_temp_ar = temp_ar.quantile(0.75) - temp_ar.quantile(0.25) if not temp_ar.empty else 0
        iqr_umi = umidade.quantile(0.75) - umidade.quantile(0.25) if not umidade.empty else 0
        iqr_chuva = chuva.quantile(0.75) - chuva.quantile(0.25) if not chuva.empty else 0
        iqr_vento = vento.quantile(0.75) - vento.quantile(0.25) if not vento.empty else 0

        # Exibição dos cards
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Média Temp. Ar", f"{temp_ar.mean():.2f} °C")
            st.caption(f"**Mediana:** {temp_ar.median():.2f} °C | **Desv. Padrão:** {temp_ar.std():.2f} | **IQR:** {iqr_temp_ar:.2f}")

        with col2:
            st.metric("Média Umidade", f"{umidade.mean():.2f}%")
            st.caption(f"**Mediana:** {umidade.median():.2f}% | **Desv. Padrão:** {umidade.std():.2f} | **IQR:** {iqr_umi:.2f}")

        with col3:
            st.metric("Chuva Acumulada", f"{chuva.sum():.2f} mm")
            st.caption(f"**Mediana:** {chuva.median():.2f} mm | **Desv. Padrão:** {chuva.std():.2f} | **IQR:** {iqr_chuva:.2f}")

        with col4:
            st.metric("Vento Médio", f"{vento.mean():.2f} km/h")
            st.caption(f"**Mediana:** {vento.median():.2f} km/h | **Desv. Padrão:** {vento.std():.2f} | **IQR:** {iqr_vento:.2f}")

        st.markdown("---")

        st.caption("*Temperatura: °C | Umidade: % | Chuva: mm | Vento: Km/h")
        # Formatação para exibição na Tabela (2 casas decimais)
        df_meteo_exibicao = df_meteo.copy()
        colunas_float_meteo = ["Temperatura", "Umidade", "Chuva", "Vento"]
        for col in colunas_float_meteo:
            df_meteo_exibicao[col] = df_meteo_exibicao[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")

        st.markdown(
            df_meteo_exibicao.to_html(classes="tabela-customizada", index=False, escape=False),
            unsafe_allow_html=True
        )

        metrica_meteo = st.selectbox(
            "Métrica para o Gráfico (Clima):",
            [
                "Temperatura",
                "Umidade",
                "Chuva",
                "Vento",
            ],
        )
        st.line_chart(df_meteo, x="Data/Hora", y=metrica_meteo)
    else:
        st.info("Nenhum registro meteorológico encontrado para o filtro selecionado.")