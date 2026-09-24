from pathlib import Path

# Uma função def é nomeada pelo usuário e para que serve? 
# Ela serve para encapsular um bloco de código que pode ser reutilizado várias vezes ao longo do programa.

DIR_MUNICIPIO = Path(__file__).parent / "src" / "ingestion" / "municipio.json"
DIR_ESTADO = Path(__file__).parent / "src" / "ingestion" / "estado.json"


def ler_json(path_arquivo):
    with open(path_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = arquivo.read()
    return print(conteudo)

json_municipio = ler_json()
