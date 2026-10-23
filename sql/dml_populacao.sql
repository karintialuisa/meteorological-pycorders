SET NOCOUNT ON;

INSERT INTO dbo.parametros (codigo, nome, unidade_medida)
SELECT origem.codigo, origem.nome, origem.unidade_medida
FROM (VALUES
    ('TEMP_AGUA', 'Temperatura da agua', 'Celsius'),
    ('TEMP_AR', 'Temperatura do ar', 'Celsius'),
    ('PH', 'Potencial hidrogenionico', 'pH'),
    ('OD', 'Oxigenio dissolvido', 'mg/L'),
    ('COND_ELETRICA', 'Condutividade eletrica', 'uS/cm'),
    ('TURBIDEZ', 'Turbidez da agua', 'NTU'),
    ('UMIDADE', 'Umidade relativa do ar', '%'),
    ('CHUVA', 'Precipitacao', 'mm'),
    ('VENTO', 'Velocidade do vento', 'km/h'),
    ('CONDICAO_METEO', 'Condicao meteorologica', 'descricao')
) AS origem(codigo, nome, unidade_medida)
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.parametros AS destino
    WHERE destino.codigo = origem.codigo
);
