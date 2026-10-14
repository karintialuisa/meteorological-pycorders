
USE monitoramento
GO

-- REFERENCIAS DE ENTREGA: projeto_final.pdf / features.csv
-- Instalacao nova. IF OBJECT_ID nao migra constraints de tabelas existentes.
-- Atualizacoes exigem revisao de schema e Migrar_Leituras explicitamente autorizado.
-- PDF secao 2, "leituras temporais de parametros" -> features.csv IDs 4-9.
-- PDF secao 3.3, "Parametros (Tabela de Dominio)" -> features.csv ID 39.
-- PDF secao 3.3, "Leituras (Tabela Transacional / Cabecalho)" -> ID 40.
-- PDF secao 3.3, "Parametros Leitura_Itens (Tabela Associativa N:M)" -> ID 41.
-- PDF secao 3.3, "Operadores (Tabela Cadastral)" -> ID 38.
--
/* ESPECIFICACAO DO MODELO NORMALIZADO (decisao da etapa 2; nao executavel):
-- dbo.parametros: 
    id BIGINT IDENTITY PK; 
    codigo VARCHAR(50) NOT NULL UNIQUE;
    nome VARCHAR(150) NOT NULL; 
    unidade_medida VARCHAR(50) NOT NULL;
-- dbo.Leituras: 
    id BIGINT IDENTITY PK; 
    origem VARCHAR(30) NOT NULL;
    chave_origem VARCHAR(150) NOT NULL; 
    id_estacao BIGINT NOT NULL FK 
    dbo.estacao(id);
    id_operador BIGINT NULL FK dbo.operadores(id); 
    data_leitura DATETIMEOFFSET NOT NULL;
    UNIQUE (origem, chave_origem);

A origem separa os dois contratos legados;
-- chave_origem usa id_leitura_origem para agua e serializacao sem ambiguidade
-- de codigo_origem da estacao + instante UTC para meteorologia.

-- dbo.Leitura_Itens: 
    id_leitura BIGINT NOT NULL FK dbo.Leituras(id) ON DELETE CASCADE;
    id_parametro BIGINT NOT NULL FK dbo.parametros(id); 
    valor_numerico NUMERIC(18,6) NULL;
    valor_texto VARCHAR(200) NULL; 
    CHECK (
        (valor_numerico IS NOT NULL AND valor_texto IS NULL) OR
        (valor_numerico IS NULL AND valor_texto IS NOT NULL)
    ) -- exige exatamente um dos dois valores;
    PRIMARY KEY (id_leitura, id_parametro) 
    
impede repetir o mesmo parametro no evento.
qualidade_agua e leitura_meteorologica sao os contratos legados de leitura.
Na migracao, parsers, chaves naturais e interfaces de consulta devem ser preservados; 
a DML grava o cabecalho e seus itens em uma transacao.
As tabelas legadas sao arquivadas pela migracao explicita, sem dual-write.
Consultas mantidas usam o modelo 3FN; relatorios e dashboard foram retirados.
Fazer backfill idempotente usando as chaves naturais atuais antes da troca; 
validar cobertura de consultas.
id_operador fica NULL para leituras automaticas/historicas sem operador conhecido;
estacao, instante, parametro e valor do item permanecem obrigatorios.*/

-- ============================================================
-- ASSUNTO: GEOGRAFIA / LOCALIZAÇÃO FÍSICA
-- ============================================================
IF OBJECT_ID('dbo.estado', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.estado (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        codigo_ibge INT NOT NULL UNIQUE,
        sigla CHAR(2) NOT NULL UNIQUE,
        nome VARCHAR(100) NOT NULL UNIQUE,
        criado_em DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
END;
GO

IF OBJECT_ID('dbo.cidade', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.cidade (
        id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        id_estado       BIGINT NOT NULL,
        codigo_ibge     INTEGER UNIQUE,
        nome            VARCHAR(150) NOT NULL,
        criado_em       DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT fk_cidade_estado
            FOREIGN KEY (id_estado)
            REFERENCES estado(id),

        CONSTRAINT uq_cidade_estado_nome
            UNIQUE (id_estado, nome)
    );

    CREATE INDEX idx_cidade_estado_id
        ON cidade (id_estado);

    CREATE INDEX idx_cidade_codigo_ibge
    ON cidade (codigo_ibge);
END;
GO

-- ======================================================================
-- ASSUNTO: CADASTRO DAS ESTAÇÕES - INFORMAÇÕES SOBRE ESTAÇÕES AMBIENTAIS
-- ======================================================================

IF OBJECT_ID('dbo.estacao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.estacao (
        id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
        codigo_origem       VARCHAR(50) NOT NULL,
        nome                VARCHAR(200) NOT NULL,
        status              BIT,
        id_cidade           BIGINT NOT NULL,
        id_estado           BIGINT NOT NULL,
        criado_em           DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT fk_estacao_cidade
            FOREIGN KEY (id_cidade)
            REFERENCES cidade(id),
        CONSTRAINT fk_estacao_estado
            FOREIGN KEY (id_estado)
            REFERENCES estado(id),
        CONSTRAINT uq_estacao_codigo_origem UNIQUE (codigo_origem),

        CONSTRAINT ck_estacao_status
            CHECK (status IN (0, 1))
    );

    CREATE INDEX idx_estacao_cidade_id
    ON estacao (id_cidade);
END;
GO

-- ============================================================
-- ASSUNTO: OPERADORES
-- Receber registros de uma fonte aprovada, protegê-los antes da gravação e persistir os campos protegidos.
-- Referencia: projeto_final.pdf, secao 1 (origem dos dados) -> features.csv ID 10;
-- secao 3.3 (tabela cadastral) -> ID 38; secao 3.2 (LGPD de operadores) -> IDs 32-34.
-- ============================================================

IF OBJECT_ID('dbo.operadores', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.operadores (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        cpf_hash CHAR(64) NOT NULL,
        nome_completo_cifrado VARCHAR(MAX) NOT NULL,
        status BIT,
        id_estacao BIGINT NOT NULL,
        criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT uq_operadores_cpf_hash UNIQUE (cpf_hash),
        CONSTRAINT ck_operadores_cpf_hash_length CHECK (LEN(cpf_hash) = 64),

        CONSTRAINT fk_operadores_estacao
            FOREIGN KEY (id_estacao)
            REFERENCES estacao(id)
            ON DELETE CASCADE
    );
END;
GO

-- ============================================================
-- ASSUNTO: PARAMETROS DE MEDICAO - TABELA DE DOMINIO
-- Referencia: projeto_final.pdf, secao 3.3; features.csv ID 39.
-- Codigos estaveis sao resolvidos pela carga em Insert_Parametros.py.
-- ============================================================
IF OBJECT_ID('dbo.parametros', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.parametros (
        id BIGINT IDENTITY(1,1) NOT NULL,
        codigo VARCHAR(50) NOT NULL,
        nome VARCHAR(150) NOT NULL,
        unidade_medida VARCHAR(50) NOT NULL,
        criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT pk_parametros PRIMARY KEY (id),
        CONSTRAINT uq_parametros_codigo UNIQUE (codigo),
        CONSTRAINT ck_parametros_codigo_nao_vazio
            CHECK (LEN(LTRIM(RTRIM(codigo))) > 0),
        CONSTRAINT ck_parametros_nome_nao_vazio
            CHECK (LEN(LTRIM(RTRIM(nome))) > 0),
        CONSTRAINT ck_parametros_unidade_nao_vazia
            CHECK (LEN(LTRIM(RTRIM(unidade_medida))) > 0)
    );
END;
GO

-- ============================================================
-- ASSUNTO: LEITURAS - CABECALHO TRANSACIONAL
-- Referencia: projeto_final.pdf, secao 3.3; features.csv ID 40.
-- A DML resolve codigo_origem da estacao e cpf_hash do operador.
-- ============================================================
IF OBJECT_ID('dbo.leituras', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.leituras (
        id BIGINT IDENTITY(1,1) NOT NULL,
        origem VARCHAR(30) NOT NULL,
        chave_origem VARCHAR(150) NOT NULL,
        id_estacao BIGINT NOT NULL,
        id_operador BIGINT NULL,
        data_leitura DATETIMEOFFSET NOT NULL,
        criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT pk_leituras PRIMARY KEY (id),
        CONSTRAINT uq_leituras_origem_chave UNIQUE (origem, chave_origem),
        CONSTRAINT ck_leituras_origem
            CHECK (origem IN ('qualidade_agua', 'leitura_meteorologica')),
        CONSTRAINT ck_leituras_chave_origem_nao_vazia
            CHECK (LEN(LTRIM(RTRIM(chave_origem))) > 0),
        CONSTRAINT fk_leituras_estacao
            FOREIGN KEY (id_estacao)
            REFERENCES dbo.estacao(id),
        CONSTRAINT fk_leituras_operador
            FOREIGN KEY (id_operador)
            REFERENCES dbo.operadores(id)
    );

    CREATE INDEX idx_leituras_estacao_data
        ON dbo.leituras (id_estacao, data_leitura);
END;
GO

-- ============================================================
-- ASSUNTO: LEITURA_ITENS - ASSOCIACAO LEITURA/PARAMETRO
-- Referencia: projeto_final.pdf, secao 3.3; features.csv ID 41.
-- A PK composta impede repetir um parametro no mesmo evento de leitura.
-- ============================================================
IF OBJECT_ID('dbo.leitura_itens', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.leitura_itens (
        id_leitura BIGINT NOT NULL,
        id_parametro BIGINT NOT NULL,
        valor_numerico NUMERIC(18,6) NULL,
        valor_texto VARCHAR(200) NULL,
        criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT pk_leitura_itens PRIMARY KEY (id_leitura, id_parametro),
        CONSTRAINT ck_leitura_itens_um_valor
            CHECK (
                (valor_numerico IS NOT NULL AND valor_texto IS NULL)
                OR (valor_numerico IS NULL AND valor_texto IS NOT NULL)
            ),
        CONSTRAINT ck_leitura_itens_texto_nao_vazio
            CHECK (valor_texto IS NULL OR LEN(LTRIM(RTRIM(valor_texto))) > 0),
        CONSTRAINT fk_leitura_itens_leitura
            FOREIGN KEY (id_leitura)
            REFERENCES dbo.leituras(id)
            ON DELETE CASCADE,
        CONSTRAINT fk_leitura_itens_parametro
            FOREIGN KEY (id_parametro)
            REFERENCES dbo.parametros(id)
    );

    CREATE INDEX idx_leitura_itens_parametro
        ON dbo.leitura_itens (id_parametro);
END;
GO

-- ============================================================
-- ASSUNTO: LGPD
-- cadastrar de forma idempotente os metadados dos dois campos.
-- Referencia: projeto_final.pdf, secao 3.2 (LGPD) -> features.csv ID 32.
-- ============================================================

IF OBJECT_ID('dbo.catalogo_dados', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.catalogo_dados (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        schema_name VARCHAR(128) NOT NULL,
        tabela VARCHAR(128) NOT NULL,
        campo_logico VARCHAR(128) NOT NULL,
        coluna_armazenada VARCHAR(128) NOT NULL,
        classificacao VARCHAR(50) NOT NULL,
        finalidade VARCHAR(300) NOT NULL,
        protecao VARCHAR(100) NOT NULL,
        politica_acesso VARCHAR(300) NOT NULL,
        criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT uq_catalogo_campo_logico
            UNIQUE (schema_name, tabela, campo_logico),
        CONSTRAINT ck_catalogo_classificacao
            CHECK (classificacao = 'Dado pessoal')
    );
END;
GO