"""Persistencia atomica e mapeamento comum de eventos 3FN."""

import logging
<<<<<<< HEAD
from collections.abc import Callable, Mapping
=======
from collections.abc import Mapping
from time import monotonic
>>>>>>> origin/feature/wagner2

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from src.database.dialect import require_sqlserver
from src.database.dml.Insert_Leituras import _normalizar_registro, inserir_leituras
from src.database.dml.Insert_Leitura_Itens import _normalizar_item, inserir_leitura_itens
from src.database.dml.etl_lock import adquirir_lock_etl


MAPEAMENTO = {
    "qualidade_agua": {
        "temperatura_agua": "TEMP_AGUA", "ph": "PH", "oxigenio": "OD",
        "condutividade": "COND_ELETRICA", "turbidez": "TURBIDEZ",
    },
    "leitura_meteorologica": {
        "temperatura_ar": "TEMP_AR", "umidade": "UMIDADE", "chuva": "CHUVA",
        "vento": "VENTO", "condicao": "CONDICAO_METEO",
    },
}


def _validar_legado_inativo(connection: Connection) -> None:
    """Impede tratar um modelo legado ativo como referencia 3FN vazia."""
    require_sqlserver(connection)
    existentes = set(inspect(connection).get_table_names(schema="dbo"))
    for tabela in MAPEAMENTO:
        if tabela in existentes and connection.execute(
            text(f"SELECT COUNT(*) FROM {tabela}")
        ).scalar_one():
            raise ValueError("legado ativo com dados: realizar migracao e arquivamento antes da carga")


def consultar_medicoes_periodo(
    engine: Engine, origem: str, inicio: pd.Timestamp, fim: pd.Timestamp,
) -> pd.DataFrame:
    """Projeta todos os eventos SQL aceitos no intervalo UTC para a Silver.

    As colunas sao derivadas apenas do mapeamento fixo. LEFT JOIN preserva
    eventos incompletos para que a reconstrucao falhe, em vez de omiti-los.
    """
    if origem not in MAPEAMENTO:
        raise ValueError("origem de medicao desconhecida")
    require_sqlserver(engine)
    medidas = []
    for coluna, codigo in MAPEAMENTO[origem].items():
        valor = "valor_texto" if codigo == "CONDICAO_METEO" else "valor_numerico"
        medidas.append(f"MAX(CASE WHEN p.codigo='{codigo}' THEN i.{valor} END) AS {coluna}")
    identificadores = (
        "l.chave_origem AS id_leitura_origem"
        if origem == "qualidade_agua" else "e.id_cidade"
    )
    consulta = text(
        f"SELECT {identificadores},l.id_estacao,l.data_leitura,{','.join(medidas)} "
        "FROM leituras l JOIN estacao e ON e.id=l.id_estacao "
        "LEFT JOIN leitura_itens i ON i.id_leitura=l.id "
        "LEFT JOIN parametros p ON p.id=i.id_parametro "
        "WHERE l.origem=:origem AND l.data_leitura>=:inicio AND l.data_leitura<:fim "
        "GROUP BY l.id,l.chave_origem,l.id_estacao,l.data_leitura,e.id_cidade "
        "ORDER BY l.data_leitura,l.chave_origem"
    )
    with engine.begin() as connection:
        adquirir_lock_etl(connection, "etl:leituras")
        adquirir_lock_etl(connection, "etl:leitura_itens")
        _validar_legado_inativo(connection)
        dados = pd.read_sql_query(
            consulta, connection,
            params={
                "origem": origem,
                "inicio": inicio.to_pydatetime(),
                "fim": fim.to_pydatetime(),
            },
        )
    dados["data_leitura"] = pd.to_datetime(dados["data_leitura"], utc=True, format="mixed")
    for coluna, codigo in MAPEAMENTO[origem].items():
        if codigo != "CONDICAO_METEO":
            dados[coluna] = pd.to_numeric(dados[coluna]).astype(float)
    for coluna in ("id_estacao", "id_cidade"):
        if coluna in dados:
            dados[coluna] = dados[coluna].astype("int64")
    if dados.empty:
        coluna_texto = "id_leitura_origem" if origem == "qualidade_agua" else "condicao"
        dados[coluna_texto] = dados[coluna_texto].astype("string")
    return dados[
        [*MAPEAMENTO[origem], "data_leitura", "id_estacao"]
        + (["id_leitura_origem"] if origem == "qualidade_agua" else ["id_cidade"])
    ]


def preparar_evento(registro: Mapping[str, object], origem: str):
    if origem not in MAPEAMENTO:
        raise ValueError("origem de medicao desconhecida")
    codigo_estacao = registro.get("estacao_id")
    if codigo_estacao is None or pd.isna(codigo_estacao) or not str(codigo_estacao).strip():
        raise ValueError("codigo da estacao obrigatorio")
    cabecalho = _normalizar_registro(
        {
            "origem": origem,
            "codigo_estacao": str(codigo_estacao).strip(),
            "data_leitura": registro["data_leitura"],
            "id_leitura_origem": registro.get("id_leitura_origem"),
            "operador_cpf_hash": registro.get("operador_cpf_hash"),
        },
        0,
    )
    itens = []
    for coluna, codigo in MAPEAMENTO[origem].items():
        valor = registro.get(coluna)
        if valor is None or pd.isna(valor):
            if origem == "leitura_meteorologica":
                raise ValueError(f"medicao meteorologica obrigatoria: {coluna}")
            continue
        item = {
            "origem": origem, "chave_origem": cabecalho["chave_origem"],
            "codigo_parametro": codigo,
            "valor_texto" if codigo == "CONDICAO_METEO" else "valor_numerico": valor,
        }
        itens.append(_normalizar_item(item, len(itens)))
    if not itens:
        raise ValueError("evento sem medicoes")
    return cabecalho, itens


def persistir_evento(connection: Connection, cabecalho, itens) -> None:
    """Usa a transacao do chamador; rejeicao deve causar rollback."""
    if not connection.in_transaction():
        raise ValueError("persistencia de evento exige transacao ativa")
    require_sqlserver(connection)
    adquirir_lock_etl(connection, "etl:leituras")
    adquirir_lock_etl(connection, "etl:leitura_itens")
    inserir_leituras([cabecalho], connection=connection, strict=True)
    tabela = "dbo.leitura_itens"
    existente = connection.execute(
        text(
            f"SELECT p.codigo FROM {tabela} i JOIN parametros p ON p.id=i.id_parametro "
            "JOIN leituras l ON l.id=i.id_leitura "
            "WHERE l.origem=:origem AND l.chave_origem=:chave"
        ),
        {"origem": cabecalho["origem"], "chave": cabecalho["chave_origem"]},
    ).scalars().all()
    codigos = {item["codigo_parametro"] for item in itens}
    if existente and set(existente) != codigos:
        raise ValueError("retransmissao conflitante: conjunto de parametros diferente")
    inserir_leitura_itens(itens, connection=connection, strict=True)


def carregar_dataframe(
    df: pd.DataFrame, origem: str, engine, *,
    progresso: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Aceita/rejeita cada evento; falhas SQL tecnicas nao sao suprimidas."""
    if origem not in MAPEAMENTO:
        raise ValueError("origem de medicao desconhecida")
    require_sqlserver(engine)
    inicio = monotonic()
    total = len(df)
    logging.info("Carga SQL iniciada: origem=%s total=%s; conectando e validando legado", origem, total)
    with engine.connect() as connection:
        _validar_legado_inativo(connection)
    logging.info("Validacao concluida: origem=%s; iniciando transacoes por leitura", origem)
    aprovados = []
<<<<<<< HEAD
    total = len(df)
    if progresso is not None:
        progresso(0, total)
=======
    ultimo_progresso = monotonic()
>>>>>>> origin/feature/wagner2
    for indice, registro in enumerate(df.to_dict("records")):
        try:
            cabecalho, itens = preparar_evento(registro, origem)
            with engine.begin() as connection:
                persistir_evento(connection, cabecalho, itens)
                estacao = connection.execute(
                    text("SELECT id, id_cidade FROM estacao WHERE codigo_origem=:codigo"),
                    {"codigo": cabecalho["codigo_estacao"]},
                ).one()
            valores = {
                item["codigo_parametro"]: (
                    item["valor_texto"] if item["valor_texto"] is not None else item["valor_numerico"]
                )
                for item in itens
            }
            silver = {
                coluna: valores.get(codigo)
                for coluna, codigo in MAPEAMENTO[origem].items()
            }
            silver["data_leitura"] = cabecalho["data_leitura"]
            silver["id_estacao"] = estacao.id
            if origem == "qualidade_agua":
                silver["id_leitura_origem"] = cabecalho["chave_origem"]
            if origem == "leitura_meteorologica":
                silver["id_cidade"] = estacao.id_cidade
            aprovados.append(silver)
        except ValueError as error:
            logging.warning(
                "Evento rejeitado: origem=%s indice=%s motivo=%s", origem, indice, error
            )
<<<<<<< HEAD
        if progresso is not None:
            progresso(indice + 1, total)
=======
        processados = indice + 1
        agora = monotonic()
        if processados == 1 or processados % 100 == 0 or processados == total or agora - ultimo_progresso >= 5:
            decorrido = agora - inicio
            velocidade = processados / decorrido if decorrido > 0 else 0
            restante = (total - processados) / velocidade if velocidade > 0 else 0
            logging.info(
                "Progresso SQL: origem=%s processados=%s/%s (%.1f%%) "
                "aceitos=%s rejeitados=%s decorrido=%.1fs taxa=%.1f leituras/s restante_estimado=%.1fs",
                origem, processados, total, 100 * processados / total,
                len(aprovados), processados - len(aprovados), decorrido, velocidade, restante,
            )
            ultimo_progresso = agora
    logging.info("Carga SQL concluida: origem=%s aceitos=%s rejeitados=%s tempo=%.1fs",
                 origem, len(aprovados), total - len(aprovados), monotonic() - inicio)
>>>>>>> origin/feature/wagner2
    return pd.DataFrame(aprovados)
