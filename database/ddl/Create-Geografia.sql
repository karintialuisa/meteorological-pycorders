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
    estado_id       BIGINT NOT NULL,
    codigo_ibge     INTEGER UNIQUE,
    nome            VARCHAR(150) NOT NULL,
    woeid           BIGINT,
    latitude        NUMERIC(9,6),
    longitude       NUMERIC(9,6),
    timezone        VARCHAR(50),
    criado_em       DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),

    CONSTRAINT fk_cidade_estado
        FOREIGN KEY (estado_id)
        REFERENCES estado(id),

    CONSTRAINT uq_cidade_estado_nome
        UNIQUE (estado_id, nome)
);
GO

CREATE INDEX idx_cidade_estado_id
    ON cidade (estado_id);
GO

CREATE INDEX idx_cidade_codigo_ibge
    ON cidade (codigo_ibge);
GO
