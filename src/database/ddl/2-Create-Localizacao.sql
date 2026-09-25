DROP TABLE IF EXISTS estacao;   
DROP TABLE IF EXISTS cidade;
DROP TABLE IF EXISTS estado;

-- ============================================================
-- ASSUNTO: GEOGRAFIA / LOCALIZAÇÃO FÍSICA
-- ============================================================

CREATE TABLE estado (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_ibge INT NOT NULL UNIQUE,
    sigla CHAR(2) NOT NULL UNIQUE,
    nome VARCHAR(100) NOT NULL UNIQUE,
    criado_em DATETIME2 NOT NULL DEFAULT SYSDATETIME()
);

CREATE TABLE cidade (
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
GO

CREATE INDEX idx_cidade_estado_id
    ON cidade (id_estado);
GO

CREATE INDEX idx_cidade_codigo_ibge
    ON cidade (codigo_ibge);
GO

-- ======================================================================
-- ASSUNTO: CADASTRO DAS ESTAÇÕES - INFORMAÇÕES SOBRE ESTAÇÕES AMBIENTAIS
-- ======================================================================

CREATE TABLE estacao (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_externo      VARCHAR(100) NOT NULL UNIQUE,
    nome                VARCHAR(200) NOT NULL,
    tipo                VARCHAR(100) NOT NULL,
    status              BIT,
    cidade_id           BIGINT NOT NULL,
    descricao           VARCHAR(MAX),
    data_instalacao     DATE,
    criado_em           DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

    CONSTRAINT fk_estacao_cidade
        FOREIGN KEY (cidade_id)
        REFERENCES cidade(id),

    CONSTRAINT ck_estacao_status
        CHECK (status IN (0, 1))
);
GO

CREATE INDEX idx_estacao_cidade_id
    ON estacao (cidade_id);
GO

CREATE INDEX idx_estacao_status
    ON estacao (status);
GO