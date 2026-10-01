"""Orquestra a execução dos scripts de carga de dados no banco.

Este módulo executa em sequência os scripts responsáveis por importar as
informações de localização e de leituras ambientais e meteorológicas para o
SQL Server.
"""

import logging
from pathlib import Path
import sys
import subprocess

# Define caminhos base
# BASE_DIR aponta para a pasta 'src'
BASE_DIR = Path(__file__).resolve().parent
# DATABASE_DIR aponta para 'src/database'
DATABASE_DIR = BASE_DIR / "database"
# LOGS_DIR aponta para a pasta 'logs' na raiz do projeto (fora de 'src')
LOGS_DIR = BASE_DIR.parent / "logs"

# Cria a pasta de logs automaticamente se ela não existir
LOGS_DIR.mkdir(parents=True, exist_ok=True)
arquivo_log = LOGS_DIR / "Insert_db_.log"

# Configuração global do Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(arquivo_log, encoding="utf-8"), # Escreve no arquivo .log
        logging.StreamHandler(sys.stdout)                   # Exibe no terminal
    ]
)

# Lista com a sequência exata dos scripts a serem executados
PARSER_SEQUENCIA = [
    ("dml", "Insert_Localizacao.py"),
    ("dml", "Insert_Leituras_Ambiental.py"),
    ("dml", "Insert_Leituras_Meteorologica.py"),
]

def executar_main(pasta: str, arquivo: str) -> None:
    """Executa um script Python localizado na pasta de dados do projeto.

    Args:
        pasta (str): Nome da subpasta dentro de database onde o script está.
        arquivo (str): Nome do arquivo Python a ser executado.

    Raises:
        FileNotFoundError: Se o arquivo informado não existir.
        RuntimeError: Se a execução do script retornar erro.
    """
    caminho_script = DATABASE_DIR / pasta / arquivo
    
    # Verifica se o arquivo existe antes de tentar executar
    if not caminho_script.exists():
        raise FileNotFoundError(f"O arquivo '{caminho_script}' não foi encontrado.")

    # Caso ele encontre o arquivo, prossegue com a execução
    logging.info(f"Iniciando a execução do script: {pasta}/{arquivo}")
    
    # Executa o script e captura erros caso o código de retorno seja !== 0
    resultado = subprocess.run(
        [sys.executable, str(caminho_script)],
        capture_output=True,
        text=True
    )
    
    # Se o script gerou saídas printadas no terminal, registra como INFO
    if resultado.stdout.strip():
        logging.info(f"[{arquivo}] Saída: {resultado.stdout.strip()}")
        
    # Se o script falhar, registra no erro e interrompe
    if resultado.returncode != 0:
        erro_detalhado = resultado.stderr.strip() if resultado.stderr else "Erro desconhecido na execução."
        raise RuntimeError(f"Falha na execução de '{arquivo}':\n{erro_detalhado}")
    
    logging.info(f"Sucesso: Script {pasta}/{arquivo} finalizado.")

def main():
    """Executa a sequência completa de scripts de carga do projeto.

    A rotina percorre a lista de arquivos em ordem e interrompe a execução caso
    qualquer etapa falhe.
    """
    logging.info("=" * 60)
    logging.info("Iniciando o fluxo de execuções dos Parsers...")
    logging.info("=" * 60)

    # O *FOR* vai iterar (percorrer) a lista definida na constante PARSER_SEQUENCIA, pois ela está dentro de [] -> (uma lista)
    for pasta, arquivo in PARSER_SEQUENCIA:
        try:
            # Aqui estou chamando a minha função criada para acessar as pastas e arquivos e executar dos processos em cadeias (subprocessos), respeitando a ordem definida na sequência.
            executar_main(pasta, arquivo)
        except (RuntimeError, FileNotFoundError) as e:
            logging.error(f"ERRO no processo '{pasta}/{arquivo}'")
            logging.error(f"Detalhes: {e}")
            logging.error("Interrompendo a sequência de execução.")
            logging.info("=" * 60)
            sys.exit(1)  # Encerra o script com código de erro
            
    logging.info("=" * 60)
    logging.info("Todos os Parsers foram executados com SUCESSO!")
    logging.info("=" * 60)

if __name__ == "__main__":
    main()