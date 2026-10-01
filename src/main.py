"""Módulo principal da aplicação de processamento meteorológico.

Este arquivo configura o sistema de logs, apresenta o menu interativo da
aplicação e orquestra a execução de scripts de ETL (Extração, Transformação
 e Carga) e de relatórios estatísticos.
"""

import logging
from pathlib import Path
import sys
import subprocess

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d-%m-%Y %H:%M",
    handlers=[
        logging.FileHandler(LOGS_DIR / "execucao_relatorio.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

MENU = {
    "1": "ETL JSON -> BD",
    "2": "Gerar relatórios estatísticos dos dados",
    "3": "Cancelar operação"
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

def executar_script(pasta: str, arquivo: str, interativo: bool = False) -> bool:
    """Executa um script Python do projeto.

    Args:
        pasta (str): Nome da subpasta em que o script está localizado.
        arquivo (str): Nome do arquivo Python a ser executado.
        interativo (bool, optional): Quando True, executa o script diretamente no
            terminal para permitir interação do usuário. Defaults to False.

    Returns:
        bool: True se a execução do script foi bem-sucedida, False em caso de erro.
    """
    caminho_script = BASE_DIR / pasta / arquivo if pasta else BASE_DIR / arquivo
    
    if not caminho_script.exists():
        logging.error(f"O arquivo '{caminho_script}' não foi encontrado.")
        return False

    logging.info("=" * 20 + f" Iniciando: {arquivo} " + "=" * 20)

    # Se for interativo (como o relatório), NÃO usa capture_output
    if interativo:
        resultado = subprocess.run([sys.executable, str(caminho_script)])
        if resultado.returncode != 0:
            logging.error(f"❌ Falha em {arquivo}")
            return False
        logging.info(f"✅ Sucesso em {arquivo}")
        return True

    # Para scripts de backend/insert, captura a saída normalmente
    resultado = subprocess.run(
        [sys.executable, str(caminho_script)],
        capture_output=True,
        text=True
    )

    if resultado.stdout.strip():
        logging.info(f"[{arquivo}] Saída: {resultado.stdout.strip()}")

    if resultado.returncode != 0:
        erro_msg = resultado.stderr.strip() if resultado.stderr else "Erro desconhecido."
        logging.error(f"❌ Falha em {arquivo}:\n{erro_msg}")
        return False
    
    logging.info(f"✅ Sucesso em {arquivo}")
    return True

def main():
    """Ponto de entrada principal da aplicação.

    Mantém o menu principal em execução até que o usuário escolha sair.
    """
    while True:
        opcao = exibir_menu()

        if opcao == "3":
            logging.info("Encerrando a aplicação.")
            break

        elif opcao == "1":
            # Executa os inserts em sequência
            executar_script("database/dml", "Insert_Localizacao.py")
            executar_script("database/dml", "Insert_Leituras_Ambiental.py")
            executar_script("database/dml", "Insert_Leituras_Meteorologica.py")

        elif opcao == "2":
            # Passa interativo=True para permitir o filtro por cidade no terminal
            executar_script("analytics", "Relatorios_estatisticos.py", interativo=True)

        else:
            print("\n ⚠️ Opção inválida! Digite 1, 2 ou 3.")

if __name__ == "__main__":
    main()