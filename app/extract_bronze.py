import os
import requests
import json
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Carregar envs
load_dotenv()
API_KEY = os.getenv("CMC_API_KEY")
DB_URI = os.getenv("DB_CONNECTION_URI")

# Configuração de Pastas
BRONZE_PATH = "data/bronze"
os.makedirs(BRONZE_PATH, exist_ok=True)

# Lista Padrão (Fallback: se o banco estiver vazio, monitora pelo menos essas)
DEFAULT_SYMBOLS = ["BTC", "ETH","LINK","XRP","SOL"]

def get_monitored_symbols():
    """
    Conecta no banco e busca quais ativos o usuário já operou.
    Retorna uma lista única de símbolos (ex: ['BTC', 'ETH', 'XRP']).
    """
    symbols = set(DEFAULT_SYMBOLS) # Usa um set para evitar duplicatas

    try:
        engine = create_engine(DB_URI)
        with engine.connect() as conn:
            # Verifica se a tabela existe antes de tentar ler
            check_table = conn.execute(text("SELECT to_regclass('public.user_transactions');")).scalar()
            
            if check_table:
                # Busca todos os símbolos distintos que o usuário cadastrou
                query = text("SELECT DISTINCT symbol FROM user_transactions")
                result = conn.execute(query)
                
                user_symbols = [row[0] for row in result]
                print(f"Ativos encontrados na carteira do usuário: {user_symbols}")
                
                # Adiciona ao set
                symbols.update(user_symbols)
    
    except Exception as e:
        print(f"Aviso: Não foi possível ler do banco ({e}). Usando lista padrão.")
    
    return list(symbols)

def extract_raw_data():
    """
    Camada Bronze: Extrai dados brutos da API CoinMarketCap
    para todos os ativos relevantes.
    """
    # 1. Define dinamicamente quais moedas buscar
    target_symbols = get_monitored_symbols()
    
    print(f"[BRONZE] Iniciando extração para {len(target_symbols)} ativos: {target_symbols}")
    
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': API_KEY,
    }
    parameters = {
        'symbol': ",".join(target_symbols), # API aceita "BTC,ETH,XRP"
        'convert': 'USD'
    }

    try:
        response = requests.get(url, headers=headers, params=parameters)
        response.raise_for_status()
        data = response.json()

        # Verifica status da API
        if data['status']['error_code'] != 0:
            print(f"Erro retornado pela API: {data['status']['error_message']}")
            return None

        # Cria nome do arquivo
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{BRONZE_PATH}/cmc_quotes_{timestamp_str}.json"

        # Salva JSON
        with open(filename, "w") as f:
            json.dump(data, f)
            
        print(f"[BRONZE] Arquivo salvo com sucesso: {filename}")
        return filename

    except Exception as e:
        print(f"[BRONZE] Erro fatal na extração: {e}")
        return None

if __name__ == "__main__":
    extract_raw_data()