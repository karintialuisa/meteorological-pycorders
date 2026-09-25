# ============================================================
# ASSUNTO: Conexão com o banco de dados SQL Server Express
# ============================================================

import urllib
import pandas as pd
from sqlalchemy import create_engine
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[3]))

from src.ingestion.localizacao.Parse_localizacao_JSON import tabela_localizacao

df_estado = tabela_localizacao()
 
# 2. Defina os parâmetros de conexão com o SQL Server Express
servidor = r'.\SQLEXPRESS'  # Ou 'localhost\SQLEXPRESS' ou o IP do seu servidor
database = 'monitoramento'
 
# String de conexão usando o driver ODBC Driver 17 for SQL Server (ou similar instalado)
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

 
# 3. Crie a engine de conexão do SQLAlchemy
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
 
# 4. Insira o DataFrame na tabela do SQL Server
df_estado.to_sql(
    name='estado',  # Nome da tabela no banco de dados
    con=engine,
    if_exists='append',     # 'append' para adicionar, 'replace' para recriar a tabela
    index=False             # Não envia o índice do DataFrame como coluna
)
 
print("Dados inseridos com sucesso!")