import pandas as pd
from sqlalchemy import create_engine
import time

# String de conexão: postgresql://usuario:senha@host:porta/banco
# Nota: Se rodar LOCALMENTE (fora do docker), o host é 'localhost'.
# Se rodar de DENTRO de um container Docker, o host seria 'postgres'.
DB_CONNECTION_URI = 'postgresql://admin:admin_password@localhost:5432/crypto_db'

def testar_banco():
    print("Tentando conectar ao Warehouse...")
    try:
        engine = create_engine(DB_CONNECTION_URI)
        
        # 1. Vamos criar um DataFrame simples (simulando dados da API)
        df_teste = pd.DataFrame({
            'ativo': ['BTC', 'ETH', 'SOL'],
            'preco_ficticio': [50000, 3000, 100]
        })

        # 2. Escrever no banco (tabela 'raw_teste')
        # if_exists='replace' cria a tabela se ela não existir
        df_teste.to_sql('raw_teste', engine, if_exists='replace', index=False)
        print("Dados escritos com sucesso na tabela 'raw_teste'!")

        # 3. Ler de volta para confirmar
        df_lido = pd.read_sql("SELECT * FROM raw_teste", engine)
        print("\nDados lidos do banco:")
        print(df_lido)

    except Exception as e:
        print(f"Erro ao conectar: {e}")

if __name__ == "__main__":
    testar_banco()

# URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

