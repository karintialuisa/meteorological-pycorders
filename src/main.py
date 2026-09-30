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
arquivo_log = LOGS_DIR / "execucao.log"

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

def executar_script(pasta: str, arquivo: str) -> None:
    """
    Executa um script Python localizado em uma subpasta de 'database'.
    Interrompe a execução e grava o erro caso o script falhe.
    """
    caminho_script = DATABASE_DIR / pasta / arquivo
    
    # Verifica se o arquivo existe antes de tentar executar
    if not caminho_script.exists():
        raise FileNotFoundError(f"O arquivo '{caminho_script}' não foi encontrado.")
    
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
    logging.info("=" * 60)
    logging.info("Iniciando o fluxo de execuções dos Parsers...")
    logging.info("=" * 60)
    
    for pasta, arquivo in PARSER_SEQUENCIA:
        try:
            executar_script(pasta, arquivo)
        except (RuntimeError, FileNotFoundError) as e:
            logging.error(f"ERRO CRÍTICO no processo '{pasta}/{arquivo}'")
            logging.error(f"Detalhes: {e}")
            logging.error("Interrompendo a sequência de execução.")
            logging.info("=" * 60)
            sys.exit(1)  # Encerra o script com código de erro
            
    logging.info("=" * 60)
    logging.info("Todos os Parsers foram executados com SUCESSO!")
    logging.info("=" * 60)

if __name__ == "__main__":
    main()