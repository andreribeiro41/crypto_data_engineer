import pandas as pd
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv
from datetime import datetime

# Carregar envs
load_dotenv()
DB_URI = os.getenv("DB_CONNECTION_URI")

def process_gold_data():
    """
    Camada Gold: Lê a tabela Silver, aplica regras de negócio (agregacões)
    e salva uma tabela otimizada para Analytics/Dashboard.
    """
    print("[GOLD] Iniciando cálculo de KPIs...")

    try:
        engine = create_engine(DB_URI)

        # 1. Leitura da Silver (Trazendo apenas colunas necessárias para economizar memória)
        # Em produção, você filtraria apenas os dados de "hoje" ou "ontem".
        query = "SELECT symbol, price_usd, processed_at FROM silver_crypto_prices"
        df_silver = pd.read_sql(query, engine)

        if df_silver.empty:
            print("[GOLD] Tabela Silver vazia.")
            return

        # 2. Transformação e Agregação
        
        # Converter string para data (garantia)
        df_silver['processed_at'] = pd.to_datetime(df_silver['processed_at'])
        
        # Criar coluna apenas com a DATA (sem hora) para agrupar
        df_silver['date'] = df_silver['processed_at'].dt.date

        # AGREGACAO: Agrupar por Moeda e Data
        df_gold = df_silver.groupby(['date', 'symbol']).agg(
            price_min=('price_usd', 'min'),
            price_max=('price_usd', 'max'),
            price_avg=('price_usd', 'mean'),
            record_count=('symbol', 'count') # Quantas leituras tivemos no dia
        ).reset_index()

        # KPI: Calcular Volatilidade Diária (%)
        # Fórmula: ((Max - Min) / Min) * 100
        df_gold['volatility_pct'] = (
            (df_gold['price_max'] - df_gold['price_min']) / df_gold['price_min']
        ) * 100

        # Adicionar data de processamento
        df_gold['updated_at'] = datetime.now()

        # 3. Load (Salvar tabela Gold no Banco)
        # if_exists='replace': Na Gold, geralmente reescrevemos ou fazemos upsert. 
        # Como é uma tabela pequena de resumo, 'replace' é aceitável para começar, 
        # mas 'append' seria o ideal se rodasse 1x por dia.
        df_gold.to_sql('gold_daily_summary', engine, if_exists='replace', index=False)
        
        print("[GOLD] Tabela 'gold_daily_summary' atualizada com sucesso!")
        print(df_gold.head()) # Mostra uma prévia no console

    except Exception as e:
        print(f"[GOLD] Erro ao calcular KPIs: {e}")

if __name__ == "__main__":
    process_gold_data()