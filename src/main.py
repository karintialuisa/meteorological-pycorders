from pathlib import Path
import sys
import subprocess

# Define o diretório base (onde o main.py está localizado)
BASE_DIR = Path(__file__).resolve().parent / "database"

# Lista com a sequência exata dos scripts a serem executados
# Formato: (nome_da_pasta, nome_do_arquivo)
PARSER_SEQUENCIA = [
    ("dml", "Insert_Localizacao.py"),
    ("dml", "Insert_Leituras_Ambiental.py"),
    ("dml", "Insert_Leituras_Meteorologica.py"),
]

def executar_script(pasta: str, arquivo: str) -> None:
    """
    Executa um script Python localizado em uma pasta específica.
    Interrompe a execução caso o script falhe.
    """
    caminho_main = BASE_DIR / pasta / arquivo
    
    # Verifica se o arquivo realmente existe antes de tentar rodar
    if not caminho_main.exists():
        raise FileNotFoundError(f"O arquivo {caminho_main} não foi encontrado.")
    
    print(f"\n" + "=" * 60)
    print(f"▶ Iniciando: {pasta}/{arquivo}")
    print("=" * 60)
    
    # Executa o script Python especificado, processo por processo via subprocess.run no terminal, aguardando a conclusão de cada um antes de prosseguir.
    subprocess.run([sys.executable, str(caminho_main)], check=True)
    
    print(f"✔ Sucesso: {pasta}/{arquivo} finalizado.")

def main():
    print("▶️ Iniciando o fluxo de execuções dos Parsers...")
    
    for pasta, arquivo in PARSER_SEQUENCIA:
        try:
            executar_script(pasta, arquivo)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("\n" + "❌" * 30)
            print(f"ERRO ao executar '{pasta}/{arquivo}'!")
            print(f"Detalhes do erro: {e}")
            print("Interrompendo a sequência de execução.")
            print("❌" * 30)
            sys.exit(1)  # Encerra o script principal com status de erro
            
    print("\n" + "=" * 60)
    print("✅ Todos os Parsers foram executados com SUCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    main()