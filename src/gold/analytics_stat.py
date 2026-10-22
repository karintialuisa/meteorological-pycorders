"""Estatisticas descritivas e validacao por Z-Score de medicoes Silver."""

import argparse
from datetime import date
import logging
import math
import os
from pathlib import Path
import sys
import tempfile

import pandas as pd

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.settings import PROJECT_ROOT, configure_logging, get_silver_dir
from src.database.dml.Insert_Parametros import CATALOGO_PARAMETROS
from src.silver.persistencia.Persistir_Silver import CONTRATOS_DATASETS


GRUPOS = ["dataset", "id_estacao", "codigo_parametro", "unidade_medida"]
METRICAS = ["media", "mediana", "desvio_padrao", "variancia", "q1", "q3", "iqr"]
COLUNAS_RESULTADO = GRUPOS + ["n_validos", "n_invalidos"] + METRICAS + ["ddof"]
PARAMETROS = {
    "temperatura_agua": "TEMP_AGUA",
    "ph": "PH",
    "oxigenio": "OD",
    "condutividade": "COND_ELETRICA",
    "turbidez": "TURBIDEZ",
    "temperatura_ar": "TEMP_AR",
    "umidade": "UMIDADE",
    "chuva": "CHUVA",
    "vento": "VENTO",
}
UNIDADES = {item["codigo"]: item["unidade_medida"] for item in CATALOGO_PARAMETROS}
SAIDA_PADRAO = PROJECT_ROOT / "data_lakehouse" / "gold" / "estatisticas_descritivas.csv"
SAIDA_ZSCORE = PROJECT_ROOT / "data_lakehouse" / "gold" / "z_scores.csv"


def _numero_finito(valor: object) -> bool:
    return (
        pd.api.types.is_number(valor)
        and not pd.api.types.is_bool_dtype(type(valor))
        and not isinstance(valor, complex)
        and math.isfinite(float(valor))
    )


def calcular_estatisticas(medicoes: pd.DataFrame) -> pd.DataFrame:
    """Calcula dispersao amostral e quartis lineares, sem arredondamento.

    A entrada longa deve conter as colunas de GRUPOS e valor. Medidas nao
    numericas ou nao finitas sao contabilizadas, mas nao entram nos calculos.
    Grupos sem medidas validas sao omitidos; n=1 preserva std/var como NaN.
    """
    faltantes = set(GRUPOS + ["valor"]) - set(medicoes.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes nas medicoes: {sorted(faltantes)}")
    if medicoes[GRUPOS].isna().any().any():
        raise ValueError("Identificacao de grupo ausente nas medicoes")
    if medicoes.empty:
        return pd.DataFrame(columns=COLUNAS_RESULTADO)

    preparado = medicoes[GRUPOS + ["valor"]].copy()
    validos = preparado["valor"].map(_numero_finito)
    preparado["valor"] = pd.to_numeric(
        preparado["valor"].where(validos), errors="coerce"
    ).astype(float)
    grupos = preparado.groupby(GRUPOS, sort=True, observed=True)["valor"]
    resultado = grupos.agg(
        n_total="size",
        n_validos="count",
        media="mean",
        mediana="median",
        desvio_padrao="std",
        variancia="var",
    )
    resultado["n_invalidos"] = resultado.pop("n_total") - resultado["n_validos"]
    resultado["q1"] = grupos.quantile(0.25, interpolation="linear")
    resultado["q3"] = grupos.quantile(0.75, interpolation="linear")
    resultado["iqr"] = resultado["q3"] - resultado["q1"]
    resultado["ddof"] = 1
    for grupo, linha in resultado.loc[resultado["n_invalidos"] > 0].iterrows():
        logging.warning(
            "Medidas descartadas: grupo=%s n_invalidos=%s n_validos=%s",
            grupo, int(linha["n_invalidos"]), int(linha["n_validos"]),
        )
    resultado = resultado.loc[resultado["n_validos"] > 0].reset_index()
    obrigatorias = ["media", "mediana", "q1", "q3", "iqr"]
    if not resultado[obrigatorias].map(_numero_finito).all().all():
        raise ValueError("Resultado estatistico nao finito")
    dispersao = resultado.loc[resultado["n_validos"] > 1, ["variancia", "desvio_padrao"]]
    if not dispersao.map(_numero_finito).all().all():
        raise ValueError("Dispersao estatistica nao finita")
    return resultado[COLUNAS_RESULTADO]


def calcular_z_scores(medicoes: pd.DataFrame, limiar: float = 3.0) -> pd.DataFrame:
    """Avalia cada medida contra a media/desvio amostral do proprio grupo.

    Preserva ordem, identidade e cardinalidade, independentemente do indice.
    Resultados indefinidos possuem escore/indicador ausentes e status explicito.
    """
    if not _numero_finito(limiar) or limiar <= 0:
        raise ValueError("Limiar de Z-Score deve ser numerico, finito e positivo")
    estatisticas = calcular_estatisticas(medicoes)
    colunas = GRUPOS + [
        coluna for coluna in ["id_leitura_origem", "data_leitura", "valor"]
        if coluna in medicoes
    ]
    resultado = medicoes[colunas].reset_index(drop=True).copy()
    referencia = ["n_validos", "n_invalidos", "media", "desvio_padrao"]
    if estatisticas.empty:
        for coluna in referencia:
            resultado[coluna] = float("nan")
    else:
        resultado = resultado.merge(
            estatisticas[GRUPOS + referencia], on=GRUPOS,
            how="left", sort=False, validate="many_to_one",
        )
    tamanhos = resultado.groupby(GRUPOS, observed=True)["valor"].transform("size")
    resultado["n_validos"] = resultado["n_validos"].fillna(0).astype("int64")
    resultado["n_invalidos"] = resultado["n_invalidos"].fillna(tamanhos).astype("int64")
    validos = resultado["valor"].map(_numero_finito).astype(bool)
    resultado["valor"] = pd.to_numeric(
        resultado["valor"].where(validos), errors="coerce"
    ).astype(float)
    resultado["ddof"] = 1
    resultado["limiar_zscore"] = float(limiar)
    resultado["z_score"] = float("nan")
    resultado["anomalia_zscore"] = pd.Series(pd.NA, index=resultado.index, dtype="boolean")
    resultado["status_zscore"] = "medida_invalida"
    insuficientes = validos & resultado["n_validos"].lt(2)
    constantes = validos & resultado["n_validos"].ge(2) & resultado["desvio_padrao"].eq(0)
    avaliaveis = validos & resultado["n_validos"].ge(2) & resultado["desvio_padrao"].gt(0)
    resultado.loc[insuficientes, "status_zscore"] = "amostra_insuficiente"
    resultado.loc[constantes, "status_zscore"] = "desvio_zero"
    escores = (
        resultado.loc[avaliaveis, "valor"] - resultado.loc[avaliaveis, "media"]
    ) / resultado.loc[avaliaveis, "desvio_padrao"]
    if not escores.map(_numero_finito).all():
        raise ValueError("Z-Score nao finito em medida avaliavel")
    resultado.loc[avaliaveis, "z_score"] = escores
    resultado.loc[avaliaveis, "anomalia_zscore"] = escores.abs().gt(limiar)
    resultado.loc[avaliaveis, "status_zscore"] = "avaliado"
    pendentes = resultado.loc[~avaliaveis, "status_zscore"].value_counts().to_dict()
    if pendentes:
        logging.warning("Medidas sem Z-Score calculavel: %s", pendentes)
    return resultado


def calcular_iqr_flags(
    medicoes: pd.DataFrame, fator: float = 1.5
) -> pd.DataFrame:
    """Classifica cada medicao pela regra de Tukey dentro do proprio grupo."""
    if not _numero_finito(fator) or fator <= 0:
        raise ValueError("Fator IQR deve ser numerico, finito e positivo")
    faltantes = set(GRUPOS + ["valor"]) - set(medicoes.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes nas medicoes: {sorted(faltantes)}")

    estatisticas = calcular_estatisticas(medicoes)
    resultado = medicoes.reset_index(drop=True).copy()
    if estatisticas.empty:
        resultado["q1"] = float("nan")
        resultado["q3"] = float("nan")
    else:
        resultado = resultado.merge(
            estatisticas[GRUPOS + ["q1", "q3"]],
            on=GRUPOS,
            how="left",
            sort=False,
            validate="many_to_one",
        )

    valores_validos = resultado["valor"].map(_numero_finito).astype(bool)
    resultado["valor"] = pd.to_numeric(
        resultado["valor"].where(valores_validos), errors="coerce"
    ).astype(float)
    resultado["iqr"] = resultado["q3"] - resultado["q1"]
    resultado["limite_inferior_iqr"] = resultado["q1"] - fator * resultado["iqr"]
    resultado["limite_superior_iqr"] = resultado["q3"] + fator * resultado["iqr"]
    flags = pd.Series(pd.NA, index=resultado.index, dtype="boolean")
    flags.loc[valores_validos] = (
        resultado.loc[valores_validos, "valor"].lt(
            resultado.loc[valores_validos, "limite_inferior_iqr"]
        )
        | resultado.loc[valores_validos, "valor"].gt(
            resultado.loc[valores_validos, "limite_superior_iqr"]
        )
    )
    resultado["anomalia_iqr"] = flags
    resultado["status_iqr"] = "medida_invalida"
    resultado.loc[valores_validos, "status_iqr"] = "avaliado"
    resultado["fator_iqr"] = float(fator)
    return resultado


def calcular_anomalias(
    medicoes: pd.DataFrame, fator_iqr: float = 1.5, limiar_zscore: float = 3.0
) -> pd.DataFrame:
    """Combina os indicadores IQR e Z-Score sem alterar a cardinalidade."""
    resultado = calcular_iqr_flags(medicoes, fator_iqr)
    z_scores = calcular_z_scores(medicoes, limiar_zscore)
    resultado["z_score"] = z_scores["z_score"].to_numpy()
    resultado["anomalia_zscore"] = pd.array(
        z_scores["anomalia_zscore"], dtype="boolean"
    )
    resultado["status_zscore"] = z_scores["status_zscore"].to_numpy()
    alerta = pd.Series(pd.NA, index=resultado.index, dtype="boolean")
    avaliadas = resultado["anomalia_iqr"].notna() | resultado["anomalia_zscore"].notna()
    alerta.loc[avaliadas] = (
        resultado.loc[avaliadas, "anomalia_iqr"].fillna(False)
        | resultado.loc[avaliadas, "anomalia_zscore"].fillna(False)
    )
    resultado["alerta_qualidade"] = alerta
    return resultado


def _data_utc(valor: str) -> pd.Timestamp:
    try:
        data = date.fromisoformat(valor)
        if data.isoformat() != valor:
            raise ValueError
        return pd.Timestamp(data, tz="UTC")
    except (TypeError, ValueError) as erro:
        raise ValueError("Data invalida: use YYYY-MM-DD") from erro


def _limites(data_inicio: str | None, data_fim: str | None):
    inicio = _data_utc(data_inicio) if data_inicio is not None else None
    fim = _data_utc(data_fim) + pd.Timedelta(days=1) if data_fim is not None else None
    if inicio is not None and fim is not None and inicio >= fim:
        raise ValueError("Data inicial posterior a data final")
    return inicio, fim


def _caminho_projeto(caminho: str | Path) -> Path:
    resolvido = Path(caminho).expanduser()
    return resolvido if resolvido.is_absolute() else PROJECT_ROOT / resolvido


def _validar_leituras(df: pd.DataFrame, dataset: str, contexto: str) -> pd.DataFrame:
    contrato = CONTRATOS_DATASETS[dataset]
    faltantes = set(contrato["obrigatorias"]) - set(df.columns)
    if faltantes:
        raise ValueError(f"{contexto}: colunas ausentes: {sorted(faltantes)}")
    preparado = df.copy()
    for coluna in contrato["relacoes"]:
        validos = preparado[coluna].map(
            lambda valor: _numero_finito(valor)
            and float(valor) > 0 and float(valor).is_integer()
        )
        if not validos.all():
            raise ValueError(f"{contexto}: identificador invalido em {coluna}")
        preparado[coluna] = preparado[coluna].astype("int64")
    if "id_leitura_origem" in contrato["chave"]:
        chaves = preparado["id_leitura_origem"]
        validas = chaves.map(lambda valor: isinstance(valor, str) and bool(valor.strip()))
        if not validas.all():
            raise ValueError(f"{contexto}: id_leitura_origem invalido")
        preparado["id_leitura_origem"] = chaves.str.strip()
    datas = preparado["data_leitura"]
    if datas.map(pd.api.types.is_number).any():
        raise ValueError(f"{contexto}: timestamp numerico invalido")
    preparado["data_leitura"] = pd.to_datetime(
        datas, errors="coerce", utc=True, format="mixed"
    )
    if preparado["data_leitura"].isna().any():
        raise ValueError(f"{contexto}: data_leitura invalida")
    return preparado


def ler_medicoes_silver(
    silver_dir: str | Path | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> pd.DataFrame:
    """Le os dois datasets Silver sem alterar os arquivos ou acessar o banco.

    Datas opcionais sao dias UTC inclusivos. Chaves duplicadas, mesmo com
    valores iguais, sao erro de integridade, nao medicoes adicionais.
    """
    inicio, fim = _limites(data_inicio, data_fim)
    raiz = get_silver_dir() if silver_dir is None else _caminho_projeto(silver_dir)
    medicoes = []
    for dataset, contrato in CONTRATOS_DATASETS.items():
        partes = []
        for particao in sorted((raiz / dataset).glob("data_leitura=*")):
            dia = _data_utc(particao.name.split("=", 1)[1])
            if (inicio is not None and dia < inicio) or (fim is not None and dia >= fim):
                continue
            for arquivo in sorted(particao.glob("*.parquet")):
                try:
                    parte = pd.read_parquet(arquivo, engine="pyarrow")
                except Exception as erro:
                    raise ValueError(f"Falha ao ler Parquet: {arquivo}") from erro
                parte = _validar_leituras(parte, dataset, str(arquivo))
                if not parte["data_leitura"].between(
                    dia, dia + pd.Timedelta(days=1), inclusive="left"
                ).all():
                    raise ValueError(f"{arquivo}: data_leitura fora da particao UTC")
                partes.append(parte)
        if not partes:
            logging.warning("Dataset sem particoes no periodo: %s", dataset)
            continue
        leituras = pd.concat(partes, ignore_index=True)
        if leituras.duplicated(contrato["chave"]).any():
            raise ValueError(f"Chaves duplicadas na Silver: {dataset}")
        if "id_leitura_origem" not in leituras:
            leituras["id_leitura_origem"] = pd.NA
        longas = leituras.melt(
            id_vars=["id_estacao", "data_leitura", "id_leitura_origem"],
            value_vars=contrato["numericas"],
            var_name="coluna_parametro", value_name="valor",
        )
        longas["dataset"] = dataset
        longas["codigo_parametro"] = longas["coluna_parametro"].map(PARAMETROS)
        longas["unidade_medida"] = longas["codigo_parametro"].map(UNIDADES)
        medicoes.append(longas[GRUPOS + ["id_leitura_origem", "data_leitura", "valor"]])
        logging.info("Silver lida: dataset=%s leituras=%s", dataset, len(leituras))
    if not medicoes:
        raise ValueError("Nenhuma leitura Silver disponivel no periodo")
    return pd.concat(medicoes, ignore_index=True)


def _gravar_csv_atomico(resultado: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destino.parent, prefix=f".{destino.stem}.", suffix=".tmp", delete=False
        ) as arquivo:
            temporario = Path(arquivo.name)
        resultado.to_csv(temporario, sep=";", encoding="utf-8-sig", index=False, na_rep="")
        os.replace(temporario, destino)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def gerar_relatorio_estatistico(
    silver_dir: str | Path | None = None,
    saida: str | Path | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> pd.DataFrame:
    """Recalcula e publica um snapshot CSV atomicamente, preservando a Silver."""
    inicio, fim = _limites(data_inicio, data_fim)
    destino = SAIDA_PADRAO if saida is None else _caminho_projeto(saida)
    raiz = get_silver_dir() if silver_dir is None else _caminho_projeto(silver_dir)
    if destino.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("O relatorio deve ficar fora da Silver")
    medicoes = ler_medicoes_silver(raiz, data_inicio, data_fim)
    resultado = calcular_estatisticas(medicoes)
    if resultado.empty:
        raise ValueError("Nenhuma medida valida para publicar o relatorio")
    if inicio is None:
        inicio = medicoes["data_leitura"].min().floor("D")
    if fim is None:
        fim = medicoes["data_leitura"].max().floor("D") + pd.Timedelta(days=1)
    resultado.insert(4, "periodo_inicio_utc", inicio.isoformat())
    resultado.insert(5, "periodo_fim_exclusivo_utc", fim.isoformat())
    _gravar_csv_atomico(resultado, destino)
    logging.info(
        "Relatorio estatistico publicado: grupos=%s n_validos=%s n_invalidos=%s "
        "inicio=%s fim_exclusivo=%s saida=%s",
        len(resultado), int(resultado["n_validos"].sum()),
        int(resultado["n_invalidos"].sum()), inicio.isoformat(), fim.isoformat(), destino,
    )
    return resultado


def gerar_relatorio_zscore(
    silver_dir: str | Path | None = None,
    saida: str | Path | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    limiar: float = 3.0,
) -> pd.DataFrame:
    """Publica Z-Score por medicao em CSV separado, sem modificar a Silver."""
    if not _numero_finito(limiar) or limiar <= 0:
        raise ValueError("Limiar de Z-Score deve ser numerico, finito e positivo")
    inicio, fim = _limites(data_inicio, data_fim)
    destino = SAIDA_ZSCORE if saida is None else _caminho_projeto(saida)
    raiz = get_silver_dir() if silver_dir is None else _caminho_projeto(silver_dir)
    if destino.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("O relatorio deve ficar fora da Silver")
    medicoes = ler_medicoes_silver(raiz, data_inicio, data_fim)
    resultado = calcular_z_scores(medicoes, limiar)
    if resultado.empty or resultado["n_validos"].eq(0).all():
        raise ValueError("Nenhuma medida valida para publicar o relatorio")
    if inicio is None:
        inicio = medicoes["data_leitura"].min().floor("D")
    if fim is None:
        fim = medicoes["data_leitura"].max().floor("D") + pd.Timedelta(days=1)
    resultado["periodo_inicio_utc"] = inicio.isoformat()
    resultado["periodo_fim_exclusivo_utc"] = fim.isoformat()
    resultado = resultado.sort_values(
        GRUPOS + ["data_leitura", "id_leitura_origem"], kind="stable"
    ).reset_index(drop=True)
    _gravar_csv_atomico(resultado, destino)
    logging.info(
        "Relatorio Z-Score publicado: grupos=%s medidas=%s avaliadas=%s "
        "anomalias=%s limiar=%s inicio=%s fim_exclusivo=%s saida=%s",
        len(resultado[GRUPOS].drop_duplicates()), len(resultado),
        int(resultado["status_zscore"].eq("avaliado").sum()),
        int(resultado["anomalia_zscore"].sum()), limiar,
        inicio.isoformat(), fim.isoformat(), destino,
    )
    return resultado


def gerar_relatorio_anomalias(
    silver_dir: str | Path | None = None,
    saida: str | Path | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    fator_iqr: float = 1.5,
    limiar_zscore: float = 3.0,
) -> pd.DataFrame:
    """Publica flags IQR, Z-Score e alerta por leitura em CSV."""
    inicio, fim = _limites(data_inicio, data_fim)
    destino = (
        PROJECT_ROOT / "data_lakehouse" / "gold" / "alertas_qualidade.csv"
        if saida is None
        else _caminho_projeto(saida)
    )
    raiz = get_silver_dir() if silver_dir is None else _caminho_projeto(silver_dir)
    if destino.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("O relatorio deve ficar fora da Silver")
    medicoes = ler_medicoes_silver(raiz, data_inicio, data_fim)
    resultado = calcular_anomalias(medicoes, fator_iqr, limiar_zscore)
    if inicio is None:
        inicio = medicoes["data_leitura"].min().floor("D")
    if fim is None:
        fim = medicoes["data_leitura"].max().floor("D") + pd.Timedelta(days=1)
    resultado["periodo_inicio_utc"] = inicio.isoformat()
    resultado["periodo_fim_exclusivo_utc"] = fim.isoformat()
    _gravar_csv_atomico(resultado, destino)
    logging.info(
        "Alertas Gold publicados: medidas=%s iqr=%s zscore=%s alertas=%s saida=%s",
        len(resultado),
        int(resultado["anomalia_iqr"].fillna(False).sum()),
        int(resultado["anomalia_zscore"].fillna(False).sum()),
        int(resultado["alerta_qualidade"].fillna(False).sum()),
        destino,
    )
    return resultado


def construir_modelo_estrela(
    medicoes: pd.DataFrame,
    diretorio_cadastros: str | Path | None = None,
    fator_iqr: float = 1.5,
    limiar_zscore: float = 3.0,
) -> dict[str, pd.DataFrame]:
    """Constrói dimensões e fato com chaves substitutas determinísticas."""
    faltantes = set(GRUPOS + ["data_leitura", "valor"]) - set(medicoes.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes nas medicoes Gold: {sorted(faltantes)}")
    if medicoes.empty:
        raise ValueError("Nao ha medicoes Silver para construir a Gold")

    fatos = calcular_anomalias(medicoes, fator_iqr, limiar_zscore)
    fatos["data_leitura"] = pd.to_datetime(
        fatos["data_leitura"], errors="coerce", utc=True, format="mixed"
    )
    if fatos["data_leitura"].isna().any():
        raise ValueError("Timestamp invalido para a dimensao de tempo")

    ids_estacao = sorted(pd.to_numeric(fatos["id_estacao"], errors="raise").astype("int64").unique())
    if diretorio_cadastros is None:
        raiz_cadastros = get_silver_dir() / "cadastros"
    else:
        raiz_cadastros = Path(diretorio_cadastros)
    estacoes_path = raiz_cadastros / "estacoes.parquet"
    cidades_path = raiz_cadastros / "cidades.parquet"
    estados_path = raiz_cadastros / "estados.parquet"

    colunas_estacao = [
        "id_estacao", "codigo_origem", "nome_estacao", "status_estacao",
        "id_cidade", "nome_cidade", "codigo_ibge_cidade", "sigla_estado",
        "nome_estado",
    ]
    if estacoes_path.is_file():
        dim_estacao = pd.read_parquet(estacoes_path, engine="pyarrow")
        if "id_estacao" not in dim_estacao:
            raise ValueError("Cadastro Silver de estacoes sem id_estacao")
        if dim_estacao["id_estacao"].duplicated().any():
            raise ValueError("Cadastro Silver de estacoes possui chaves duplicadas")
        if cidades_path.is_file() and "id_cidade" in dim_estacao:
            cidades = pd.read_parquet(cidades_path, engine="pyarrow")
            dim_estacao = dim_estacao.merge(
                cidades, on="id_cidade", how="left", validate="many_to_one",
                suffixes=("", "_cidade"),
            )
        if estados_path.is_file() and "id_estado" in dim_estacao:
            estados = pd.read_parquet(estados_path, engine="pyarrow")
            dim_estacao = dim_estacao.merge(
                estados, on="id_estado", how="left", validate="many_to_one",
                suffixes=("", "_estado"),
            )
        dim_estacao = dim_estacao.loc[
            dim_estacao["id_estacao"].isin(ids_estacao)
        ].copy()
        dim_estacao = dim_estacao.set_index("id_estacao").reindex(ids_estacao).reset_index()
    else:
        dim_estacao = pd.DataFrame({"id_estacao": ids_estacao})
    for coluna in colunas_estacao:
        if coluna not in dim_estacao:
            dim_estacao[coluna] = pd.NA
    dim_estacao = dim_estacao[colunas_estacao]
    dim_estacao.insert(0, "sk_estacao", range(1, len(dim_estacao) + 1))

    catalogo = {item["codigo"]: item for item in CATALOGO_PARAMETROS}
    codigos = sorted(fatos["codigo_parametro"].dropna().astype(str).unique())
    dim_parametro = pd.DataFrame(
        [
            {
                "codigo_parametro": codigo,
                "nome_parametro": catalogo.get(codigo, {}).get("nome", codigo),
                "unidade_medida": UNIDADES.get(codigo, "desconhecida"),
            }
            for codigo in codigos
        ]
    )
    dim_parametro.insert(0, "sk_parametro", range(1, len(dim_parametro) + 1))

    dias = fatos["data_leitura"].dt.floor("D").drop_duplicates().sort_values().reset_index(drop=True)
    dim_tempo = pd.DataFrame({"data": dias})
    dim_tempo.insert(0, "sk_tempo", range(1, len(dim_tempo) + 1))
    dim_tempo["ano"] = dim_tempo["data"].dt.year
    dim_tempo["mes"] = dim_tempo["data"].dt.month
    dim_tempo["dia"] = dim_tempo["data"].dt.day
    dim_tempo["trimestre"] = dim_tempo["data"].dt.quarter
    dim_tempo["dia_semana"] = dim_tempo["data"].dt.day_of_week
    dim_tempo["dia_util"] = dim_tempo["dia_semana"].lt(5)

    fatos = fatos.sort_values(
        ["dataset", "id_estacao", "codigo_parametro", "data_leitura"],
        kind="stable",
    ).reset_index(drop=True)
    fatos["media_movel"] = fatos.groupby(
        ["dataset", "id_estacao", "codigo_parametro"], sort=False
    )["valor"].transform(
        lambda valores: pd.to_numeric(valores, errors="coerce").rolling(
            window=7, min_periods=1
        ).mean()
    )
    fatos["_dia"] = fatos["data_leitura"].dt.floor("D")
    fatos = fatos.merge(
        dim_estacao[["sk_estacao", "id_estacao"]],
        on="id_estacao", how="left", validate="many_to_one",
    )
    fatos = fatos.merge(
        dim_parametro[["sk_parametro", "codigo_parametro"]],
        on="codigo_parametro", how="left", validate="many_to_one",
    )
    fatos = fatos.merge(
        dim_tempo[["sk_tempo", "data"]],
        left_on="_dia", right_on="data", how="left", validate="many_to_one",
    )
    if fatos[["sk_estacao", "sk_parametro", "sk_tempo"]].isna().any().any():
        raise ValueError("Fato Gold sem correspondencia em uma dimensao")
    fato_medicoes = fatos[
        [
            "sk_estacao", "sk_tempo", "sk_parametro", "dataset",
            "id_leitura_origem", "data_leitura", "valor", "media_movel",
            "anomalia_iqr", "anomalia_zscore", "alerta_qualidade",
        ]
    ].rename(columns={"valor": "valor_lido"})
    return {
        "Dim_Estacao": dim_estacao,
        "Dim_Tempo": dim_tempo,
        "Dim_Parametro": dim_parametro,
        "Fato_Medicoes": fato_medicoes,
    }


def _gravar_parquet_gold(tabela: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destino.parent,
            prefix=f".{destino.stem}.",
            suffix=".parquet",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
        tabela.to_parquet(temporario, engine="pyarrow", compression="snappy", index=False)
        os.replace(temporario, destino)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def gerar_modelo_estrela(
    silver_dir: str | Path | None = None,
    gold_dir: str | Path | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> dict[str, Path]:
    """Materializa fato e dimensoes como Parquet Snappy na pasta Gold."""
    medicoes = ler_medicoes_silver(silver_dir, data_inicio, data_fim)
    raiz_silver = get_silver_dir() if silver_dir is None else _caminho_projeto(silver_dir)
    dimensoes_fato = construir_modelo_estrela(
        medicoes, diretorio_cadastros=raiz_silver / "cadastros"
    )
    destino = (
        PROJECT_ROOT / "data_lakehouse" / "gold"
        if gold_dir is None
        else _caminho_projeto(gold_dir)
    )
    if destino.resolve().is_relative_to(raiz_silver.resolve()):
        raise ValueError("O modelo Gold deve ficar fora da Silver")
    caminhos = {}
    for nome, tabela in dimensoes_fato.items():
        caminho = destino / f"{nome}.parquet"
        _gravar_parquet_gold(tabela, caminho)
        caminhos[nome] = caminho
    return caminhos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analise",
        choices=["estatisticas", "zscore", "anomalias", "star_schema"],
        default="estatisticas",
    )
    parser.add_argument("--limiar", type=float, default=3.0, help="Limiar positivo de |z| no modo zscore; padrao: 3")
    parser.add_argument("--fator-iqr", type=float, default=1.5, help="Multiplicador IQR no modo anomalias; padrao: 1.5")
    parser.add_argument("--silver-dir", help="Diretorio Silver; padrao: SILVER_DIR")
    parser.add_argument("--saida", help="CSV de destino; padrao em data_lakehouse/gold/ conforme --analise")
    parser.add_argument("--data-inicio", help="Primeiro dia UTC, YYYY-MM-DD, inclusivo")
    parser.add_argument("--data-fim", help="Ultimo dia UTC, YYYY-MM-DD, inclusivo")
    argumentos = parser.parse_args(argv)
    try:
        configure_logging(categoria="execucao")
        logging.info("Iniciando analise Silver: %s", argumentos.analise)
        opcoes = {
            "silver_dir": argumentos.silver_dir, "saida": argumentos.saida,
            "data_inicio": argumentos.data_inicio, "data_fim": argumentos.data_fim,
        }
        if argumentos.analise == "zscore":
            gerar_relatorio_zscore(**opcoes, limiar=argumentos.limiar)
        elif argumentos.analise == "anomalias":
            gerar_relatorio_anomalias(
                **opcoes,
                fator_iqr=argumentos.fator_iqr,
                limiar_zscore=argumentos.limiar,
            )
        elif argumentos.analise == "star_schema":
            gerar_modelo_estrela(
                silver_dir=argumentos.silver_dir,
                gold_dir=argumentos.saida,
                data_inicio=argumentos.data_inicio,
                data_fim=argumentos.data_fim,
            )
        else:
            gerar_relatorio_estatistico(**opcoes)
    except Exception:
        logging.exception("Falha ao gerar relatorio: analise=%s", argumentos.analise)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())