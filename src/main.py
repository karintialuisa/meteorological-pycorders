"""Módulo principal da aplicação de processamento meteorológico.

Este arquivo configura o sistema de logs, apresenta o menu interativo da
aplicação e orquestra a execução de scripts de ETL (Extração, Transformação
 e Carga) e de relatórios estatísticos.
"""

import logging
import os
from pathlib import Path
import subprocess
import sys
from dotenv import load_dotenv

# Carrega o .env localizado na raiz do projeto
BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BASE_DIR / ".env")


def get_env(chave: str) -> str:
    """Busca uma variável no .env e lança exceção se ela não estiver configurada."""
    valor = os.getenv(chave)
    if not valor:
        raise KeyError(
            f"❌ Configuração ausente: A chave '{chave}' não foi encontrada no arquivo .env"
        )
    return valor


# Diretório de logs vindo estritamente do .env
LOGS_FOLDER = get_env("LOGS_DIR")
LOGS_DIR = BASE_DIR / LOGS_FOLDER
LOGS_DIR.mkdir(parents=True, exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d-%m-%Y %H:%M",
    handlers=[
        logging.FileHandler(
            LOGS_DIR / "execucao_relatorio.log", encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

MENU = {
    "1": "ETL JSON -> BD",
    "2": "Gerar relatórios estatísticos dos dados",
    "3": "Cancelar operação",
}


def exibir_menu() -> str:
    """Exibe as opções disponíveis ao usuário e retorna a escolha informada.

    Returns:
        str: Valor digitado pelo usuário, sem espaços extras.
    """
    print("\n" + "=" * 40)
    print("Menu de opções:")
    for key, value in MENU.items():
        print(f" {key}. {value}")
    print("=" * 40)
    return input("Escolha uma opção: ").strip()


def executar_script(
    caminho_relativo: str, interativo: bool = False
) -> bool:
    caminho_script = BASE_DIR / caminho_relativo

    if not caminho_script.exists():
        logging.error(f"O arquivo '{caminho_script}' não foi encontrado.")
        return False

    logging.info("=" * 20 + f" Iniciando: {caminho_script.name} " + "=" * 20)

    if interativo:
        resultado = subprocess.run([sys.executable, str(caminho_script)])
        if resultado.returncode != 0:
            logging.error(f"❌ Falha em {caminho_script.name}")
            return False
        logging.info(f"✅ Sucesso em {caminho_script.name}")
        return True

    resultado = subprocess.run(
        [sys.executable, str(caminho_script)], capture_output=True, text=True
    )

    if resultado.stdout.strip():
        logging.info(
            f"[{caminho_script.name}] Saída: {resultado.stdout.strip()}"
        )

    if resultado.returncode != 0:
        erro_msg = (
            resultado.stderr.strip()
            if resultado.stderr
            else "Erro desconhecido."
        )
        logging.error(f"❌ Falha em {caminho_script.name}:\n{erro_msg}")
        return False

    logging.info(f"✅ Sucesso em {caminho_script.name}")
    return True


def main():
    """Ponto de entrada principal da aplicação.

    Mantém o menu principal em execução até que o usuário escolha sair.
    """
    while True:
        opcao = exibir_menu()

        if opcao == "3":
            logging.info("Aplicação encerrada pelo usuário ao selecionar a opção '3'.")
            break

        elif opcao == "1":
            # Leitura obrigatória das chaves do .env sem fallbacks
            script_loc = get_env("INSERT_LOCALIZACAO")
            script_amb = get_env("INSERT_LEITURA_AMBIENTAL")
            script_met = get_env("INSERT_LEITURA_METEOROLOGICA")

            executar_script(script_loc)
            executar_script(script_amb)
            executar_script(script_met)

        elif opcao == "2":
            script_rel = get_env("RELATORIO_ESTATISTICO")

            executar_script(
                script_rel, interativo=True
            )

        else:
            print("\n ⚠️ Opção inválida! Digite 1, 2 ou 3.")


if __name__ == "__main__":
    main()