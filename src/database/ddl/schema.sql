-- Inicializa o banco de dados monitoramento e contém consultas rápidas para verificar os relacionamentos entre estados, cidades e estações.
-- A criação das tabelas está centralizada em create-tables.sql.
-- As consultas ao final deste arquivo servem apenas para inspeção manual dos dados.
/*create database monitoramento;

use monitoramento; 
go

SELECT * FROM estacao;

use monitoramento; 
GO

SELECT * FROM cidade a inner join estacao b on a.id = b.id_cidade WHERE a.id = 3832;
SELECT * FROM estado e inner join estacao b on e.id = b.id_estado WHERE e.id = 20;*/
