-- ============================================================
-- ASSUNTO: METEOROLOGIA OBSERVADA
-- ============================================================
USE monitoramento
GO

CREATE TABLE leitura_meteorologica (
    id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_cidade               BIGINT NOT NULL UNIQUE,
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

    CONSTRAINT ck_meteo_umidade
        CHECK (umidade IS NULL OR umidade BETWEEN 0 AND 100),

    CONSTRAINT ck_meteo_chuva
        CHECK (chuva IS NULL OR chuva >= 0),

    CONSTRAINT ck_meteo_vento
        CHECK (vento IS NULL OR vento >= 0),

);
GO

CREATE INDEX idx_leitura_meteorologica_id
    ON leitura_meteorologica (id_cidade);
GO
 