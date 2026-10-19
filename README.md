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
├── sql/
│   └── queries_analiticas.sql      # Estatísticas amostrais e anomalias no SQL Server
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

### Ingestão REST genérica e Bronze (IDs 21–25)

O conector `src/ingestion/api_ingestion.py` é um fluxo REST genérico, independente do coletor Agritempo. Ele processa os datasets `ambiental` e `meteorologica` quando seus endpoints estão configurados no `src/config/.env`. As variáveis `API_URL_AMBIENTAL` e `API_URL_METEOROLOGICA` habilitam cada endpoint; `API_SOURCE_NAME_AMBIENTAL` e `API_SOURCE_NAME_METEOROLOGICA` definem rótulos de origem opcionais, `API_TIMEOUT_SECONDS` controla o timeout e `API_REQUESTS_PER_MINUTE` limita as requisições. `API_RAW_DIR` define onde gravar os arquivos.

Cada registro aprovado é gravado como uma linha JSONL com o conteúdo original em `record` e os metadados `dataset`, `source` e `ingested_at`. O timestamp de ingestão é gerado em UTC para cada registro; `source` usa o nome configurado ou, na ausência dele, host e caminho da URL, sem parâmetros de consulta. Cada lote recebe um arquivo exclusivo, publicado após a gravação completa; uma execução seguinte não sobrescreve arquivos históricos. Registros rejeitados não entram na Bronze: geram um evento de auditoria no log de tratamento com dataset, índice, identificador/estação, motivo e instante UTC, sem despejar o payload completo.

Os requisitos dos IDs 22 e 23 já estavam atendidos pela persistência JSONL original e pela criação de arquivos exclusivos por lote, por isso não exigiram alteração de implementação nesta revisão. O campo `source` do ID 25 também já era gravado por registro. O `ingested_at` do ID 24 já existia no gravador Bronze; nesta revisão foram reforçadas sua documentação e a cobertura de teste. O ID 21 passou a incluir instante de auditoria explícito.

### Decisões sobre os artefatos estruturais (IDs 99–104)

Não foram criados módulos adicionais para os IDs 99, 100, 101 e 103, pois os fluxos e responsabilidades já estão separados na estrutura atual: `src/ingestion/` organiza a ingestão, os parsers e o conector REST contêm as respectivas validações, `src/config/settings.py` cria a conexão e `src/database/dml/` mantém as cargas, enquanto `src/main.py` já orquestra as opções do menu. Criar `src/ingestion.py`, `src/quality_governance.py`, `src/database_manager.py` ou outro orquestrador apenas como fachada adicionaria indireção sem comportamento novo. Uma extração futura deve responder a uma necessidade concreta de lógica compartilhada, reutilização ou teste, não somente à presença do arquivo no checklist.

O ID 104 foi concluído com `tests/test_quality_data.py`. Os testes validam aceitação e rejeição de leituras ambientais e meteorológicas na camada Silver e verificam as métricas do manifesto para completude, tempestividade, acurácia e validade.

## Execução

Prepare o banco em uma instância SQL Server dedicada. Execute `src/database/ddl/create-database.sql` apenas quando o banco `monitoramento` ainda não existir; o comando `CREATE DATABASE` falha se o nome já estiver em uso. Em seguida, execute `src/database/ddl/create-tables.sql` pelo SSMS ou `sqlcmd`, pois o arquivo contém separadores `GO`. O script cria tabelas ausentes, mas não remove nem recria tabelas existentes e não migra constraints para um schema já criado. Em um banco criado com uma versão anterior do script, confira o catálogo antes das cargas, pois colunas acrescentadas depois à definição (como `qualidade_agua.turbidez`) não chegam a tabelas já criadas.

Para abrir o menu e executar as cargas:

   ```bash
   python src/main.py
   ```

No menu, a opção 1 executa localização, cadastro dos parâmetros e, em seguida, as cargas ambientais e meteorológicas. A opção 3 executa os cadastros de parâmetros, catálogo LGPD e operadores, nessa ordem, interrompendo ao primeiro erro. A carga depende de uma conexão SQL Server configurada em `src/config/.env` e de estações previamente cadastradas para os operadores. A opção 4 encerra o menu; a opção 5 gera o relatório estatístico da Silver e a opção 6 gera a validação por Z-Score, ambas sem consultar o banco.

A opção `2` executa `Get_dados.py`: consulta estações e dados climáticos, aplica o limite `API_REQUESTS_PER_MINUTE` e acrescenta os resultados ao JSON cumulativo. Também é possível executar com `python Get_dados.py`. O módulo `src/ingestion/api_ingestion.py` permanece como conector genérico separado para endpoints que já atendam aos contratos ambiental ou meteorológico definidos nele; ele não é o coletor da Agritempo.

### Reprocessamento histórico por período — ID 70

A opção **7** do menu executa o backfill de leituras: informe `ambiental`, `meteorologica` ou `ambos`, a data inicial inclusiva e a data final exclusiva, no formato `AAAA-MM-DD`. O filtro considera a data da leitura normalizada em UTC, não a data de ingestão. Também é possível executar diretamente:

```powershell
.\.venv\Scripts\python.exe .\src\database\dml\Backfill_Leituras.py --dataset ambos --data-inicio 2026-09-15 --data-fim 2026-09-18
```

Esse exemplo seleciona os dias 15, 16 e 17 de setembro em UTC. As fontes são os JSONs definidos por `INGESTION_LEITURA_AMBIENTAL` e `INGESTION_LEITURA_METEOROLOGICA` no `src/config/.env`. Os arquivos precisam conter os registros históricos desejados: o backfill não busca dados em APIs, não lê os envelopes JSONL da Bronze e não consome o JSON cumulativo Agritempo. Preservar esses arquivos é necessário para futuras reexecuções.

Os parsers existentes continuam responsáveis pela qualidade e deduplicação; o filtro por período é aplicado ao resultado validado. As contagens de selecionados/aprovados/rejeitados do backfill referem-se a essa etapa; rejeições anteriores dos parsers mantêm seus próprios logs. Estações e parâmetros devem estar cadastrados no destino 3FN; não execute com medições ativas nas tabelas legadas sem a migração descrita neste documento.

O destino SQL usa `DB_*` e a Silver usa `SILVER_DIR`, exatamente como nas cargas normais. **Executar esse comando grava nos destinos configurados**, não seleciona automaticamente o banco descartável das integrações. Primeiro valide em ambiente isolado.

Reexecutar o mesmo intervalo no modo padrão não duplica eventos: replays preservam identidades/valores no SQL e ignoram chaves já presentes na Silver. Dados conflitantes são rejeitados, sem substituir o histórico aceito. O log de inserção registra fonte, período e contagens; rejeições da carga retornam código de saída 1. No modo padrão, períodos sem leituras são registrados com zero selecionados, sem abrir conexão SQL.

Cada evento SQL é transacional, mas não existe transação única para todo o período nem transação distribuída SQL/Parquet. Em falha da Silver após commit SQL, o erro permanece explícito e a repetição do período pode reconstruir a projeção ausente. Partições fora do período permanecem preservadas. A migração de tabelas legadas em `Migrar_Leituras.py` continua sendo uma operação distinta.

Os testes locais em `tests/test_backfill.py` usam JSONs sintéticos, SQLite e Silver temporária para verificar fronteiras UTC, ambos os datasets, replay, conflitos, preservação dos dados fora do intervalo e recuperação da Silver. O ID 70 está concluído; a integração opt-in abaixo permite repetir a validação no SQL Server descartável.

#### Testar o backfill no banco descartável

Use `monitoramento_lgpd_test`, já configurado em `SQLSERVER_LGPD_TEST_URL` no `src/config/.env`, com `RUN_SQLSERVER_LGPD_TESTS=1`. A configuração de testes é separada de `DB_*`: **não é necessário alterar o destino normal da aplicação**.

Na raiz do repositório, execute somente os dois cenários de integração do backfill:

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests\test_backfill.py -k backfill_sqlserver_disposable -v
```

O teste passa explicitamente a engine descartável ao backfill. Para cada dataset (ambiental e meteorológico), cria o DDL oficial, cadastra estação e parâmetros sintéticos, lê JSONs temporários e grava a Silver apenas sob o diretório temporário do pytest (`.pytest_tmp` por padrão). Confere fronteiras UTC, preservação de registros e partições fora do período, identidade e valores no replay, ausência de duplicação e reconstrução da Silver ausente. Também homologa o ID 71: introduz duplicatas, valores incorretos e linhas extras na Silver, reduz o JSON a um lote parcial e verifica que duas reconstruções restauram exatamente os eventos aceitos no SQL, sem modificar o banco.

**Pré-condições e limpeza:** a instância deve estar acessível e o banco descartável deve existir e estar sem tabelas em `dbo`. O lifecycle valida o nome e o banco conectado, adquire um lock exclusivo e remove as tabelas do projeto ao final, inclusive em falhas após a inicialização. Não execute contra `monitoramento` nem remova tabelas preexistentes apenas para liberar o teste. O resultado esperado é **2 testes aprovados**; `SKIPPED` significa integração desabilitada, não homologação concluída.

Para executar os testes locais e esses cenários SQL no mesmo comando, use `python -m pytest tests\test_backfill.py -v` com o interpretador do ambiente virtual e a integração habilitada. Essa validação usa exclusivamente dados sintéticos: não carrega os JSONs operacionais nem publica dados no banco normal.

### Reconstrução das partições Silver — ID 71

O backfill também permite **substituir integralmente as partições diárias afetadas**, sem duplicar suas chaves lógicas. Na opção **7** do menu, responda `s` à pergunta sobre reconstruir a Silver a partir do SQL; Enter ou `n` mantém o backfill padrão. Pela CLI:

```powershell
.\.venv\Scripts\python.exe .\src\database\dml\Backfill_Leituras.py --dataset ambos --data-inicio 2026-09-15 --data-fim 2026-09-18 --reconstruir-silver
```

**Esse comando grava nos destinos normais configurados**, não no banco descartável. O intervalo abrange os dias 15, 16 e 17 em UTC. O processo é:

1. Ler os JSONs operacionais e executar os parsers e a carga SQL existentes. Novos eventos válidos são inseridos; o histórico aceito continua protegido contra alterações conflitantes.
2. Se houver rejeição na carga do dataset, cancelar sua reconstrução Silver, registrar o motivo e retornar falha. Eventos de outros datasets e eventos já confirmados no SQL não são revertidos.
3. Sob lock exclusivo do dataset Silver, consultar **todos os eventos SQL aceitos no intervalo**, incluindo os que não estão no JSON disponível. A consulta usa os locks ETL existentes durante a leitura.
4. Validar o conjunto completo antes da primeira substituição: contrato, qualidade, intervalo e unicidade. Dados SQL incompletos ou inválidos causam erro explícito, sem descartar silenciosamente registros para reconstruir a partição.
5. Regravar os dias selecionados com Parquet/Snappy e troca atômica por arquivo. Remover duplicatas e linhas indevidas decorre da substituição pelo conjunto SQL, não de aceitar o último valor recebido. Dias fora do intervalo não são alterados.
6. Registrar manifesto em `_audit/<dataset>` com modo `reconstrucao_sql`, período UTC, contagens anteriores/finais por partição e métricas de qualidade, sem valores das medições ou dados pessoais.

**Referência e cardinalidade:** os JSONs continuam sendo a entrada operacional; o SQL aceito é a referência da projeção Silver no instante da consulta. Repetir a reconstrução sem novos eventos mantém as mesmas chaves, valores e quantidade lógica. Uma partição defeituosa pode ter sua quantidade corrigida para corresponder ao SQL. As chaves permanecem `id_leitura_origem` para água e `(id_estacao, data_leitura UTC)` para meteorologia. O recurso não autoriza corrigir valores já aceitos no SQL.

Neste modo, `gravados_silver` conta todas as linhas reconstruídas da referência SQL, inclusive em replay; pode ser maior que `selecionados`/`aprovados`, que continuam contando apenas o lote JSON validado do período.

**Dias sem eventos:** um JSON sem registros no período não causa exclusão por si só; neste modo, o SQL é consultado mesmo assim. Se um dia existente na Silver não possui eventos no SQL, seu arquivo é substituído por um Parquet vazio com o contrato do dataset. Dias sem eventos e sem arquivo existente não geram partições novas.

**Concorrência e recuperação:** todos os escritores Silver deste módulo compartilham `.silver.lock` por dataset, inclusive o modo de mesclagem normal. A reserva tem timeout de 60 segundos e é liberada pelo sistema operacional no encerramento do processo; não apague o arquivo de lock para tentar liberá-la. A coordenação pressupõe escritores cooperantes no mesmo destino e um sistema de arquivos com suporte aos locks utilizados. Os arquivos temporários são criados junto ao destino, não na pasta global `Temp`. A substituição é atômica por arquivo, não para todo o intervalo ou entre SQL/Parquet; falhas intermediárias são explícitas e permitem retomada por reexecução. Um erro de auditoria pode ocorrer após a troca dos arquivos e também exige reexecução.

O layout aceito continua sendo um `part-00000.parquet` por dia. Arquivos Parquet adicionais no dia afetado ou colisões de chave com dias fora do intervalo causam erro antes das substituições; precisam de investigação, não de exclusão automática. Arquivos existentes devem estar legíveis para contabilização e auditoria.

Os testes locais em `tests/test_silver.py` e `tests/test_backfill.py` cobrem igualdade com a referência SQL, JSON parcial ou sem registros no período, limpeza de dias sem eventos SQL, rejeições, replay, preservação fora do intervalo, falhas e retomada, timeout e coordenação com um escritor em outro processo. O comando de homologação no banco descartável da seção anterior também executa os cenários de reconstrução dos dois datasets.

Na validação desta implementação, a tentativa de integração com `monitoramento_lgpd_test` foi bloqueada na conexão: SQLSTATE `28000`, erros SQL Server `18456`/`4060` (login/acesso ao banco). Nenhuma tabela foi criada ou alterada por essa tentativa. A homologação real deve ser repetida após verificar a existência/disponibilidade do banco na instância configurada e a permissão do login utilizado; teste ignorado ou falha de conexão não equivale a homologação aprovada.

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

Os logs registram início, datasets/quantidades, descartes, período, destino e resultado. O relatório é um artefato analítico separado, não uma camada Gold. A rotina descritiva não classifica anomalias; a validação independente por Z-Score do ID 51 está documentada a seguir. O detector IQR (ID 50) e a persistência de flags operacionais (ID 52) permanecem fora do escopo.

Para validar esta entrega:

```bash
python -m pytest tests/test_analytics_statistics.py tests/test_config_and_main.py tests/test_silver.py -q
```

Verificação local em 2026-10-15: 68 testes focados passaram; a suíte sem integrações SQL teve 193 aprovados e 42 ignorados (`RUN_SQLSERVER_LGPD_TESTS=0`). A tentativa de integração SQL foi impedida por falha de acesso ao banco descartável, sem homologação SQL nesta entrega. A Silver local gerou 422 grupos, com 120 leituras de água e 2.817 meteorológicas (11.868 medidas válidas), cobrindo os dias UTC de 2026-09-15 a 2026-10-30. Módulo e menu foram executados; o replay preservou o CSV byte a byte e os hashes dos 54 Parquets de origem.

## Consultas analíticas SQL - ID 97

`sql/queries_analiticas.sql` contém consultas para SQL Server sobre o modelo relacional 3FN (`leituras`, `leitura_itens`, `parametros` e `estacao`). Execute o arquivo no banco alvo já selecionado; ajuste `@data_inicio` e `@data_fim` para a janela desejada. Os valores padrão são UTC, com início inclusivo e fim exclusivo, e as datas das leituras são normalizadas para UTC antes do filtro.

O primeiro resultado tem granularidade de estação e parâmetro e apresenta média, mediana e quartis contínuos (`PERCENTILE_CONT`), desvio padrão e variância amostrais (`STDEV` e `VAR`), IQR e limites de `1,5 × IQR`. O segundo resultado tem uma linha por leitura/parâmetro numérico, com Z-score e indicadores IQR e Z; limites IQR são estritos (`valor < limite inferior` ou `valor > limite superior`) e Z sinaliza quando `|Z| >= 3`. Z-score fica nulo e não sinaliza com menos de duas observações ou desvio amostral zero. Itens sem `valor_numerico`, incluindo medidas textuais, não participam dos cálculos nem são classificados.

O teste `test_analytical_queries_calculate_statistics_and_flag_outliers` usa dados sintéticos e roda junto à migração no SQL Server descartável. Valide com `pytest -q tests/test_sqlserver_migration.py`; a execução depende da configuração opt-in documentada em Testes. Este artefato não implementa flags persistidas (ID 52), Gold ou Power BI.

Verificação SQL Server em 2026-10-16: `python -m pytest -q tests/test_sqlserver_migration.py` concluiu com 10 testes aprovados, incluindo as métricas analíticas e a preservação da granularidade das quatro consultas essenciais. O banco descartável `monitoramento_lgpd_test` ficou online e sem tabelas em `dbo` ao final do lifecycle.

## Validação por Z-Score - ID 51

O mesmo módulo oferece `calcular_z_scores()` e `gerar_relatorio_zscore()`. O cálculo usa as observações válidas do período selecionado, agrupadas por `dataset`, `id_estacao`, `codigo_parametro` e `unidade_medida`. Reutiliza a média e o desvio amostral (`ddof=1`) calculados em memória, não o CSV descritivo que pode estar desatualizado:

$$
z = \frac{x - \bar{x}}{s}, \qquad s = \sqrt{\frac{\sum_{i=1}^{n}(x_i-\bar{x})^2}{n-1}}
$$

O Z-Score é adimensional. A condição de sinalização é estrita: `abs(z_score) > limiar`; igualdade não sinaliza. O limiar padrão é `3.0` e deve ser numérico, finito e positivo. Não se excluem extremos finitos antes de calcular a referência, nem se ajusta o limiar automaticamente.

Execute na raiz do projeto, com as dependências e `LOGS_DIR` já configurados:

```bash
python -m src.analytics_statistics --analise zscore
```

A opção 6 do menu executa esse modo com todo o histórico, limiar 3 e saída `reports/z_scores.csv`. Também funciona como script direto: `python src/analytics_statistics.py --analise zscore`. Para personalizar a janela, o limiar ou o destino:

```bash
python -m src.analytics_statistics --analise zscore --limiar 2.5 --data-inicio 2026-10-01 --data-fim 2026-10-14 --saida reports/z_scores_outubro.csv
```

`--silver-dir` e as datas UTC inclusivas seguem as mesmas regras da rotina descritiva. Sem `--analise`, o modo continua sendo `estatisticas`, com saída `reports/estatisticas_descritivas.csv`; a opção 5 permanece inalterada. Cada modo tem seu próprio destino padrão. Um `--saida` explícito substitui o arquivo informado, portanto não use o mesmo destino para relatórios que deseja manter separados.

O CSV Z-Score tem uma linha por medição e parâmetro, inclusive quando o escore é indefinido. Preserva `id_leitura_origem` da água (dois eventos no mesmo instante não são confundidos). Na meteorologia, essa coluna fica vazia e a leitura é identificada por `id_estacao` e `data_leitura` UTC, além do dataset. As nove colunas numéricas do catálogo continuam sendo as únicas medidas.

As colunas de saída são `dataset`, `id_estacao`, `codigo_parametro`, `unidade_medida`, `id_leitura_origem`, `data_leitura`, `valor`, `n_validos`, `n_invalidos`, `media`, `desvio_padrao`, `ddof`, `limiar_zscore`, `z_score`, `anomalia_zscore`, `status_zscore`, `periodo_inicio_utc` e `periodo_fim_exclusivo_utc`. As contagens e referências são do grupo, repetidas em cada medição; não some essas contagens entre as linhas. `valor`, média e desvio usam a unidade original.

| `status_zscore` | Situação | Escore e indicador |
|---|---|---|
| `avaliado` | Medida válida, pelo menos duas observações válidas e desvio positivo | Escore numérico; indicador `True` ou `False` |
| `medida_invalida` | Nulo, booleano, string ou número não finito | Vazios; valor numérico também vazio |
| `amostra_insuficiente` | Medida válida, mas menos de duas observações válidas no grupo | Vazios |
| `desvio_zero` | Medida válida em uma série constante com pelo menos duas observações | Vazios |

Um Z-Score igual a zero é válido quando a medida coincide com a média e há dispersão positiva; não equivale aos casos indefinidos. Textos de medidas rejeitadas não são exportados. Grupos inteiramente inválidos mantêm suas linhas e contagens na função de cálculo, mas uma execução sem nenhuma medida válida falha sem substituir o relatório anterior. Grupos válidos com escores todos indefinidos produzem CSV explicativo e `WARNING`, sem afirmar ausência de anomalias.

Formato, compressão de origem e validações da Silver permanecem inalterados. O CSV usa `;`, decimal `.`, UTF-8 com BOM, campos ausentes vazios e ordenação determinística. A escrita atômica é compartilhada com o relatório descritivo e limpa arquivos temporários em caso de falha. O destino não pode estar dentro da Silver. Schema/chaves inválidos, arquivo corrompido ou resultado calculável não finito geram erro e retorno não zero, preservando o CSV anterior.

Os logs de execução informam período, limiar, grupos, medidas avaliadas, quantidade sinalizada e destino. Casos não calculáveis são resumidos em `WARNING`; falhas geram `ERROR`. Não há conexão SQL, alteração dos Parquets nem gravação de flags no banco/Silver. Evite executar writers Silver durante a leitura, pois não há snapshot transacional entre partições.

O resultado é um indicador estatístico para validação, não prova de erro físico, risco sanitário ou concordância com IQR. A própria leitura participa da referência do seu grupo; não há janela móvel, treinamento separado ou avaliação preditiva. Com `ddof=1`, referência no próprio grupo e limiar 3, grupos com até dez observações não conseguem ultrapassar o limiar. Sazonalidade, assimetria e múltiplos extremos também podem mascarar anomalias. Esta entrega não conclui os IDs 50, 52, 102 ou o relatório completo de qualidade do ID 108.

Verificação local em 2026-10-16: 102 testes focados aprovados; suíte local com 227 aprovados e 42 integrações SQL ignoradas, definindo `RUN_SQLSERVER_LGPD_TESTS=0` somente no processo. Módulo e opção 6 foram executados sobre 11.868 medições de 422 grupos, com 92 sinalizadas por `abs(z)>3`. O replay gerou CSV idêntico; o relatório descritivo e os hashes dos 54 Parquets foram preservados. A execução não realizou homologação SQL.

## Regras de qualidade e pendências

Os parsers rejeitam leituras sem identidade, estação, data ou medições obrigatórias, validam temperaturas, pH, umidade, precipitação e vento, e normalizam datas para UTC. As faixas inclusivas de temperatura são -50 °C a +60 °C para o ar e 0 °C a +50 °C para a água; parser e Silver rejeitam valores fora delas. As dimensões de consistência também não cobrem todas as possíveis contradições entre leituras de fontes diferentes.

## Testes

Os testes SQLite exercitam parsers, loaders, constraints, configuração e writer Parquet com dados temporários. O fixture configura `SILVER_DIR` sob o diretório temporário do pytest para não produzir arquivos na raiz do repositório. Execute a suíte com o interpretador do ambiente virtual, onde `cryptography` está instalado:

```bash
.venv\Scripts\python -m pytest tests -v
```

Com o Python global, a coleta de `tests/test_lgpd.py` falha se `cryptography` não estiver instalado nele.

O `pytest.ini` configura `--basetemp=.pytest_tmp`: ao executar os comandos a partir da raiz do repositório, as fixtures `tmp_path` e `tmp_path_factory` usam essa pasta local, ignorada pelo Git, em vez de `%TEMP%\pytest-of-...\pytest-current`. Isso evita a falha de permissão na limpeza do link temporário do Windows, sem alterar as variáveis globais `TEMP`/`TMP` nem a configuração do SQL Server.

Essa pasta é exclusiva dos testes: o pytest apaga seu conteúdo no início de cada execução. Não armazene arquivos importantes nela e não execute duas sessões simultâneas com o mesmo `--basetemp`. Para execuções paralelas independentes, informe caminhos locais distintos, por exemplo `--basetemp=.pytest_tmp\sessao-a` e `--basetemp=.pytest_tmp\sessao-b`. O ajuste elimina o problema de limpeza temporária; eventuais erros de autenticação ou de asserção dos testes continuam sendo exibidos normalmente.

As integrações LGPD, integridade, unicidade e migração com SQL Server exigem um banco descartável vazio, separado de `monitoramento`. Todas compartilham a configuração carregada automaticamente de `src/config/.env`, independentemente do diretório de execução. Configure nesse arquivo local, não versionado, `RUN_SQLSERVER_LGPD_TESTS=1` e `SQLSERVER_LGPD_TEST_URL` para uma instância SQL Server e um banco descartável que já exista. O banco deve ter nome terminado em `_test`, `_tests`, `_disposable` ou `_scratch`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest '.\tests\test_sqlserver_lgpd.py' -v
```

Não é necessário exportar variáveis a cada execução. `RUN_SQLSERVER_LGPD_TESTS=1` habilita a integração e `SQLSERVER_LGPD_TEST_URL` define a URL SQLAlchemy. Variáveis já definidas no processo têm prioridade; use `RUN_SQLSERVER_LGPD_TESTS=0` para desabilitar. Sem ativação, apenas a integração é ignorada; os testes da configuração continuam executando. Ativação sem URL gera erro explícito, não `SKIPPED`.

Nunca aponte essa configuração para `monitoramento`. O lifecycle exige um nome com sufixo `_test`, `_tests`, `_disposable` ou `_scratch`, recusa tabelas preexistentes em `dbo`, aplica o DDL oficial (sem o `USE monitoramento`) e remove suas tabelas ao final. O banco permanece disponível e vazio para a próxima execução. Um application lock exclusivo serializa as suítes que compartilham a base, com erro explícito em caso de timeout. A configuração normal da aplicação em `src/config/.env` não é usada como fallback.

### Integridade relacional no SQL Server

As suítes SQL de integridade e unicidade validam PKs, FKs, nulabilidade, CHECKs, cascatas, cargas e replay contra o DDL real. Use somente uma instância e uma base descartáveis, configuradas em `src/config/.env`; as suítes carregam esse arquivo automaticamente, e variáveis do processo podem sobrescrevê-lo. Não aponte testes ou migrações para dados reais.

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
3. Em base descartável, exercite os testes SQL com `src/config/.env`; a configuração local é carregada automaticamente pelas suítes SQL, com variáveis do processo podendo sobrescrevê-la. Preserve constraints/FKs durante os testes; não as desabilite nem as remova para limpar os dados.
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

A integração automática SQLExpress usa JSON temporário sintético e o DDL oficial para validar estrutura, carga, replay, atualização, rejeições e ausência de CPF/nome/chaves/ciphertext nos logs. A fonte operacional do ID 10 foi definida como `src/ingestion/localizacao/operadores.json`; a homologação SQL Server é uma verificação técnica separada, feita somente com dados sintéticos em banco descartável, sem publicar dados em `monitoramento`. O ID 44 tem homologação própria nas suítes de integridade, unicidade e migração.

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
