import urllib
import pandas as pd
from sqlalchemy import create_engine
from Parse_JSON import tabela_cidade, tabela_estado, tabela_leituras_agua, tabela_leituras_meteorologicas
 
# 2. Defina os parâmetros de conexão com o SQL Server Express
servidor = r'.\SQLEXPRESS'  # Ou 'localhost\SQLEXPRESS' ou o IP do seu servidor
database = 'EstacaoDB'
 
# String de conexão usando o driver ODBC Driver 17 for SQL Server (ou similar instalado)
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={servidor};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

 
# 3. Crie a engine de conexão do SQLAlchemy
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


tabelas = {
    'Cidade': tabela_cidade(),
    'Estado': tabela_estado(),
    'Leituras_Agua': tabela_leituras_agua(),
    'Leituras_Meteorologicas': tabela_leituras_meteorologicas(),    

} 
# 4. Insira o DataFrame na tabela do SQL Server
for nome_tabela, df in tabelas.items():
    df.to_sql(
        name=nome_tabela,  # Nome da tabela no banco de dados
        con=engine,
        if_exists='replace',     # 'append' para adicionar, 'replace' para recriar a tabela
        index=False             # Não envia o índice do DataFrame como coluna
    )
 
print("Dados inseridos com sucesso!")