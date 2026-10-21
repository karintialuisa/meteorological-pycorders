"""IDs39-44: constraints e replay no DDL real em banco descartavel automatico.

src/config/.env configura todas as suites SQLServer. Constraints usam
rollback; replay usa dados sinteticos commitados e limpeza explicita.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.database.dml.Insert_Leitura_Itens import inserir_leitura_itens
from src.database.dml.Insert_Leituras import inserir_leituras
from src.database.dml.Insert_Parametros import inserir_parametros


from sqlserver_support import RUN_TESTS, disposable_engine

pytestmark = pytest.mark.skipif(
    not RUN_TESTS, reason="Habilite SQL Server em src/config/.env.",
)

# ID 42: PK de cada entidade do modelo; leitura_itens usa PK composta.
PKS_ESPERADAS = {
    "estado": ("id",),
    "cidade": ("id",),
    "estacao": ("id",),
    "operadores": ("id",),
    "catalogo_dados": ("id",),
    "parametros": ("id",),
    "leituras": ("id",),
    "leitura_itens": ("id_leitura", "id_parametro"),
}

# ID 44: (tabela, coluna, referencia, coluna_ref, acao_ao_excluir).
FKS_ESPERADAS = {
    ("cidade", "id_estado", "estado", "id", "NO_ACTION"),
    ("estacao", "id_cidade", "cidade", "id", "NO_ACTION"),
    ("estacao", "id_estado", "estado", "id", "NO_ACTION"),
    ("operadores", "id_estacao", "estacao", "id", "CASCADE"),
    ("leituras", "id_estacao", "estacao", "id", "NO_ACTION"),
    ("leituras", "id_operador", "operadores", "id", "NO_ACTION"),
    ("leitura_itens", "id_leitura", "leituras", "id", "CASCADE"),
    ("leitura_itens", "id_parametro", "parametros", "id", "NO_ACTION"),
}

NULAVEIS = {
    ("leituras", "id_operador"),
    ("leitura_itens", "valor_numerico"),
    ("leitura_itens", "valor_texto"),
}
OBRIGATORIAS = {
    ("leituras", "origem"),
    ("leituras", "chave_origem"),
    ("leituras", "id_estacao"),
    ("leituras", "data_leitura"),
    ("leitura_itens", "id_leitura"),
    ("leitura_itens", "id_parametro"),
    ("parametros", "codigo"),
    ("parametros", "nome"),
    ("parametros", "unidade_medida"),
    ("operadores", "id_estacao"),
}


@pytest.fixture(scope="module")
def sqlserver_engine():
    with disposable_engine() as engine:
        yield engine


@pytest.fixture
def conn(sqlserver_engine):
    # Rollback ao final garante que nenhum dado sintetico persista.
    with sqlserver_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


def _insert_id(conn, sql: str, params: dict) -> int:
    return int(conn.execute(text(sql), params).scalar_one())


def _reservar_chaves_estado(conn) -> tuple[str, int]:
    for _ in range(20):
        sigla = uuid4().hex[:2].upper()
        codigo = 100_000_000 + int(uuid4().hex[:8], 16) % 1_000_000_000
        if conn.execute(
            text("SELECT 1 FROM dbo.estado WHERE sigla = :s OR codigo_ibge = :c"),
            {"s": sigla, "c": codigo},
        ).first() is None:
            return sigla, codigo
    pytest.fail("Não foi possível reservar chaves sintéticas de estado.")


@pytest.fixture
def base(conn):
    token = uuid4().hex
    sigla, codigo = _reservar_chaves_estado(conn)

    estado = _insert_id(
        conn,
        "INSERT INTO dbo.estado (codigo_ibge, sigla, nome) OUTPUT INSERTED.id "
        "VALUES (:codigo, :sigla, :nome)",
        {"codigo": codigo, "sigla": sigla, "nome": f"INT-STATE-{token}"},
    )
    cidade = _insert_id(
        conn,
        "INSERT INTO dbo.cidade (id_estado, nome) OUTPUT INSERTED.id "
        "VALUES (:estado, :nome)",
        {"estado": estado, "nome": f"INT-CITY-{token}"},
    )
    estacao = _insert_id(
        conn,
        "INSERT INTO dbo.estacao (codigo_origem, nome, status, id_cidade, id_estado) "
        "OUTPUT INSERTED.id VALUES (:codigo, :nome, 1, :cidade, :estado)",
        {
            "codigo": f"INT-{token}",
            "nome": f"INT-STATION-{token}",
            "cidade": cidade,
            "estado": estado,
        },
    )
    operador = _insert_id(
        conn,
        "INSERT INTO dbo.operadores (cpf_hash, nome_completo_cifrado, id_estacao) "
        "OUTPUT INSERTED.id VALUES (:hash, 'cifrado-sintetico', :estacao)",
        {"hash": token[:32] * 2, "estacao": estacao},
    )
    parametro = _insert_id(
        conn,
        "INSERT INTO dbo.parametros (codigo, nome, unidade_medida) OUTPUT INSERTED.id "
        "VALUES (:codigo, 'Parametro sintetico', 'un')",
        {"codigo": f"INT{token}"},
    )
    return {"estacao": estacao, "operador": operador, "parametro": parametro}


def _nova_leitura(conn, base, **overrides) -> int:
    params = {
        "origem": "qualidade_agua",
        "chave": f"INT-{uuid4().hex}",
        "estacao": base["estacao"],
        "operador": None,
        "data": "2026-10-12T12:00:00+00:00",
    }
    params.update(overrides)
    return _insert_id(
        conn,
        "INSERT INTO dbo.leituras (origem, chave_origem, id_estacao, id_operador, "
        "data_leitura) OUTPUT INSERTED.id "
        "VALUES (:origem, :chave, :estacao, :operador, :data)",
        params,
    )


def _novo_item(conn, base, id_leitura, **overrides) -> None:
    params = {
        "leitura": id_leitura,
        "parametro": base["parametro"],
        "numerico": 1.5,
        "texto": None,
    }
    params.update(overrides)
    conn.execute(
        text(
            "INSERT INTO dbo.leitura_itens "
            "(id_leitura, id_parametro, valor_numerico, valor_texto) "
            "VALUES (:leitura, :parametro, :numerico, :texto)"
        ),
        params,
    )


def test_pks_do_modelo_existem_e_estao_habilitadas(conn):
    rows = conn.execute(
        text(
            "SELECT t.name, c.name, ic.key_ordinal, i.is_disabled "
            "FROM sys.key_constraints kc "
            "JOIN sys.tables t ON t.object_id = kc.parent_object_id "
            "JOIN sys.indexes i ON i.object_id = kc.parent_object_id "
            "AND i.index_id = kc.unique_index_id "
            "JOIN sys.index_columns ic ON ic.object_id = i.object_id "
            "AND ic.index_id = i.index_id "
            "JOIN sys.columns c ON c.object_id = ic.object_id "
            "AND c.column_id = ic.column_id "
            "WHERE kc.type = 'PK' AND SCHEMA_NAME(t.schema_id) = 'dbo'"
        )
    ).all()
    assert not any(row[3] for row in rows)
    pks = {}
    for tabela, coluna, ordem, _ in sorted(rows, key=lambda row: (row[0], row[2])):
        pks.setdefault(tabela, []).append(coluna)
    for tabela, colunas in PKS_ESPERADAS.items():
        assert tuple(pks.get(tabela, ())) == colunas, tabela


def test_fks_do_modelo_estao_habilitadas_e_confiaveis(conn):
    rows = conn.execute(
        text(
            "SELECT OBJECT_NAME(fk.parent_object_id), "
            "COL_NAME(fkc.parent_object_id, fkc.parent_column_id), "
            "OBJECT_NAME(fk.referenced_object_id), "
            "COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id), "
            "fk.delete_referential_action_desc, fk.is_disabled, fk.is_not_trusted "
            "FROM sys.foreign_keys fk "
            "JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id"
        )
    ).all()
    encontradas = {tuple(row[:5]) for row in rows}
    assert FKS_ESPERADAS <= encontradas
    inativas = [row[:2] for row in rows if tuple(row[:5]) in FKS_ESPERADAS and (row[5] or row[6])]
    assert inativas == []


def test_nulabilidade_do_modelo(conn):
    rows = conn.execute(
        text(
            "SELECT t.name, c.name, c.is_nullable FROM sys.columns c "
            "JOIN sys.tables t ON t.object_id = c.object_id "
            "WHERE SCHEMA_NAME(t.schema_id) = 'dbo'"
        )
    ).all()
    nulabilidade = {(tabela, coluna): bool(nulavel) for tabela, coluna, nulavel in rows}
    assert all(nulabilidade[chave] for chave in NULAVEIS)
    assert not any(nulabilidade[chave] for chave in OBRIGATORIAS)


def test_insercoes_validas_incluindo_operador_nulo(conn, base):
    sem_operador = _nova_leitura(conn, base)
    com_operador = _nova_leitura(conn, base, operador=base["operador"])
    _novo_item(conn, base, sem_operador)
    parametro_texto = _insert_id(
        conn,
        "INSERT INTO dbo.parametros (codigo, nome, unidade_medida) OUTPUT INSERTED.id "
        "VALUES (:codigo, 'Texto sintetico', 'descricao')",
        {"codigo": f"INT{uuid4().hex}"},
    )
    _novo_item(conn, base, com_operador, parametro=parametro_texto, numerico=None, texto="Nublado")
    total = conn.execute(
        text("SELECT COUNT(*) FROM dbo.leitura_itens WHERE id_leitura IN (:a, :b)"),
        {"a": sem_operador, "b": com_operador},
    ).scalar_one()
    assert total == 2


@pytest.mark.parametrize(
    "caso",
    ["estacao_inexistente", "operador_inexistente", "leitura_inexistente", "parametro_inexistente"],
)
def test_fk_invalida_e_rejeitada(conn, base, caso):
    inexistente = 9_000_000_000_000
    with pytest.raises(IntegrityError):
        if caso == "estacao_inexistente":
            _nova_leitura(conn, base, estacao=inexistente)
        elif caso == "operador_inexistente":
            _nova_leitura(conn, base, operador=inexistente)
        elif caso == "leitura_inexistente":
            _novo_item(conn, base, inexistente)
        else:
            _novo_item(conn, base, _nova_leitura(conn, base), parametro=inexistente)


@pytest.mark.parametrize("campo", ["estacao", "data", "origem", "chave"])
def test_nulo_em_campo_obrigatorio_de_leituras_e_rejeitado(conn, base, campo):
    with pytest.raises(IntegrityError):
        _nova_leitura(conn, base, **{campo: None})


def test_nulo_em_coluna_da_pk_composta_e_rejeitado(conn, base):
    id_leitura = _nova_leitura(conn, base)
    with pytest.raises(IntegrityError):
        _novo_item(conn, base, id_leitura, parametro=None)


def test_pk_composta_duplicada_e_rejeitada(conn, base):
    id_leitura = _nova_leitura(conn, base)
    _novo_item(conn, base, id_leitura)
    with pytest.raises(IntegrityError):
        _novo_item(conn, base, id_leitura, numerico=2.5)


@pytest.mark.parametrize(
    "valores",
    [
        {"numerico": 1.5, "texto": "ambos"},
        {"numerico": None, "texto": None},
        {"numerico": None, "texto": "   "},
    ],
    ids=["ambos_preenchidos", "ambos_nulos", "texto_vazio"],
)
def test_check_de_valor_unico_e_rejeitado(conn, base, valores):
    id_leitura = _nova_leitura(conn, base)
    with pytest.raises(IntegrityError):
        _novo_item(conn, base, id_leitura, **valores)


def test_chave_de_origem_duplicada_e_origem_invalida_sao_rejeitadas(conn, base):
    chave = f"INT-{uuid4().hex}"
    _nova_leitura(conn, base, chave=chave)
    with pytest.raises(IntegrityError):
        _nova_leitura(conn, base, chave=chave)
    with pytest.raises(IntegrityError):
        _nova_leitura(conn, base, origem="origem_desconhecida")


def test_exclusao_de_leitura_remove_itens_em_cascata(conn, base):
    id_leitura = _nova_leitura(conn, base)
    _novo_item(conn, base, id_leitura)
    conn.execute(text("DELETE FROM dbo.leituras WHERE id = :id"), {"id": id_leitura})
    restantes = conn.execute(
        text("SELECT COUNT(*) FROM dbo.leitura_itens WHERE id_leitura = :id"),
        {"id": id_leitura},
    ).scalar_one()
    assert restantes == 0


@pytest.mark.parametrize(
    "pai",
    ["parametros", "operadores", "estacao"],
)
def test_exclusao_de_pai_referenciado_sem_cascata_e_bloqueada(conn, base, pai):
    id_leitura = _nova_leitura(conn, base, operador=base["operador"])
    _novo_item(conn, base, id_leitura)
    chave = {"parametros": "parametro", "operadores": "operador", "estacao": "estacao"}[pai]
    with pytest.raises(IntegrityError):
        conn.execute(text(f"DELETE FROM dbo.{pai} WHERE id = :id"), {"id": base[chave]})
    assert conn.execute(text(f"SELECT COUNT(*) FROM dbo.{pai} WHERE id=:id"),
                        {"id": base[chave]}).scalar_one() == 1
    assert conn.execute(text("SELECT COUNT(*) FROM leituras WHERE id=:id"),
                        {"id": id_leitura}).scalar_one() == 1
    assert conn.execute(text("SELECT COUNT(*) FROM leitura_itens WHERE id_leitura=:id"),
                        {"id": id_leitura}).scalar_one() == 1


# IDs 39-41 e 44: os loaders abrem as proprias transacoes, entao os dados sao commitados e limpos.
@pytest.fixture
def dados_commitados(sqlserver_engine):
    token = uuid4().hex
    with sqlserver_engine.begin() as connection:
        sigla, codigo_ibge = _reservar_chaves_estado(connection)
        estado = _insert_id(
            connection,
            "INSERT INTO dbo.estado (codigo_ibge, sigla, nome) OUTPUT INSERTED.id "
            "VALUES (:codigo, :sigla, :nome)",
            {"codigo": codigo_ibge, "sigla": sigla, "nome": f"INT-STATE-{token}"},
        )
        cidade = _insert_id(
            connection,
            "INSERT INTO dbo.cidade (id_estado, nome) OUTPUT INSERTED.id "
            "VALUES (:estado, :nome)",
            {"estado": estado, "nome": f"INT-CITY-{token}"},
        )
        estacao = _insert_id(
            connection,
            "INSERT INTO dbo.estacao (codigo_origem, nome, status, id_cidade, id_estado) "
            "OUTPUT INSERTED.id VALUES (:codigo, :nome, 1, :cidade, :estado)",
            {
                "codigo": f"INT-{token}",
                "nome": f"INT-STATION-{token}",
                "cidade": cidade,
                "estado": estado,
            },
        )
        cpf_hash = token[:32] * 2
        operador = _insert_id(
            connection,
            "INSERT INTO dbo.operadores (cpf_hash, nome_completo_cifrado, id_estacao) "
            "OUTPUT INSERTED.id VALUES (:hash, 'cifrado-sintetico', :estacao)",
            {"hash": cpf_hash, "estacao": estacao},
        )

    prefixo = f"INT{token.upper()}"
    dados = {
        "token": token,
        "estado": estado,
        "cidade": cidade,
        "estacao": estacao,
        "operador": operador,
        "codigo_estacao": f"INT-{token}",
        "cpf_hash": cpf_hash,
        "prefixo": prefixo,
        "param_a": f"{prefixo}_A",
        "param_b": f"{prefixo}_B",
    }
    try:
        yield dados
    finally:
        with sqlserver_engine.begin() as connection:
            # Itens saem em cascata junto com os cabecalhos.
            connection.execute(
                text("DELETE FROM dbo.leituras WHERE id_estacao = :id"), {"id": estacao}
            )
            connection.execute(
                text("DELETE FROM dbo.parametros WHERE codigo LIKE :p"),
                {"p": f"{prefixo}%"},
            )
            connection.execute(
                text("DELETE FROM dbo.operadores WHERE id_estacao = :id"), {"id": estacao}
            )
            connection.execute(text("DELETE FROM dbo.estacao WHERE id = :id"), {"id": estacao})
            connection.execute(text("DELETE FROM dbo.cidade WHERE id = :id"), {"id": cidade})
            connection.execute(text("DELETE FROM dbo.estado WHERE id = :id"), {"id": estado})

    with sqlserver_engine.connect() as connection:
        restos = connection.execute(
            text(
                "SELECT (SELECT COUNT(*) FROM dbo.estacao WHERE id = :e) "
                "+ (SELECT COUNT(*) FROM dbo.leituras WHERE id_estacao = :e) "
                "+ (SELECT COUNT(*) FROM dbo.parametros WHERE codigo LIKE :p)"
            ),
            {"e": estacao, "p": f"{prefixo}%"},
        ).scalar_one()
    assert restos == 0


def _contar(engine, sql: str, params: dict) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(sql), params).scalar_one())


def _leitura_agua(dados, **overrides) -> dict:
    leitura = {
        "origem": "qualidade_agua",
        "id_leitura_origem": f"INT-W-{dados['token']}",
        "codigo_estacao": dados["codigo_estacao"],
        "data_leitura": datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
        "operador_cpf_hash": None,
    }
    leitura.update(overrides)
    return leitura


def test_replay_de_parametros_no_sqlserver(sqlserver_engine, dados_commitados):
    dados = dados_commitados
    lote = [
        {"codigo": dados["param_a"], "nome": "Parametro A", "unidade_medida": "un"},
        {"codigo": dados["param_b"], "nome": "Parametro B", "unidade_medida": "un"},
    ]
    assert inserir_parametros(lote, sqlserver_engine) == (2, 0)
    assert inserir_parametros(lote, sqlserver_engine) == (0, 0)
    lote[0] = {**lote[0], "nome": "Parametro A revisado"}
    assert inserir_parametros(lote, sqlserver_engine) == (0, 1)

    with pytest.raises(ValueError):
        inserir_parametros(
            [{"codigo": dados["param_a"], "unidade_medida": "un"}], sqlserver_engine
        )
    with pytest.raises(ValueError):
        inserir_parametros([lote[0], lote[0]], sqlserver_engine)

    total = _contar(
        sqlserver_engine,
        "SELECT COUNT(*) FROM dbo.parametros WHERE codigo LIKE :p",
        {"p": f"{dados['prefixo']}%"},
    )
    assert total == 2


def test_replay_de_cabecalhos_no_sqlserver(sqlserver_engine, dados_commitados):
    dados = dados_commitados
    agua = _leitura_agua(dados)
    assert inserir_leituras([agua], sqlserver_engine) == (1, 0, 0)
    assert inserir_leituras([agua], sqlserver_engine) == (0, 0, 0)

    com_operador = {**agua, "operador_cpf_hash": dados["cpf_hash"]}
    assert inserir_leituras([com_operador], sqlserver_engine) == (0, 1, 0)

    conflitante = {
        **agua,
        "data_leitura": datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc),
    }
    assert inserir_leituras([conflitante], sqlserver_engine) == (0, 0, 1)

    nova_chave = f"INT-W2-{dados['token']}"
    estacao_desconhecida = _leitura_agua(
        dados, id_leitura_origem=nova_chave, codigo_estacao="INT-INEXISTENTE"
    )
    operador_desconhecido = _leitura_agua(
        dados, id_leitura_origem=nova_chave, operador_cpf_hash="f" * 64
    )
    assert inserir_leituras(
        [estacao_desconhecida, operador_desconhecido], sqlserver_engine
    ) == (0, 0, 2)

    meteorologia = {
        "origem": "leitura_meteorologica",
        "codigo_estacao": dados["codigo_estacao"],
        "data_leitura": datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
    }
    assert inserir_leituras([meteorologia], sqlserver_engine) == (1, 0, 0)
    assert inserir_leituras([meteorologia], sqlserver_engine) == (0, 0, 0)

    with sqlserver_engine.connect() as connection:
        linhas = connection.execute(
            text(
                "SELECT origem, id_operador FROM dbo.leituras "
                "WHERE id_estacao = :id ORDER BY origem"
            ),
            {"id": dados["estacao"]},
        ).all()
    assert [tuple(linha) for linha in linhas] == [
        ("leitura_meteorologica", None),
        ("qualidade_agua", dados["operador"]),
    ]


def test_replay_de_itens_no_sqlserver(sqlserver_engine, dados_commitados):
    dados = dados_commitados
    inserir_parametros(
        [
            {"codigo": dados["param_a"], "nome": "Parametro A", "unidade_medida": "un"},
            {"codigo": dados["param_b"], "nome": "Parametro B", "unidade_medida": "un"},
        ],
        sqlserver_engine,
    )
    agua = _leitura_agua(dados)
    assert inserir_leituras([agua], sqlserver_engine) == (1, 0, 0)
    chave = agua["id_leitura_origem"]

    numerico = {
        "origem": "qualidade_agua",
        "chave_origem": chave,
        "codigo_parametro": dados["param_a"],
        "valor_numerico": 21.25,
    }
    assert inserir_leitura_itens([numerico], sqlserver_engine) == (1, 0, 0)
    assert inserir_leitura_itens([numerico], sqlserver_engine) == (0, 1, 0)
    assert inserir_leitura_itens(
        [{**numerico, "valor_numerico": 22}], sqlserver_engine
    ) == (0, 0, 1)

    # Um lote misto prova que a rejeicao de um item nao afeta os demais.
    texto = {
        "origem": "qualidade_agua",
        "chave_origem": chave,
        "codigo_parametro": dados["param_b"],
        "valor_texto": "Nublado",
    }
    parametro_desconhecido = {**numerico, "codigo_parametro": f"{dados['prefixo']}_X"}
    assert inserir_leitura_itens(
        [texto, parametro_desconhecido, numerico], sqlserver_engine
    ) == (1, 1, 1)

    cabecalho_desconhecido = {**numerico, "chave_origem": f"INT-SEM-CABECALHO-{dados['token']}"}
    sem_valor = {**texto, "valor_texto": None}
    assert inserir_leitura_itens(
        [cabecalho_desconhecido, sem_valor], sqlserver_engine
    ) == (0, 0, 2)

    with sqlserver_engine.connect() as connection:
        valor = connection.execute(
            text(
                "SELECT i.valor_numerico FROM dbo.leitura_itens i "
                "JOIN dbo.parametros p ON p.id = i.id_parametro WHERE p.codigo = :c"
            ),
            {"c": dados["param_a"]},
        ).scalar_one()
    assert float(valor) == 21.25
    total = _contar(
        sqlserver_engine,
        "SELECT COUNT(*) FROM dbo.leitura_itens i JOIN dbo.leituras l ON l.id = i.id_leitura "
        "WHERE l.id_estacao = :id",
        {"id": dados["estacao"]},
    )
    assert total == 2


def test_cargas_concorrentes_do_mesmo_cabecalho_gravam_uma_vez(
    sqlserver_engine, dados_commitados
):
    dados = dados_commitados
    agua = _leitura_agua(dados)
    with ThreadPoolExecutor(max_workers=4) as executor:
        resultados = list(
            executor.map(lambda _: inserir_leituras([agua], sqlserver_engine), range(4))
        )
    assert sum(resultado[0] for resultado in resultados) == 1
    assert sum(resultado[2] for resultado in resultados) == 0
    total = _contar(
        sqlserver_engine,
        "SELECT COUNT(*) FROM dbo.leituras WHERE id_estacao = :id",
        {"id": dados["estacao"]},
    )
    assert total == 1
