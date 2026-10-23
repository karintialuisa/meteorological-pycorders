"""Fornece fixtures comuns e SQL Server descartavel para testes de persistencia."""

import pytest
import sys
from pathlib import Path
path = Path(__file__).resolve().parents[1] 
sys.path.append(str(path))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlserver_support import RUN_TESTS, disposable_engine


@pytest.fixture(autouse=True)
def silver_dir_teste(monkeypatch, tmp_path):
    monkeypatch.setenv("SILVER_DIR", str(tmp_path / "silver"))


@pytest.fixture
def catalogo_lgpd_esperado():
    return [
        (
            "dbo", "operadores", "cpf", "cpf_hash", "Dado pessoal",
            "Cadastro e identificacao de operadores de campo", "HMAC-SHA-256",
            "Chave HMAC restrita ao processo autorizado; digest nao reversivel",
        ),
        (
            "dbo", "operadores", "nome_completo", "nome_completo_cifrado",
            "Dado pessoal", "Cadastro e identificacao de operadores de campo",
            "Fernet",
            "Descriptografia autorizada por principal; tentativas auditadas sem PII",
        ),
    ]


@pytest.fixture
def banco_teste():
    if not RUN_TESTS:
        pytest.skip("Habilite o SQL Server descartavel em config/.env.")
    with disposable_engine(legacy=True) as engine:
        yield engine