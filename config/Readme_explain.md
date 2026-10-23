# Referência complementar

Este arquivo foi reduzido para evitar instruções históricas incompatíveis com o layout atual. A arquitetura por camadas, instalação e contratos estão documentados em [README.md](README.md); os comandos e pré-condições operacionais estão em [RUNBOOK.md](../RUNBOOK.md).

O código Python fica em `src/`, os dados ficam em `data_lakehouse/bronze`, `data_lakehouse/silver` e `data_lakehouse/gold`, e os scripts SQL ficam em `sql/`. O ponto de entrada do pipeline é `src/pipeline_orchestrator.py`.
