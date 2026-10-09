USE monitoramento;
-- 1. Desativa temporariamente as restrições de chave estrangeira
EXEC sp_msforeachtable "ALTER TABLE ? NOCHECK CONSTRAINT all";

-- 2. Limpa os dados de todas as tabelas
DELETE FROM leitura_meteorologica;
DELETE FROM qualidade_agua;
DELETE FROM estacao;
DELETE FROM cidade;
DELETE FROM estado;

-- 3. Reseta o contador do ID (IDENTITY) para 0 em cada tabela
-- (O próximo registro inserido receberá o ID 1)
DBCC CHECKIDENT ('leitura_meteorologica', RESEED, 0);
DBCC CHECKIDENT ('qualidade_agua', RESEED, 0);
DBCC CHECKIDENT ('estacao', RESEED, 0);
DBCC CHECKIDENT ('cidade', RESEED, 0);
DBCC CHECKIDENT ('estado', RESEED, 0);

-- 4. Reativa as restrições de chave estrangeira
EXEC sp_msforeachtable "ALTER TABLE ? WITH CHECK CHECK CONSTRAINT all";

-- 5. Valida que realmente as tabelas foram limpas
SELECT * FROM estado;
SELECT * FROM leitura_meteorologica;