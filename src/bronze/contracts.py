"""Data contracts Pydantic dos registros REST aceitos na camada Bronze."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator
from pydantic_core import PydanticCustomError

Texto = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
Numero = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class _Contrato(BaseModel):
    model_config = ConfigDict(extra="allow")


class _Valor(_Contrato):
    valor: Numero


class _Vento(_Contrato):
    velocidade: Numero


class _Condicao(_Contrato):
    description: Texto


class _QualidadeAgua(_Contrato):
    temperatura: _Valor
    ph: _Valor
    oxigenio_dissolvido: _Valor
    condutividade: _Valor
    turbidez: _Valor


class _DadosMeteorologicos(_Contrato):
    temperatura_ar: _Valor
    umidade: _Valor
    chuva: _Valor
    vento: _Vento
    condicao: _Condicao


class _Leitura(_Contrato):
    id: Texto
    estacao_id: Texto
    timestamp: Texto

    @field_validator("timestamp")
    @classmethod
    def _timestamp_iso_com_fuso(cls, valor: str) -> str:
        try:
            instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            raise PydanticCustomError(
                "timestamp_formato", "tipo/formato incompatível: timestamp deve ser ISO 8601"
            ) from None
        if instante.tzinfo is None:
            raise PydanticCustomError(
                "timestamp_fuso", "tipo/formato incompatível: timestamp deve conter fuso horário"
            )
        return valor


class LeituraAmbiental(_Leitura):
    qualidade_agua: _QualidadeAgua


class LeituraMeteorologica(_Leitura):
    cidade: Texto
    estado: Texto
    dados_meteorologicos: _DadosMeteorologicos


CONTRATOS_PYDANTIC = {
    "ambiental": LeituraAmbiental,
    "meteorologica": LeituraMeteorologica,
}


def _motivo(erro: dict) -> str:
    caminho = ".".join(str(parte) for parte in erro["loc"])
    tipo = erro["type"]
    if tipo.startswith("timestamp_"):
        return erro["msg"]
    if tipo in {"float_type", "float_parsing", "finite_number"}:
        sufixo = "finito" if tipo == "finite_number" else "numérico"
        return f"tipo/formato incompatível: {caminho} deve ser {sufixo}"
    return f"campo obrigatório ausente ou inválido: {caminho}"


def validar_contrato(dataset: str, registro: dict) -> str | None:
    """Retorna o primeiro motivo de rejeição do contrato ou None se válido."""
    try:
        CONTRATOS_PYDANTIC[dataset].model_validate(registro)
    except ValidationError as erro:
        return _motivo(erro.errors()[0])
    return None
