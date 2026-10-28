# -*- coding: utf-8 -*-
import os
import re
import unicodedata
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.express as px

# ============================================================
# 1. CONFIGURAÇÕES DE SISTEMA
# ============================================================
st.set_page_config(
    page_title="SESA | Gestão Orçamentária",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

CAMINHO_REDE = r"\\fileserver\sesa$\FES\NEOF\JOAO VITOR\MONITORAMENTO GFES\EMPENHO EM ABERTO - REDE SESA\SALDO DE EMPENHO EM ABERTO - REDE SAÚDE.xlsx"
NOME_ABA = "Base_Dados"
LINHA_CABECALHO = 1
UG_INICIAL, UG_FINAL = 440901, 440929

CORES = {"azul_topo": "#0D47A1", "azul_cards": "#FFFFFF", "fundo": "#F8F9FA", "texto": "#333333"}

# ============================================================
# 2. ESTILIZAÇÃO FUNCIONAL
# ============================================================
st.markdown(f"""
    <style>
    .stApp {{ background-color: {CORES['fundo']}; color: {CORES['texto']}; }}
    .main-header {{
        background-color: {CORES['azul_topo']}; color: white; padding: 20px; 
        border-radius: 0px 0px 15px 15px; display: flex; 
        justify-content: space-between; align-items: center; margin-bottom: 25px;
    }}
    .main-header h1 {{ color: white !important; font-size: 22px !important; margin: 0 !important; font-weight: 600 !important; }}
    .main-header p {{ color: #BDBDBD !important; margin: 0 !important; font-size: 14px !important; }}
    .kpi-card {{
        background-color: white; border: 1px solid #E0E0E0; border-radius: 10px;
        padding: 15px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    .kpi-label {{ color: #666666; font-size: 13px; font-weight: 500; }}
    .kpi-value {{ color: #0D47A1; font-size: 20px; font-weight: 700; }}
    .section-container {{
        background: white; border-radius: 10px; padding: 20px; border: 1px solid #E0E0E0;
    }}
    .section-title {{ color: #0D47A1; font-size: 16px; font-weight: 700; margin-bottom: 15px; }}
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 3. TRATAMENTO DE DADOS
# ============================================================
def normalizar(v):
    if pd.isna(v): return ""
    return "".join(c for c in unicodedata.normalize("NFKD", str(v).strip().upper()) if not unicodedata.combining(c))

def extrair_ug(v):
    if pd.isna(v): return None
    res = re.match(r"^\s*(\d{6})", str(v).strip())
    return res.group(1) if res else None

def conv_fin(v):
    if pd.isna(v) or isinstance(v, bool): return 0.0
    if isinstance(v, (int, float)): return float(v)
    t = str(v).strip().replace("R$", "").strip()
    neg = t.startswith("(") and t.endswith(")")
    if neg: t = t[1:-1].strip()
    t = t.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return -abs(float(re.sub(r"[^0-9.\-+]", "", t))) if neg else float(re.sub(r"[^0-9.\-+]", "", t))
    except: return 0.0

def format_curr(v):
    return f"R$ {v:,.2f}".replace(",", "T").replace(".", ",").replace("T", ".")

@st.cache_data(ttl=300)
def load_data():
    if not os.path.exists(CAMINHO_REDE): return None, "Arquivo não encontrado"
    try:
        df = pd.read_excel(CAMINHO_REDE, sheet_name=NOME_ABA, header=LINHA_CABECALHO, dtype=object)
        df = df.dropna(axis=1, how="all").copy()
        df.columns = [str(c).strip() for c in df.columns]
        
        cols = df.columns.tolist()
        m = {
            "ug": next((c for c in cols if any(t in normalizar(c) for t in ["UG", "CÓDIGO UG"])), None),
            "nome": next((c for c in cols if any(t in normalizar(c) for t in ["NOME UG", "UNIDADE GESTORA"])), None),
            "fonte": next((c for c in cols if "FONTE" in normalizar(c)), None),
            "nat": next((c for c in cols if "NATUREZA" in normalizar(c)), None),
            "acao": next((c for c in cols if any(t in normalizar(c) for t in ["AÇÃO", "ACAO"])), None),
            "po": next((c for c in cols if "PO" in normalizar(c)), None),
        }
        if not m["ug"]: return None, "Coluna UG não encontrada."

        df["_CODIGO_UG"] = df[m["ug"]].map(extrair_ug)
        df = df[df["_CODIGO_UG"].apply(lambda x: pd.notna(x) and UG_INICIAL <= int(x) <= UG_FINAL)].copy()
        df = df[~df.apply(lambda r: r.astype(str).str.upper().str.contains("TOTAL|SUBTOTAL").any(), axis=1)]
        
        if m["nome"] is None or m["nome"] not in df.columns:
            m["nome"] = "_NOME_VIRTUAL"; df[m["nome"]] = df["_CODIGO_UG"]
        else:
            df[m["nome"]] = df[m["nome"]].fillna(df["_CODIGO_UG"])

        termos = ["VALOR", "SALDO", "EMPENHADO", "LIQUIDADO", "PAGO", "DISPONIVEL", "LIQUIDAR", "DESPESA"]
        cols_fin = [c for c in df.columns if any(t in normalizar(c) for t in termos)]
        for c in cols_fin: df[c] = df[c].map(conv_fin)
        
        return df, {**m, "financeiras": cols_fin}
    except Exception as e: return None, str(e)

df_raw, meta = load_data()
if df_raw is None: st.error(f"Erro: {meta}"); st.stop()

# ============================================================
# 4. INTERFACE DE FILTROS (CASCATA)
# ============================================================
st.markdown(f"""
    <div class="main-header">
        <div style="display: flex; gap: 20px; align-items: center;">
            <div style="background: white; padding: 5px 10px; border-radius: 5px; color: {CORES['azul_topo']} !important; font-weight: bold;">SESA</div>
            <div>
                <h1>Painel de Gestão Orçamentária e Empenhos</h1>
                <p>Cubo de Valores por Unidade Gestora (UG)</p>
            </div>
        </div>
        <div style="text-align: right; font-size: 12px; color: #BDBDBD;">
            Exercício: 2026 | Atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}
        </div>
    </div>
    """, unsafe_allow_html=True)

with st.container():
    f_cols = st.columns([1.5, 1, 1, 1, 1])
    
    # 1. Filtro UG (Âncora)
    ugs_presentes = sorted(df_raw["_CODIGO_UG"].unique())
    mapa_nomes = df_raw.groupby("_CODIGO_UG")[meta["nome"]].first().to_dict()
    opcoes_ug = [f"{c} - {mapa_nomes.get(c, c)}" for c in ugs_presentes]
    sel_ugs = f_cols[0].multiselect("Unidade Gestora (UG)", options=opcoes_ug)

    df_f = df_raw.copy()
    if sel_ugs:
        cods = [r.split(" - ")[0] for r in sel_ugs]
        df_f = df_f[df_f["_CODIGO_UG"].isin(cods)]
    
    # Filtros dependentes
    with f_cols[1]:
        op_fon = sorted(df_f[meta["fonte"]].dropna().unique().tolist()) if meta["fonte"] else []
        sel_fon = st.multiselect("Fonte", options=op_fon)
    with f_cols[2]:
        op_nat = sorted(df_f[meta["nat"]].dropna().unique().tolist()) if meta["nat"] else []
        sel_nat = st.multiselect("Natureza", options=op_nat)
    with f_cols[3]:
        op_acao = sorted(df_f[meta["acao"]].dropna().unique().tolist()) if meta["acao"] else []
        sel_acao = st.multiselect("Ação", options=op_acao)
    with f_cols[4]:
        op_po = sorted(df_f[meta["po"]].dropna().unique().tolist()) if meta["po"] else []
        sel_po = st.multiselect("PO", options=op_po)

    if sel_fon: df_f = df_f[df_f[meta["fonte"]].astype(str).isin(sel_fon)]
    if sel_nat: df_f = df_f[df_f[meta["nat"]].astype(str).isin(sel_nat)]
    if sel_acao: df_f = df_f[df_f[meta["acao"]].astype(str).isin(sel_acao)]
    if sel_po: df_f = df_f[df_f[meta["po"]].astype(str).isin(sel_po)]

# ============================================================
# 5. KPIs EXECUTIVOS
# ============================================================
if not df_f.empty:
    met_principal = next((c for c in meta["financeiras"] if "SALDO" in normalizar(c)), meta["financeiras"][0])
    
    st.markdown("<br>", unsafe_allow_html=True)
    k_cols = st.columns(len(meta["financeiras"]) if len(meta["financeiras"]) <= 5 else 5)
    
    for i, m in enumerate(meta["financeiras"][:5]):
        with k_cols[i]:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">{m}</div><div class="kpi-value">{format_curr(df_f[m].sum())}</div></div>', unsafe_allow_html=True)
else:
    st.warning("Selecione uma UG ou limpe os filtros para visualizar os dados.")
    st.stop()

# ============================================================
# 6. GRÁFICOS DE GESTÃO DIRETA (SINCEROS)
# ============================================================
st.markdown("<br>", unsafe_allow_html=True)
g_cols = st.columns([1.2, 1])

with g_cols[0]:
    st.markdown('<div class="section-container"><div class="section-title">Ranking de Saldo por UG (Pareto)</div>', unsafe_allow_html=True)
    
    # GRÁFICO DE BARRAS HORIZONTAIS (ORDENADO)
    df_rank = df_f.groupby("_CODIGO_UG")[met_principal].sum().reset_index().sort_values(met_principal, ascending=True)
    df_rank["UG_Nome"] = df_rank["_CODIGO_UG"].map(mapa_nomes)
    df_rank["Rótulo"] = df_rank["_CODIGO_UG"] + " - " + df_rank["UG_Nome"].astype(str)
    
    fig_bar = px.bar(df_rank, x=met_principal, y="Rótulo", orientation='h', 
                     text=met_principal, color=met_principal, color_continuous_scale="Blues")
    fig_bar.update_traces(texttemplate="R$ %{x:,.2f}", textposition="outside")
    fig_bar.update_layout(template="plotly_white", height=400, showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig_bar, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with g_cols[1]:
    st.markdown('<div class="section-container"><div class="section-title">Composição por Natureza / Fonte</div>', unsafe_allow_html=True)
    
    # DONUT CHART (DISTRIBUIÇÃO)
    # Alterna entre Natureza e Fonte dependendo de qual estiver disponível
    col_dist = meta["nat"] if meta["nat"] else meta["fonte"]
    if col_dist:
        df_dist = df_f.groupby(col_dist)[met_principal].sum().reset_index().sort_values(met_principal, ascending=False).head(8)
        fig_pie = px.pie(df_dist, values=met_principal, names=col_dist, hole=0.5)
        fig_pie.update_traces(textinfo='percent+label')
        fig_pie.update_layout(template="plotly_white", height=400, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Sem dados de Natureza/Fonte para composição.")
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 7. CUBO DE VALORES (A FONTE DA VERDADE)
# ============================================================
st.markdown("<br>", unsafe_allow_html=True)
st.markdown('<div class="section-container"><div class="section-title">Cubo de Valores Detalhado (Auditável)</div>', unsafe_allow_html=True)

df_final = df_f.copy()
df_final["SOMA_FINAL"] = df_final[met_principal]

cols_view = [meta["ug"], meta["nome"], meta["fonte"], meta["nat"], meta["acao"], meta["po"], "SOMA_FINAL"]
st.dataframe(
    df_final[cols_view], 
    use_container_width=True, 
    hide_index=True,
    column_config={
        "SOMA_FINAL": st.column_config.NumberColumn("Valor Consolidado", format="R$ %.2f")
    }
)

st.markdown(f"""
    <div style="text-align: right; font-weight: 800; font-size: 18px; padding: 15px; 
    background: {CORES['azul_topo']}; color: white; border-radius: 10px; margin-top: 10px;">
        TOTAL GERAL FILTRADO: {format_curr(df_f[met_principal].sum())}
    </div>
    """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
