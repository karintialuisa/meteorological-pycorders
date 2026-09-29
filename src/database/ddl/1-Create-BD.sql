-- Cria o banco de dados "monitoramento".
CREATE DATABASE monitoramento;

use monitoramento;
go

select * from estacao;
select * from qualidade_agua;

DROP table qualidade_agua;
GO
