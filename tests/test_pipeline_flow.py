"""Fluxo Bronze (JSONL) -> Silver -> Gold sem banco relacional."""

import pandas as pd

from config.settings import get_silver_dir
from src.bronze.ingestion import _gravar_bronze
from src.bronze.leitor_bronze import ler_registros_bronze
from src.pipeline_orchestrator import executar_pipeline


def _ambiental(indice: int, ph: float, estacao: str = "E1") -> dict:
    return {
        "id": f"a{indice}",
        "estacao_id": estacao,
        "timestamp": f"2026-10-0{indice}T10:00:00Z",
        "qualidade_agua": {
            "temperatura": {"valor": 20 + indice},
            "ph": {"valor": ph},
            "oxigenio_dissolvido": {"valor": 8},
            "condutividade": {"valor": 100},
            "turbidez": {"valor": 3},
        },
    }


def _meteorologica(indice: int) -> dict:
    return {
        "id": f"m{indice}",
        "estacao_id": "E1",
        "timestamp": f"2026-10-0{indice}T12:00:00Z",
        "cidade": "Recife",
        "estado": "PE",
        "dados_meteorologicos": {
            "temperatura_ar": {"valor": 30 + indice},
            "umidade": {"valor": 60},
            "chuva": {"valor": 0},
            "vento": {"velocidade": 10},
            "condicao": {"description": "sol"},
        },
    }


def _preparar(tmp_path):
    bronze = tmp_path / "bronze"
    ambientais = [_ambiental(i, 7.0 + i / 10) for i in range(1, 6)]
    ambientais.append(_ambiental(6, 7.0, estacao="SEM-CADASTRO"))
    _gravar_bronze(ambientais, "ambiental", "teste", bronze)
    _gravar_bronze(
        [_meteorologica(i) for i in range(1, 6)], "meteorologica", "teste", bronze
    )
    cadastros = get_silver_dir() / "cadastros"
    cadastros.mkdir(parents=True)
    pd.DataFrame(
        [{"id_estacao": 1, "codigo_origem": "E1", "nome_estacao": "Rio", "id_cidade": 10}]
    ).to_parquet(cadastros / "estacoes.parquet", index=False)
    return bronze


def _linhas_silver(dataset: str) -> int:
    arquivos = (get_silver_dir() / dataset).rglob("*.parquet")
    return sum(len(pd.read_parquet(arquivo)) for arquivo in arquivos)


def test_reader_returns_records_without_metadata(tmp_path):
    bronze = _preparar(tmp_path)

    registros = ler_registros_bronze("ambiental", bronze)

    assert [r["id"] for r in registros][:2] == ["a1", "a2"]
    assert "ingested_at" not in registros[0]


def test_pipeline_runs_bronze_silver_gold_without_sql_and_is_idempotent(tmp_path):
    bronze = _preparar(tmp_path)
    gold = tmp_path / "gold"

    primeiro = executar_pipeline(diretorio_bronze=bronze, diretorio_gold=gold)
    segundo = executar_pipeline(diretorio_bronze=bronze, diretorio_gold=gold)

    assert primeiro["qualidade_agua"] == 5
    assert primeiro["leitura_meteorologica"] == 5
    assert _linhas_silver("qualidade_agua") == 5
    assert _linhas_silver("leitura_meteorologica") == 5
    assert segundo["qualidade_agua"] == 5
    fato = pd.read_parquet(gold / "Fato_Medicoes.parquet")
    assert len(fato) == 5 * 5 + 4 * 5
    for nome in ("Dim_Estacao", "Dim_Tempo", "Dim_Parametro"):
        assert (gold / f"{nome}.parquet").is_file()
    assert (gold / "alertas_qualidade.csv").is_file()


def test_apenas_gold_reads_existing_silver(tmp_path):
    bronze = _preparar(tmp_path)
    gold = tmp_path / "gold"
    executar_pipeline(diretorio_bronze=bronze, diretorio_gold=gold)
    (gold / "Fato_Medicoes.parquet").unlink()

    executar_pipeline(apenas_gold=True, diretorio_gold=gold)

    assert (gold / "Fato_Medicoes.parquet").is_file()
