-- SQL Server. Ajuste a janela UTC; inicio inclusivo e fim exclusivo.
SET NOCOUNT ON;
DECLARE @data_inicio DATETIMEOFFSET = '2026-09-15T00:00:00+00:00';
DECLARE @data_fim DATETIMEOFFSET = '2026-10-17T00:00:00+00:00';

IF OBJECT_ID('tempdb..#dados_analiticos') IS NOT NULL DROP TABLE #dados_analiticos;
IF OBJECT_ID('tempdb..#metricas_analiticas') IS NOT NULL DROP TABLE #metricas_analiticas;

-- A origem textual (como CONDICAO_METEO) e itens sem numero ficam fora.
SELECT l.id AS id_leitura, l.id_estacao, es.nome AS estacao,
    p.id AS id_parametro, p.codigo AS codigo_parametro, p.nome AS parametro,
    p.unidade_medida, SWITCHOFFSET(l.data_leitura, '+00:00') AS data_leitura_utc,
    i.valor_numerico
INTO #dados_analiticos
FROM dbo.leituras l
JOIN dbo.leitura_itens i ON i.id_leitura = l.id
JOIN dbo.parametros p ON p.id = i.id_parametro
JOIN dbo.estacao es ON es.id = l.id_estacao
WHERE i.valor_numerico IS NOT NULL
    AND SWITCHOFFSET(l.data_leitura, '+00:00') >= @data_inicio
    AND SWITCHOFFSET(l.data_leitura, '+00:00') < @data_fim;

WITH valores_com_metricas AS (
    SELECT d.*,
        COUNT(*) OVER (PARTITION BY id_estacao, id_parametro) AS n,
        AVG(CONVERT(float, valor_numerico))
            OVER (PARTITION BY id_estacao, id_parametro) AS media,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY valor_numerico)
            OVER (PARTITION BY id_estacao, id_parametro) AS mediana,
        STDEV(CONVERT(float, valor_numerico))
            OVER (PARTITION BY id_estacao, id_parametro) AS desvio_padrao,
        VAR(CONVERT(float, valor_numerico))
            OVER (PARTITION BY id_estacao, id_parametro) AS variancia,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor_numerico)
            OVER (PARTITION BY id_estacao, id_parametro) AS q1,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor_numerico)
            OVER (PARTITION BY id_estacao, id_parametro) AS q3
    FROM #dados_analiticos d
)
SELECT *, q3 - q1 AS iqr,
    q1 - 1.5 * (q3 - q1) AS limite_inferior_iqr,
    q3 + 1.5 * (q3 - q1) AS limite_superior_iqr
INTO #metricas_analiticas
FROM valores_com_metricas;

-- Resultado 1: uma linha por estação e parâmetro.
SELECT id_estacao, estacao, id_parametro, codigo_parametro, parametro, unidade_medida,
    MAX(n) AS n,
    MAX(media) AS media,
    MAX(mediana) AS mediana,
    MAX(desvio_padrao) AS desvio_padrao_amostral,
    MAX(variancia) AS variancia_amostral,
    MAX(q1) AS q1,
    MAX(q3) AS q3,
    MAX(iqr) AS iqr,
    MAX(limite_inferior_iqr) AS limite_inferior_iqr,
    MAX(limite_superior_iqr) AS limite_superior_iqr
FROM #metricas_analiticas
GROUP BY id_estacao, estacao, id_parametro, codigo_parametro, parametro, unidade_medida
ORDER BY estacao, codigo_parametro;

-- Resultado 2: uma linha por item numérico, com indicadores IQR e |Z| >= 3.
WITH escores AS (
    SELECT m.*,
        CASE WHEN n >= 2 AND desvio_padrao > 0
            THEN (CONVERT(float, valor_numerico) - media) / desvio_padrao
            ELSE NULL
        END AS z_score
    FROM #metricas_analiticas m
)
SELECT id_leitura, id_estacao, estacao, id_parametro, codigo_parametro,
    parametro, unidade_medida, data_leitura_utc, valor_numerico AS valor,
    n, media, desvio_padrao AS desvio_padrao_amostral,
    q1, q3, iqr, limite_inferior_iqr, limite_superior_iqr, z_score,
    CONVERT(bit, CASE WHEN valor_numerico < limite_inferior_iqr
        OR valor_numerico > limite_superior_iqr THEN 1 ELSE 0 END) AS anomalia_iqr,
    CONVERT(bit, CASE WHEN z_score IS NOT NULL AND ABS(z_score) >= 3.0
        THEN 1 ELSE 0 END) AS anomalia_zscore
FROM escores
ORDER BY estacao, codigo_parametro, data_leitura_utc, id_leitura;

DROP TABLE #metricas_analiticas;
DROP TABLE #dados_analiticos;
SET NOCOUNT OFF;