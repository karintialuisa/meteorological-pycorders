# PyCordersMeteorological

Pipeline de Monitoramento e Análise de Dados Ambientais

Projeto Prático Integrador desenvolvido pela equipe PyCorders para capturar, tratar, persistir e analisar dados de estações meteorológicas e de qualidade da água.

## Sobre o projeto

A aplicação trata arquivos JSON de leituras ambientais, meteorológicas e de localização, persiste os dados em SQL Server, calcula estatísticas e disponibiliza consultas por API REST e dashboard. O fluxo principal de carga é executado por scripts Python independentes, orquestrados por um menu de terminal.

## Funcionalidades

O pipeline contempla:

- Leitura e normalização de JSONs de estados, municípios, estações e leituras.
- Coleta dos dados meteorológicos de temperatura do ar da API Agritempo, com bearer no `.env`, limite de requisições e acumulação dos resultados no mesmo JSON.
- Carga incremental de estados, cidades, estações, qualidade da água e meteorologia.
- Resolução e validação de chaves entre os arquivos JSON e o SQL Server.
- Modelo relacional de leituras com `parametros`, `leituras` e `leitura_itens`, cujas cargas na camada DML validam campos, resolvem chaves por código e são idempotentes.
- Proteção de dados pessoais de operadores: CPF em HMAC-SHA-256 e nome completo cifrado com Fernet, com catálogo LGPD. A descriptografia exige autorização explícita do chamador e registra auditoria sem conteúdo pessoal ou chaves.
- Relatórios interativos por cidade e estação, com média, mediana, desvio padrão, variância amostral, IQR e contagem de outliers por parâmetro.
- API FastAPI para listar cidades e consultar leituras carregadas dos JSONs.
- Dashboard Streamlit para consultar no SQL Server e visualizar indicadores, tabelas e séries temporais.
- Logs separados para tratamento, inserção no banco e relatórios/cálculos, além do log de execução do menu.

## Tecnologias

- Python 3.10 ou superior
- SQL Server
- SQL Server e Microsoft ODBC Driver 17 for SQL Server
- pandas, PyArrow, SQLAlchemy, pyodbc, python-dotenv e cryptography
- FastAPI e Uvicorn (API)
- Streamlit (dashboard)
- tabulate (relatórios no terminal) e pytest (testes)

## Arquitetura do projeto

```text
meteorological-pycorders/
├── Get_dados.py                    # Coleta meteorologia da API Agritempo
├── src/
│   ├── config/
│   │   ├── .env                     # Configuração local, não versionar
│   │   ├── .env.example             # Modelo sem segredos
│   │   ├── requirements.txt
│   │   └── settings.py              # Ambiente, logs, caminhos JSON e conexão SQL
│   ├── analytics/
│   │   └── Relatorios_estatisticos.py
│   ├── api/
│   │   └── main.py                  # API FastAPI sobre os JSONs
│   ├── security/
│   │   └── pii.py                   # CPF, HMAC-SHA-256 e criptografia Fernet
│   ├── database/
│   │   ├── ddl/
│   │   │   ├── create-database.sql
│   │   │   └── create-tables.sql
│   │   ├── dml/
│   │   │   ├── delete-data-table.sql
│   │   │   ├── etl_lock.py              # Lock cooperativo sp_getapplock
│   │   │   ├── Insert_Catalogo_LGPD.py
│   │   │   ├── Insert_Localizacao.py
│   │   │   ├── Insert_Leituras_ambiental.py
│   │   │   ├── Insert_Leituras_Meteorologica.py
│   │   │   ├── Insert_Leituras.py       # Cabeçalho relacional de leituras
│   │   │   ├── Insert_Leitura_Itens.py  # Itens: leitura x parâmetro
│   │   │   ├── Insert_Operadores.py
│   │   │   ├── Insert_Parametros.py
│   │   │   └── seed.sql
│   │   └── dql/
│   │       └── consultas-essenciais.sql
│   ├── ingestion/
│   │   ├── api_ingestion.py         # Consumo REST e preservação das respostas brutas
│   │   ├── leituras/
│   │   │   ├── Parse_LeituraAmbiental.py
│   │   │   ├── Parse_LeituraMetereologica.py
│   │   │   ├── Persistir_Silver.py
│   │   │   ├── leituras_ambientais.json
│   │   │   └── leituras_meteorologicas.json
│   │   └── localizacao/
│   │       ├── Parse_localizacao_JSON.py
│   │       ├── estacoes.json
│   │       ├── estado.json
│   │       ├── municipio.json
│   │       └── operadores.json
│   ├── dashboard.py                 # Dashboard Streamlit
│   ├── main.py                      # Menu e orquestração das cargas
│   └── __init__.py
├── .gitignore
├── features.csv                     # Inventário de requisitos, status e evidências
├── projeto_final.pdf                # Enunciado do projeto
├── README.md
└── tests/                           # Testes SQLite e testes opt-in para SQL Server
    ├── conftest.py
    ├── test_analytics.py
    ├── test_api.py
    ├── test_api_ingestion.py
    ├── test_config_and_main.py
    ├── test_database_loading.py
    ├── test_get_dados.py
    ├── test_lgpd.py
    ├── test_parsers.py
    ├── test_silver.py
    ├── test_sqlserver_lgpd.py           # Opt-in
    ├── test_sqlserver_relational_integrity.py  # Opt-in
    └── test_sqlserver_uniqueness.py     # Opt-in
```

## Responsabilidades dos módulos

- `src/ingestion/leituras`: guarda os JSONs de entrada e transforma leituras ambientais e meteorológicas em DataFrames; respostas REST brutas são salvas aqui por padrão.
- `src/ingestion/localizacao`: normaliza estados, municípios e estações.
- `src/database/ddl`: contém `create-database.sql` e `create-tables.sql`.
- `src/database/dml`: valida, resolve chaves e carrega localização, leituras (tabelas atuais), parâmetros, cabeçalhos e itens de leitura, operadores e catálogo LGPD de forma idempotente; `etl_lock.py` serializa cargas no SQL Server; `delete-data-table.sql` e `seed.sql` são auxiliares.
- `src/security`: normaliza e valida CPF, aplica HMAC-SHA-256 e a criptografia Fernet do nome.
- `src/database/dql`: reúne consultas de inspeção e análise.
- `src/analytics`: consulta leituras relacionais e gera relatórios estatísticos por parâmetro e estação.
- `src/api`: expõe cidades e leituras dos arquivos JSON pelos endpoints HTTP.
- `src/dashboard.py`: apresenta dados persistidos no SQL Server em tabelas, métricas e gráficos.
- `src/config/settings.py`: concentra leitura do `.env`, caminhos JSON, conexão SQL Server e configuração dos logs por categoria.
- `tests`: testes SQLite por padrão; os módulos `test_sqlserver_*` são opt-in e só rodam contra uma instância SQL Server descartável (ver Testes).

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
   SILVER_DIR=data_lake/silver
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
   AGRITEMPO_BEARER_TOKEN=adicione_o_token_fornecido_pela_fonte
   API_REQUESTS_PER_MINUTE=30
   API_RAW_DIR=src/ingestion/leituras
   HMAC_SECRET_KEY=gere_um_segredo_aleatorio_longo
   ENCRYPTION_KEY=gere_uma_chave_fernet
   ```

`src/config/.env.example` é um modelo sem segredos. Copie-o para `src/config/.env` e substitua os marcadores antes de executar cargas que protegem dados de operadores. A opção 5 do menu executa os cadastros de parâmetros, catálogo LGPD e operadores; para operadores, as chaves HMAC e Fernet devem ser reais. O loader recusa valores que começam com `replace-with`.

`Get_dados.py` usa a API Agritempo da Embrapa. O bearer deve ficar somente em `src/config/.env`; não o coloque no código nem o versione. O escopo atual dessa fonte é meteorológico, com os dados de temperatura do ar disponíveis no retorno climático. O contrato em `src/ingestion/api_ingestion.py` valida o envelope, os dados da estação e cada observação diária, exigindo data, ID e temperaturas mínima/máxima numéricas, finitas e coerentes entre si. Estações sem série climática são aceitas.

Para consumo analítico, a projeção usa somente `temperatura_minima` e `temperatura_maxima` (incluindo os indicadores de estimativa). `temperatura_media` e as demais variáveis que venham da API permanecem no JSON bruto como resposta original, mas não entram nessa projeção; a média será calculada posteriormente nos relatórios.

Bronze, Silver e Gold são nomes de etapas, não uma exigência de criar pastas com esses nomes. A coleta da Agritempo acumula os resultados no mesmo `dados_agritempo.json`, dentro do diretório de `API_RAW_DIR` (por padrão, `src/ingestion/leituras`). Novas execuções preservam os resultados anteriores e acrescentam os novos; não é criada uma pasta `data/bronze`.

## Execução

Prepare o banco em uma instância SQL Server dedicada. Execute `src/database/ddl/create-database.sql` apenas quando o banco `monitoramento` ainda não existir; o comando `CREATE DATABASE` falha se o nome já estiver em uso. Em seguida, execute `src/database/ddl/create-tables.sql` pelo SSMS ou `sqlcmd`, pois o arquivo contém separadores `GO`. O script cria tabelas ausentes, mas não remove nem recria tabelas existentes e não migra constraints para um schema já criado. Em um banco criado com uma versão anterior do script, confira o catálogo antes das cargas, pois colunas acrescentadas depois à definição (como `qualidade_agua.turbidez`) não chegam a tabelas já criadas.

Para abrir o menu e executar as cargas ou relatórios:

   ```bash
   python -m src.main
   ```

No menu, a opção 1 executa as inserções de localização, leituras ambientais e leituras meteorológicas. A opção 2 abre relatórios; a opção 5 executa os cadastros de parâmetros, catálogo LGPD e operadores, nessa ordem, interrompendo ao primeiro erro. A carga depende de uma conexão SQL Server configurada em `src/config/.env` e de estações previamente cadastradas para os operadores.

A opção `4` executa `Get_dados.py`: consulta estações e dados climáticos, aplica o limite `API_REQUESTS_PER_MINUTE` e acrescenta os resultados ao JSON cumulativo. Também é possível executar com `python Get_dados.py`. O módulo `src/ingestion/api_ingestion.py` permanece como conector genérico separado para endpoints que já atendam aos contratos ambiental ou meteorológico definidos nele; ele não é o coletor da Agritempo.

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

`LOGS_DIR` define o diretório dos logs; caminhos relativos são resolvidos a partir da raiz do projeto. Os arquivos são separados por tipo de saída:

- `logs/tratamento_dados.log`: ingestão REST e execução isolada dos parsers/tratamentos.
- `logs/insercao_dados.log`: cargas e inserções no banco, incluindo eventos de validação ocorridos durante a carga.
- `logs/relatorios_calculos.log`: consultas, cálculos e relatórios estatísticos.
- `logs/execucao_relatorio.log`: menu e orquestração geral.

Os logs são gerados localmente e ignorados pelo Git. O único parâmetro de conexão fixo no código é `ODBC Driver 17 for SQL Server`; servidor, porta, banco e autenticação vêm do `.env`.

## Fluxo de processamento

1. Os parsers leem os JSONs versionados em `src/ingestion` e normalizam os dados com pandas.
2. A carga de localização insere estados, cidades e estações ainda não cadastrados.
3. As cargas ambientais e meteorológicas associam leituras às entidades do banco e inserem os registros.
4. O relatório estatístico lê os arquivos de leituras, permite filtrar cidade/estação e calcula estatísticas por variável.
5. A API consulta os JSONs diretamente; o dashboard consulta as tabelas SQL Server.

## Camada Silver

As cargas de qualidade da água e meteorologia persistem os DataFrames limpos e enriquecidos em Parquet usando PyArrow e compressão Snappy. `SILVER_DIR` é opcional: por padrão, os arquivos são gravados em `data_lake/silver`, sob a raiz do projeto. Um caminho relativo configurado em `SILVER_DIR` também é resolvido a partir da raiz; caminhos absolutos são usados diretamente.

O layout particiona por dia UTC e dataset:

```text
data_lake/silver/
├── qualidade_agua/data_leitura=AAAA-MM-DD/part-00000.parquet
├── leitura_meteorologica/data_leitura=AAAA-MM-DD/part-00000.parquet
└── _audit/<dataset>/<id-da-execucao>.json
```

O writer mescla novas linhas com a partição diária existente, remove retransmissões pela chave natural e substitui o Parquet por meio de arquivo temporário e troca atômica. As chaves são `id_leitura_origem` para água e `id_estacao + data_leitura` normalizada em UTC para meteorologia. O índice do DataFrame não é gravado.

As regras verificadas na Silver são:

- **Completude:** campos obrigatórios nulos/vazios são rejeitados.
- **Unicidade:** duplicatas no lote ou já persistidas são contabilizadas e não são regravadas.
- **Acurácia:** temperatura do ar fora de -50 °C a +60 °C e temperatura da água fora de 0 °C a +50 °C são rejeitadas; os limites são inclusivos.
- **Validade:** pH fora de 0–14, oxigênio/condutividade negativos, umidade fora de 0–100 e chuva/vento negativos são rejeitados; valores numéricos não finitos também são inválidos.
- **Tempestividade:** timestamps são convertidos para UTC e as linhas da partição são ordenadas cronologicamente.
- **Consistência:** as chaves resolvidas de estação e cidade precisam estar preenchidas; as cargas também resolvem as FKs antes da persistência.

Cada execução cria um manifesto JSON em `_audit/<dataset>/` com contagens avaliadas, aprovadas e rejeitadas por dimensão, formato/codec e partições escritas. O manifesto contém apenas contagens e metadados técnicos; não grava valores das leituras, CPF, nome completo ou segredos.

O Parquet da Silver e o SQL Server não compartilham uma transação distribuída. O writer Silver roda antes do `to_sql`; se a gravação SQL falhar depois, a partição Silver pode já estar persistida. Reexecuções são idempotentes pelas chaves naturais. O lock `sp_getapplock` protege apenas writers SQL Server que usem o mesmo recurso; não impede inserts feitos por aplicações externas que ignorem o lock.

## Regras de qualidade e pendências

Os parsers rejeitam leituras sem identidade, estação, data ou medições obrigatórias, validam temperaturas, pH, umidade, precipitação e vento, e normalizam datas para UTC. As faixas inclusivas de temperatura são -50 °C a +60 °C para o ar e 0 °C a +50 °C para a água; parser e Silver rejeitam valores fora delas. As dimensões de consistência também não cobrem todas as possíveis contradições entre leituras de fontes diferentes.

## Testes

Os testes SQLite exercitam parsers, loaders, constraints, configuração e writer Parquet com dados temporários. O fixture configura `SILVER_DIR` sob o diretório temporário do pytest para não produzir arquivos na raiz do repositório. Execute a suíte com o interpretador do ambiente virtual, onde `cryptography` está instalado:

```bash
.venv\Scripts\python -m pytest tests -v
```

Com o Python global, a coleta de `tests/test_lgpd.py` falha se `cryptography` não estiver instalado nele.

O teste de integração LGPD com SQL Server exige um banco descartável vazio, separado de `monitoramento`. As configurações são carregadas automaticamente de `src/config/.env.test`, independentemente do diretório de execução. Esse arquivo local não é versionado; para configurar outra máquina, copie `src/config/.env.test.example` para `src/config/.env.test` e ajuste a conexão. O modelo usa a instância local `localhost\SQLEXPRESS`, autenticação Windows e o banco `monitoramento_lgpd_test`, que deve existir previamente.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest '.\tests\test_sqlserver_lgpd.py' -v
```

Não é necessário exportar variáveis a cada execução. `RUN_SQLSERVER_LGPD_TESTS=1` habilita a integração e `SQLSERVER_LGPD_TEST_URL` define a URL SQLAlchemy. Variáveis já definidas no processo têm prioridade; use `RUN_SQLSERVER_LGPD_TESTS=0` para desabilitar. Sem ativação, apenas a integração é ignorada; os testes da configuração continuam executando. Ativação sem URL gera erro explícito, não `SKIPPED`.

Nunca aponte essa configuração para `monitoramento`. O teste exige um nome com sufixo `_test`, `_tests`, `_disposable` ou `_scratch`, recusa tabelas preexistentes em `dbo`, aplica o DDL oficial (sem o `USE monitoramento`) e remove suas tabelas ao final. O banco permanece disponível e vazio para a próxima execução. Não execute duas integrações simultaneamente na mesma base. A configuração normal da aplicação em `src/config/.env` não é usada como fallback.

### Integridade relacional no SQL Server

`tests/test_sqlserver_relational_integrity.py` valida PKs, FKs, nulabilidade, CHECKs, cascatas e o replay idempotente de `inserir_parametros`, `inserir_leituras` e `inserir_leitura_itens` contra o DDL real. Ele exige uma instância SQL Server descartável com `create-tables.sql` já aplicado e o banco `monitoramento` vazio. Defina, apenas para a execução:

- `RUN_SQLSERVER_UNIQUENESS_TESTS=1`
- `SQLSERVER_UNIQUENESS_TEST_DISPOSABLE=1`, confirmando que a instância é descartável
- `SQLSERVER_UNIQUENESS_TEST_URL`, com a URL SQLAlchemy da instância
- `SQLSERVER_UNIQUENESS_TEST_EXPECTED_SERVER` (opcional), para conferir o nome retornado por `SERVERPROPERTY('ServerName')`

```bash
.venv\Scripts\python -m pytest tests/test_sqlserver_relational_integrity.py -v -s
```

Os testes de constraints usam transações revertidas ao final. Os testes de replay confirmam dados sintéticos (os loaders controlam as próprias transações) e os removem em `finally`, falhando se restar alguma linha. Nunca execute contra um banco com dados reais. O mesmo conjunto de variáveis habilita `tests/test_sqlserver_uniqueness.py`.

## Modelo de dados simplificado

| Tabela                  | Finalidade                                      |
| ----------------------- | ----------------------------------------------- |
| `estado`                | Unidades federativas e código IBGE              |
| `cidade`                | Municípios vinculados a um estado               |
| `estacao`               | Estações vinculadas a cidade e estado           |
| `qualidade_agua`        | Leituras de água vinculadas à estação           |
| `leitura_meteorologica` | Leituras meteorológicas vinculadas à cidade     |
| `operadores`            | Operadores de campo com `cpf_hash` (HMAC-SHA-256), `nome_completo_cifrado` (Fernet) e estação |
| `catalogo_dados`        | Inventário LGPD dos campos pessoais, com finalidade, proteção e política de acesso |
| `parametros`            | Domínio dos parâmetros medidos: código único, nome e unidade |
| `leituras`              | Cabeçalho da leitura: origem, chave de origem, estação, operador opcional e data/hora |
| `leitura_itens`         | Valor medido por parâmetro em cada leitura; PK composta `(id_leitura, id_parametro)` |

`leituras` e `leitura_itens` seguem o modelo previsto no projeto: cada item guarda exatamente um valor, numérico ou textual, e a exclusão de uma leitura remove seus itens. As cargas de `qualidade_agua` e `leitura_meteorologica` ainda gravam somente nas tabelas atuais; a integração com `leituras` e `leitura_itens`, com backfill idempotente, está pendente.

## Análises estatísticas

Para cada parâmetro ambiental, o sistema calcula média, mediana, desvio padrão e intervalo interquartil. Os valores abaixo de `Q1 − 1,5 × IQR` ou acima de `Q3 + 1,5 × IQR` são classificados como possíveis outliers.

## Segurança e governança

- `src/config/.env` contém configurações locais e não deve ser versionado.
- As tabelas `operadores` e `catalogo_dados` agora são criadas por `src/database/ddl/create-tables.sql`, junto ao esquema relacional. O script usa `IF OBJECT_ID` para preservar tabelas existentes; execute depois `python -m src.database.dml.Insert_Catalogo_LGPD` para registrar os metadados. Ele cria tabelas ausentes, mas não apaga, recria nem migra tabelas existentes.
- A tabela `operadores` guarda apenas `cpf_hash` (HMAC-SHA-256) e `nome_completo_cifrado` (Fernet). O módulo `src/security/pii.py` oferece as funções de proteção; `inserir_operadores()` recebe registros de uma fonte aprovada com os campos `cpf` e `nome_completo`. Nenhum cadastro fictício ou arquivo com valores pessoais é fornecido.
- Defina `HMAC_SECRET_KEY` e `ENCRYPTION_KEY` no ambiente do processo autorizado. Gere uma chave Fernet com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` e um segredo HMAC forte com `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Não grave chaves no banco, no código, em logs ou no controle de versão. O arquivo `src/config/.env.example` ainda não existe; use a lista de variáveis da seção Configuração como modelo.
- HMAC permite comparar CPFs normalizados sem armazená-los, mas não é anonimização jurídica. A troca da chave HMAC muda todos os identificadores; como o CPF original não é persistido, planeje a rotação e a reidentificação com a fonte autorizada antes de trocar a chave. A rotação da chave Fernet também requer recriptografia ou uma estratégia de chaves versionadas.
- A descriptografia exige principal técnico e callback de autorização e audita sucesso/negação sem nome, ciphertext ou chave. Não há provedor de identidade de usuário final; a aplicação chamadora deve vincular a autorização a uma identidade autenticada. Restrinja a chave e o processo/conta que a lê.
- Atenção: `src/config/.env` já está versionado neste repositório. A regra no `.gitignore` não remove arquivos já rastreados. Antes de armazenar chaves reais, remova esse arquivo do índice do Git e revise/rotacione quaisquer segredos que tenham sido publicados.
- O arquivo `logs/execucao_relatorio.log` é local e está coberto pelo `.gitignore`.
- Configure e proteja `SILVER_DIR` conforme a política de retenção do Data Lake; os arquivos Parquet contêm dados ambientais e não devem receber campos pessoais de operadores.
- Revise mensagens e dados registrados antes de incluir logs em chamados ou compartilhá-los.
- O dashboard e os scripts de carga compartilham a conexão definida em `src/config/.env`.

### Catálogo de dados pessoais — ID 32

`dbo.catalogo_dados` inventaria os campos de `dbo.operadores`, sem guardar valores pessoais:

| Campo lógico | Coluna armazenada | Classificação | Finalidade | Proteção e política de acesso |
| --- | --- | --- | --- | --- |
| `cpf` | `cpf_hash` | Dado pessoal | Cadastro e identificação de operadores de campo | HMAC-SHA-256; chave restrita ao processo autorizado, digest não reversível |
| `nome_completo` | `nome_completo_cifrado` | Dado pessoal | Cadastro e identificação de operadores de campo | Fernet; descriptografia autorizada por principal, tentativas auditadas sem PII |

`inserir_catalogo_lgpd` insere ou atualiza os metadados em transação, preservando o ID e a data de criação em reexecuções. A opção 5 do menu executa essa carga. Os testes conferem todos os metadados e, no SQLExpress descartável com o DDL oficial, validam reexecução, correção de metadados desatualizados e rejeição de duplicidade/classificação inválida. Essa homologação não publica o catálogo nem altera dados no banco `monitoramento`.

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
