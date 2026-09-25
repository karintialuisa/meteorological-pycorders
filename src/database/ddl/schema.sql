-- Estruturas DDL iniciais do projeto PyCordersMeteorological.
import urllib
import pandas as pd
from Parse_JSON import df_cidade as df

#2. Defina os parametros de conexão com o SQL Server Express
servidor = '\SQLEXPRESS'  # Nome do servidor SQL Server Express
database = 'EstacaoDB'

#String de conexão 
params = urllib.parse.quote_plus
    (f'DRIVER={{SQL Server}};
    f SERVER={servidor};
    DATABASE={database};
    Trusted_Connection=yes;'
    )