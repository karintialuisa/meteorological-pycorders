# Runbook operacional

Execute os comandos a partir da raiz do repositório. As cargas escrevem no SQL e no Data Lakehouse configurados; confira ambiente, origem e destino antes de executar.

## Preparação

1. Crie e ative um ambiente virtual; instale as dependências com `python -m pip install -r config/requirements.txt`.
2. Copie `config/.env.example` para `config/.env` somente se ainda não existir configuração local. Execute os comandos a partir da raiz, mesmo com o README em `config/`.
3. Configure `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_TRUSTED_CONNECTION`, `LOGS_DIR`, `SILVER_DIR`, `API_RAW_DIR` e `AGRITEMPO_RAW_DIR`. As chaves HMAC/Fernet e tokens devem ser valores locais reais, nunca commitados.
4. Para banco novo, crie o database com `sql/ddl/create-database.sql` apenas se ainda não existir; depois execute `sql/ddl_banco_relacional.sql`. Popule o domínio de parâmetros com `sql/dml_populacao.sql` ou com `python -m src.database.dml.Insert_Parametros`.
5. Cadastre estados, municípios e estações antes das leituras. A carga de localização existente pode limpar ou inserir dados conforme seu modo configurado; revise o módulo e o banco-alvo antes de executá-la.

## Estrutura e caminhos

```text
config/
  .env.example
  requirements.txt
  README.md
  settings.py
main.py
RUNBOOK.md
FLUXO_SOLUCAO.md
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

Destinos padrão: `data_lakehouse/bronze`, `data_lakehouse/silver` e `data_lakehouse/gold`. Um caminho relativo nas variáveis de ambiente é resolvido a partir da raiz do repositório; caminho absoluto é usado diretamente. `config/.env` é carregado por `config/settings.py`.

## Execução

### Orquestrador principal: menu interativo

O ponto de entrada principal da aplicação é [main.py](main.py). Execute na raiz do repositório, com o ambiente virtual ativo:

```powershell
python main.py
```

O menu permanece aberto até selecionar a opção 4:

| Opção | Menu | O que executa |
| --- | --- | --- |
| 1 | ETL JSON -> BD | Localização, parâmetros, leituras ambientais e leituras meteorológicas, nessa ordem; as cargas de leituras confirmam o SQL antes de publicar a Silver. |
| 2 | Coletar meteorologia Agritempo -> JSON | Coletor Agritempo, sem iniciar as cargas SQL ou gerar a Gold. |
| 3 | Cadastrar parâmetros, catálogo LGPD e operadores | Cargas de parâmetros, catálogo LGPD e operadores, nessa ordem. |
| 4 | Cancelar Operação | Encerra o menu; não cancela uma carga já em execução nem desfaz transações confirmadas. |
| 5 | Gerar estatísticas descritivas da Silver -> CSV | Rotina descritiva Gold a partir da Silver. |
| 6 | Validar anomalias por Z-Score -> CSV | Rotina Gold com `--analise zscore`. |
| 7 | Reprocessar leituras historicas por periodo (backfill) | Solicita dataset, início UTC inclusivo, fim UTC exclusivo e se deve reconstruir a Silver a partir do SQL. |

A opção 1 resolve os scripts pelas variáveis `INSERT_LOCALIZACAO`, `INSERT_LEITURA_AMBIENTAL` e `INSERT_LEITURA_METEOROLOGICA` de `config/.env`; a carga de parâmetros usa o caminho fixo do projeto. As opções 1 e 3 interrompem a sequência se um script retornar falha, sem reverter etapas já confirmadas. A opção 3 exige estações previamente cadastradas para associar operadores. O menu não dispara o pipeline JSONL abaixo nem gera todos os produtos Gold automaticamente após a opção 1.

**Saída dos scripts pelo menu:** atualmente, `executar_script()` usa `subprocess.run(..., capture_output=True)`. Por isso, o menu mostra o início de cada script, mas exibe sua saída capturada somente quando ele termina. Para acompanhar a carga meteorológica durante a execução, execute o módulo diretamente, conforme a seção [Carga meteorológica direta](#carga-meteorológica-direta), ou acompanhe o arquivo de inserção em outro terminal:

```powershell
Get-Content .\logs\insercao_dados.log -Tail 20 -Wait
```

Ajuste o caminho se `LOGS_DIR` não for `logs`. Use `Ctrl+C` nesse terminal para encerrar apenas o acompanhamento do arquivo. Os novos logs de progresso não alteram a captura de saída feita pelo menu.

### Pipeline de lotes REST JSONL

O módulo `src.pipeline_orchestrator` é uma entrada distinta do menu principal, voltada aos lotes JSONL da Bronze e à publicação dos produtos Gold.

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

O backfill usa início inclusivo e fim exclusivo: esse exemplo seleciona os dias 15, 16 e 17 em UTC, diferentemente da janela inclusiva do orquestrador. Esse comando grava nos destinos `DB_*` e `SILVER_DIR` normais. Execute primeiro em ambiente isolado quando estiver validando uma mudança.

## Carga meteorológica direta

Para carregar o JSON definido por `INGESTION_LEITURA_METEOROLOGICA` no modelo SQL 3FN e, depois, publicar as leituras aprovadas na Silver:

```powershell
python -m src.database.dml.Insert_Leituras_Meteorologica
```

O comando exige banco, parâmetros e estações cadastrados. Ele não coleta dados de API, não lê os lotes REST JSONL e não gera a Gold. Confira `DB_*`, `SILVER_DIR` e o caminho do JSON em `config/.env` antes de executar.

O terminal e `LOGS_DIR/insercao_dados.log` mostram:

- Início e duração do tratamento do JSON Bronze.
- Conexão/validação do legado e início das transações SQL.
- Progresso SQL com processados/total, percentual, aceitos, rejeitados, tempo decorrido, leituras por segundo e tempo restante estimado.
- Início/fim da persistência Silver e duração total da carga.

O progresso é emitido na primeira leitura, a cada 100 leituras, na última leitura ou quando pelo menos cinco segundos se passam desde a atualização anterior. A verificação ocorre entre leituras: não é um heartbeat enquanto uma consulta, conexão ou lock estiver bloqueado. A estimativa restante refere-se somente à etapa SQL e pode variar ao longo da carga. As contagens SQL partem dos registros devolvidos pelo parser; descartes anteriores têm seus próprios logs.

Cada leitura usa uma transação para o cabeçalho e as cinco medições, com consultas de validação e solicitações de locks. Essas operações repetidas podem tornar cargas grandes lentas; concorrência no banco também pode acrescentar espera. Os logs dão visibilidade, mas não alteram a estratégia de inserção nem comprovam, por si só, o gargalo do servidor. Aceitos incluem replays compatíveis, não apenas novas inserções.

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

As integrações SQL Server são opt-in e carregam `config/.env`. Use apenas banco descartável vazio, com nome terminado em `_test`, `_tests`, `_disposable` ou `_scratch`, configurado por `RUN_SQLSERVER_LGPD_TESTS=1` e `SQLSERVER_LGPD_TEST_URL`. Nunca aponte a suíte para o banco operacional. Para validar localmente sem SQL Server, desabilite a integração somente no processo:

```powershell
$env:RUN_SQLSERVER_LGPD_TESTS='0'
python -m pytest tests/test_database_loading.py tests/silver/test_parsers.py -q
```

Esse recorte cobre os logs de andamento com banco simulado e os parsers. Testes ignorados não equivalem à homologação SQL. Restaure o valor anterior da variável ao terminar, se precisar executar integrações no mesmo terminal.

## Logs e falhas

`LOGS_DIR` recebe logs de execução, tratamento e inserção com timestamp, nível e mensagem. Uma falha do SQL interrompe o pipeline. Se SQL confirmar e a Silver falhar, corrija a causa e repita o mesmo período: as chaves naturais tornam a carga idempotente e a Silver pode ser reparada por replay. Não remova manualmente locks, partições ou arquivos de auditoria durante uma execução.

Para entender o fluxo e as integrações ainda pendentes, consulte [FLUXO_SOLUCAO.md](FLUXO_SOLUCAO.md). Para requisitos, contratos e arquitetura, consulte [config/README.md](config/README.md).
