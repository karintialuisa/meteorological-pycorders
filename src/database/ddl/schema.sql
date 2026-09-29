-- Estruturas DDL iniciais do projeto PyCordersMeteorological.
create database monitoramento;

use monitoramento; 
go

SELECT * FROM estacao;

use monitoramento; 
GO

SELECT * FROM cidade a inner join estacao b on a.id = b.id_cidade WHERE a.id = 3832;
SELECT * FROM estado e inner join estacao b on e.id = b.id_estado WHERE e.id = 20;
