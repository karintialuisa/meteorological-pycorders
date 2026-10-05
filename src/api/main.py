from fastapi import FastAPI, Query
from pathlib import Path
import sys
import json
import pandas as pd
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import get_path

app = FastAPI(
    title="API de Leituras Ambientais e Meteorológicas",
    version="1.0.0",
    description="API REST para consulta de dados de qualidade da água e meteorologia."
)

def carregar_e_normalizar(caminho: Path, chave_lista: str) -> pd.DataFrame:
    if not caminho.exists():
        return pd.DataFrame()
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = json.load(f)
        if isinstance(conteudo, list):
            return pd.json_normalize(conteudo, record_path=[chave_lista], errors="ignore")
        return pd.json_normalize([conteudo], record_path=[chave_lista], errors="ignore")
    except Exception:
        return pd.DataFrame()


@app.get("/")
def home():
    return {"status": "API Online", "documentacao": "/docs"}


@app.get("/cidades", response_model=List[str])
def listar_cidades():
    """Retorna a lista de todas as cidades disponíveis nos dados."""
    df_agua = carregar_e_normalizar(
        get_path("INGESTION_LEITURA_AMBIENTAL"), "leituras_ambientais"
    )
    df_meteo = carregar_e_normalizar(
        get_path("INGESTION_LEITURA_METEOROLOGICA"),
        "leituras_meteorologicas",
    )

    cidades_agua = set(df_agua["cidade"].dropna().unique()) if "cidade" in df_agua.columns else set()
    cidades_meteo = set(df_meteo["cidade"].dropna().unique()) if "cidade" in df_meteo.columns else set()

    return sorted(list(cidades_agua.union(cidades_meteo)))


@app.get("/leituras/ambientais")
def obter_leituras_ambientais(cidade: Optional[str] = Query(None, description="Filtrar por nome da cidade")):
    """Retorna as leituras de qualidade da água/ambientais."""
    df = carregar_e_normalizar(
        get_path("INGESTION_LEITURA_AMBIENTAL"), "leituras_ambientais"
    )
    if df.empty:
        return []
    if cidade and "cidade" in df.columns:
        df = df[df["cidade"].str.lower() == cidade.lower()]
    return df.to_dict(orient="records")


@app.get("/leituras/meteorologicas")
def obter_leituras_meteorologicas(cidade: Optional[str] = Query(None, description="Filtrar por nome da cidade")):
    """Retorna as leituras meteorológicas."""
    df = carregar_e_normalizar(
        get_path("INGESTION_LEITURA_METEOROLOGICA"),
        "leituras_meteorologicas",
    )
    if df.empty:
        return []
    if cidade and "cidade" in df.columns:
        df = df[df["cidade"].str.lower() == cidade.lower()]
    return df.to_dict(orient="records")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)