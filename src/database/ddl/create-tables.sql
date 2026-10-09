-- Cria a estrutura relacional do banco de dados monitoramento.
-- O script recria as tabelas operacionais listadas no bloco DROP e cria, se ausentes,
-- as entidades de localização, leituras, operadores e catálogo LGPD.
-- A ordem das operações respeita as dependências entre as chaves estrangeiras.

USE monitoramento
GO

DROP TABLE IF EXISTS leitura_meteorologica;
DROP TABLE IF EXISTS qualidade_agua;

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

    CREATE INDEX idx_estacao_status
        ON estacao (status);
END;
GO

IF COL_LENGTH('dbo.estacao', 'codigo_origem') IS NULL
    ALTER TABLE dbo.estacao ADD codigo_origem VARCHAR(50) NULL;
GO

-- ============================================================
-- ASSUNTO: LEITURA DA QUALIDADE DA ÁGUA
-- ============================================================

IF OBJECT_ID('dbo.qualidade_agua', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.qualidade_agua (
        id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
        id_leitura_origem       VARCHAR(100) NULL,
        id_estacao              BIGINT NOT NULL,
        data_leitura            DATETIMEOFFSET NOT NULL,
        temperatura_agua        NUMERIC(8,3),
        ph                      NUMERIC(5,3),
        oxigenio                NUMERIC(10,3),
        condutividade           NUMERIC(12,3),
        criado_em               DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

        CONSTRAINT fk_qualidade_estacao
            FOREIGN KEY (id_estacao)
            REFERENCES estacao(id)
            ON DELETE CASCADE,

        CONSTRAINT ck_qualidade_ph
            CHECK (ph IS NULL OR ph BETWEEN 0 AND 14),

        CONSTRAINT ck_qualidade_oxigenio
            CHECK (oxigenio IS NULL OR oxigenio >= 0),

        CONSTRAINT ck_qualidade_condutividade
            CHECK (condutividade IS NULL OR condutividade >= 0)
        );
    END;
GO

-- ============================================================
-- ASSUNTO: METEOROLOGIA OBSERVADA
-- ============================================================

IF OBJECT_ID('dbo.leitura_meteorologica', 'U') IS NULL
BEGIN
CREATE TABLE dbo.leitura_meteorologica (
    id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_cidade               BIGINT NOT NULL,
    id_estacao              BIGINT NOT NULL,
    temperatura_ar          NUMERIC(8,3) NOT NULL,
    umidade                 NUMERIC(5,2) NOT NULL,
    chuva                   NUMERIC(10,3) NOT NULL,
    vento                   NUMERIC(10,3) NOT NULL,
    condicao                VARCHAR(100) NOT NULL,
    data_leitura            DATETIMEOFFSET NOT NULL, 
    criado_em               DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

    CONSTRAINT fk_meteorologica
        FOREIGN KEY (id_cidade)
        REFERENCES cidade(id),

    CONSTRAINT fk_meteorologica_estacao
        FOREIGN KEY (id_estacao)
        REFERENCES estacao(id)
        ON DELETE CASCADE,

    CONSTRAINT ck_meteo_umidade
        CHECK (umidade IS NULL OR umidade BETWEEN 0 AND 100),

    CONSTRAINT ck_meteo_chuva
        CHECK (chuva IS NULL OR chuva >= 0),

    CONSTRAINT ck_meteo_vento
        CHECK (vento IS NULL OR vento >= 0)

    );

    CREATE INDEX idx_leitura_meteorologica_id
    ON leitura_meteorologica (id_cidade);
END;
GO

-- ============================================================
-- ASSUNTO: OPERADORES
-- Receber registros de uma fonte aprovada, protegê-los antes da gravação e persistir os campos protegidos.
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

IF COL_LENGTH('dbo.operadores', 'status') IS NULL
    ALTER TABLE dbo.operadores ADD status BIT NULL;
GO

IF COL_LENGTH('dbo.operadores', 'id_estacao') IS NULL
    ALTER TABLE dbo.operadores ADD id_estacao BIGINT NULL;
GO

-- ============================================================
-- ASSUNTO: LGPD
-- cadastrar de forma idempotente os metadados dos dois campos.
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