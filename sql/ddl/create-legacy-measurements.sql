USE monitoramento
GO

-- Somente fixture de homologacao pre-migracao. Nao usar em instalacao nova.
CREATE TABLE dbo.qualidade_agua (
    id BIGINT IDENTITY PRIMARY KEY,
    id_leitura_origem VARCHAR(100) NOT NULL,
    id_estacao BIGINT NOT NULL,
    data_leitura DATETIMEOFFSET NOT NULL,
    temperatura_agua NUMERIC(8,3) NULL,
    ph NUMERIC(5,3) NULL,
    oxigenio NUMERIC(10,3) NULL,
    condutividade NUMERIC(12,3) NULL,
    turbidez NUMERIC(12,3) NULL,
    criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    CONSTRAINT fk_qualidade_estacao FOREIGN KEY (id_estacao)
        REFERENCES dbo.estacao(id) ON DELETE CASCADE,
    CONSTRAINT uq_qualidade_agua_id_leitura_origem UNIQUE (id_leitura_origem),
    CONSTRAINT ck_qualidade_ph CHECK (ph IS NULL OR ph BETWEEN 0 AND 14),
    CONSTRAINT ck_qualidade_oxigenio CHECK (oxigenio IS NULL OR oxigenio >= 0),
    CONSTRAINT ck_qualidade_condutividade CHECK (condutividade IS NULL OR condutividade >= 0),
    CONSTRAINT ck_qualidade_turbidez CHECK (turbidez IS NULL OR turbidez >= 0)
);
GO
CREATE TABLE dbo.leitura_meteorologica (
    id BIGINT IDENTITY PRIMARY KEY,
    id_cidade BIGINT NOT NULL,
    id_estacao BIGINT NOT NULL,
    temperatura_ar NUMERIC(8,3) NOT NULL,
    umidade NUMERIC(5,2) NOT NULL,
    chuva NUMERIC(10,3) NOT NULL,
    vento NUMERIC(10,3) NOT NULL,
    condicao VARCHAR(100) NOT NULL,
    data_leitura DATETIMEOFFSET NOT NULL,
    criado_em DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    CONSTRAINT fk_meteorologica FOREIGN KEY (id_cidade) REFERENCES dbo.cidade(id),
    CONSTRAINT fk_meteorologica_estacao FOREIGN KEY (id_estacao)
        REFERENCES dbo.estacao(id) ON DELETE CASCADE,
    CONSTRAINT uq_leitura_meteorologica_estacao_data UNIQUE (id_estacao, data_leitura),
    CONSTRAINT ck_meteo_umidade CHECK (umidade BETWEEN 0 AND 100),
    CONSTRAINT ck_meteo_chuva CHECK (chuva >= 0),
    CONSTRAINT ck_meteo_vento CHECK (vento >= 0)
);
CREATE INDEX idx_leitura_meteorologica_id ON dbo.leitura_meteorologica(id_cidade);
GO
