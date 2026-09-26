import urllib.parse

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

params = urllib.parse.quote_plus(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=.\\SQLEXPRESS;"
    "DATABASE=EstacaoDB;"
    "Trusted_Connection=yes;"
)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

st.title("Estações meteorológicas")

with engine.connect() as connection:
    cidades = pd.read_sql("SELECT Estacao_ID, Cidade FROM Cidade", connection)

st.dataframe(cidades, hide_index=True)