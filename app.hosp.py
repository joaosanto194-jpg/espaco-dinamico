import streamlit as st
import pandas as pd
import os

# Configuração da página web em modo tela cheia/wide
st.set_page_config(page_title="Resumo Sintético - Hospitais da Rede Própria", layout="wide")

st.title("🏥 RESUMO SINTÉTICO - HOSPITAIS DA REDE PRÓPRIA")
st.markdown("**Comparativo de Execução Orçamentária e Financeira**")
st.divider()

# Caminho do seu arquivo Excel no Desktop
CAMINHO_EXCEL = r"C:\Users\joaovitorsantos\Desktop\COMPARATIVO DE EXECUÇÃO - GERAL.xlsx"
NOME_ABA = "RESUMO"

@st.cache_data(ttl=60) # Atualiza o cache caso a planilha seja alterada
def carregar_aba_resumo():
    if not os.path.exists(CAMINHO_EXCEL):
        st.error(f"❌ O arquivo não foi encontrado no caminho: {CAMINHO_EXCEL}")
        return None
    
    try:
        # Lê estritamente a aba 'RESUMO' mantendo a estrutura da planilha original
        df = pd.read_excel(CAMINHO_EXCEL, sheet_name=NOME_ABA, header=None)
        return df
    except ValueError:
        st.error(f"❌ A aba '{NOME_ABA}' não foi encontrada na planilha. Verifique o nome exato da aba no Excel.")
        return None
    except Exception as e:
        st.error(f"❌ Erro ao abrir a planilha Excel: {e}")
        return None

# Carregamento dos dados
df_resumo = carregar_aba_resumo()

if df_resumo is not None:
    # Barra de busca para filtrar informações na aba RESUMO
    col_busca, col_botao = st.columns([4, 1])
    with col_busca:
        termo_busca = st.text_input("🔍 Pesquisar na aba RESUMO:", "")
    with col_botao:
        st.write("") # Espaçamento vertical
        if st.button("🔄 Recarregar Dados"):
            st.cache_data.clear()
            st.rerun()

    # Aplicação do filtro de busca
    if termo_busca:
        mascara = df_resumo.astype(str).apply(lambda row: row.str.contains(termo_busca, case=False, na=False)).any(axis=1)
        df_exibicao = df_resumo[mascara]
    else:
        df_exibicao = df_resumo

    # Exibição da tabela exatamente como configurada na aba RESUMO
    st.dataframe(df_exibicao, use_container_width=True, height=700)