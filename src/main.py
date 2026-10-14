"""Módulo principal da aplicação de processamento meteorológico.

Este arquivo configura o sistema de logs, apresenta o menu interativo da
aplicação e orquestra a execução de scripts de ETL (Extração, Transformação
 e Carga) e de relatórios estatísticos.
"""

import logging
from pathlib import Path
import subprocess
import sys

from config.settings import PROJECT_ROOT, configure_logging, get_env

BASE_DIR = PROJECT_ROOT
configure_logging(BASE_DIR)


MENU = {
    "1": "ETL JSON -> BD",
    "2": "Gerar relatórios estatísticos dos dados",
    "3": "Cancelar operação",
    "4": "Coletar meteorologia Agritempo -> JSON",
    "5": "Cadastrar parâmetros, catálogo LGPD e operadores",
}


def exibir_menu() -> str:
    """Exibe as opções disponíveis ao usuário e retorna a escolha informada.

    Returns:
        str: Valor digitado pelo usuário, sem espaços extras.
    """
    opcoes = "\n".join(
        f" {key}. {value}" for key, value in MENU.items()
    )
    logging.info("\n%s\nMenu de opções:\n%s\n%s", "=" * 40, opcoes, "=" * 40)
    return input("Escolha uma opção: ").strip()


def executar_script(caminho_relativo: str, interativo: bool = False) -> bool:
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
        sys.stdout.write(resultado.stdout)

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

            for script in (script_loc, script_amb, script_met):
                if not executar_script(script):
                    logging.error(
                        "Carga ETL interrompida após falha em %s.",
                        Path(script).name,
                    )
                    break

        elif opcao == "2":
            script_rel = get_env("RELATORIO_ESTATISTICO")

            executar_script(
                script_rel, interativo=True
            )

        elif opcao == "4":
            executar_script("Get_dados.py")

        elif opcao == "5":
            # projeto_final.pdf secoes 3.2/3.3 -> features.csv IDs 32-34, 38 e 39.
            scripts_cadastro = (
                "src/database/dml/Insert_Parametros.py",
                "src/database/dml/Insert_Catalogo_LGPD.py",
                "src/database/dml/Insert_Operadores.py",
            )
            for script in scripts_cadastro:
                if not executar_script(script):
                    logging.error(
                        "Cadastro interrompido após falha em %s.",
                        Path(script).name,
                    )
                    break

        else:
            logging.warning("Opção inválida. Digite uma opção de 1 a 5.")


if __name__ == "__main__":
    main()