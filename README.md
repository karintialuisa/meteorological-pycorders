# PyCordersMeteorological

Pipeline de Monitoramento e Análise de Dados Ambientais

Projeto Prático Integrador desenvolvido pela equipe PyCorders para capturar, tratar, persistir e analisar dados de estações meteorológicas e de qualidade da água.

## Sobre o projeto

A aplicação trata arquivos JSON de leituras ambientais, meteorológicas e de localização, persiste os dados em SQL Server, calcula estatísticas e disponibiliza consultas por API REST e dashboard. O fluxo principal de carga é executado por scripts Python independentes, orquestrados por um menu de terminal.

## Funcionalidades

O pipeline contempla:

- Leitura e normalização de JSONs de estados, municípios, estações e leituras.
- Carga incremental de estados, cidades, estações, qualidade da água e meteorologia.
- Resolução e validação de chaves entre os arquivos JSON e o SQL Server.
- Relatórios interativos por cidade e estação, com média, mediana, desvio padrão, IQR e contagem de outliers.
- API FastAPI para listar cidades e consultar leituras carregadas dos JSONs.
- Dashboard Streamlit para consultar no SQL Server e visualizar indicadores, tabelas e séries temporais.
- Registro de eventos no console e em `logs/execucao_relatorio.log`.

## Tecnologias

- Python 3.10 ou superior
- SQL Server
- SQL Server e Microsoft ODBC Driver 17 for SQL Server
- pandas, SQLAlchemy, pyodbc e python-dotenv
- FastAPI e Uvicorn (API)
- Streamlit (dashboard)
- tabulate (relatórios no terminal) e pytest (testes)

## Arquitetura do projeto

```text
meteorological-pycorders/
├── src/
│   ├── config/
│   │   ├── .env                     # Configuração local, não versionar
│   │   ├── requirements.txt
│   │   └── settings.py              # Ambiente, logs, caminhos JSON e conexão SQL
│   ├── analytics/
│   │   └── Relatorios_estatisticos.py
│   ├── api/
│   │   └── main.py                  # API FastAPI sobre os JSONs
│   ├── database/
│   │   ├── ddl/
│   │   │   ├── create-database.sql
│   │   │   ├── create-tables.sql
│   │   │   ├── delete-data-table.sql
│   │   │   └── schema.sql
│   │   ├── dml/
│   │   │   ├── Insert_Localizacao.py
│   │   │   ├── Insert_Leituras_ambiental.py
│   │   │   ├── Insert_Leituras_Meteorologica.py
│   │   │   └── seed.sql
│   │   └── dql/
│   │       └── consultas-essenciais.sql
│   ├── ingestion/
│   │   ├── leituras/
│   │   │   ├── Parse_LeituraAmbiental.py
│   │   │   ├── Parse_LeituraMetereologica.py
│   │   │   ├── leituras_ambientais.json
│   │   │   └── leituras_meteorologicas.json
│   │   └── localizacao/
│   │       ├── Parse_localizacao_JSON.py
│   │       ├── estacoes.json
│   │       ├── estado.json
│   │       └── municipio.json
│   ├── dashboard.py                 # Dashboard Streamlit
│   ├── main.py                      # Menu e orquestração das cargas
│   └── __init__.py
├── .gitignore
├── README.md
├── tests/
│   └── test_database_insertions.py  # Testes de inserção com SQLite em memória
└── TESTE.PY                         # Script auxiliar de demonstração
```

## Responsabilidades dos módulos

- `src/ingestion/leituras`: transforma os JSONs ambientais e meteorológicos em DataFrames.
- `src/ingestion/localizacao`: normaliza estados, municípios e estações.
- `src/database/ddl`: contém `create-database.sql`, `create-tables.sql`, `schema.sql` e `delete-data-table.sql`.
- `src/database/dml`: carrega localização e leituras; `seed.sql` contém dados SQL auxiliares.
- `src/database/dql`: reúne consultas de inspeção e análise.
- `src/analytics`: gera relatórios estatísticos interativos a partir dos JSONs.
- `src/api`: expõe cidades e leituras dos arquivos JSON pelos endpoints HTTP.
- `src/dashboard.py`: apresenta dados persistidos no SQL Server em tabelas, métricas e gráficos.
- `src/config/settings.py`: concentra leitura do `.env`, caminhos JSON, conexão SQL Server e configuração de logs.
- `tests/test_database_insertions.py`: exercita inserções de localização e leituras sem conectar ao SQL Server.

## Pré-requisitos

- Python 3.10 ou superior instalado.
- Git instalado.
- Instância acessível do SQL Server.
- Driver ODBC compatível com o SQL Server.
- Credenciais para a fonte de dados, quando exigidas.

## Instalação

1. Clone o repositório:

   ```bash
   git clone <URL_DO_REPOSITORIO>
   cd meteorological-pycorders
   ```

2. Crie e ative um ambiente virtual:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

   No Linux ou macOS, use `source .venv/bin/activate`.

3. Instale as dependências:

   ```bash
   pip install -r src/config/requirements.txt
   ```

## Configuração

Configure `src/config/.env` com as variáveis abaixo. Esse arquivo é local e ignorado pelo Git; não compartilhe nem versione credenciais:

   ```env
   LOGS_DIR=logs
   DB_HOST=.\SQLEXPRESS
   DB_PORT=1433
   DB_NAME=monitoramento
   DB_TRUSTED_CONNECTION=yes
   INSERT_LOCALIZACAO=src/database/dml/Insert_Localizacao.py
   INSERT_LEITURA_AMBIENTAL=src/database/dml/Insert_Leituras_ambiental.py
   INSERT_LEITURA_METEOROLOGICA=src/database/dml/Insert_Leituras_Meteorologica.py
   RELATORIO_ESTATISTICO=src/analytics/Relatorios_estatisticos.py
   INGESTION_LEITURA_AMBIENTAL=src/ingestion/leituras/leituras_ambientais.json
   INGESTION_LEITURA_METEOROLOGICA=src/ingestion/leituras/leituras_meteorologicas.json
   INGESTION_LOCALIZACAO_ESTADOS=src/ingestion/localizacao/estado.json
   INGESTION_LOCALIZACAO_MUNICIPIOS=src/ingestion/localizacao/municipio.json
   INGESTION_LOCALIZACAO_ESTACOES=src/ingestion/localizacao/estacoes.json
   ```

## Execução

Prepare o banco no SQL Server executando `src/database/ddl/create-database.sql` e, em seguida, `src/database/ddl/create-tables.sql`. Atenção: o script de criação das tabelas remove tabelas existentes antes de recriá-las.

Para abrir o menu e executar as cargas ou relatórios:

   ```bash
   python -m src.main
   ```

No menu, a opção de carga executa as inserções de localização, leituras ambientais e leituras meteorológicas. A opção de relatório permite selecionar cidade e estação. A carga depende de uma conexão SQL Server configurada em `src/config/.env`.

Para iniciar a API que lê os JSONs (não consulta o banco):

```bash
uvicorn src.api.main:app --reload
```

A documentação interativa da API ficará disponível em `http://127.0.0.1:8000/docs`. Os endpoints incluem `/cidades`, `/leituras/ambientais` e `/leituras/meteorologicas`.

Para iniciar o dashboard Streamlit, em outro terminal:

```bash
streamlit run src/dashboard.py
```

O dashboard consulta o SQL Server usando servidor, porta, banco e autenticação definidos em `src/config/.env`.

Os logs são gravados em `logs/execucao_relatorio.log`. `LOGS_DIR` pode apontar para outro caminho; caminhos relativos são resolvidos a partir da raiz do projeto. O arquivo de log é gerado localmente e ignorado pelo Git. O único parâmetro de conexão fixo no código é `ODBC Driver 17 for SQL Server`; servidor, porta, banco e autenticação vêm do `.env`.

## Fluxo de processamento

1. Os parsers leem os JSONs versionados em `src/ingestion` e normalizam os dados com pandas.
2. A carga de localização insere estados, cidades e estações ainda não cadastrados.
3. As cargas ambientais e meteorológicas associam leituras às entidades do banco e inserem os registros.
4. O relatório estatístico lê os arquivos de leituras, permite filtrar cidade/estação e calcula estatísticas por variável.
5. A API consulta os JSONs diretamente; o dashboard consulta as tabelas SQL Server.

## Modelo de dados simplificado

| Tabela                  | Finalidade                                      |
| ----------------------- | ----------------------------------------------- |
| `estado`                | Unidades federativas e código IBGE              |
| `cidade`                | Municípios vinculados a um estado               |
| `estacao`               | Estações vinculadas a cidade e estado           |
| `qualidade_agua`        | Leituras de água vinculadas à estação           |
| `leitura_meteorologica` | Leituras meteorológicas vinculadas à cidade     |

## Análises estatísticas

Para cada parâmetro ambiental, o sistema calcula média, mediana, desvio padrão e intervalo interquartil. Os valores abaixo de `Q1 − 1,5 × IQR` ou acima de `Q3 + 1,5 × IQR` são classificados como possíveis outliers.

## Testes

Os testes usam dados manuais e SQLite em memória para exercitar `estado`, `cidade`, `estacao`, `qualidade_agua` e `leitura_meteorologica`, sem alterar o SQL Server. Execute-os com:

```bash
python -m pytest tests -v
```

## Segurança e governança

- `src/config/.env` contém configurações locais e não deve ser versionado.
- O arquivo `logs/execucao_relatorio.log` é local e está coberto pelo `.gitignore`.
- Revise mensagens e dados registrados antes de incluir logs em chamados ou compartilhá-los.
- O dashboard e os scripts de carga compartilham a conexão definida em `src/config/.env`.

## Equipe

| Integrante | Responsabilidade principal |
| ---------- | -------------------------- |
| Jaclin     | Coordenação, integração, acompanhamento dos marcos e Pull Request final |
| Jorge      | Ingestão, parsing, validação e tratamento dos dados |
| Karíntia   | Modelagem do banco, scripts DDL/DML e consultas SQL |
| Wagner     | Análise estatística, detecção de outliers e testes unitários |
| Anderson   | Segurança, documentação e apresentação |

Cada integrante trabalha em branch própria, mantém commits objetivos e participa da revisão cruzada antes da integração.

## Fluxo Git e contribuição

1. Atualize a branch principal:

   ```bash
   git checkout main
   git pull
   ```

2. Crie uma branch de funcionalidade:

   ```bash
   git checkout -b feature/nome-da-funcionalidade
   ```

3. Implemente e teste a alteração.
4. Registre um commit objetivo:

   ```bash
   git add .
   git commit -m "feat: descreve a alteração"
   ```

5. Envie a branch e abra uma Pull Request:

   ```bash
   git push -u origin feature/nome-da-funcionalidade
   ```

6. Solicite revisão e faça o merge somente após a validação.

## Critérios de conclusão

- Estrutura do banco criada e cargas executadas em SQL Server configurado.
- Relatórios, API e dashboard iniciados conforme as instruções deste README.
- Configurações locais e logs mantidos fora do controle de versão.

## Licença

Este projeto foi desenvolvido para fins acadêmicos. Caso uma licença seja definida, inclua o arquivo correspondente no repositório e atualize esta seção.
