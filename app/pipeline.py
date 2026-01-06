import time
import os
from extract_bronze import extract_raw_data
from process_silver import process_silver_data
from process_gold import process_gold_data

def run_pipeline():
    """
    Orquestra a execução sequencial das camadas:
    Bronze (Extração) -> Silver (Carga/Limpeza) -> Gold (KPIs)
    """
    start_time = time.time()
    
    print("\n=================================================")
    print(f"INICIANDO PIPELINE DE DADOS: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=================================================\n")

    # --- ETAPA 1: BRONZE (Extração) ---
    # A função deve retornar o caminho do arquivo JSON salvo
    print("--- [1/3] Executando Camada Bronze ---")
    novo_arquivo_json = extract_raw_data()

    if not novo_arquivo_json:
        print("Pipeline interrompido: Falha na extração ou nenhum dado retornado.")
        return

    # --- ETAPA 2: SILVER (Limpeza e Carga) ---
    # Passamos o arquivo gerado na etapa anterior
    print("\n--- [2/3] Executando Camada Silver ---")
    try:
        process_silver_data(novo_arquivo_json)
    except Exception as e:
        print(f"Pipeline interrompido na Silver: {e}")
        return

    # --- ETAPA 3: GOLD (Agregação) ---
    # Calcula os KPIs baseados nos dados novos
    print("\n--- [3/3] Executando Camada Gold ---")
    try:
        process_gold_data()
    except Exception as e:
        print(f"Erro na Gold (mas dados foram salvos na Silver): {e}")
        return

    elapsed_time = time.time() - start_time
    print("\n=================================================")
    print(f"PIPELINE FINALIZADO COM SUCESSO em {elapsed_time:.2f}s")
    print("=================================================")

if __name__ == "__main__":
    # --- MODO DE EXECUÇÃO ---
    
    # Opção 1: Rodar uma única vez (ideal para testar agora)
    run_pipeline()

    # Opção 2: Loop Infinito (ex: rodar a cada 30 minutos)
    # Descomente as linhas abaixo se quiser deixar rodando no terminal
    # while True:
    #     run_pipeline()
    #     print("Aguardando 30 minutos para a próxima execução...")
    #     time.sleep(1800) # 1800 segundos = 30 minutos