import json
import pandas as pd
import os
from sqlalchemy import create_engine
from datetime import datetime
from dotenv import load_dotenv
import glob

load_dotenv()
DB_URI = os.getenv("DB_CONNECTION_URI")

def process_silver_data(json_file_path):
    """
    Camada Silver: Lê o arquivo JSON da Bronze, estrutura em DataFrame 
    e salva no Data Warehouse (Postgres).
    """
    print(f"[SILVER] Processando arquivo: {json_file_path}")

    try:
        # 1. Leitura da Bronze
        with open(json_file_path, "r") as f:
            data = json.load(f)

        # 2. Transformação (Seu código original vem aqui)
        records = []
        timestamp_extract = datetime.now() # Ou pegar do nome do arquivo se preferir

        # A estrutura do JSON da CMC é { "data": { "BTC": {...}, "ETH": {...} } }
        # Vamos iterar sobre os valores do dicionário 'data'
        if 'data' in data:
            for symbol, coin_data in data['data'].items():
                quote = coin_data['quote']['USD']
                
                records.append({
                    "symbol": symbol,
                    "name": coin_data['name'],
                    "price_usd": quote['price'],
                    "market_cap": quote['market_cap'],
                    "volume_24h": quote['volume_24h'],
                    "percent_change_24h": quote['percent_change_24h'],
                    "processed_at": timestamp_extract 
                })

        df = pd.DataFrame(records)

        # 3. Load (Salvar no Banco Postgres)
        if not df.empty:
            engine = create_engine(DB_URI)
            # Renomeei a tabela para 'silver_crypto_prices' para ficar semanticamente correto
            df.to_sql('silver_crypto_prices', engine, if_exists='append', index=False)
            print(f"[SILVER] {len(df)} registros salvos no Banco de Dados!")
            
            # (Opcional) Mover o arquivo JSON processado para uma pasta de backup/processados
            # para não processar o mesmo arquivo duas vezes depois.
        
    except Exception as e:
        print(f"[SILVER] Erro no processamento: {e}")

if __name__ == "__main__":
    # Exemplo: Pega o arquivo mais recente da pasta bronze para processar
    list_of_files = glob.glob('data/bronze/*.json')
    if list_of_files:
        latest_file = max(list_of_files, key=os.path.getctime)
        process_silver_data(latest_file)
    else:
        print("Nenhum arquivo novo na Bronze para processar.")