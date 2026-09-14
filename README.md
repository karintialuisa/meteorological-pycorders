# meteorological-pycorders
A aplicação tem como objetivo capturar, tratar, analisar, persistir e disponibilizar dados de estações de monitoramento ambiental, abrangendo qualidade da água e dados meteorológicos.

# Pipeline de Monitoramento e Análise de Dados Ambientais

Projeto Prático Integrador desenvolvido pela equipe PyCorders para capturar, tratar, persistir e analisar dados de estações meteorológicas e de qualidade da água.
Sobre o projeto
A aplicação implementa um pipeline completo em Python para ingestão de dados provenientes de API REST ou arquivo JSON, validação e limpeza dos registros, armazenamento em SQL Server e cálculo de métricas estatísticas. O projeto prioriza modularidade, segurança, governança, testes automatizados e rastreabilidade por meio do Git e do GitHub.
Funcionalidades

O pipeline contempla:

•	Consumo de API REST pública ou leitura de arquivo JSON simulado.
•	Conversão do JSON em listas e dicionários Python.
•	Validação de campos ausentes, nulos, inválidos ou duplicados.
•	Persistência das estações e leituras em banco relacional.
•	Consultas SQL com JOINs, agregações por estação e filtros por período.
•	Cálculo de média, mediana, desvio padrão e intervalo interquartil.
•	Detecção de outliers pela regra de 1,5 × IQR.
•	Exibição dos resultados no terminal ou em relatório textual.
•	Proteção de credenciais por variáveis de ambiente e tratamento de dados conforme a LGPD.

# Tecnologias

•	Python 3.10 ou superior
•	SQL Server
•	Biblioteca de acesso a API HTTP definida pelo projeto
•	Biblioteca de conexão com SQL Server definida pelo projeto
•	python-dotenv
•	pytest
•	Git e GitHub
•	GitHub Copilot como apoio à documentação, testes e otimização

# Arquitetura do projeto

PyCordersMeteorological
│── data/
│   ├── input/
│   └── output/
├── database/
│   ├── ddl/
│   └── dml/
├── reports/
├── src/
│   ├── ingestion/
│   ├── database/
│   ├── analytics/
│   └── main.py
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md

# Responsabilidades dos módulos

•	src/ingestion: captura, leitura, parsing e validação dos dados.
•	src/database: conexão, criação das estruturas e persistência.
•	src/analytics: consultas, métricas estatísticas e identificação de outliers.
•	tests: testes unitários das regras de validação e dos cálculos.
•	database: scripts DDL e DML para reprodução do banco.
•	reports: resultados textuais e materiais da demonstração.
Pré-requisitos
•	Python 3.10 ou superior instalado.
•	Git instalado.
•	Instância acessível do SQL Server.
•	Driver ODBC compatível com o SQL Server.
•	Credenciais para a fonte de dados, quando exigidas.

# Instalação

1.	Clone o repositório:
git clone <URL_DO_REPOSITORIO>
cd PyCordersMeteorological

3.	Crie e ative um ambiente virtual:
python -m venv .venv
.venv\Scripts\activate
No Linux ou macOS, use source .venv/bin/activate.

5.	Instale as dependências:
pip install -r requirements.txt

Configuração

1.	Copie o arquivo de exemplo:
copy .env.example .env
No Linux ou macOS, use cp .env.example .env.

3.	Preencha as variáveis conforme o ambiente:
   
DATA_SOURCE=api
API_URL=<ENDERECO_DA_API>
API_KEY=<CHAVE_SE_NECESSARIA>
DB_SERVER=<SERVIDOR>
DB_NAME=<BANCO>
DB_USER=<USUARIO>
DB_PASSWORD=<SENHA>
DB_DRIVER=<DRIVER_ODBC>

# Execução

1.	Prepare o banco executando os scripts DDL e DML disponíveis na pasta database.
2.	Execute o pipeline principal:
python -m src.main
3.	Consulte no terminal ou na pasta reports os resultados produzidos.
Fluxo de processamento
1.	Coleta das leituras ambientais.
2.	Conversão e normalização do JSON.
3.	Validação e descarte ou correção de registros inconsistentes.
4.	Anonimização ou remoção de identificadores sensíveis.
5.	Persistência nas tabelas estacoes e leituras.
6.	Consulta dos dados persistidos.
7.	Cálculo das métricas estatísticas e identificação de outliers.
8.	Exibição ou geração do relatório textual.
   
# Modelo de dados simplificado

Tabela	Finalidade	Dados principais
estacoes	Armazenar metadados das estações	Identificador anonimizado, nome ou código, localização permitida e tipo
leituras	Armazenar séries temporais ambientais	Estação, data e hora, parâmetro, valor e unidade
Análises estatísticas
Para cada parâmetro ambiental, o sistema calcula média, mediana, desvio padrão e intervalo interquartil. Os valores abaixo de Q1 − 1,5 × IQR ou acima de Q3 + 1,5 × IQR são classificados como possíveis outliers.
Testes
Execute a suíte de testes com:
pytest -v
Os testes devem cobrir os cálculos estatísticos, a regra de outliers, as validações da entrada e os principais cenários de erro.

# Segurança e governança

•	Credenciais e endereços de API são carregados pelo arquivo .env.
•	O arquivo .env não deve ser versionado; somente .env.example deve ficar no repositório.
•	Identificadores pessoais de operadores ou estações devem ser removidos ou anonimizados.
•	Logs e relatórios não devem expor segredos ou dados pessoais.
•	As decisões relacionadas à retenção, minimização e tratamento de dados devem observar os princípios da LGPD.

# Equipe

Integrante	Responsabilidade principal
Jaclin	Coordenação, integração, acompanhamento dos marcos e Pull Request final
Jorge	Ingestão, parsing, validação e tratamento dos dados
Karíntia	Modelagem do banco, scripts DDL/DML e consultas SQL
Wagner	Análise estatística, detecção de outliers e testes unitários
Anderson	Segurança, documentação e apresentação
Cada integrante trabalha em branch própria, mantém commits objetivos e participa da revisão cruzada antes da integração.

# Fluxo Git e contribuição

1.	Atualize a branch principal:
git checkout main
git pull

3.	Crie uma branch de funcionalidade:
git checkout -b feature/nome-da-funcionalidade

5.	Implemente e teste a alteração.
   
7.	Registre um commit objetivo:
git add .
git commit -m "feat: descreve a alteração"

9.	Envie a branch e abra uma Pull Request:
git push -u origin feature/nome-da-funcionalidade

11.	Solicite revisão e faça o merge somente após a validação.
    
# Critérios de conclusão

•	Pipeline executado de ponta a ponta.
•	Banco criado e populado por processo reproduzível.
•	Consultas SQL e análises estatísticas disponíveis.
•	Testes unitários executados com sucesso.
•	Configuração segura e documentação atualizada.
•	Pull Request final revisada e aprovada.

# Licença

Este projeto foi desenvolvido para fins acadêmicos. Caso uma licença seja definida, inclua o arquivo correspondente no repositório e atualize esta seção.
