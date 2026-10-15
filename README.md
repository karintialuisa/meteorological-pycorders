# PyCordersMeteorological

Pipeline de Monitoramento e Análise de Dados Ambientais

Projeto Prático Integrador desenvolvido pela equipe PyCorders para capturar, tratar e persistir dados de estações meteorológicas e de qualidade da água, com consultas por API REST.

## Sobre o projeto

A aplicação trata arquivos JSON de leituras ambientais, meteorológicas e de localização, persiste os dados em SQL Server e disponibiliza consultas por API REST. O fluxo principal de carga é executado por scripts Python independentes, orquestrados por um menu de terminal.

## Funcionalidades

O pipeline contempla:

- Leitura e normalização de JSONs de estados, municípios, estações e leituras.
- Coleta dos dados meteorológicos de temperatura do ar da API Agritempo, com bearer no `.env`, limite de requisições e acumulação dos resultados no mesmo JSON.
- Carga incremental de estados, cidades, estações, qualidade da água e meteorologia.
- Resolução e validação de chaves entre os arquivos JSON e o SQL Server.
- Modelo relacional de leituras com `parametros`, `leituras` e `leitura_itens`, cujas cargas na camada DML validam campos, resolvem chaves por código e são idempotentes.
- Proteção de dados pessoais de operadores: CPF em HMAC-SHA-256 e nome completo cifrado com Fernet, com catálogo LGPD. A descriptografia exige autorização explícita do chamador e registra auditoria sem conteúdo pessoal ou chaves.
- API FastAPI para listar cidades e consultar leituras carregadas dos JSONs.
- Logs separados para tratamento, inserção no banco e execução do menu.
- Estatísticas descritivas por estação e parâmetro a partir da Silver, com relatório CSV (IDs 45 a 49).

## Tecnologias

- Python 3.10 ou superior
- SQL Server
- SQL Server e Microsoft ODBC Driver 17 for SQL Server
- pandas, PyArrow, SQLAlchemy, pyodbc, python-dotenv e cryptography
- FastAPI e Uvicorn (API)
- pytest (testes)

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
│   ├── analytics_statistics.py      # Estatísticas da Silver e relatório CSV
│   ├── main.py                      # Menu e orquestração das cargas
│   └── __init__.py
├── .gitignore
├── features.csv                     # Inventário de requisitos, status e evidências
├── projeto_final.pdf                # Enunciado do projeto
├── README.md
└── tests/                           # Testes SQLite e testes opt-in para SQL Server
    ├── conftest.py
    ├── test_api.py
    ├── test_api_ingestion.py
    ├── test_config_and_main.py
    ├── test_database_loading.py
    ├── test_get_dados.py
    ├── test_lgpd.py
    ├── test_parsers.py
    ├── test_silver.py
   ├── test_analytics_statistics.py  # Estatísticas, leitura Silver e CSV
    ├── test_sqlserver_lgpd.py           # Opt-in
    ├── test_sqlserver_relational_integrity.py  # Opt-in
    ├── test_sqlserver_uniqueness.py     # Opt-in
    ├── test_sqlserver_migration.py      # Backfill/cutover no DDL real
    └── sqlserver_support.py             # Configuracao e lifecycle compartilhados
```

## Responsabilidades dos módulos

- `src/ingestion/leituras`: guarda os JSONs de entrada e transforma leituras ambientais e meteorológicas em DataFrames; respostas REST brutas são salvas aqui por padrão.
- `src/ingestion/localizacao`: normaliza estados, municípios e estações.
- `src/database/ddl`: contém `create-database.sql` e `create-tables.sql`.
- `src/database/dml`: valida, resolve chaves e carrega localização, leituras (tabelas atuais), parâmetros, cabeçalhos e itens de leitura, operadores e catálogo LGPD de forma idempotente; `etl_lock.py` serializa cargas no SQL Server; `delete-data-table.sql` e `seed.sql` são auxiliares.
- `src/security`: normaliza e valida CPF, aplica HMAC-SHA-256 e a criptografia Fernet do nome.
- `src/database/dql`: reúne consultas de inspeção e análise.
- `src/api`: expõe cidades e leituras dos arquivos JSON pelos endpoints HTTP.
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

`src/config/.env.example` é um modelo sem segredos. Copie-o para `src/config/.env` e substitua os marcadores antes de executar cargas que protegem dados de operadores. A opção 3 do menu executa os cadastros de parâmetros, catálogo LGPD e operadores; para operadores, as chaves HMAC e Fernet devem ser reais. O loader recusa valores que começam com `replace-with`.

`Get_dados.py` usa a API Agritempo da Embrapa. O bearer deve ficar somente em `src/config/.env`; não o coloque no código nem o versione. O escopo atual dessa fonte é meteorológico, com os dados de temperatura do ar disponíveis no retorno climático. O contrato em `src/ingestion/api_ingestion.py` valida o envelope, os dados da estação e cada observação diária, exigindo data, ID e temperaturas mínima/máxima numéricas, finitas e coerentes entre si. Estações sem série climática são aceitas.

Para consumo analítico, a projeção usa somente `temperatura_minima` e `temperatura_maxima` (incluindo os indicadores de estimativa). `temperatura_media` e as demais variáveis que venham da API permanecem no JSON bruto como resposta original, mas não entram nessa projeção; a média não é calculada pelo pipeline atual.

Bronze, Silver e Gold são nomes de etapas, não uma exigência de criar pastas com esses nomes. A coleta da Agritempo acumula os resultados no mesmo `dados_agritempo.json`, dentro do diretório de `API_RAW_DIR` (por padrão, `src/ingestion/leituras`). Novas execuções preservam os resultados anteriores e acrescentam os novos; não é criada uma pasta `data/bronze`.

## Execução

Prepare o banco em uma instância SQL Server dedicada. Execute `src/database/ddl/create-database.sql` apenas quando o banco `monitoramento` ainda não existir; o comando `CREATE DATABASE` falha se o nome já estiver em uso. Em seguida, execute `src/database/ddl/create-tables.sql` pelo SSMS ou `sqlcmd`, pois o arquivo contém separadores `GO`. O script cria tabelas ausentes, mas não remove nem recria tabelas existentes e não migra constraints para um schema já criado. Em um banco criado com uma versão anterior do script, confira o catálogo antes das cargas, pois colunas acrescentadas depois à definição (como `qualidade_agua.turbidez`) não chegam a tabelas já criadas.

Para abrir o menu e executar as cargas:

   ```bash
   python src/main.py
   ```

No menu, a opção 1 executa localização, cadastro dos parâmetros e, em seguida, as cargas ambientais e meteorológicas. A opção 3 executa os cadastros de parâmetros, catálogo LGPD e operadores, nessa ordem, interrompendo ao primeiro erro. A carga depende de uma conexão SQL Server configurada em `src/config/.env` e de estações previamente cadastradas para os operadores. A opção 4 encerra o menu; a opção 5 gera o relatório estatístico da Silver, sem consultar o banco.

A opção `2` executa `Get_dados.py`: consulta estações e dados climáticos, aplica o limite `API_REQUESTS_PER_MINUTE` e acrescenta os resultados ao JSON cumulativo. Também é possível executar com `python Get_dados.py`. O módulo `src/ingestion/api_ingestion.py` permanece como conector genérico separado para endpoints que já atendam aos contratos ambiental ou meteorológico definidos nele; ele não é o coletor da Agritempo.

Para iniciar a API que lê os JSONs (não consulta o banco):

```bash
uvicorn src.api.main:app --reload
```

A documentação interativa da API ficará disponível em `http://127.0.0.1:8000/docs`. Os endpoints incluem `/cidades`, `/leituras/ambientais` e `/leituras/meteorologicas`.

`LOGS_DIR` define o diretório dos logs; caminhos relativos são resolvidos a partir da raiz do projeto. Os arquivos são separados por tipo de saída:

- `logs/tratamento_dados.log`: ingestão REST e execução isolada dos parsers/tratamentos.
- `logs/insercao_dados.log`: cargas e inserções no banco, incluindo eventos de validação ocorridos durante a carga.
- `logs/execucao_relatorio.log`: menu, orquestração geral e geração do relatório estatístico.

Os logs são gerados localmente e ignorados pelo Git. O único parâmetro de conexão fixo no código é `ODBC Driver 17 for SQL Server`; servidor, porta, banco e autenticação vêm do `.env`.

## Fluxo de processamento

1. Os parsers leem os JSONs versionados em `src/ingestion` e normalizam os dados com pandas.
2. A carga de localização insere estados, cidades e estações ainda não cadastrados.
3. A carga dos parâmetros ocorre antes das cargas ambientais e meteorológicas, que associam as leituras às entidades do banco e inserem os registros.
4. A API consulta os JSONs diretamente; parsers, ingestão REST e persistência Silver continuam disponíveis sem depender da camada de apresentação removida.

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

O Parquet da Silver e o SQL Server não compartilham uma transação distribuída. Nas cargas relacionais canônicas, o SQL é confirmado antes da escrita Silver; se Silver falhar, o erro é explícito e uma reexecução compatível repara a projeção Silver. Reexecuções são idempotentes pelas chaves naturais. O lock `sp_getapplock` protege apenas writers SQL Server que usem o mesmo recurso; não impede inserts feitos por aplicações externas que ignorem o lock.

## Estatísticas descritivas - IDs 45 a 49

`src/analytics_statistics.py` lê os Parquets de `SILVER_DIR` (padrão `data_lake/silver`) e gera `reports/estatisticas_descritivas.csv`. A execução não acessa o SQL Server, não modifica a Silver e não exige novas dependências. Execute na raiz do projeto, com `LOGS_DIR` configurado como nas demais rotinas:

```bash
python -m src.analytics_statistics
```

Também é possível usar a opção 5 do menu ou executar `python src/analytics_statistics.py`. O menu usa todo o histórico disponível e o destino padrão. Para selecionar um período e outro destino:

```bash
python -m src.analytics_statistics --data-inicio 2026-10-01 --data-fim 2026-10-14 --saida reports/estatisticas_outubro.csv
```

`--silver-dir` permite escolher outra Silver sem alterar o `.env`. Caminhos relativos de entrada e saída são resolvidos a partir da raiz do projeto. As duas datas são dias UTC inclusivos; internamente, o limite final é a meia-noite do dia seguinte, exclusiva. Sem datas, o período abrange os dias das observações disponíveis. Só as partições do recorte são lidas, e todas as observações são agregadas juntas, não por média de médias diárias.

O agrupamento usa `dataset`, `id_estacao`, `codigo_parametro` e `unidade_medida`. O identificador é o ID numérico resolvido na Silver, sem enriquecimento com nome/município ou dados de operadores. Os códigos e unidades seguem o catálogo de parâmetros:

| Dataset | Coluna Silver | Código | Unidade |
|---|---|---|---|
| qualidade_agua | temperatura_agua | TEMP_AGUA | Celsius |
| qualidade_agua | ph | PH | pH |
| qualidade_agua | oxigenio | OD | mg/L |
| qualidade_agua | condutividade | COND_ELETRICA | uS/cm |
| qualidade_agua | turbidez | TURBIDEZ | NTU |
| leitura_meteorologica | temperatura_ar | TEMP_AR | Celsius |
| leitura_meteorologica | umidade | UMIDADE | % |
| leitura_meteorologica | chuva | CHUVA | mm |
| leitura_meteorologica | vento | VENTO | km/h |

`condicao`, IDs e demais campos de controle não são medidas. As funções `ler_medicoes_silver`, `calcular_estatisticas` e `gerar_relatorio_estatistico` também podem ser importadas; o cálculo recebe um DataFrame longo com as quatro colunas de agrupamento e `valor`.

- ID 45: média aritmética das observações válidas.
- ID 46: mediana, incluindo a média dos dois valores centrais quando a quantidade é par.
- IDs 47 e 48: desvio padrão e variância **amostrais**, com divisor `n - 1` (`ddof=1`).
- ID 49: `iqr = q3 - q1`, com quantis de 25% e 75% e interpolação linear.

Não há arredondamento intermediário. Para `[1, 2, 3, 4]`, média e mediana são `2.5`, variância `5/3`, desvio `sqrt(5/3)`, Q1 `1.75`, Q3 `3.25` e IQR `1.5`. Com uma única observação, média/mediana/Q1/Q3 são o próprio valor e IQR é zero; desvio e variância ficam vazios no CSV, pois não há amostra suficiente. Séries constantes com pelo menos duas observações têm dispersão zero. A variância usa a unidade da variável ao quadrado; as demais métricas usam a unidade original.

O CSV tem separador `;`, decimal `.`, codificação UTF-8 com BOM e uma linha por grupo. As colunas são as quatro chaves do grupo, `periodo_inicio_utc`, `periodo_fim_exclusivo_utc`, `n_validos`, `n_invalidos`, `media`, `mediana`, `desvio_padrao`, `variancia`, `q1`, `q3`, `iqr` e `ddof`. A ordem é determinística e o período identifica a janela comum de cálculo.

Medidas nulas, booleanas, não numéricas (inclusive strings numéricas) ou infinitas são descartadas por parâmetro e contabilizadas em `WARNING`. Grupos sem valor válido são omitidos e registrados no log. A ausência de um dataset permite processar o outro com aviso. Se não houver dados ou grupos válidos, a execução termina com código não zero e não publica um relatório vazio.

Schema incompleto, identificadores/timestamps inválidos, datas fora da partição UTC, chaves naturais duplicadas ou Parquet corrompido interrompem a execução com `ERROR`. Não há deduplicação silenciosa nem alteração dos dados de origem. A escrita usa arquivo temporário e substituição atômica: reexecutar substitui o snapshot sem duplicar linhas; falhas preservam o CSV anterior. O destino não pode ficar dentro da Silver. Não execute writers Silver durante a leitura: os arquivos não oferecem snapshot transacional entre partições.

Os logs registram início, datasets/quantidades, descartes, período, destino e resultado. O relatório é um artefato analítico separado, não uma camada Gold. Esta entrega não detecta outliers, não calcula Z-Score nem persiste flags; os IDs 50 a 52 permanecem fora do escopo.

Para validar esta entrega:

```bash
python -m pytest tests/test_analytics_statistics.py tests/test_config_and_main.py tests/test_silver.py -q
```

Verificação local em 2026-10-15: 68 testes focados passaram; a suíte sem integrações SQL teve 193 aprovados e 42 ignorados (`RUN_SQLSERVER_LGPD_TESTS=0`). A tentativa de integração SQL foi impedida por falha de acesso ao banco descartável, sem homologação SQL nesta entrega. A Silver local gerou 422 grupos, com 120 leituras de água e 2.817 meteorológicas (11.868 medidas válidas), cobrindo os dias UTC de 2026-09-15 a 2026-10-30. Módulo e menu foram executados; o replay preservou o CSV byte a byte e os hashes dos 54 Parquets de origem.

## Regras de qualidade e pendências

Os parsers rejeitam leituras sem identidade, estação, data ou medições obrigatórias, validam temperaturas, pH, umidade, precipitação e vento, e normalizam datas para UTC. As faixas inclusivas de temperatura são -50 °C a +60 °C para o ar e 0 °C a +50 °C para a água; parser e Silver rejeitam valores fora delas. As dimensões de consistência também não cobrem todas as possíveis contradições entre leituras de fontes diferentes.

## Testes

Os testes SQLite exercitam parsers, loaders, constraints, configuração e writer Parquet com dados temporários. O fixture configura `SILVER_DIR` sob o diretório temporário do pytest para não produzir arquivos na raiz do repositório. Execute a suíte com o interpretador do ambiente virtual, onde `cryptography` está instalado:

```bash
.venv\Scripts\python -m pytest tests -v
```

Com o Python global, a coleta de `tests/test_lgpd.py` falha se `cryptography` não estiver instalado nele.

As integrações LGPD, integridade, unicidade e migração com SQL Server exigem um banco descartável vazio, separado de `monitoramento`. Todas compartilham a configuração carregada automaticamente de `src/config/.env.test`, independentemente do diretório de execução. Esse arquivo local não é versionado; para configurar outra máquina, copie `src/config/.env.test.example` para `src/config/.env.test` e ajuste a conexão. O modelo usa a instância local `localhost\SQLEXPRESS`, autenticação Windows e o banco `monitoramento_lgpd_test`, que deve existir previamente.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest '.\tests\test_sqlserver_lgpd.py' -v
```

Não é necessário exportar variáveis a cada execução. `RUN_SQLSERVER_LGPD_TESTS=1` habilita a integração e `SQLSERVER_LGPD_TEST_URL` define a URL SQLAlchemy. Variáveis já definidas no processo têm prioridade; use `RUN_SQLSERVER_LGPD_TESTS=0` para desabilitar. Sem ativação, apenas a integração é ignorada; os testes da configuração continuam executando. Ativação sem URL gera erro explícito, não `SKIPPED`.

Nunca aponte essa configuração para `monitoramento`. O lifecycle exige um nome com sufixo `_test`, `_tests`, `_disposable` ou `_scratch`, recusa tabelas preexistentes em `dbo`, aplica o DDL oficial (sem o `USE monitoramento`) e remove suas tabelas ao final. O banco permanece disponível e vazio para a próxima execução. Um application lock exclusivo serializa as suítes que compartilham a base, com erro explícito em caso de timeout. A configuração normal da aplicação em `src/config/.env` não é usada como fallback.

### Integridade relacional no SQL Server

As suítes SQL de integridade e unicidade validam PKs, FKs, nulabilidade, CHECKs, cascatas, cargas e replay contra o DDL real. Use somente uma instância e uma base descartáveis, configuradas em `src/config/.env.test`; as suítes carregam esse arquivo automaticamente, e variáveis do processo podem sobrescrevê-lo. Não aponte testes ou migrações para dados reais.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  '.\tests\test_sqlserver_relational_integrity.py' `
  '.\tests\test_sqlserver_uniqueness.py' `
  '.\tests\test_sqlserver_migration.py' -v -s
```

Os testes de constraints usam transações revertidas ao final. Os testes de replay confirmam dados sintéticos (os loaders controlam as próprias transações) e os removem em `finally`, falhando se restar alguma linha. As FKs não são desabilitadas nem removidas para limpar dados; uma falha de limpeza deve falhar o teste. Nunca execute contra um banco com dados reais.

## Modelo de dados simplificado

| Tabela                  | Finalidade                                      |
| ----------------------- | ----------------------------------------------- |
| `estado`                | Unidades federativas e código IBGE              |
| `cidade`                | Municípios vinculados a um estado               |
| `estacao`               | Estações vinculadas a cidade e estado           |
| `operadores`            | Operadores de campo com `cpf_hash` (HMAC-SHA-256), `nome_completo_cifrado` (Fernet) e estação |
| `catalogo_dados`        | Inventário LGPD dos campos pessoais, com finalidade, proteção e política de acesso |
| `parametros`            | Domínio dos parâmetros medidos: código único, nome e unidade |
| `leituras`              | Cabeçalho da leitura: origem, chave de origem, estação, operador opcional e data/hora |
| `leitura_itens`         | Valor medido por parâmetro em cada leitura; PK composta `(id_leitura, id_parametro)` |

`leituras` e `leitura_itens` seguem o modelo previsto no projeto: cada item guarda exatamente um valor, numérico ou textual, e a exclusão de uma leitura remove seus itens. As cargas ambientais e meteorológicas escrevem nesse modelo canônico, sem dual-write nas tabelas antigas. As tabelas `qualidade_agua` e `leitura_meteorologica` existem somente no schema legado e são arquivadas após reconciliação; os datasets Silver mantêm esses nomes.

ID 44 homologado em 2026-10-14: suíte completa com **194 testes PASSED, nenhum SKIPPED**, incluindo SQLExpress `WINAPpbE3Y0yOD8\SQLEXPRESS` em `monitoramento_lgpd_test`. Foram verificados FKs/PKs/CHECKs, carga atômica, replay/conflitos, quatro cargas concorrentes, exclusões bloqueadas preservando dados, cascatas, backfill/arquivamento, rollback de falha técnica, precisão/nulos/instantes e consultas 3FN. O lifecycle confirmou a base descartável vazia ao final. O banco `monitoramento` não foi alterado; a implantação real não faz parte desse aceite.

### Cargas canônicas e migração do legado — ID 44

`src/database/ddl/create-tables.sql` define o esquema canônico para uma instalação nova; não cria as tabelas de medições legadas, não migra esquemas existentes e não aplica alterações implícitas à tabela `operadores`. `src/database/ddl/create-legacy-measurements.sql` é somente um fixture de testes, não uma etapa de instalação. Em uma base existente, revise e atualize explicitamente o esquema e as constraints antes de carregar dados.

No ETL do menu, a carga de localização é seguida por `Insert_Parametros.py` e, então, pelos loaders ambiental e meteorológico. Os loaders convertem cada medida em item da leitura:

| Fonte | Medidas → códigos de `parametros` |
| --- | --- |
| `TEMP_AGUA` | temperatura da água |
| `PH` | potencial hidrogeniônico |
| `OD` | oxigênio dissolvido |
| `COND_ELETRICA` | condutividade elétrica |
| `TURBIDEZ` | turbidez |
| `TEMP_AR` | temperatura do ar |
| `UMIDADE` | umidade |
| `CHUVA` | chuva |
| `VENTO` | vento |
| `CONDICAO_METEO` | condição meteorológica |

Os nomes dos códigos são os valores armazenados em `parametros.codigo`. A identidade idempotente é derivada de `codigo_origem` e de uma chave natural normalizada, incluindo o timestamp UTC; os IDs canônicos permanecem estáveis em reexecuções. O wrapper de carga é estrito e limitado à conexão recebida: cabeçalho e todos os itens são gravados atomicamente, com validação dos domínios e locks adquiridos sempre na ordem `leituras` e depois `leitura_itens`. Erros técnicos são propagados. O commit do SQL precede a escrita Silver; uma falha Silver é reportada explicitamente, e repetir uma leitura correspondente reconcilia a Silver sem duplicar registros.

Não inicie novas cargas enquanto houver medições ativas nas tabelas legadas. Primeiro faça o backfill e a virada controlada. Para uma base já existente:

1. Faça e valide um backup recuperável, abra janela de manutenção e congele os writers legados. Não permita cargas concorrentes durante a migração.
2. Revise o catálogo da base, aplique o esquema canônico e cadastre os parâmetros. O comando de migração não cria nem atualiza schema ou parâmetros por conta própria.
3. Em base descartável, exercite os testes SQL com `src/config/.env.test`; a configuração local de teste é carregada automaticamente pelas suítes SQL, com variáveis do processo podendo sobrescrevê-la. Preserve constraints/FKs durante os testes; não as desabilite nem as remova para limpar os dados.
4. Após revisar o destino e autorizar operacionalmente a execução, rode a migração explicitamente:

   ```powershell
   .\.venv\Scripts\python.exe -m src.database.dml.Migrar_Leituras --expected-database NOME_DA_BASE --confirm
   ```

   Acrescente `--arquivar` somente quando a política aprovar a retenção no mesmo banco:

   ```powershell
   .\.venv\Scripts\python.exe -m src.database.dml.Migrar_Leituras --expected-database NOME_DA_BASE --confirm --arquivar
   ```

   `--confirm` é uma trava contra execução acidental, não uma autorização de produção. Nunca execute a migração em `monitoramento` sem autorização explícita, backup verificado e plano de cutover aprovado.

O `migrar_legado(engine, arquivar=False)` faz preflight e backfill em uma transação única. Ele verifica colunas canônicas, PKs, índices UNIQUE, FKs e confiança das constraints, política de FKs, colunas de origem, duplicatas, órfãos e consistência de cidade. Reconcilia códigos, timestamps UTC, valores decimais exatos, nulos e ausência de órfãos. Preserva `criado_em` nos cabeçalhos e os IDs originais nas tabelas arquivadas; IDs legados não são forçados numericamente para as tabelas canônicas mescladas. IDs normalizados gerados são estáveis por origem/chave natural. Conflitos abortam a transação inteira; uma repetição idempotente mantém IDs e valores, sem completar silenciosamente referências inconsistentes.

Com `--arquivar`, as tabelas de origem são renomeadas para `legado_*` e recebem triggers `AFTER INSERT`, `UPDATE` e `DELETE` que bloqueiam novas escritas. O arquivamento preserva os registros/IDs e os pais legados ainda referenciados; não apaga tabelas nem limpa referências. A política de exclusão do modelo canônico bloqueia (NO ACTION) a remoção de estações, operadores e parâmetros referenciados; remover um cabeçalho em cascata remove seus itens. A exclusão de estação só remove operadores em cascata quando não há leituras bloqueando a exclusão. Mantenha e valide as FKs habilitadas.

Antes de retomar cargas, a reversão só deve ocorrer a partir de backup e após revisão. Depois que novas leituras canônicas forem gravadas, exporte e reconcilie os dados antes de qualquer retorno; não restaure writers legados às cegas nem faça rollback direto sobre novas leituras.

Este runbook documenta o procedimento; nenhuma migração foi executada em `monitoramento`.

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

### Catálogo de dados pessoais — ID 32

`dbo.catalogo_dados` inventaria os campos de `dbo.operadores`, sem guardar valores pessoais:

| Campo lógico | Coluna armazenada | Classificação | Finalidade | Proteção e política de acesso |
| --- | --- | --- | --- | --- |
| `cpf` | `cpf_hash` | Dado pessoal | Cadastro e identificação de operadores de campo | HMAC-SHA-256; chave restrita ao processo autorizado, digest não reversível |
| `nome_completo` | `nome_completo_cifrado` | Dado pessoal | Cadastro e identificação de operadores de campo | Fernet; descriptografia autorizada por principal, tentativas auditadas sem PII |

`inserir_catalogo_lgpd` insere ou atualiza os metadados em transação, preservando o ID e a data de criação em reexecuções. A opção 3 do menu executa essa carga. Os testes conferem todos os metadados e, no SQLExpress descartável com o DDL oficial, validam reexecução, correção de metadados desatualizados e rejeição de duplicidade/classificação inválida. Essa homologação não publica o catálogo nem altera dados no banco `monitoramento`.

### Operadores em 3FN — ID 38

`dbo.operadores` representa um operador por CPF pseudonimizado, vinculado a uma estação. Seus atributos dependem da chave do operador; dados geográficos e atributos da estação permanecem em seus cadastros próprios, referenciados por FK, sem repetição na tabela de operadores.

| Coluna | Definição |
| --- | --- |
| `id` | BIGINT IDENTITY, chave primária |
| `cpf_hash` | CHAR(64) NOT NULL, UNIQUE e CHECK de tamanho; HMAC-SHA-256 |
| `nome_completo_cifrado` | VARCHAR(MAX) NOT NULL; ciphertext Fernet |
| `status` | BIT nullable no DDL; a carga JSON grava 1 para ativo e 0 nos demais casos |
| `id_estacao` | BIGINT NOT NULL; FK para `estacao.id` com ON DELETE CASCADE |
| `criado_em` | DATETIMEOFFSET NOT NULL com default SYSDATETIMEOFFSET |

`carregar_operadores` recebe JSON com `date` e uma lista `operadores`. Cada item usa `cpf`, `nome`, `estacao_id` (código de origem, não ID do banco) e `status`. A carga resolve a estação por `codigo_origem` e protege CPF/nome antes de persistir. Estação desconhecida, CPF inválido ou nome ausente impedem a gravação do registro, com erro contextual sem PII; os demais registros do lote continuam. Status ausente/desconhecido gera WARNING e grava 0.

A reexecução mantém uma linha por hash e preserva ID, data de criação e ciphertext quando nada muda. Alterações de nome, status ou estação atualizam a mesma linha; a comparação de nome utiliza descriptografia autorizada e auditada. O JSON original pode conter PII e exige acesso restrito; a proteção da tabela não anonimiza o arquivo de origem.

A integração automática SQLExpress usa JSON temporário sintético e o DDL oficial para validar estrutura, carga, replay, atualização, rejeições e ausência de CPF/nome/chaves/ciphertext nos logs. O aceite dos operadores é técnico, em `monitoramento_lgpd_test`: não publica dados em `monitoramento` nem aprova a fonte operacional (ID 10). O ID 44 tem homologação própria nas suítes de integridade, unicidade e migração.

## Equipe

| Integrante | Responsabilidade principal |
| ---------- | -------------------------- |
| Jaclin     | Coordenação, integração, acompanhamento dos marcos e Pull Request final |
| Jorge      | Ingestão, parsing, validação e tratamento dos dados |
| Karíntia   | Modelagem do banco, scripts DDL/DML e consultas SQL |
| Wagner   | Qualidade de dados e testes unitários |
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
- Cargas e API iniciadas conforme as instruções deste README.
- Configurações locais e logs mantidos fora do controle de versão.

## Licença

Este projeto foi desenvolvido para fins acadêmicos. Caso uma licença seja definida, inclua o arquivo correspondente no repositório e atualize esta seção.
