"""Estatisticas descritivas de medicoes por estacao e parametro."""

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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import PROJECT_ROOT, configure_logging, get_silver_dir
from src.database.dml.Insert_Parametros import CATALOGO_PARAMETROS
from src.ingestion.leituras.Persistir_Silver import CONTRATOS_DATASETS


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
SAIDA_PADRAO = PROJECT_ROOT / "reports" / "estatisticas_descritivas.csv"


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
        longas = leituras.melt(
            id_vars=["id_estacao", "data_leitura"],
            value_vars=contrato["numericas"],
            var_name="coluna_parametro", value_name="valor",
        )
        longas["dataset"] = dataset
        longas["codigo_parametro"] = longas["coluna_parametro"].map(PARAMETROS)
        longas["unidade_medida"] = longas["codigo_parametro"].map(UNIDADES)
        medicoes.append(longas[GRUPOS + ["data_leitura", "valor"]])
        logging.info("Silver lida: dataset=%s leituras=%s", dataset, len(leituras))
    if not medicoes:
        raise ValueError("Nenhuma leitura Silver disponivel no periodo")
    return pd.concat(medicoes, ignore_index=True)


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
    logging.info(
        "Relatorio estatistico publicado: grupos=%s n_validos=%s n_invalidos=%s "
        "inicio=%s fim_exclusivo=%s saida=%s",
        len(resultado), int(resultado["n_validos"].sum()),
        int(resultado["n_invalidos"].sum()), inicio.isoformat(), fim.isoformat(), destino,
    )
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver-dir", help="Diretorio Silver; padrao: SILVER_DIR")
    parser.add_argument("--saida", help="CSV de destino; padrao: reports/estatisticas_descritivas.csv")
    parser.add_argument("--data-inicio", help="Primeiro dia UTC, YYYY-MM-DD, inclusivo")
    parser.add_argument("--data-fim", help="Ultimo dia UTC, YYYY-MM-DD, inclusivo")
    argumentos = parser.parse_args(argv)
    try:
        configure_logging(categoria="execucao")
        logging.info("Iniciando estatisticas descritivas dos IDs 45-49")
        gerar_relatorio_estatistico(
            silver_dir=argumentos.silver_dir, saida=argumentos.saida,
            data_inicio=argumentos.data_inicio, data_fim=argumentos.data_fim,
        )
    except Exception:
        logging.exception("Falha ao gerar relatorio estatistico")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())