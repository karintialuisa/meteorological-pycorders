# Explicação das alterações

Este documento resume as mudanças realizadas no pipeline meteorológico, na configuração do projeto e nos testes automatizados.

## Configuração centralizada

As configurações da aplicação ficam em `src/config/`. O módulo `settings.py` carrega `src/config/.env` e concentra as operações comuns:

- `get_env()` lê variáveis obrigatórias do ambiente.
- `get_path()` transforma caminhos relativos configurados em caminhos absolutos a partir da raiz do projeto.
- `create_db_engine()` cria a conexão SQL Server usando servidor, porta, banco e autenticação do `.env`.
- `configure_logging()` configura a saída de logs para o console e para `logs/execucao_relatorio.log`.

O driver ODBC continua fixo como `ODBC Driver 17 for SQL Server`, pois depende dessa configuração para conectar neste ambiente. Os demais parâmetros de conexão vêm do `.env`. A antiga implementação separada `src/config/logging_config.py` foi removida; agora há um único módulo de configuração.

Os caminhos dos arquivos de leituras, estados, municípios e estações também vêm do `.env`. Assim, parsers, relatório e API não dependem de caminhos montados diretamente a partir da localização do código.

## Cargas e dados

Os três scripts em `src/database/dml/` fazem a carga de localização, qualidade da água e leituras meteorológicas. As leituras são associadas às chaves das tabelas de localização antes de serem inseridas. A inserção de estados também foi corrigida para renomear as colunas conforme o esquema SQL.

O dashboard compartilha a mesma função de criação da conexão SQL. O menu principal e os scripts individuais usam a configuração comum de logging.

## Testes

`tests/test_database_insertions.py` usa dados manuais e SQLite em memória para exercitar as inserções nas tabelas `estado`, `cidade`, `estacao`, `qualidade_agua` e `leitura_meteorologica`. Os testes verificam também a resolução de caminhos configurados pelo ambiente.

Esses testes não conectam ao SQL Server e não alteram dados do banco real. Para executá-los a partir da raiz do repositório:

```bash
python -m pytest tests -v
```

## Arquivos alterados

- `.gitignore`: ignora o `.env` local em `src/config/` e arquivos de log gerados.
- `README.md`: documenta a estrutura atual, configuração, execução e testes.
- `Readme_explain.md`: este resumo das alterações.
- `TESTE.PY`: atualiza o import do logging após a mudança de localização.
- `src/__init__.py` e `src/config/__init__.py`: identificam os diretórios como pacotes Python.
- `src/config/.env`: mantém parâmetros locais e caminhos configuráveis para os arquivos JSON; não deve ser versionado.
- `src/config/requirements.txt`: lista dependências da aplicação e de testes.
- `src/config/settings.py`: reúne leitura do `.env`, resolução de caminhos, conexão ao SQL Server e configuração de logs.
- `src/main.py`: importa configuração e logging pelo módulo unificado.
- `src/analytics/Relatorios_estatisticos.py`: lê os JSONs configurados e usa a função compartilhada de logging.
- `src/api/main.py`: carrega os JSONs pelos caminhos configurados no ambiente.
- `src/dashboard.py`: obtém a engine SQL pela configuração comum.
- `src/database/dml/Insert_Localizacao.py`: usa a conexão compartilhada e insere estados com os nomes de coluna esperados pelo banco.
- `src/database/dml/Insert_Leituras_ambiental.py` e `Insert_Leituras_Meteorologica.py`: usam a conexão e o logging compartilhados.
- `src/ingestion/leituras/Parse_LeituraAmbiental.py` e `Parse_LeituraMetereologica.py`: leem os arquivos indicados no `.env`.
- `src/ingestion/localizacao/Parse_localizacao_JSON.py`: obtém do `.env` os caminhos de estados, municípios e estações.
- `tests/test_database_insertions.py`: testa as cargas com SQLite em memória.

## Validação realizada

A suíte de testes de inserção foi executada com sucesso: quatro testes aprovados. Também foram verificadas a compilação e as importações dos módulos alterados. A conexão real e a execução das cargas no SQL Server não fazem parte desses testes automatizados.