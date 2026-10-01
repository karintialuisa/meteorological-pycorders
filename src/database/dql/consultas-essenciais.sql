USE monitoramento;
GO

-- Intervalo semiaberto: inclui o inicio e exclui o fim.
-- Ajuste os valores conforme o periodo desejado.
DECLARE @data_inicio DATETIMEOFFSET = '2026-09-15T00:00:00-03:00';
DECLARE @data_fim DATETIMEOFFSET = '2026-09-18T00:00:00-03:00';

-- 1. Quantidade e medias das leituras de qualidade da agua por estacao.
-- LEFT JOIN mantem no resultado estacoes sem leitura no intervalo.
SELECT
    es.id AS id_estacao,
    es.nome AS estacao,
    ci.nome AS cidade,
    uf.sigla AS estado,
    COUNT(qa.id) AS quantidade_leituras,
    AVG(qa.temperatura_agua) AS temperatura_media_agua,
    AVG(qa.ph) AS ph_medio,
    AVG(qa.oxigenio) AS oxigenio_medio,
    AVG(qa.condutividade) AS condutividade_media
FROM estacao AS es
INNER JOIN cidade AS ci
    ON ci.id = es.id_cidade
INNER JOIN estado AS uf
    ON uf.id = ci.id_estado
LEFT JOIN qualidade_agua AS qa
    ON qa.id_estacao = es.id
    AND qa.data_leitura >= @data_inicio
    AND qa.data_leitura < @data_fim
GROUP BY es.id, es.nome, ci.nome, uf.sigla
ORDER BY quantidade_leituras DESC, es.nome;

-- 2. Evolucao diaria das variaveis de qualidade da agua por estacao.
SELECT
    es.id AS id_estacao,
    es.nome AS estacao,
    CAST(qa.data_leitura AS date) AS data_leitura,
    COUNT(qa.id) AS quantidade_leituras,
    AVG(qa.temperatura_agua) AS temperatura_media_agua,
    AVG(qa.ph) AS ph_medio,
    AVG(qa.oxigenio) AS oxigenio_medio
FROM qualidade_agua AS qa
INNER JOIN estacao AS es
    ON es.id = qa.id_estacao
WHERE qa.data_leitura >= @data_inicio
  AND qa.data_leitura < @data_fim
GROUP BY es.id, es.nome, CAST(qa.data_leitura AS date)
ORDER BY data_leitura, id_estacao;

-- 3. Leituras detalhadas com estacao, cidade e estado.
SELECT
    qa.id AS id_leitura,
    qa.id_estacao,
    qa.data_leitura,
    qa.criado_em,
    es.nome AS estacao,
    ci.nome AS cidade,
    uf.sigla AS estado,
    qa.temperatura_agua,
    qa.ph,
    qa.oxigenio,
    qa.condutividade
FROM qualidade_agua AS qa
INNER JOIN estacao AS es
    ON es.id = qa.id_estacao
INNER JOIN cidade AS ci
    ON ci.id = es.id_cidade
INNER JOIN estado AS uf
    ON uf.id = ci.id_estado
WHERE qa.data_leitura >= @data_inicio
  AND qa.data_leitura < @data_fim
ORDER BY qa.data_leitura DESC, es.nome;

-- 4. Agregacao meteorologica por cidade e estado.
-- A tabela meteorologica referencia cidade, nao estacao.
SELECT
    ci.nome AS cidade,
    uf.sigla AS estado,
    COUNT(lm.id) AS quantidade_leituras,
    AVG(lm.temperatura_ar) AS temperatura_media_ar,
    AVG(lm.umidade) AS umidade_media,
    SUM(lm.chuva) AS chuva_acumulada,
    AVG(lm.vento) AS velocidade_media_vento
FROM leitura_meteorologica AS lm
INNER JOIN cidade AS ci
    ON ci.id = lm.id_cidade
INNER JOIN estado AS uf
    ON uf.id = ci.id_estado
WHERE lm.data_leitura >= @data_inicio
  AND lm.data_leitura < @data_fim
GROUP BY ci.nome, uf.sigla
ORDER BY uf.sigla, ci.nome;