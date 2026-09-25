import urllib
import pandas as pd
from sqlalchemy import create_engine
 
# 1. Crie um DataFrame de exemplo
dados = {
    'Nome': ["Karintia","Jorge","Wagner","Jaclin","Anderson"],
    'Idade': [60, 32, 45, 59, 78],
    'Salario': [4500.00, 6200.50, 3100.00, 7200.00, 5100.00]
}
df = pd.DataFrame(dados)
 
# 2. Defina os parâmetros de conexão com o SQL Server Express
servidor = r'.\SQLEXPRESS'  # Ou 'localhost\SQLEXPRESS' ou o IP do seu servidor
database = 'TesteDB'
 
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
df.to_sql(
    name='Cliente',  # Nome da tabela no banco de dados
    con=engine,
    if_exists='append',     # 'append' para adicionar, 'replace' para recriar a tabela
    index=False             # Não envia o índice do DataFrame como coluna
)
 
print("Dados inseridos com sucesso!")