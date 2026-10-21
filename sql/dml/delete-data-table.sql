/*
Modelo manual de exclusao SELETIVA. Nao executa ao carregar este arquivo.
Exige backup, autorizacao e conexao explicitamente selecionada.
Nunca desabilitar FKs, nunca reseed de IDs de registros relacionados.
Arquivos legado_* sao imutaveis e nao participam desta limpeza.

SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @id_leitura BIGINT = <id autorizado>;
DELETE FROM dbo.leituras WHERE id = @id_leitura;
-- Os itens sao removidos pela FK ON DELETE CASCADE.
COMMIT;

Para remover cadastros autorizados, usar transacao e predicados especificos,
na ordem: leituras/itens -> operadores -> estacao -> cidade -> estado.
Remover parametros somente depois dos itens que os referenciam.
NO_ACTION deve bloquear exclusoes de pais ainda referenciados.
Se houver arquivo legado referenciando o cadastro, preservar o cadastro.
Nao existe limpeza global automatica do banco monitoramento.
*/
