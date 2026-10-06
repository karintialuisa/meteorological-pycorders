import pandas as pd
import streamlit as st
from datetime import datetime, date

from config.settings import create_db_engine
from analytics.Relatorios_estatisticos import identificar_outliers_iqr

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitoramento Ambiental e Meteorológico",
    page_icon="🌊",
    layout="wide",
)

# --- CSS PERSONALIZADO PARA AS TABELAS COM QUEBRA DE LINHA ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Sora:wght@400;500;600;700&display=swap');

    :root {
        --pycoders-forest: #10201e;
        --pycoders-lime: #d7f36a;
        --pycoders-paper: #f0f1e9;
        --pycoders-clay: #c86645;
        --pycoders-muted: #60706a;
    }

    .pycoders-hero {
        position: relative;
        display: flex;
        min-height: 260px;
        align-items: center;
        overflow: hidden;
        border-radius: 4px;
        margin: 0 0 12px;
        padding: 32px 38px;
        background: var(--pycoders-forest);
        color: #fff;
        font-family: 'DM Sans', sans-serif;
    }
    .pycoders-hero-image,
    .pycoders-hero-shade {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
    }
    .pycoders-hero-image {
        background-image: url('https://images.unsplash.com/photo-1534088568595-a066f410bcda?auto=format&fit=crop&w=1800&q=85');
        background-position: center 45%;
        background-size: cover;
    }
    .pycoders-hero-shade { background: rgba(10, 24, 23, 0.58); }
    .pycoders-hero-copy {
        position: relative;
        z-index: 1;
        max-width: 720px;
    }
    .pycoders-eyebrow {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0 0 10px;
        color: var(--pycoders-lime);
        font-size: 12px;
        font-weight: 700;
    }
    .pycoders-eyebrow::before {
        width: 24px;
        height: 2px;
        background: var(--pycoders-lime);
        content: '';
    }
    .pycoders-title {
        margin: 0;
        color: #fff;
        font-family: 'Sora', sans-serif;
        font-size: 64px;
        font-weight: 600;
        line-height: 1;
    }
    .pycoders-title span { color: var(--pycoders-lime); }
    .pycoders-description {
        max-width: 480px;
        margin: 12px 0 0;
        color: rgba(255, 255, 255, 0.9);
        font-size: 16px;
        line-height: 1.5;
    }
    .pycoders-hero-mark {
        position: absolute;
        z-index: 1;
        right: 38px;
        bottom: 28px;
        color: rgba(255, 255, 255, 0.88);
        font-size: 11px;
        font-weight: 700;
        text-align: right;
    }
    .pycoders-hero-mark span {
        display: block;
        margin-top: 5px;
        color: var(--pycoders-lime);
        font-weight: 500;
    }
    .pycoders-founders {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0 28px;
        padding: 4px 0 8px;
    }
    .pycoders-founder {
        display: grid;
        grid-template-columns: 34px 1fr;
        align-items: center;
        gap: 10px;
        min-height: 54px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.35);
        color: inherit !important;
        font-family: 'Sora', sans-serif;
        font-size: 14px;
    }
    .pycoders-founder span {
        color: var(--pycoders-clay);
        font-size: 12px;
        font-weight: 700;
    }
    @media (max-width: 700px) {
        .pycoders-hero { min-height: 230px; padding: 26px 22px; }
        .pycoders-title { font-size: 48px; }
        .pycoders-description { max-width: 380px; font-size: 14px; }
        .pycoders-hero-mark { right: 22px; bottom: 16px; font-size: 9px; }
        .pycoders-founders { grid-template-columns: 1fr; }
    }

    .tabela-customizada {
        width: 100%;
        border-collapse: collapse;
        font-family: sans-serif;
        font-size: 14px;
        margin-bottom: 20px;
    }
    .tabela-customizada th {
        background-color: transparent;
        color: inherit !important;
        font-weight: 600;
        text-align: left;
        padding: 10px;
        border-bottom: 2px solid #e6e9ef;
    }
    .tabela-customizada td {
        background-color: transparent;
        color: inherit !important;
        padding: 10px;
        border-bottom: 1px solid #e6e9ef;
        word-wrap: break-word;
        white-space: normal;
        vertical-align: middle;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <section class="pycoders-hero" aria-label="PyCoders: tecnologia, dados e ambiente">
        <div class="pycoders-hero-image" aria-hidden="true"></div>
        <div class="pycoders-hero-shade" aria-hidden="true"></div>
        <div class="pycoders-hero-copy">
            <p class="pycoders-eyebrow">TECNOLOGIA · DADOS · AMBIENTE</p>
            <h1 class="pycoders-title">Py<span>Coders</span></h1>
            <p class="pycoders-description">Dados ambientais transformados em uma leitura mais clara do mundo ao nosso redor.</p>
        </div>
        <div class="pycoders-hero-mark">MONITORAMENTO<span>ÁGUA · ATMOSFERA · SÉRIES</span></div>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.expander("Conheça os fundadores da PyCoders"):
    st.markdown(
        """
        <div class="pycoders-founders">
            <div class="pycoders-founder"><span>01</span>Wagner Dos Santos</div>
            <div class="pycoders-founder"><span>02</span>Karíntia Luisa Arruda Nunes</div>
            <div class="pycoders-founder"><span>03</span>Jaclin Siqueira Saramago Santos</div>
            <div class="pycoders-founder"><span>04</span>Jorge Lucas Caldas Cardoso</div>
            <div class="pycoders-founder"><span>05</span>Anderson Bolsanelli</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def exibir_tabela_paginada(df, chave: str) -> None:
    """Exibe uma tabela e só habilita paginação quando há mais de dez linhas."""
    linhas_por_pagina = 10
    total_linhas = len(df)
    if total_linhas <= linhas_por_pagina:
        st.markdown(
            df.to_html(classes="tabela-customizada", index=False, escape=False),
            unsafe_allow_html=True,
        )
        return

    total_paginas = max(1, (total_linhas + linhas_por_pagina - 1) // linhas_por_pagina)
    chave_pagina = f"pagina_{chave}"
    pagina_atual = st.session_state.get(chave_pagina, 1)
    pagina_atual = min(max(pagina_atual, 1), total_paginas)
    st.session_state[chave_pagina] = pagina_atual

    coluna_anterior, coluna_status, coluna_proxima = st.columns([1, 2, 1])
    if coluna_anterior.button(
        "← Anterior", key=f"{chave}_anterior", disabled=pagina_atual == 1
    ):
        st.session_state[chave_pagina] = pagina_atual - 1
        st.rerun()

    inicio = (pagina_atual - 1) * linhas_por_pagina
    fim = min(inicio + linhas_por_pagina, total_linhas)
    coluna_status.caption(
        f"Página {pagina_atual} de {total_paginas} · linhas "
        f"{inicio + 1}–{fim} de {total_linhas}"
    )

    if coluna_proxima.button(
        "Próxima →",
        key=f"{chave}_proxima",
        disabled=pagina_atual == total_paginas,
    ):
        st.session_state[chave_pagina] = pagina_atual + 1
        st.rerun()

    st.markdown(
        df.iloc[inicio:fim].to_html(
            classes="tabela-customizada", index=False, escape=False
        ),
        unsafe_allow_html=True,
    )


def preparar_dados_grafico(df, metrica: str):
    dados_grafico = df[["Data/Hora", metrica]].copy()
    dados_grafico["Data"] = (
        dados_grafico["Data/Hora"]
        .astype("string")
        .str.slice(0, 10)
        .str.replace("/", "-", regex=False)
    )
    return dados_grafico[["Data", metrica]]


def exibir_relatorio_outliers(df, mapa_colunas: dict, chave: str, contexto: list):
    outliers = identificar_outliers_iqr(df, mapa_colunas)

    with st.expander(
        f"Possíveis outliers pelo IQR ({len(outliers)} leituras)"
    ):
        st.caption(
            "Sinalizadas as leituras abaixo de Q1 − 1,5×IQR ou acima de "
            "Q3 + 1,5×IQR. São alertas estatísticos, não confirmação de erro."
        )
        if outliers.empty:
            st.info("Nenhum registro fora dos limites foi identificado.")
            return

        colunas_relatorio = contexto + [
            "Indicador",
            "Valor da leitura",
            "Limite inferior",
            "Limite superior",
        ]
        tabela_outliers = outliers[colunas_relatorio].copy()
        colunas_numericas = [
            "Valor da leitura",
            "Limite inferior",
            "Limite superior",
        ]
        for coluna in colunas_numericas:
            tabela_outliers[coluna] = tabela_outliers[coluna].map(
                lambda valor: f"{valor:.2f}"
            )
        exibir_tabela_paginada(tabela_outliers, f"outliers_{chave}")


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

# 1. CARREGAR ESTADOS E CIDADES DISPONÍVEIS
try:
    query_cidades_com_dados = """
        SELECT DISTINCT c.nome AS cidade, e.nome AS estado
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
        ORDER BY e.nome, c.nome
    """
    df_cidades = carregar_dados(query_cidades_com_dados)
    lista_cidades = (
        (df_cidades["cidade"] + " - " + df_cidades["estado"])
        .drop_duplicates()
        .tolist()
        if not df_cidades.empty
        else []
    )

except Exception as err:
    st.error(f"Erro ao carregar cidades e estados: {err}")
    df_cidades = pd.DataFrame(columns=["cidade", "estado"])
    lista_cidades = []

cidade_estado_selecionado = st.sidebar.selectbox(
    "Selecione Cidade - Estado",
    options=lista_cidades,
    index=None,
    placeholder="Escolha uma cidade e estado",
)
if cidade_estado_selecionado:
    filtro_cidade, filtro_estado = cidade_estado_selecionado.rsplit(" - ", 1)
else:
    filtro_cidade = None
    filtro_estado = None

aba1, aba2 = st.tabs(
    ["💧 Qualidade da Água", "🌤️ Meteorologia"],
    key="relatorios_tabs",
    on_change="rerun",
)

# 2. BUSCAR APENAS AS ESTAÇÕES DA CIDADE SELECIONADA (DEPENDENCIA)
filtro_estacao = None
if not aba2.open:
    try:
        query_estacoes_com_dados = """
            SELECT DISTINCT est.nome AS estacao
            FROM estacao est
            JOIN cidade c ON est.id_cidade = c.id
            JOIN estado estado_estacao ON estado_estacao.id = est.id_estado
            WHERE est.id IN (SELECT DISTINCT id_estacao FROM qualidade_agua)
        """
        if filtro_cidade:
            cidade_sql = filtro_cidade.replace("'", "''")
            estado_sql = filtro_estado.replace("'", "''")
            query_estacoes_com_dados += (
                f" AND c.nome = '{cidade_sql}'"
                f" AND estado_estacao.nome = '{estado_sql}'"
            )

        query_estacoes_com_dados += " ORDER BY est.nome"

        df_estacoes = carregar_dados(query_estacoes_com_dados)
        nomes_estacoes = (
            df_estacoes["estacao"]
            .astype("string")
            .str.split("-", n=1)
            .str[0]
            .str.strip()
            .dropna()
            .drop_duplicates()
            .tolist()
        )
        lista_estacoes = nomes_estacoes

    except Exception as err:
        st.error(f"Erro ao carregar lista de estações: {err}")
        lista_estacoes = []

    estacao_selecionada = st.sidebar.selectbox(
        "Estação da Água (opcional)",
        options=lista_estacoes,
        index=None,
        placeholder="Não filtrar por estação",
        disabled=not lista_estacoes,
    )
    filtro_estacao = estacao_selecionada


# 3. FILTRO DE PERÍODO DE DATAS
st.sidebar.subheader("📅 Período")
data_padrao_inicio = date(2026, 9, 15)
data_padrao_fim = date(2026, 9, 26)
periodo_selecionado = st.sidebar.date_input(
    "Selecione o Intervalo",
    value=(data_padrao_inicio, data_padrao_fim),
    format="DD/MM/YYYY",
)

if isinstance(periodo_selecionado, (tuple, list)) and len(periodo_selecionado) == 2:
    data_inicio, data_fim = periodo_selecionado
else:
    data_inicio = None
    data_fim = None

filtros_obrigatorios_preenchidos = all(
    (filtro_estado, filtro_cidade, data_inicio, data_fim)
)


# --- MONTAGEM DAS QUERIES SQL DINÂMICAS ---

condicoes_agua = []
condicoes_meteo = []

# Filtros obrigatórios de Estado e Cidade
if filtro_cidade:
    cidade_sql = filtro_cidade.replace("'", "''")
    estado_sql = filtro_estado.replace("'", "''")
    condicoes_agua.append(f"c.nome = '{cidade_sql}'")
    condicoes_agua.append(f"est.nome = '{estado_sql}'")
    condicoes_meteo.append(f"c.nome = '{cidade_sql}'")
    condicoes_meteo.append(f"e.nome = '{estado_sql}'")

# Filtro por Estação (apenas para a qualidade da água)
if filtro_estacao:
    filtro_estacao_sql = filtro_estacao.replace("'", "''")
    condicoes_agua.append(
        "LTRIM(RTRIM(LEFT(e.nome, CHARINDEX('-', e.nome + '-') - 1))) = "
        f"'{filtro_estacao_sql}'"
    )

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
query_agua += " ORDER BY e.nome ASC, q.data_leitura DESC"


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


# --- CARREGAR DATAFRAMES APENAS COM FILTROS OBRIGATÓRIOS ---
df_agua = pd.DataFrame()
df_meteo = pd.DataFrame()
if filtros_obrigatorios_preenchidos:
    try:
        df_agua = carregar_dados(query_agua)
        df_meteo = carregar_dados(query_meteo)
    except Exception as err:
        st.error(f"Erro ao consultar o banco de dados: {err}")
else:
    st.info("Selecione o estado, a cidade e o intervalo de datas para gerar os relatórios.")

if not filtros_obrigatorios_preenchidos:
    df_agua, df_meteo = pd.DataFrame(), pd.DataFrame()

# --- ABA DE EXIBIÇÃO ---
with aba1:
    st.subheader("Leituras da Qualidade da Água")
    if not filtros_obrigatorios_preenchidos:
        st.info("Preencha os filtros obrigatórios para consultar a qualidade da água.")
    elif not df_agua.empty:
        # Métricas Estatísticas para Água
        temp_agua = df_agua['Temperatura'].dropna()
        ph_agua = df_agua['pH'].dropna()
        ox_agua = df_agua['Oxigênio'].dropna()
        condutividade_agua = df_agua['Condutividade'].dropna()

        # Cálculo de IQR (Q3 - Q1)
        iqr_temp = temp_agua.quantile(0.75) - temp_agua.quantile(0.25) if not temp_agua.empty else 0
        iqr_ph = ph_agua.quantile(0.75) - ph_agua.quantile(0.25) if not ph_agua.empty else 0
        iqr_ox = ox_agua.quantile(0.75) - ox_agua.quantile(0.25) if not ox_agua.empty else 0
        iqr_condutividade = condutividade_agua.quantile(0.75) - condutividade_agua.quantile(0.25) if not condutividade_agua.empty else 0
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
            st.metric("Média Condutividade", f"{condutividade_agua.mean():.2f} µS/cm")
            st.caption(f"**Mediana:** {condutividade_agua.median():.2f} µS/cm | **Desv. Padrão:** {condutividade_agua.std():.2f} | **IQR:** {iqr_condutividade:.2f}")

        exibir_relatorio_outliers(
            df_agua,
            {
                "Temperatura": "Temperatura da água",
                "pH": "pH",
                "Oxigênio": "Oxigênio dissolvido",
                "Condutividade": "Condutividade",
            },
            "agua",
            ["ID", "Estação", "Cidade", "UF", "Data/Hora"],
        )

        st.markdown("---")
        st.caption("*Temperatura: °C | Chuva: mm | Vento: Km/h | Condutividade: µS/cm | Oxigênio: mg/L")

        # Formatação para exibição na Tabela (2 casas decimais)
        df_agua_exibicao = df_agua.copy()
        colunas_float_agua = ["Temperatura", "pH", "Oxigênio", "Condutividade"]
        for col in colunas_float_agua:
            df_agua_exibicao[col] = df_agua_exibicao[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")

        exibir_tabela_paginada(df_agua_exibicao, "agua")

        metrica_agua = st.selectbox(
            "Métrica para o Gráfico (Água):",
            [
                "pH",
                "Temperatura",
                "Oxigênio",
                "Condutividade",
            ],
        )
        dados_grafico_agua = preparar_dados_grafico(df_agua, metrica_agua)
        st.line_chart(dados_grafico_agua, x="Data", y=metrica_agua)
    else:
        st.info("Nenhum registro de qualidade da água encontrado para o filtro selecionado.")

with aba2:
    st.subheader("Leituras Meteorológicas")
    if not filtros_obrigatorios_preenchidos:
        st.info("Preencha os filtros obrigatórios para consultar a meteorologia.")
    elif not df_meteo.empty:
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

        exibir_relatorio_outliers(
            df_meteo,
            {
                "Temperatura": "Temperatura do ar",
                "Umidade": "Umidade",
                "Chuva": "Chuva",
                "Vento": "Vento",
            },
            "meteorologia",
            ["ID", "Cidade", "UF", "Data/Hora"],
        )

        st.markdown("---")

        st.caption("*Temperatura: °C | Umidade: % | Chuva: mm | Vento: Km/h")
        # Formatação para exibição na Tabela (2 casas decimais)
        df_meteo_exibicao = df_meteo.copy()
        colunas_float_meteo = ["Temperatura", "Umidade", "Chuva", "Vento"]
        for col in colunas_float_meteo:
            df_meteo_exibicao[col] = df_meteo_exibicao[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "")

        exibir_tabela_paginada(df_meteo_exibicao, "meteorologia")

        metrica_meteo = st.selectbox(
            "Métrica para o Gráfico (Clima):",
            [
                "Temperatura",
                "Umidade",
                "Chuva",
                "Vento",
            ],
        )
        dados_grafico_meteo = preparar_dados_grafico(df_meteo, metrica_meteo)
        st.line_chart(dados_grafico_meteo, x="Data", y=metrica_meteo)
    else:
        st.info("Nenhum registro meteorológico encontrado para o filtro selecionado.")