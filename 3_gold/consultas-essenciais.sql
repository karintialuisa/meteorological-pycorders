-- Executar na conexao explicitamente escolhida; dias agrupados em UTC.
-- Intervalo semiaberto: inclui inicio, exclui fim.
DECLARE @data_inicio DATETIMEOFFSET = '2026-09-15T00:00:00-03:00';
DECLARE @data_fim DATETIMEOFFSET = '2026-09-18T00:00:00-03:00';

-- 1. Medias ambientais por estacao, incluindo estacoes sem leituras.
SELECT es.id AS id_estacao, es.nome AS estacao, ci.nome AS cidade, uf.sigla AS estado,
    COUNT(DISTINCT l.id) AS quantidade_leituras,
    AVG(CASE WHEN p.codigo='TEMP_AGUA' THEN i.valor_numerico END) AS temperatura_media_agua,
    AVG(CASE WHEN p.codigo='PH' THEN i.valor_numerico END) AS ph_medio,
    AVG(CASE WHEN p.codigo='OD' THEN i.valor_numerico END) AS oxigenio_medio,
    AVG(CASE WHEN p.codigo='COND_ELETRICA' THEN i.valor_numerico END) AS condutividade_media,
    AVG(CASE WHEN p.codigo='TURBIDEZ' THEN i.valor_numerico END) AS turbidez_media
FROM estacao es
JOIN cidade ci ON ci.id=es.id_cidade
JOIN estado uf ON uf.id=ci.id_estado
LEFT JOIN leituras l ON l.id_estacao=es.id AND l.origem='qualidade_agua'
    AND l.data_leitura>=@data_inicio AND l.data_leitura<@data_fim
LEFT JOIN leitura_itens i ON i.id_leitura=l.id
LEFT JOIN parametros p ON p.id=i.id_parametro
GROUP BY es.id, es.nome, ci.nome, uf.sigla
ORDER BY quantidade_leituras DESC, es.nome;

-- 2. Evolucao diaria ambiental por estacao.
SELECT es.id AS id_estacao, es.nome AS estacao,
    CAST(SWITCHOFFSET(l.data_leitura, '+00:00') AS date) AS data_leitura,
    COUNT(DISTINCT l.id) AS quantidade_leituras,
    AVG(CASE WHEN p.codigo='TEMP_AGUA' THEN i.valor_numerico END) AS temperatura_media_agua,
    AVG(CASE WHEN p.codigo='PH' THEN i.valor_numerico END) AS ph_medio,
    AVG(CASE WHEN p.codigo='OD' THEN i.valor_numerico END) AS oxigenio_medio,
    AVG(CASE WHEN p.codigo='TURBIDEZ' THEN i.valor_numerico END) AS turbidez_media
FROM leituras l
JOIN estacao es ON es.id=l.id_estacao
LEFT JOIN leitura_itens i ON i.id_leitura=l.id
LEFT JOIN parametros p ON p.id=i.id_parametro
WHERE l.origem='qualidade_agua' AND l.data_leitura>=@data_inicio AND l.data_leitura<@data_fim
GROUP BY es.id, es.nome, CAST(SWITCHOFFSET(l.data_leitura, '+00:00') AS date)
ORDER BY data_leitura, id_estacao;

-- 3. Uma linha por evento ambiental, sem multiplicar cabecalhos pelos itens.
SELECT l.id AS id_leitura, l.id_estacao, l.data_leitura, l.criado_em,
    es.nome AS estacao, ci.nome AS cidade, uf.sigla AS estado,
    MAX(CASE WHEN p.codigo='TEMP_AGUA' THEN i.valor_numerico END) AS temperatura_agua,
    MAX(CASE WHEN p.codigo='PH' THEN i.valor_numerico END) AS ph,
    MAX(CASE WHEN p.codigo='OD' THEN i.valor_numerico END) AS oxigenio,
    MAX(CASE WHEN p.codigo='COND_ELETRICA' THEN i.valor_numerico END) AS condutividade,
    MAX(CASE WHEN p.codigo='TURBIDEZ' THEN i.valor_numerico END) AS turbidez
FROM leituras l
JOIN estacao es ON es.id=l.id_estacao
JOIN cidade ci ON ci.id=es.id_cidade
JOIN estado uf ON uf.id=ci.id_estado
LEFT JOIN leitura_itens i ON i.id_leitura=l.id
LEFT JOIN parametros p ON p.id=i.id_parametro
WHERE l.origem='qualidade_agua' AND l.data_leitura>=@data_inicio AND l.data_leitura<@data_fim
GROUP BY l.id, l.id_estacao, l.data_leitura, l.criado_em, es.nome, ci.nome, uf.sigla
ORDER BY l.data_leitura DESC, es.nome;

-- 4. Meteorologia por cidade/estado, resolvidos pela estacao.
SELECT ci.nome AS cidade, uf.sigla AS estado, COUNT(DISTINCT l.id) AS quantidade_leituras,
    AVG(CASE WHEN p.codigo='TEMP_AR' THEN i.valor_numerico END) AS temperatura_media_ar,
    AVG(CASE WHEN p.codigo='UMIDADE' THEN i.valor_numerico END) AS umidade_media,
    SUM(CASE WHEN p.codigo='CHUVA' THEN i.valor_numerico END) AS chuva_acumulada,
    AVG(CASE WHEN p.codigo='VENTO' THEN i.valor_numerico END) AS velocidade_media_vento
FROM leituras l
JOIN estacao es ON es.id=l.id_estacao
JOIN cidade ci ON ci.id=es.id_cidade
JOIN estado uf ON uf.id=ci.id_estado
LEFT JOIN leitura_itens i ON i.id_leitura=l.id
LEFT JOIN parametros p ON p.id=i.id_parametro
WHERE l.origem='leitura_meteorologica' AND l.data_leitura>=@data_inicio AND l.data_leitura<@data_fim
GROUP BY ci.nome, uf.sigla
ORDER BY uf.sigla, ci.nome;
