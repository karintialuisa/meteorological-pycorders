# Runbook operacional

Execute os comandos a partir da raiz do repositório. As cargas escrevem no SQL e no Data Lakehouse configurados; confira ambiente, origem e destino antes de executar.

## Preparação

1. Instale as dependências: `python -m pip install -r requirements.txt`.
2. Copie `.env.example` para `src/config/.env` somente se ainda não existir configuração local.
3. Configure `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_TRUSTED_CONNECTION`, `LOGS_DIR`, `SILVER_DIR`, `API_RAW_DIR` e `AGRITEMPO_RAW_DIR`. As chaves HMAC/Fernet e tokens devem ser valores locais reais, nunca commitados.
4. Para banco novo, crie o database com `sql/ddl/create-database.sql` apenas se ainda não existir; depois execute `sql/ddl_banco_relacional.sql`. Popule o domínio de parâmetros com `sql/dml_populacao.sql` ou com `python -m src.database.dml.Insert_Parametros`.
5. Cadastre estados, municípios e estações antes das leituras. A carga de localização existente pode limpar ou inserir dados conforme seu modo configurado; revise o módulo e o banco-alvo antes de executá-la.

## Estrutura e caminhos

```text
.env.example
requirements.txt
README.md
config/
sql/
  ddl_banco_relacional.sql
  dml_populacao.sql
  queries_analiticas.sql
data_lakehouse/
  bronze/
  silver/
  gold/
src/
  ingestion.py
  quality_governance.py
  database_manager.py
  analytics_stat.py
  pipeline_orchestrator.py
  bronze/
  silver/
  database/dml/
  gold/
tests/
power_bi/
```

Destinos padrão: `data_lakehouse/bronze`, `data_lakehouse/silver` e `data_lakehouse/gold`. Um caminho relativo nas variáveis de ambiente é resolvido a partir da raiz do repositório; caminho absoluto é usado diretamente. `src/config/.env` é carregado por `config/settings.py`.

## Execução

Confira as opções sem iniciar cargas:

```powershell
python -m src.pipeline_orchestrator --help
```

Execução completa a partir dos lotes JSONL da Bronze (`API_RAW_DIR`):

```powershell
python -m src.pipeline_orchestrator
```

O orquestrador valida os lotes pelos parsers Silver, resolve as estações pelo cadastro Silver (gerado dos JSONs de localização se ainda não existir), grava Parquet Snappy e publica estatísticas, Z-Score, alertas IQR e esquema estrela Gold. Não precisa de SQL Server. Para replicar também no modelo 3FN, use `--carregar-sql`: exige schema, parâmetros e estações cadastrados, e não há transação distribuída entre SQL e Parquet.

Regenerar produtos Gold apenas a partir da Silver:

```powershell
python -m src.pipeline_orchestrator --apenas-gold
```

Uma janela UTC pode ser informada com `--data-inicio AAAA-MM-DD --data-fim AAAA-MM-DD`; ambas as datas são inclusivas.

## Ingestão e replay

A ingestão REST genérica valida os registros com os contratos Pydantic (`src/bronze/contracts.py`), rejeita e audita os inválidos e grava JSONL append-only com metadados. Esses lotes são a entrada do pipeline:

```powershell
python -m src.ingestion --help
```

O coletor Agritempo mantém seu arquivo cumulativo e também é acionado separadamente:

```powershell
python -m src.bronze.Get_dados
```

Backfill de um intervalo já presente nos JSONs, sem executar coleta de API:

```powershell
python -m src.database.dml.Backfill_Leituras --dataset ambos --data-inicio 2026-09-15 --data-fim 2026-09-18
```

Esse comando grava nos destinos `DB_*` e `SILVER_DIR` normais. Execute primeiro em ambiente isolado quando estiver validando uma mudança.

## Produtos Gold

Relatório descritivo:

```powershell
python -m src.gold.analytics_stat
```

Relatório de alertas por medição e materialização do esquema estrela:

```powershell
python -m src.gold.analytics_stat --analise anomalias
python -m src.gold.analytics_stat --analise star_schema
```

Os quatro Parquets dimensionais são escritos em `data_lakehouse/gold`: `Fato_Medicoes`, `Dim_Estacao`, `Dim_Tempo` e `Dim_Parametro`. A dimensão de tempo inclui ano, mês, dia, trimestre, dia da semana e indicador de dia útil. O Power BI ainda exige conexão do modelo semântico e montagem do dashboard.

## Testes

Validação rápida da estrutura e dos contratos Gold:

```powershell
python -m pytest tests/test_project_layout.py tests/test_quality_stat.py -q
```

Testes focados por camada:

```powershell
python -m pytest tests/bronze -q
python -m pytest tests/silver -q
python -m pytest tests/gold -q
```

Suíte geral:

```powershell
python -m pytest -q
```

As integrações SQL Server são opt-in. Use apenas banco descartável vazio, com nome terminado em `_test`, `_tests`, `_disposable` ou `_scratch`, configurado por `RUN_SQLSERVER_LGPD_TESTS=1` e `SQLSERVER_LGPD_TEST_URL`. Nunca aponte a suíte para o banco operacional.

## Logs e falhas

`LOGS_DIR` recebe logs de execução, tratamento e inserção com timestamp, nível e mensagem. Uma falha do SQL interrompe o pipeline. Se SQL confirmar e a Silver falhar, corrija a causa e repita o mesmo período: as chaves naturais tornam a carga idempotente e a Silver pode ser reparada por replay. Não remova manualmente locks, partições ou arquivos de auditoria durante uma execução.

Para entender o fluxo e as integrações ainda pendentes, consulte [FLUXO_SOLUCAO.md](FLUXO_SOLUCAO.md). Para requisitos, contratos e arquitetura, consulte [README.md](README.md).
