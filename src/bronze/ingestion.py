"""Consome APIs REST de leituras e persiste registros aprovados na camada Bronze."""

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import PROJECT_ROOT, configure_logging, get_api_raw_dir
from src.bronze.contracts import validar_contrato


CONTRATOS = {
    "ambiental": {
        "lista": "leituras_ambientais",
        "id": "id",
        "medicoes": {
            "qualidade_agua": {
                "temperatura": ("valor",),
                "ph": ("valor",),
                "oxigenio_dissolvido": ("valor",),
                "condutividade": ("valor",),
                "turbidez": ("valor",),
            }
        },
        "textos": (),
        "textos_aninhados": (),
    },
    "meteorologica": {
        "lista": "leituras_meteorologicas",
        "id": "id",
        "medicoes": {
            "dados_meteorologicos": {
                "temperatura_ar": ("valor",),
                "umidade": ("valor",),
                "chuva": ("valor",),
                "vento": ("velocidade",),
            }
        },
        "textos": ("cidade", "estado"),
        "textos_aninhados": (
            ("dados_meteorologicos", "condicao", "description"),
        ),
    },
}


CONTRATO_AGRITEMPO = {
    "documento": ("metadados", "resultados"),
    "metadados": (
        "gerado_em",
        "data_inicial",
        "data_final",
        "total_consultas_configuradas",
        "total_registros_acumulados",
    ),
    "estacao": (
        "uf",
        "id_municipio",
        "id_estacao",
        "capturado_em",
        "detalhes_estacao",
        "dados_climaticos",
    ),
    "detalhes_estacao": (
        "id",
        "nome",
        "municipio",
        "uf",
        "latitude",
        "longitude",
    ),
    "temperaturas_ar": (
        "temperatura_minima",
        "temperatura_maxima",
    ),
}


def _id_agritempo_valido(valor: object) -> bool:
    """Aceita identificadores inteiros positivos ou textos não vazios."""
    return not isinstance(valor, bool) and (
        (isinstance(valor, int) and valor > 0)
        or (isinstance(valor, str) and bool(valor.strip()))
    )


def _data_agritempo_valida(valor: object) -> bool:
    """Verifica se o valor representa uma data ISO 8601 sem componente de hora."""
    if not isinstance(valor, str):
        return False
    try:
        date.fromisoformat(valor)
    except ValueError:
        return False
    return True


def _timestamp_agritempo_valido(valor: object) -> bool:
    """Exige timestamp ISO 8601 com informação explícita de fuso horário."""
    if not isinstance(valor, str) or not valor.strip():
        return False
    try:
        instante = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return instante.tzinfo is not None


def _numero_agritempo_valido(valor: object) -> bool:
    """Aceita números finitos, mas não booleanos (subclasse de int em Python)."""
    return (
        not isinstance(valor, bool)
        and isinstance(valor, (int, float))
        and math.isfinite(valor)
    )


def validar_resultado_agritempo(resultado: object, indice: int = 0) -> list[str]:
    """Valida uma estação e suas observações de temperatura mínima/máxima."""
    prefixo = f"resultados[{indice}]"
    if not isinstance(resultado, dict):
        return [f"{prefixo} deve ser um objeto JSON"]

    erros = [
        f"{prefixo}.{campo} ausente"
        for campo in CONTRATO_AGRITEMPO["estacao"]
        if campo not in resultado
    ]
    id_estacao = resultado.get("id_estacao")
    if not _id_agritempo_valido(id_estacao):
        erros.append(f"{prefixo}.id_estacao inválido")
    id_municipio = resultado.get("id_municipio")
    if isinstance(id_municipio, bool) or not isinstance(id_municipio, (str, int)):
        erros.append(f"{prefixo}.id_municipio deve ser texto ou inteiro")
    elif isinstance(id_municipio, str) and not id_municipio.strip():
        erros.append(f"{prefixo}.id_municipio não pode ser vazio")

    uf = resultado.get("uf")
    if not isinstance(uf, str) or len(uf.strip()) != 2 or not uf.isalpha():
        erros.append(f"{prefixo}.uf deve conter uma sigla de dois caracteres")
    if not _timestamp_agritempo_valido(resultado.get("capturado_em")):
        erros.append(f"{prefixo}.capturado_em deve ser ISO 8601 com fuso horário")

    detalhes = resultado.get("detalhes_estacao")
    if not isinstance(detalhes, dict):
        erros.append(f"{prefixo}.detalhes_estacao deve ser um objeto JSON")
        detalhes = {}
    for campo in CONTRATO_AGRITEMPO["detalhes_estacao"]:
        if campo not in detalhes:
            erros.append(f"{prefixo}.detalhes_estacao.{campo} ausente")
    if detalhes and _id_agritempo_valido(id_estacao) and str(
        detalhes.get("id")
    ) != str(id_estacao):
        erros.append(f"{prefixo}.detalhes_estacao.id não corresponde à estação")
    if isinstance(uf, str) and detalhes.get("uf") != uf:
        erros.append(f"{prefixo}.detalhes_estacao.uf não corresponde à UF")
    for campo in ("nome", "municipio"):
        valor = detalhes.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            erros.append(f"{prefixo}.detalhes_estacao.{campo} deve ser texto não vazio")
    for campo, minimo, maximo in (("latitude", -90, 90), ("longitude", -180, 180)):
        valor = detalhes.get(campo)
        if not _numero_agritempo_valido(valor) or not minimo <= valor <= maximo:
            erros.append(f"{prefixo}.detalhes_estacao.{campo} fora do domínio")

    clima = resultado.get("dados_climaticos")
    if clima == {}:
        clima = []
    if not isinstance(clima, list):
        erros.append(f"{prefixo}.dados_climaticos deve ser lista ou objeto vazio")
        return erros

    for indice_clima, leitura in enumerate(clima):
        caminho = f"{prefixo}.dados_climaticos[{indice_clima}]"
        if not isinstance(leitura, dict):
            erros.append(f"{caminho} deve ser um objeto JSON")
            continue
        campos_obrigatorios = (
            "id",
            "id_estacao",
            "data",
            *CONTRATO_AGRITEMPO["temperaturas_ar"],
        )
        erros.extend(
            f"{caminho}.{campo} ausente"
            for campo in campos_obrigatorios
            if campo not in leitura
        )
        if not _id_agritempo_valido(leitura.get("id")):
            erros.append(f"{caminho}.id inválido")
        if str(leitura.get("id_estacao")) != str(id_estacao):
            erros.append(f"{caminho}.id_estacao não corresponde à estação")
        if not _data_agritempo_valida(leitura.get("data")):
            erros.append(f"{caminho}.data deve ser uma data ISO 8601")

        minimo = leitura.get("temperatura_minima")
        maximo = leitura.get("temperatura_maxima")
        for campo, valor in (
            ("temperatura_minima", minimo),
            ("temperatura_maxima", maximo),
        ):
            if not _numero_agritempo_valido(valor) or not -50 <= valor <= 60:
                erros.append(f"{caminho}.{campo} deve ser numérica entre -50 e 60 °C")
        if (
            _numero_agritempo_valido(minimo)
            and _numero_agritempo_valido(maximo)
            and minimo > maximo
        ):
            erros.append(f"{caminho}.temperatura_minima maior que temperatura_maxima")
        for campo in (
            "temperatura_minima_estimada",
            "temperatura_maxima_estimada",
        ):
            estimada = leitura.get(campo)
            if estimada is not None and not isinstance(estimada, bool):
                erros.append(f"{caminho}.{campo} deve ser booleana")
    return erros


def validar_documento_agritempo(documento: object) -> list[str]:
    """Valida o envelope e os registros do JSON cumulativo da Agritempo."""
    if not isinstance(documento, dict):
        return ["documento deve ser um objeto JSON"]
    erros = [
        f"{campo} ausente"
        for campo in CONTRATO_AGRITEMPO["documento"]
        if campo not in documento
    ]
    metadados = documento.get("metadados")
    if not isinstance(metadados, dict):
        return erros + ["metadados deve ser um objeto JSON"]
    erros.extend(
        f"metadados.{campo} ausente"
        for campo in CONTRATO_AGRITEMPO["metadados"]
        if campo not in metadados
    )
    if not _timestamp_agritempo_valido(metadados.get("gerado_em")):
        erros.append("metadados.gerado_em deve ser ISO 8601 com fuso horário")
    for campo in ("data_inicial", "data_final"):
        if not _data_agritempo_valida(metadados.get(campo)):
            erros.append(f"metadados.{campo} deve ser uma data ISO 8601")
    for campo in ("total_consultas_configuradas", "total_registros_acumulados"):
        valor = metadados.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
            erros.append(f"metadados.{campo} deve ser inteiro não negativo")

    resultados = documento.get("resultados")
    if not isinstance(resultados, list):
        return erros + ["resultados deve ser uma lista"]
    if metadados.get("total_registros_acumulados") != len(resultados):
        erros.append("metadados.total_registros_acumulados não corresponde a resultados")
    for indice, resultado in enumerate(resultados):
        erros.extend(validar_resultado_agritempo(resultado, indice))
    return erros


def extrair_temperaturas_ar(resultados: list[dict]) -> list[dict]:
    """Projeta somente temperaturas mínima e máxima para consumo analítico."""
    leituras = []
    for indice, resultado in enumerate(resultados):
        erros = validar_resultado_agritempo(resultado, indice)
        if erros:
            raise ValueError("; ".join(erros[:10]))
        clima = resultado["dados_climaticos"]
        if clima == {}:
            continue
        detalhes = resultado["detalhes_estacao"]
        for observacao in clima:
            leituras.append(
                {
                    "id_leitura_origem": str(observacao["id"]),
                    "id_estacao": str(resultado["id_estacao"]),
                    "municipio": detalhes["municipio"],
                    "uf": resultado["uf"],
                    "data_leitura": observacao["data"],
                    "temperatura_ar_minima": observacao["temperatura_minima"],
                    "temperatura_ar_maxima": observacao["temperatura_maxima"],
                    "temperatura_ar_minima_estimada": observacao.get(
                        "temperatura_minima_estimada"
                    ),
                    "temperatura_ar_maxima_estimada": observacao.get(
                        "temperatura_maxima_estimada"
                    ),
                }
            )
    return leituras


@dataclass(frozen=True)
class ResultadoIngestao:
    """Resumo imutável da quantidade e do resultado de uma carga REST."""

    dataset: str
    recebidos: int
    aprovados: int
    rejeitados: int
    arquivo_bronze: Path | None
    ok: bool = True


class LimiteRequisicoes:
    """Aplica um limite de janela móvel compartilhado entre endpoints."""

    def __init__(
        self,
        requisicoes_por_minuto: int,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configura o limite e injeta relógio/espera para permitir testes determinísticos."""
        if requisicoes_por_minuto < 1:
            raise ValueError("O limite de requisições deve ser maior que zero.")
        self.requisicoes_por_minuto = requisicoes_por_minuto
        self.relogio = relogio
        self.dormir = dormir
        self._instantes: deque[float] = deque()

    def aguardar_permissao(self) -> None:
        """Aguarda até haver espaço na janela móvel de sessenta segundos."""
        agora = self.relogio()
        while self._instantes and agora - self._instantes[0] >= 60:
            self._instantes.popleft()
        if len(self._instantes) >= self.requisicoes_por_minuto:
            espera = 60 - (agora - self._instantes[0])
            logging.info("Rate limit atingido; aguardando %.2f segundos.", espera)
            self.dormir(espera)
            agora = self.relogio()
            while self._instantes and agora - self._instantes[0] >= 60:
                self._instantes.popleft()
        self._instantes.append(agora)


def _valor_aninhado(registro: dict, objeto: str, campo: str):
    """Retorna um campo aninhado ou None se o valor intermediário não for objeto."""
    conteudo = registro.get(objeto)
    return conteudo.get(campo) if isinstance(conteudo, dict) else None


def validar_registro(dataset: str, registro: object) -> str | None:
    """Valida os campos obrigatórios, medições e timestamp de um registro REST.

    Retorna o primeiro motivo de rejeição encontrado; retorna None se o
    registro estiver de acordo com o contrato do dataset.
    """
    if dataset not in CONTRATOS:
        return f"dataset desconhecido: {dataset}"
    if not isinstance(registro, dict):
        return "registro deve ser um objeto JSON"
    return validar_contrato(dataset, registro)


def _extrair_registros(payload: object, dataset: str) -> list:
    """Normaliza lista, envelope ou objeto individual em uma lista de registros."""
    chave = CONTRATOS[dataset]["lista"]
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("A resposta da API deve ser uma lista ou objeto JSON.")
    if chave in payload:
        registros = payload[chave]
        if not isinstance(registros, list):
            raise ValueError(f"O campo {chave} deve conter uma lista.")
        return registros
    return [payload]


def _fonte_segura(url: str, nome_fonte: str | None) -> str:
    """Escolhe um rótulo de fonte sem incluir credenciais ou query string da URL."""
    if nome_fonte and nome_fonte.strip():
        return nome_fonte.strip()
    partes = urlsplit(url)
    return f"{partes.hostname or 'api'}{partes.path.rstrip('/') or '/'}"


def _gravar_bronze(
    registros: list[dict], dataset: str, fonte: str, diretorio: Path
) -> Path:
    """Grava registros JSONL com metadados, sem alterar arquivos de lotes anteriores.

    O arquivo é escrito primeiro com nome temporário exclusivo e publicado por
    rename ao terminar, evitando deixar um lote parcial como arquivo final.
    """
    instante = datetime.now(timezone.utc)
    nome = f"api_{dataset}_{instante:%Y%m%dT%H%M%S%fZ}_{uuid4().hex}.jsonl"
    destino = diretorio / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    try:
        with temporario.open("x", encoding="utf-8", newline="\n") as arquivo:
            for registro in registros:
                linha = {
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "source": fonte,
                    "dataset": dataset,
                    "record": registro,
                }
                arquivo.write(json.dumps(linha, ensure_ascii=False, allow_nan=False))
                arquivo.write("\n")
        temporario.replace(destino)
    except Exception:
        temporario.unlink(missing_ok=True)
        raise
    return destino


def ingerir_endpoint(
    url: str,
    dataset: str,
    diretorio_bronze: Path,
    limite: LimiteRequisicoes,
    timeout: float = 15,
    token: str | None = None,
    nome_fonte: str | None = None,
) -> ResultadoIngestao:
    """Busca um endpoint, audita rejeições e persiste apenas registros aprovados.

    Falhas de transporte, resposta fora do contrato ou persistência retornam
    um resultado com ``ok=False`` para que o chamador possa interromper o fluxo.
    """
    if dataset not in CONTRATOS:
        raise ValueError(f"Dataset não suportado: {dataset}")
    partes = urlsplit(url)
    if partes.scheme not in {"http", "https"} or not partes.hostname:
        raise ValueError("A URL do endpoint deve usar HTTP ou HTTPS.")

    limite.aguardar_permissao()
    cabecalhos = {"Accept": "application/json", "User-Agent": "pycorders-ingestion/1.0"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    requisicao = Request(url, headers=cabecalhos)
    try:
        with urlopen(requisicao, timeout=timeout) as resposta:
            corpo = resposta.read()
    except HTTPError as erro:
        logging.error(
            "Falha HTTP na ingestão: dataset=%s status=%s fonte=%s",
            dataset,
            erro.code,
            _fonte_segura(url, nome_fonte),
        )
        return ResultadoIngestao(dataset, 0, 0, 0, None, ok=False)
    except (URLError, TimeoutError, OSError) as erro:
        logging.error(
            "Falha de conexão na ingestão: dataset=%s fonte=%s motivo=%s",
            dataset,
            _fonte_segura(url, nome_fonte),
            erro,
        )
        return ResultadoIngestao(dataset, 0, 0, 0, None, ok=False)

    if not corpo.strip():
        logging.warning("Resposta HTTP vazia: dataset=%s fonte=%s", dataset, _fonte_segura(url, nome_fonte))
        return ResultadoIngestao(dataset, 0, 0, 0, None)
    try:
        payload = json.loads(corpo)
        registros = _extrair_registros(payload, dataset)
    except (json.JSONDecodeError, ValueError) as erro:
        logging.error(
            "Resposta fora do contrato JSON: dataset=%s fonte=%s motivo=%s",
            dataset,
            _fonte_segura(url, nome_fonte),
            erro,
        )
        return ResultadoIngestao(dataset, 0, 0, 0, None, ok=False)

    if not registros:
        logging.warning("Resposta sem leituras: dataset=%s fonte=%s", dataset, _fonte_segura(url, nome_fonte))
        return ResultadoIngestao(dataset, 0, 0, 0, None)

    aprovados = []
    rejeitados = 0
    for indice, registro in enumerate(registros):
        motivo = validar_registro(dataset, registro)
        if motivo:
            rejeitados += 1
            identificador = registro.get("id") if isinstance(registro, dict) else None
            estacao = registro.get("estacao_id") if isinstance(registro, dict) else None
            momento_auditoria = datetime.now(timezone.utc).isoformat()
            logging.warning(
                "Auditoria de contrato - Registro da API rejeitado: "
                "dataset=%s indice=%s id=%s estacao_id=%s motivo=%s "
                "momento_utc=%s",
                dataset,
                indice,
                identificador,
                estacao,
                motivo,
                momento_auditoria,
            )
        else:
            aprovados.append(registro)

    arquivo_bronze = None
    if aprovados:
        try:
            arquivo_bronze = _gravar_bronze(
                aprovados,
                dataset,
                _fonte_segura(url, nome_fonte),
                diretorio_bronze,
            )
        except OSError as erro:
            logging.exception(
                "Falha ao persistir lote Bronze: dataset=%s motivo=%s", dataset, erro
            )
            return ResultadoIngestao(
                dataset, len(registros), 0, rejeitados, None, ok=False
            )

    logging.info(
        "Ingestão HTTP concluída: dataset=%s recebidos=%s aprovados=%s rejeitados=%s arquivo=%s",
        dataset,
        len(registros),
        len(aprovados),
        rejeitados,
        arquivo_bronze,
    )
    return ResultadoIngestao(
        dataset, len(registros), len(aprovados), rejeitados, arquivo_bronze
    )


def main() -> int:
    """Executa a ingestão dos endpoints configurados em ``src/config/.env``."""
    configure_logging(PROJECT_ROOT, categoria="tratamento")
    limite = LimiteRequisicoes(int(os.getenv("API_REQUESTS_PER_MINUTE", "30")))
    diretorio_bronze = get_api_raw_dir()
    resultados = []
    for dataset in CONTRATOS:
        sufixo = dataset.upper()
        url = os.getenv(f"API_URL_{sufixo}")
        if not url:
            logging.info("Endpoint não configurado; dataset ignorado: %s", dataset)
            continue
        resultados.append(
            ingerir_endpoint(
                url=url,
                dataset=dataset,
                diretorio_bronze=diretorio_bronze,
                limite=limite,
                timeout=float(os.getenv("API_TIMEOUT_SECONDS", "15")),
                token=os.getenv(f"API_TOKEN_{sufixo}"),
                nome_fonte=os.getenv(f"API_SOURCE_NAME_{sufixo}"),
            )
        )
    if not resultados:
        logging.error("Nenhum endpoint configurado. Defina API_URL_AMBIENTAL e/ou API_URL_METEOROLOGICA.")
        return 1
    return 0 if all(result.ok for result in resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())