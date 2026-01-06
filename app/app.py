from readline import add_history
import streamlit as st
import time
import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(layout="wide", page_title="Crypto Portfolio Manager")

# Carregar variáveis de ambiente
load_dotenv()
DB_URI = os.getenv("DB_CONNECTION_URI")

# Conexão com o Banco de Dados
# Em produção, ideal usar st.cache_resource para não recriar a conexão a cada clique
engine = create_engine(DB_URI)

# Lista de Ativos Suportados (Pode vir do banco futuramente)
ASSETS = ["BTC", "ETH", "SOL", "ADA", "DOT"]

# --- FUNÇÕES DE ACESSO A DADOS (CAMADA DE SERVIÇO) ---


def get_latest_prices():
    """
    Busca a cotação mais recente de cada moeda na tabela SILVER.
    Retorna um DataFrame indexado pelo symbol.
    """
    query = """
    SELECT symbol, price_usd 
    FROM silver_crypto_prices 
    WHERE processed_at = (SELECT MAX(processed_at) FROM silver_crypto_prices)
    """
    try:
        df = pd.read_sql(query, engine)
        if df.empty:
            return pd.DataFrame(columns=['symbol', 'price_usd']).set_index('symbol')
        return df.set_index('symbol')
    except Exception as e:
        st.error(f"Erro ao ler cotações: {e}")
        return pd.DataFrame()

def get_user_transactions():
    """Lê todas as transações do usuário."""
    try:
        # Verifica se a tabela existe antes de ler
        with engine.connect() as conn:
            # Postgres check table existence
            check_query = text("SELECT to_regclass('public.user_transactions');")
            result = conn.execute(check_query).scalar()
            if result is None:
                return pd.DataFrame()

        query = "SELECT * FROM user_transactions ORDER BY data_transacao DESC"
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Erro ao ler transações: {e}")
        return pd.DataFrame()

def save_transaction(symbol, tipo, qtd, preco, data):
    """Salva uma nova transação no banco."""
    try:
        df_new = pd.DataFrame([{
            "symbol": symbol,
            "tipo": tipo,
            "quantidade": float(qtd),
            "preco_unitario": float(preco),
            "data_transacao": pd.to_datetime(data)
        }])
        df_new.to_sql("user_transactions", engine, if_exists="append", index=False)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def update_transaction_history(df_edited):
    """
    Atualiza o banco de dados comparando o DataFrame editado com os dados existentes.
    Realiza UPDATE para registros modificados, DELETE para removidos e INSERT para novos.
    Mantém os IDs originais.
    """
    try:
        # 1. Normalizar tipos de dados
        df_edited['data_transacao'] = pd.to_datetime(df_edited['data_transacao'])
        df_edited['quantidade'] = df_edited['quantidade'].astype(float)
        df_edited['preco_unitario'] = df_edited['preco_unitario'].astype(float)
        
        # Garante que a coluna ID é tratada como numérica (novas linhas virão com NaN)
        if 'id' in df_edited.columns:
            df_edited['id'] = pd.to_numeric(df_edited['id'], errors='coerce')
        
        with engine.begin() as conn:
            # 2. Buscar IDs existentes no banco para comparação
            existing_ids_query = text("SELECT id FROM user_transactions")
            result = conn.execute(existing_ids_query)
            db_ids = {row[0] for row in result} # Set de IDs no banco
            
            # IDs presentes no editor (ignorando novos que são NaN)
            editor_ids = set(df_edited['id'].dropna().astype(int).tolist()) if 'id' in df_edited.columns else set()
            
            # 3. DELETE: IDs que estão no banco mas não no editor
            ids_to_delete = db_ids - editor_ids
            if ids_to_delete:
                delete_query = text("DELETE FROM user_transactions WHERE id = :id")
                for del_id in ids_to_delete:
                    conn.execute(delete_query, {"id": del_id})
            
            # 4. UPSERT: Iterar sobre as linhas do editor
            for _, row in df_edited.iterrows():
                row_id = row.get('id')
                
                params = {
                    "symbol": row['symbol'], "tipo": row['tipo'],
                    "qtd": row['quantidade'], "price": row['preco_unitario'],
                    "date": row['data_transacao']
                }
                
                # Se tem ID e ele existe no banco -> UPDATE
                if pd.notna(row_id) and row_id in db_ids:
                    update_query = text("""
                        UPDATE user_transactions 
                        SET symbol = :symbol, tipo = :tipo, quantidade = :qtd, 
                            preco_unitario = :price, data_transacao = :date
                        WHERE id = :id
                    """)
                    params["id"] = int(row_id)
                    conn.execute(update_query, params)
                
                # Se não tem ID (NaN) -> INSERT
                else:
                    insert_query = text("""
                        INSERT INTO user_transactions (symbol, tipo, quantidade, preco_unitario, data_transacao)
                        VALUES (:symbol, :tipo, :qtd, :price, :date)
                    """)
                    conn.execute(insert_query, params)
                    
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar histórico: {e}")
        return False


# --- LÓGICA DE NEGÓCIO (CÁLCULO DE PORTFÓLIO) ---

def calculate_portfolio_positions(df_transacoes):
    """
    Processa o histórico e calcula:
    1. Quantidade Atual
    2. Preço Médio (Cost Basis)
    3. Fluxo de Caixa (Total Investido Bruto vs Total Retornado)
    """
    if df_transacoes.empty:
        return pd.DataFrame()

    resumo = {}

    # Agrupa por ativo
    for symbol in df_transacoes['symbol'].unique():
        # Filtra e ordena por data (CRÍTICO para cálculo de preço médio)
        df_coin = df_transacoes[df_transacoes['symbol'] == symbol].sort_values('data_transacao')
        
        qtd_acumulada = 0.0
        custo_ajustado = 0.0 # Cost Basis (para cálculo de lucro aberto)
        
        soma_compras_bruta = 0.0
        soma_vendas_bruta = 0.0
        
        for _, row in df_coin.iterrows():
            qtd = float(row['quantidade'])
            preco = float(row['preco_unitario'])
            total_op = qtd * preco

            if row['tipo'] == 'COMPRA':
                custo_ajustado += total_op
                qtd_acumulada += qtd
                soma_compras_bruta += total_op

            elif row['tipo'] == 'VENDA':
                # Quando vende, reduzimos o custo da posição proporcionalmente ao preço médio atual
                preco_medio_momento = custo_ajustado / qtd_acumulada if qtd_acumulada > 0 else 0
                custo_ajustado -= qtd * preco_medio_momento
                qtd_acumulada -= qtd
                
                soma_vendas_bruta += total_op

        # Preço Médio Final
        preco_medio_final = custo_ajustado / qtd_acumulada if qtd_acumulada > 0 else 0

        resumo[symbol] = {
            "Quantidade": qtd_acumulada,
            "Preço Médio": preco_medio_final,
            "Custo da Posição (Basis)": custo_ajustado,
            "Total Aportado (Bruto)": soma_compras_bruta,
            "Total Vendido (Bruto)": soma_vendas_bruta
        }

    return pd.DataFrame.from_dict(resumo, orient='index')

# --- INTERFACE GRÁFICA (STREAMLIT) ---

st.title("📊 Gerenciador de Portfólio Crypto")

# Abas de navegação
tab1, tab2 = st.tabs(["Dashboard Geral", "Registrar Operação"])

# --- ABA 1: DASHBOARD ---
with tab1:
    st.markdown("### Visão Geral da Carteira")
    
    # 1. Carregar dados
    df_transacoes = get_user_transactions()
    df_prices = get_latest_prices()

    if df_transacoes.empty:
        st.info("Nenhuma transação registrada. Vá para a aba 'Registrar Operação' para começar.")
    else:
        # 2. Processar Dados
        df_portfolio = calculate_portfolio_positions(df_transacoes)

        # 3. Cruzar com Cotação Atual (Market Data)
        # Left join para garantir que temos dados do usuário mesmo se a API falhar
        df_final = df_portfolio.join(df_prices)

        # Tratar caso não tenha cotação (preenche com 0 ou mantém NaN)
        df_final['price_usd'] = df_final['price_usd'].fillna(0)

        # 4. Cálculos Finais de KPI
        df_final['Valor Atual'] = df_final['Quantidade'] * df_final['price_usd']
        
        # Lucro Aberto (Unrealized PnL)
        df_final['Lucro Aberto ($)'] = df_final['Valor Atual'] - df_final['Custo da Posição (Basis)']
        df_final['Lucro Aberto (%)'] = (df_final['Lucro Aberto ($)'] / df_final['Custo da Posição (Basis)']) * 100
        
        # Limpar infinitos e NaNs gerados por divisão por zero
        df_final = df_final.fillna(0)

        # 5. Exibição dos Cards (Metrics)
        
        # --- BLOCO A: FLUXO DE CAIXA (Dinheiro Real) ---
        total_aportado = df_final['Total Aportado (Bruto)'].sum()
        total_sacado = df_final['Total Vendido (Bruto)'].sum()
        net_cash_flow = total_aportado - total_sacado

        st.subheader("💰 Fluxo de Caixa (Histórico)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Aportado", f"${total_aportado:,.2f}", help="Soma bruta de tudo que saiu do bolso")
        c2.metric("Total Vendido/Sacado", f"${total_sacado:,.2f}", help="Soma bruta de tudo que voltou pro bolso")
        c3.metric("Capital Líquido Alocado", f"${net_cash_flow:,.2f}", help="Quanto de dinheiro 'novo' ainda está investido")

        st.divider()

        # --- BLOCO B: RENTABILIDADE (Posição Atual) ---
        valor_patrimonio = df_final['Valor Atual'].sum()
        custo_posicao_total = df_final['Custo da Posição (Basis)'].sum()
        pnl_aberto = valor_patrimonio - custo_posicao_total
        pnl_pct_geral = (pnl_aberto / custo_posicao_total * 100) if custo_posicao_total > 0 else 0

        st.subheader("📈 Performance da Carteira (Holdings)")
        c4, c5, c6 = st.columns(3)
        c4.metric("Patrimônio Atual", f"${valor_patrimonio:,.2f}", help="Se vender tudo agora a mercado")
        c5.metric("Custo da Posição", f"${custo_posicao_total:,.2f}", help="Preço Médio das moedas em carteira")
        c6.metric("Lucro/Prejuízo Aberto", f"${pnl_aberto:,.2f}", f"{pnl_pct_geral:.2f}%")

        st.divider()

      # 6. Tabela Detalhada
        st.subheader("Detalhamento por Ativo")
        
        # ADICIONEI 'Custo da Posição (Basis)' na lista abaixo
        display_cols = ['Quantidade', 'Preço Médio', 'price_usd', 'Custo da Posição (Basis)', 'Valor Atual', 'Lucro Aberto ($)', 'Lucro Aberto (%)']
        
        df_display = df_final[display_cols].sort_values('Valor Atual', ascending=False)
        
        # Renomear colunas (Adicionei 'Valor Alocado')
        df_display.columns = ['Qtd', 'Preço Médio', 'Preço Mercado', 'Valor Alocado', 'Saldo Atual', 'P/L ($)', 'P/L (%)']

        st.dataframe(
            df_display.style.format({
                "Qtd": "{:.4f}",
                "Preço Médio": "${:.2f}",
                "Preço Mercado": "${:.2f}",
                "Valor Alocado": "${:,.2f}",  # Nova formatação
                "Saldo Atual": "${:,.2f}",
                "P/L ($)": "${:,.2f}",
                "P/L (%)": "{:.2f}%"
            }).background_gradient(subset=['P/L (%)'], cmap="RdYlGn", vmin=-50, vmax=50)
        )

# --- ABA 2: CADASTRO ---
with tab2:
    st.header("Registrar Nova Operação")
    
    with st.form("form_transacao", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        
        with col_a:
            # input_symbol = st.selectbox("Ativo", ASSETS)
            # .upper() garante que se o usuário digitar "btc" ou "Btc", o sistema salve "BTC"
            input_symbol = st.text_input("Símbolo do Ativo (ex: BTC, XRP)").upper()
            input_tipo = st.radio("Tipo de Operação", ["COMPRA", "VENDA"], horizontal=True)
        
        with col_b:
            input_qtd = st.number_input("Quantidade", min_value=0.00000001, format="%.8f")
            input_preco = st.number_input("Preço Unitário (USD)", min_value=0.01, format="%.2f")
            input_data = st.date_input("Data da Operação", datetime.today())
        
        submitted = st.form_submit_button("💾 Salvar Transação")
        
        if submitted:
            if input_qtd > 0 and input_preco > 0:
                sucesso = save_transaction(input_symbol, input_tipo, input_qtd, input_preco, input_data)
                if sucesso:
                    st.success("Transação registrada com sucesso!")
                    # Pequeno hack para forçar recarregamento e atualizar o dashboard
                    st.rerun() 
            else:
                st.warning("Preencha valores maiores que zero.")

    # Exibir histórico recente
    st.subheader("Histórico de Transações (Editável)")
    st.info("Você pode editar os valores diretamente na tabela abaixo. Clique em 'Salvar Alterações' para confirmar.")
    
    df_history = get_user_transactions()
    if not df_history.empty:
        # Editor de dados (permite editar células e deletar linhas)
        df_edited = st.data_editor(
            df_history,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True, format="%d"),
                "symbol": "Ativo",
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["COMPRA", "VENDA"]),
                "quantidade": st.column_config.NumberColumn("Qtd", format="%.6f"),
                "preco_unitario": st.column_config.NumberColumn("Preço ($)", format="$%.2f"),
                "data_transacao": st.column_config.DateColumn("Data"),
            },
            num_rows="dynamic", # Permite adicionar e remover linhas
            use_container_width=True,
            key="editor_transacoes"
        )
        
        if st.button("💾 Salvar Alterações no Banco"):
            if update_transaction_history(df_edited):
                st.success("Histórico atualizado com sucesso!")
                time.sleep(1.5)
                st.rerun()