import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime
from io import BytesIO
import google.generativeai as genai
import plotly.express as px

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="LeadUp | Auditoria Automotiva", page_icon="🚀", layout="wide")

st.markdown("""
    <style>
    div.stButton > button:first-child { background-color: #6c757d; color: white; border: none; border-radius: 4px; }
    </style>
""", unsafe_allow_html=True)

if 'ultimo_resultado' not in st.session_state: st.session_state['ultimo_resultado'] = None
if 'parecer_ia' not in st.session_state: st.session_state['parecer_ia'] = None

# ==========================================
# 2. MENU LATERAL (SISTEMA DE ORIGEM)
# ==========================================
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.title("🚀 LeadUp Hub")
    st.markdown("---")
    
    # SELETOR DE MÚLTIPLOS SISTEMAS (O Hub Universal)
    sistema_origem = st.selectbox("⚙️ Sistema de Origem:", ["Revenda Mais"])
    
    st.markdown("---")
    st.caption("⚡ Tecnologia **OThree**")

st.title("📊 Relatório de Auditoria LeadUp")

# ==========================================
# 3. FUNÇÕES GERAIS E EXPORTAÇÃO
# ==========================================
def limpar_telefone(p):
    if pd.isna(p) or str(p).strip() == '' or p == '­': return None
    digitos = re.sub(r'\D', '', str(p))
    if digitos.startswith('55'): digitos = digitos[2:]
    return digitos[:2] + digitos[-8:] if len(digitos) >= 10 else digitos

def limpar_email(e):
    if pd.isna(e) or str(e).strip() == '' or e == '­': return None
    return str(e).strip().lower()

CANAIS_FISICOS = ['visita a loja', 'cliente da loja', 'pista shopping', 'autoshopping', 'telefone', 'indicação', 'feirão', 'repasse']
CANAIS_DIGITAIS = ['webmotors', 'socarrao', 'sócarrão', 'olx', 'na pista', 'icarros', 'chaves na mao', 'facebook', 'google', 'mercadolivre', 'site']

EXCLUSAO_DASH_02 = [
    'autoshopping', 'cliente da loja', 'facebook', 'feirão shopping', 
    'google', 'indicação de amigo', 'indicação de funcionario', 
    'pista shopping', 'repasse', 'site da loja', 'telefone', 'visita a loja'
]

def gerar_relatorio_html(titulo, fig, df_tabela):
    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
    table_html = df_tabela.to_html(index=False, border=0, classes="styled-table")
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{titulo}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 30px; color: #333; }}
            h2 {{ text-align: center; color: #2c3e50; }}
            .styled-table {{ border-collapse: collapse; margin: 25px 0; font-size: 0.9em; width: 100%; box-shadow: 0 0 20px rgba(0, 0, 0, 0.1); }}
            .styled-table thead tr {{ background-color: #6c757d; color: #ffffff; text-align: left; }}
            .styled-table th, .styled-table td {{ padding: 12px 15px; border: 1px solid #ddd; }}
            .styled-table tbody tr {{ border-bottom: 1px solid #dddddd; }}
            .styled-table tbody tr:nth-of-type(even) {{ background-color: #f9f9f9; }}
            @media print {{
                .styled-table {{ page-break-inside: auto; }}
                tr {{ page-break-inside: avoid; page-break-after: auto; }}
            }}
        </style>
    </head>
    <body>
        <h2>{titulo}</h2>
        <div style="width: 100%; margin: 0 auto;">{chart_html}</div>
        <hr style="border: 1px solid #eee; margin: 30px 0;">
        <h3>Lista de Vendas Referentes</h3>
        <div>{table_html}</div>
    </body>
    </html>
    """
    return template

# ==========================================
# 4. INTERFACE E PROCESSAMENTO CENTRAL
# ==========================================
tab_upload, tab_dash = st.tabs(["📂 1. Nova Auditoria", "📈 2. Dashboards de Apresentação"])

with tab_upload:
    st.markdown(f"**Importando dados do sistema:** `{sistema_origem}`")
    col1, col2 = st.columns(2)
    with col1: arquivo_vendas = st.file_uploader("VENDAS (.xlsx)", type=['xlsx'])
    with col2: arquivo_leads = st.file_uploader("LEADS (.xlsx)", type=['xlsx'])

    if st.button("Gerar Auditoria e Dashboards", use_container_width=True):
        if arquivo_vendas and arquivo_leads:
            with st.spinner(f'Cruzando dados e aplicando regras LeadUp para {sistema_origem}...'):
                try:
                    CHAVE_SECRETA = st.secrets["GEMINI_API_KEY"]
                    genai.configure(api_key=CHAVE_SECRETA)
                    modelo_ia = genai.GenerativeModel('gemini-2.5-flash')

                    # ---------------------------------------------------------
                    # MÓDULO 1: REVENDA MAIS
                    # ---------------------------------------------------------
                    if sistema_origem == "Revenda Mais":
                        vendas = pd.read_excel(arquivo_vendas)
                        leads = pd.read_excel(arquivo_leads)
                        vendas.columns = vendas.columns.str.strip()
                        leads.columns = leads.columns.str.strip()

                        vendas['email_key'] = vendas['E-mail'].apply(limpar_email)
                        vendas['phone_key'] = vendas['Celular'].apply(limpar_telefone)
                        leads['email_key'] = leads['E-mail'].apply(limpar_email)
                        leads['phone_key'] = leads['Telefone'].apply(limpar_telefone)
                        leads['Data criação'] = pd.to_datetime(leads['Data criação'], errors='coerce')

                        def motor(row):
                            e, p = row['email_key'], row['phone_key']
                            mask = (leads['email_key'] == e) | (leads['phone_key'] == p) if e or p else pd.Series([False]*len(leads))
                            m_leads = leads[mask].sort_values('Data criação')
                            
                            canal_vendedor_raw = str(row['Canal']).strip()
                            canal_vendedor_padrao = canal_vendedor_raw.title()
                            
                            if m_leads.empty:
                                return pd.Series({
                                    'Id Leads (Leads)': '-', 'Nome Cliente (Leads)': '-', 'E-mail (Leads)': '-',
                                    'Conversão (Leads)': '-', 'Canais Leads (Leads)': canal_vendedor_padrao, 
                                    'Data Primeiro Lead (Leads)': '-', 'Data Último Lead (Leads)': '-', 
                                    'Validação (Status)': 'Venda Direta / Sem Lead'
                                })

                            canal_lead_recente = str(m_leads.iloc[-1]['Canal']).strip().title()
                            
                            ids = ' / '.join(m_leads['Id'].astype(str).unique())
                            names = ' / '.join(m_leads['Cliente'].dropna().unique())
                            emails = ' / '.join(m_leads['E-mail'].dropna().unique())
                            first_date = m_leads['Data criação'].min()
                            last_date = m_leads['Data criação'].max()
                            last_conv = m_leads.iloc[-1]['Conversão'] if 'Conversão' in m_leads.columns else '-'

                            c_leads_all = ' '.join(m_leads['Canal'].dropna().unique()).lower()
                            is_phys = any(p in canal_vendedor_raw.lower() for p in CANAIS_FISICOS)
                            has_dig = any(d in c_leads_all for d in CANAIS_DIGITAIS)
                            
                            status = 'Validado'
                            if is_phys and has_dig:
                                status = 'ALERTA: Perda de Atribuição (Digital -> Pátio)'
                            elif not is_phys and not any(canal_vendedor_raw.lower() in str(c).lower() for c in m_leads['Canal'].unique()):
                                status = 'Divergência: Canais Digitais Diferentes'

                            return pd.Series({
                                'Id Leads (Leads)': ids,
                                'Nome Cliente (Leads)': names,
                                'E-mail (Leads)': emails,
                                'Conversão (Leads)': last_conv,
                                'Canais Leads (Leads)': canal_lead_recente,
                                'Data Primeiro Lead (Leads)': first_date.strftime('%d/%m/%Y') if pd.notnull(first_date) else '-',
                                'Data Último Lead (Leads)': last_date.strftime('%d/%m/%Y') if pd.notnull(last_date) else '-',
                                'Validação (Status)': status
                            })

                        res = vendas.apply(motor, axis=1)
                        relatorio_bruto = pd.concat([vendas, res], axis=1)
                        
                        relatorio_bruto = relatorio_bruto.rename(columns={
                            'Cliente': 'Nome Cliente (Vendas)',
                            'CPF/CNPJ': 'CPF/CNPJ (Vendas)',
                            'E-mail': 'E-mail (Vendas)',
                            'Canal': 'Canal Venda (Vendas)'
                        })
                        
                        colunas_finais = [
                            'Id Leads (Leads)', 'Nome Cliente (Vendas)', 'Nome Cliente (Leads)', 
                            'CPF/CNPJ (Vendas)', 'E-mail (Vendas)', 'E-mail (Leads)', 
                            'Conversão (Leads)', 'Canal Venda (Vendas)', 'Canais Leads (Leads)', 
                            'Validação (Status)', 'Data Primeiro Lead (Leads)', 'Data Último Lead (Leads)', 
                            'Dt. venda', 'Modelo', 'Placa', 'Celular'
                        ]
                        
                        for col in colunas_finais:
                            if col not in relatorio_bruto.columns: relatorio_bruto[col] = '-'

                        relatorio_final = relatorio_bruto[colunas_finais]
                    # ---------------------------------------------------------
                    
                    st.session_state['ultimo_resultado'] = relatorio_final
                    
                    prompt = "Aja como auditor da LeadUp. Escreva 1 parágrafo de resumo executivo focado em apontar falhas de preenchimento de CRM que escondem o ROI dos portais digitais da operação analisada."
                    st.session_state['parecer_ia'] = modelo_ia.generate_content(prompt).text
                    st.success("✅ Auditoria finalizada! Veja os Dashboards.")

                except Exception as e: st.error(f"Erro no processamento: {e}")

# --- ABA 2: DASHBOARDS SEPARADOS ---
with tab_dash:
    if st.session_state['ultimo_resultado'] is not None:
        df = st.session_state['ultimo_resultado']
        
        st.markdown("### 📄 Parecer Executivo IA")
        if st.session_state['parecer_ia']: st.info(st.session_state['parecer_ia'])
        st.markdown("---")
        
        colunas_lista = [
            'Dt. venda', 
            'Nome Cliente (Vendas)', 
            'Modelo', 
            'Canal Venda (Vendas)', 
            'Canais Leads (Leads)', 
            'Validação (Status)'
        ]
        
        dash_pag1, dash_pag2 = st.tabs(["📊 DASH 01: Visão Vendedor (Sem Filtros)", "🎯 DASH 02: Visão Plataformas (Filtrado)"])
        
        # --- DASH 01: Visão Vendedor ---
        with dash_pag1:
            st.subheader("Atribuição Original (Coluna 'Canal Venda')")
            vendedor_counts = df['Canal Venda (Vendas)'].value_counts().reset_index()
            vendedor_counts.columns = ['Canal', 'Vendas']
            
            fig1 = px.bar(vendedor_counts, x='Canal', y='Vendas', text_auto=True, color_discrete_sequence=['#6c757d'])
            fig1.update_traces(textfont_size=16, textangle=0, textposition="inside")
            fig1.update_layout(height=450, xaxis_title="", yaxis_title="Qtd Vendas")
            st.plotly_chart(fig1, use_container_width=True)
            
            df_lista_1 = df[colunas_lista]
            st.markdown("**Lista de Vendas (Visão Original Completa):**")
            st.dataframe(df_lista_1, use_container_width=True)
            
            html_dash1 = gerar_relatorio_html("Dashboard 01 - Visão Vendedor", fig1, df_lista_1)
            st.download_button("💾 Salvar este Dashboard (Gráfico + Tabela)", data=html_dash1, file_name="Dash01_Vendedor.html", mime="text/html")

        # --- DASH 02: Visão Plataformas ---
        with dash_pag2:
            st.subheader("Performance Real de Plataformas (Coluna 'Canais Leads')")
            mask_exclusao = df['Canais Leads (Leads)'].astype(str).str.lower().str.strip().isin(EXCLUSAO_DASH_02)
            df_plataformas = df[~mask_exclusao]
            
            leads_counts = df_plataformas['Canais Leads (Leads)'].value_counts().reset_index()
            leads_counts.columns = ['Canal', 'Vendas']
            
            fig2 = px.bar(leads_counts, x='Canal', y='Vendas', text_auto=True, color_discrete_sequence=['#2ecc71'])
            fig2.update_traces(textfont_size=16, textangle=0, textposition="inside")
            fig2.update_layout(height=450, xaxis_title="", yaxis_title="Qtd Vendas")
            st.plotly_chart(fig2, use_container_width=True)
            
            df_lista_2 = df_plataformas[colunas_lista]
            st.markdown("**Lista de Vendas Qualificadas (Apenas Plataformas Digitais):**")
            st.dataframe(df_lista_2, use_container_width=True)
            
            html_dash2 = gerar_relatorio_html("Dashboard 02 - Visão Plataformas", fig2, df_lista_2)
            st.download_button("💾 Salvar este Dashboard (Gráfico + Tabela)", data=html_dash2, file_name="Dash02_Plataformas.html", mime="text/html", key="btn_dash2")

        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### 🗄️ Base de Dados Oficial")
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button(
            label="📥 Baixar Planilha Oficial (Padrão LeadUp com 16 colunas)", 
            data=output.getvalue(), 
            file_name="Auditoria_LeadUp.xlsx", 
            type="primary"
        )