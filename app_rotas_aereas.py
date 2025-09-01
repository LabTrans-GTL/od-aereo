import streamlit as st
import polars as pl
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
import plotly.express as px
from folium import plugins
from folium.plugins import AntPath
import math
import json
import unicodedata
import re
import os
import hashlib
import requests
import io
from pathlib import Path

# Funções de autenticação
def hash_password(password):
    """Cria hash da senha para comparação segura"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_credentials(username, password):
    """Verifica se as credenciais estão corretas"""
    try:
        # Tentar obter credenciais dos secrets do Streamlit primeiro
        if hasattr(st, 'secrets'):
            env_username = st.secrets.get('STREAMLIT_USERNAME')
            env_password = st.secrets.get('STREAMLIT_PASSWORD')
        else:
            # Fallback para variáveis de ambiente
            env_username = os.getenv('STREAMLIT_USERNAME')
            env_password = os.getenv('STREAMLIT_PASSWORD')
    except Exception as e:
        # Fallback para variáveis de ambiente se secrets não funcionar
        env_username = os.getenv('STREAMLIT_USERNAME')
        env_password = os.getenv('STREAMLIT_PASSWORD')
    
    # Verificar se as credenciais foram configuradas
    if not env_username or not env_password:
        return False
    
    # Hash da senha do ambiente
    env_password_hash = hash_password(env_password)
    input_password_hash = hash_password(password)
    
    return username == env_username and input_password_hash == env_password_hash

def login_page():
    """Página de login"""
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px;
            margin: 0 auto;
            padding: 2rem;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            margin-top: 5rem;
        }
        .login-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        .login-header h1 {
            color: #1e3c72;
            margin-bottom: 0.5rem;
        }
        .login-header p {
            color: #6c757d;
            margin: 0;
        }
        .stTextInput > div > div > input {
            border-radius: 8px;
            border: 2px solid #e9ecef;
            padding: 0.75rem;
        }
        .stTextInput > div > div > input:focus {
            border-color: #1e3c72;
            box-shadow: 0 0 0 2px rgba(30, 60, 114, 0.1);
        }
        .login-button {
            width: 100%;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            border: none;
            padding: 0.75rem;
            border-radius: 8px;
            font-weight: 500;
            margin-top: 1rem;
        }
        .login-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(30, 60, 114, 0.3);
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="login-container">
        <div class="login-header">
            <h1>🔐 Acesso ao Sistema</h1>
            <p>Sistema de Análise de Rotas Aéreas</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    with st.form("login_form"):
        username = st.text_input("Usuário", placeholder="Digite seu usuário")
        password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            login_button = st.form_submit_button("Entrar", use_container_width=True)
        
        if login_button:
            if check_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos!")

def logout():
    """Função de logout"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.rerun()

# Funções para download de dados do Google Drive
def get_google_drive_file_id(url):
    """Extrai o ID do arquivo do Google Drive a partir da URL"""
    if 'drive.google.com' in url:
        # Para URLs do tipo: https://drive.google.com/file/d/FILE_ID/view
        if '/file/d/' in url:
            return url.split('/file/d/')[1].split('/')[0]
        # Para URLs do tipo: https://drive.google.com/open?id=FILE_ID
        elif 'id=' in url:
            return url.split('id=')[1].split('&')[0]
    return None

def download_file_from_google_drive(file_id, filename, destination_folder="Dados"):
    """Baixa um arquivo do Google Drive usando o ID do arquivo"""
    try:
        # URL para download direto do Google Drive
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        # Criar diretórios se não existirem
        os.makedirs(f"{destination_folder}/raw", exist_ok=True)
        os.makedirs(f"{destination_folder}/interim", exist_ok=True)
        
        # Determinar o caminho de destino baseado na extensão do arquivo
        if filename.endswith('.csv'):
            file_path = f"{destination_folder}/raw/{filename}"
        elif filename.endswith('.parquet'):
            file_path = f"{destination_folder}/interim/{filename}"
        else:
            file_path = f"{destination_folder}/raw/{filename}"
        
        # Baixar o arquivo
        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        
        # Salvar o arquivo
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return file_path
        
    except Exception as e:
        return None

def get_google_drive_folder_files(folder_url):
    """Obtém lista de arquivos de uma pasta do Google Drive (requer API key)"""
    # Para simplificar, vamos usar uma abordagem diferente
    # O usuário pode fornecer os IDs dos arquivos diretamente
    return None

def download_data_files():
    """Baixa todos os arquivos de dados necessários"""
    try:
        # Tentar obter configurações dos secrets do Streamlit primeiro
        if hasattr(st, 'secrets'):
            # Acessar diretamente (sem seção [secrets])
            drive_folder_url = st.secrets.get('GOOGLE_DRIVE_FOLDER_URL')
            file_mapping = {
                'mun_UTPs.csv': st.secrets.get('FILE_ID_MUN_UTPS'),
                'aeroportos.parquet': st.secrets.get('FILE_ID_AEROPORTOS'),
                'classificacao_pares.parquet': st.secrets.get('FILE_ID_CLASSIFICACAO'),
                'comerciais.parquet': st.secrets.get('FILE_ID_COMERCIAL'),
                'executivos.parquet': st.secrets.get('FILE_ID_EXECUTIVO')
            }
        else:
            # Fallback para variáveis de ambiente
            drive_folder_url = os.getenv('GOOGLE_DRIVE_FOLDER_URL')
            file_mapping = {
                'mun_UTPs.csv': os.getenv('FILE_ID_MUN_UTPS'),
                'aeroportos.parquet': os.getenv('FILE_ID_AEROPORTOS'),
                'classificacao_pares.parquet': os.getenv('FILE_ID_CLASSIFICACAO'),
                'comerciais.parquet': os.getenv('FILE_ID_COMERCIAL'),
                'executivos.parquet': os.getenv('FILE_ID_EXECUTIVO')
            }
    except:
        # Fallback para variáveis de ambiente se secrets não funcionar
        drive_folder_url = os.getenv('GOOGLE_DRIVE_FOLDER_URL')
        file_mapping = {
            'mun_UTPs.csv': os.getenv('FILE_ID_MUN_UTPS'),
            'aeroportos.parquet': os.getenv('FILE_ID_AEROPORTOS'),
            'classificacao_pares.parquet': os.getenv('FILE_ID_CLASSIFICACAO'),
            'comerciais.parquet': os.getenv('FILE_ID_COMERCIAL'),
            'executivos.parquet': os.getenv('FILE_ID_EXECUTIVO')
        }
    
    # Verificar quais arquivos estão faltando
    required_files = [
        "Dados/raw/mun_UTPs.csv",
        "Dados/interim/aeroportos.parquet",
        "Dados/interim/classificacao_pares.parquet",
        "Dados/interim/comerciais.parquet",
        "Dados/interim/executivos.parquet"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if not missing_files:
        return True

    
    # Baixar arquivos faltantes
    with st.spinner("Baixando dados do Google Drive..."):
        for file_path in missing_files:
            filename = os.path.basename(file_path)
            if filename in file_mapping:
                file_id = file_mapping[filename]
                if not download_file_from_google_drive(file_id, filename):
                    st.error(f"❌ Falha ao baixar {filename}")
                    return False
    
    return True

def check_data_files():
    """Verifica se todos os arquivos de dados necessários existem"""
    required_files = [
        "Dados/raw/mun_UTPs.csv",
        "Dados/interim/aeroportos.parquet",
        "Dados/interim/classificacao_pares.parquet",
        "Dados/interim/comerciais.parquet",
        "Dados/interim/executivos.parquet"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    return missing_files

# Configuração da página
st.set_page_config(
    page_title="Sistema de Análise de Rotas Aéreas",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado para design profissional
st.markdown("""
<style>
    /* Fonte e cores profissionais */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    /* Cabeçalho elegante */
    .main-header {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-weight: 600;
        font-size: 2.5rem;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.9;
        font-size: 1.1rem;
    }
    
    /* Cartões de informação */
    .info-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
        border-left: 4px solid #2a5298;
    }
    
    .metric-container {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        margin: 0.5rem;
        transition: transform 0.2s;
    }
    
    .metric-container:hover {
        transform: translateY(-5px);
        box-shadow: 0 5px 20px rgba(0,0,0,0.1);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1e3c72;
        margin: 0;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #6c757d;
        margin: 0;
        font-weight: 500;
    }
    
    /* Seleções estilizadas */
    .stSelectbox > div > div {
        background-color: #f8f9fa;
        border-radius: 8px;
        border: 2px solid #e9ecef;
    }
    
    .stSelectbox > label {
        font-weight: 500;
        color: #495057;
    }
    
    /* Fix para texto da selectbox */
    .stSelectbox .st-emotion-cache-1y4p8pa {
        overflow: visible !important;
    }
    
    .stSelectbox input {
        color: #495057 !important;
        background-color: transparent !important;
    }
    
    /* Melhorar comportamento do selectbox */
    .stSelectbox div[data-baseweb="select"] {
        background-color: #f8f9fa !important;
    }
    
    .stSelectbox div[data-baseweb="select"]:focus-within {
        border-color: #2a5298 !important;
        box-shadow: 0 0 0 2px rgba(42, 82, 152, 0.1) !important;
    }
    
    /* Botões estilizados */
    .stButton > button {
        background: linear-gradient(135deg, #2a5298 0%, #1e3c72 100%);
        color: #fff !important;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 20px rgba(42,82,152,0.3);
    }
    
    /* Sidebar estilizada */
    .css-1d391kg {
        background-color: #f8f9fa;
    }
    
    /* Remover espaços desnecessários */
    .block-container {
        padding-top: 2rem;
    }
    
    /* Estilo para labels de trajeto */
    .route-label {
        background: #e3f2fd;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: 500;
        color: #1565c0;
        display: inline-block;
        margin: 0.25rem;
    }
    
    /* Mensagem inicial elegante */
    .info-message {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 400px;
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 15px;
        padding: 2rem;
        text-align: center;
    }
    
    .info-message h3 {
        color: #1e3c72;
        margin-bottom: 1rem;
        font-size: 1.5rem;
    }
    
    .info-message p {
        color: #6c757d;
        font-size: 1.1rem;
        max-width: 600px;
    }
    
    /* Aviões estáticos - sem animação */
    
    /* Melhorias no selectbox - sem transições problemáticas */
    .stSelectbox > div > div {
        position: relative;
        background-color: #f8f9fa;
        border-radius: 8px;
        border: 2px solid #e9ecef;
    }
    
    .stSelectbox > div > div:hover {
        border-color: #2a5298;
        box-shadow: 0 2px 8px rgba(42, 82, 152, 0.1);
    }
    
    /* Tooltip customizado */
    .leaflet-tooltip {
        background: rgba(30, 60, 114, 0.9);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 14px;
        font-weight: 500;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    .leaflet-tooltip::before {
        border-top-color: rgba(30, 60, 114, 0.9);
    }
    
    /* Popup customizado */
    .leaflet-popup-content-wrapper {
        background: white;
        border-radius: 12px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.15);
        padding: 0;
    }
    
    .leaflet-popup-content {
        margin: 0;
        padding: 16px;
        font-size: 14px;
        line-height: 1.6;
    }
    
    .leaflet-popup-content b {
        color: #1e3c72;
        font-size: 16px;
        display: block;
        margin-bottom: 8px;
    }
    
    /* Animação de entrada suave */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .main > div {
        animation: fadeInUp 0.6s ease-out;
    }
    
    /* Animações suaves para interface */
    
    /* Efeito de entrada suave para elementos do mapa */
    @keyframes map-element-enter {
        from {
            opacity: 0;
            transform: scale(0.8);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }
    
    /* Hover suave para elementos interativos */
    .leaflet-marker-icon:hover {
        transform: scale(1.1);
        transition: transform 0.2s ease;
    }
    
    /* Interface limpa para selectboxes */
    .stSelectbox > div > div {
        border-radius: 8px;
        border: 1px solid #ddd;
        transition: border-color 0.2s ease;
    }
    
    .stSelectbox > div > div:focus-within {
        border-color: #1e3c72;
        box-shadow: 0 0 0 2px rgba(30, 60, 114, 0.1);
    }
    
    /* Estilo limpo para botões */
    .stButton > button[kind="secondary"] {
        border-radius: 8px;
        border: 1px solid #ddd;
        background-color: #f8f9fa;
        color: #495057;
        transition: all 0.2s ease;
    }
    
    .stButton > button[kind="secondary"]:hover {
        background-color: #e9ecef;
        border-color: #1e3c72;
    }
</style>

""", unsafe_allow_html=True)

# Verificação de autenticação
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_page()
    st.stop()

# Aplicativo principal (só executa se autenticado)
@st.cache_data
def load_data():
    # Verificar se os arquivos de dados existem, se não, tentar baixar
    missing_files = check_data_files()
    if missing_files:
        if not download_data_files():
            st.error("❌ Não foi possível baixar todos os dados necessários. Verifique a configuração.")
            st.stop()
    
    try:
        # Dados dos municípios
        dados_municipios = pl.read_csv("Dados/raw/mun_UTPs.csv").rename({
            'long_utp': 'long',
            'lat_utp': 'lat'
        }).with_columns(
            pl.col('municipio').cast(pl.Utf8).str.slice(0,6).alias('municipio')
        ).select(['municipio', 'nome_municipio', 'uf', 'lat', 'long'])
        
        # Dados de rotas
        comerciais = pl.read_parquet("Dados/interim/comerciais.parquet")
        executivos = pl.read_parquet("Dados/interim/executivos.parquet")
        classificacao = pl.read_parquet("Dados/interim/classificacao_pares.parquet")
        aeroportos = pl.read_parquet('Dados/interim/aeroportos.parquet')
        
        return dados_municipios, comerciais, executivos, classificacao, aeroportos
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {str(e)}")
        st.stop()

# Cache para lookups de coordenadas
@st.cache_data
def create_coordinate_maps(dados_municipios, aeroportos):
    # Criar dicionários para lookup rápido de coordenadas
    mun_coords = {}
    for row in dados_municipios.iter_rows(named=True):
        mun_coords[row['municipio']] = (row['lat'], row['long'])
    
    aero_coords = {}
    for row in aeroportos.iter_rows(named=True):
        aero_coords[row['icao']] = (row['latitude'], row['longitude'])
    
    return mun_coords, aero_coords

# Funções auxiliares
def get_mun_coord(cod_municipio, mun_coords_cache):
    return mun_coords_cache.get(cod_municipio, (None, None))

def get_aerodromo_coord(cod_aeroporto, aero_coords_cache):
    return aero_coords_cache.get(cod_aeroporto, (None, None))

def format_time(hours):
    """Formata tempo de horas decimais para XhYmin"""
    if hours is None or hours == 0:
        return "0h00min"
    try:
        hours_float = float(hours)
        hours_int = int(hours_float)
        minutes = int((hours_float - hours_int) * 60)
        return f"{hours_int}h{minutes:02d}min"
    except (ValueError, TypeError):
        return "N/A"

def format_currency(value):
    """Formata valor monetário"""
    if value is None:
        return "R$ 0,00"
    try:
        value_float = float(value)
        return f"R$ {value_float:,.2f}".replace(",", ".")
    except (ValueError, TypeError):
        return "R$ N/A"

def format_currency_for_table(value):
    """Formata valor monetário para tabela (sem símbolo R$ para permitir ordenação numérica)"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def create_curved_line(start_coords, end_coords, weight=0.2):
    """Cria pontos para uma linha curva entre dois pontos"""
    lat1, lon1 = start_coords
    lat2, lon2 = end_coords
    
    # Ponto de controle para a curva
    ctrl_lat = (lat1 + lat2) / 2 + weight * abs(lon2 - lon1)
    ctrl_lon = (lon1 + lon2) / 2 - weight * abs(lat2 - lat1)
    
    # Gerar pontos ao longo da curva
    points = []
    for t in [i/20 for i in range(21)]:
        # Curva de Bézier quadrática
        lat = (1-t)**2 * lat1 + 2*(1-t)*t * ctrl_lat + t**2 * lat2
        lon = (1-t)**2 * lon1 + 2*(1-t)*t * ctrl_lon + t**2 * lon2
        points.append([lat, lon])
    
    return points



def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calcula o ângulo de direção entre dois pontos"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(x, y)
    return math.degrees(bearing)

def remove_accents(text):
    """Remove acentos de uma string para facilitar a busca"""
    if not text:
        return ""
    # Normalizar e remover acentos
    normalized = unicodedata.normalize('NFD', text.lower())
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents

def create_searchable_options(municipio_map):
    """Cria opções pesquisáveis com código e nome (incluindo busca sem acentos)"""
    options = []
    search_map = {}
    
    for cod, nome_com_uf in municipio_map.items():
        # Texto de exibição (nome com UF)
        display_text = nome_com_uf
        
        # Extrair apenas o nome (sem UF) para busca adicional
        nome_sem_uf = nome_com_uf.split(',')[0].strip() if ',' in nome_com_uf else nome_com_uf
        
        # Textos de busca (múltiplas variações para melhor busca)
        search_texts = [
            nome_com_uf.lower(),                    # Nome completo com UF
            nome_sem_uf.lower(),                    # Nome sem UF
            remove_accents(nome_com_uf),            # Nome com UF sem acentos
            remove_accents(nome_sem_uf),            # Nome sem UF sem acentos
            cod.lower()                             # Código do município
        ]
        
        # Remover duplicatas mantendo ordem
        search_texts = list(dict.fromkeys(search_texts))
        
        options.append(display_text)
        search_map[display_text] = {
            'codigo': cod,
            'nome': nome_com_uf,
            'search_texts': search_texts
        }
    
    return sorted(options), search_map

def filter_options_by_search(options, search_map, search_term):
    """Filtra opções baseado no termo de busca"""
    if not search_term:
        return options
    
    search_term_clean = remove_accents(search_term.lower())
    filtered = []
    
    for option in options:
        option_data = search_map[option]
        for search_text in option_data['search_texts']:
            if search_term_clean in search_text:
                filtered.append(option)
                break
    
    return filtered

# Inicialização
dados_municipios, comerciais, executivos, classificacao, aeroportos = load_data()

# Criar dicionários de mapeamento código -> nome com UF
@st.cache_data
def create_mappings(comerciais, executivos, dados_municipios):
    # Usar operações vetorizadas do Polars para melhor performance
    mun_map = {}
    
    # Criar dicionário de UF baseado nos dados dos municípios
    uf_map = dict(zip(dados_municipios['municipio'].to_list(), dados_municipios['uf'].to_list()))
    
    # De comerciais - usando concat para evitar loops
    comerciais_origem = comerciais.select(['cod_mun_origem', 'mun_origem']).rename({
        'cod_mun_origem': 'codigo', 'mun_origem': 'nome'
    })
    comerciais_destino = comerciais.select(['cod_mun_destino', 'mun_destino']).rename({
        'cod_mun_destino': 'codigo', 'mun_destino': 'nome'
    })
    
    # De executivos
    executivos_origem = executivos.select(['cod_mun_origem', 'mun_origem']).rename({
        'cod_mun_origem': 'codigo', 'mun_origem': 'nome'
    })
    executivos_destino = executivos.select(['cod_mun_destino', 'mun_destino']).rename({
        'cod_mun_destino': 'codigo', 'mun_destino': 'nome'
    })
    
    # Concatenar todas as combinações e remover duplicatas
    todos_municipios = pl.concat([
        comerciais_origem, comerciais_destino,
        executivos_origem, executivos_destino
    ]).unique()
    
    # Converter para dicionário adicionando UF
    for row in todos_municipios.iter_rows(named=True):
        codigo = row['codigo']
        nome = row['nome']
        uf = uf_map.get(codigo, '')
        
        # Formato: "Nome do Município, UF"
        nome_com_uf = f"{nome}, {uf}" if uf else nome
        mun_map[codigo] = nome_com_uf
    
    return mun_map

municipio_map = create_mappings(comerciais, executivos, dados_municipios)
mun_coords_cache, aero_coords_cache = create_coordinate_maps(dados_municipios, aeroportos)

# Criar opções pesquisáveis usando operações otimizadas
@st.cache_data
def get_unique_origins(comerciais, executivos):
    origins_comerciais = set(comerciais['cod_mun_origem'].unique().to_list())
    origins_executivos = set(executivos['cod_mun_origem'].unique().to_list())
    return origins_comerciais.union(origins_executivos)

unique_origins = get_unique_origins(comerciais, executivos)
opcoes_origem_todas, search_map_origem = create_searchable_options({k: v for k, v in municipio_map.items() 
                                                                   if k in unique_origins})

# Site sempre inicia com tela inicial - sem valores padrão
# Removido para garantir que sempre inicie vazio

# Cabeçalho
st.markdown(f"""
<div class="main-header">
    <h1>Sistema de Análise de Rotas Aéreas</h1>
</div>
""", unsafe_allow_html=True)

# Sidebar para seleção
with st.sidebar:
    # Header com informações do usuário e logout
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
    ">
        <div style="font-size: 0.9rem; opacity: 0.9;">Usuário logado:</div>
        <div style="font-weight: 600; font-size: 1rem;">{st.session_state.username}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Botão de logout
    if st.button("🚪 Sair", use_container_width=True, type="secondary"):
        logout()
    
    st.markdown("---")
    
    # st.markdown('<div style="margin-bottom: 0.3rem;"></div>', unsafe_allow_html=True)
    st.markdown("### Seleção de Rota")
    
    # Inicializar contador de limpeza se não existir
    if 'clear_counter' not in st.session_state:
        st.session_state.clear_counter = 0
    
    

    origem_selecionada_nome = st.selectbox(
        "Origem",
        options=opcoes_origem_todas,
        index=None,
        placeholder="Digite para buscar origem...",
        key=f"origem_select_{st.session_state.clear_counter}",
        label_visibility="visible"
    )
    
    # Obter código da origem selecionada
    origem_selecionada = ""
    if origem_selecionada_nome:
        origem_selecionada = search_map_origem[origem_selecionada_nome]['codigo']
    
    # Filtrar destinos baseado na origem selecionada
    if origem_selecionada:
        destinos_disponiveis_cod = list(set(
            comerciais.filter(pl.col('cod_mun_origem') == origem_selecionada)['cod_mun_destino'].unique().to_list() +
            executivos.filter(pl.col('cod_mun_origem') == origem_selecionada)['cod_mun_destino'].unique().to_list()
        ))
        
        opcoes_destino_filtradas, search_map_destino = create_searchable_options({k: v for k, v in municipio_map.items() 
                                                                                 if k in destinos_disponiveis_cod})
        
        # Sempre começar com destino vazio
        default_destino_index = 0
    else:
        opcoes_destino_filtradas = []
        search_map_destino = {}
        default_destino_index = 0
    

    destino_selecionado_nome = st.selectbox(
        "Destino",
        options=opcoes_destino_filtradas,
        index=None,
        placeholder="Digite para buscar destino...",
        key=f"destino_select_{st.session_state.clear_counter}",
        label_visibility="visible",
        disabled=not origem_selecionada_nome
    )
    
    # Botão de limpeza discreto
    if st.button("Limpar Seleção", type="secondary", use_container_width=True):
        st.session_state.clear_counter += 1
        st.rerun()
    
    
    
    st.markdown("---")
   
    # Opções de visualização
    st.markdown("### Opções de Visualização")
    mostrar_todas_rotas = st.checkbox("Mostrar todas as rotas simultaneamente", value=False)
    # Métricas sempre ativadas por padrão
    mostrar_metricas = True
    
     
    # Obter códigos das seleções
    origem_selecionada = ""
    if origem_selecionada_nome:
        origem_selecionada = search_map_origem[origem_selecionada_nome]['codigo']
    
    destino_selecionado = ""
    if destino_selecionado_nome and destino_selecionado_nome in search_map_destino:
        destino_selecionado = search_map_destino[destino_selecionado_nome]['codigo']
    


        st.markdown("---")
    
    if origem_selecionada and destino_selecionado:
            # Verificar tipo de voo
            tipo_voo = classificacao.filter(
                (pl.col('cod_mun_origem') == origem_selecionada) & 
                (pl.col('cod_mun_destino') == destino_selecionado)
            )
            
            if tipo_voo.height > 0:
                tipo = tipo_voo['tipo_voo'][0]
                st.markdown(f"""
                <div class="info-card">
                    <strong>Tipo de Voo:</strong> {tipo}
                </div>
                """, unsafe_allow_html=True)
    

    # Header informativo com contexto geográfico
    if origem_selecionada_nome and destino_selecionado_nome:
        # Calcular distância aproximada (coordenadas)
        coord_orig = get_mun_coord(origem_selecionada, mun_coords_cache)
        coord_dest = get_mun_coord(destino_selecionado, mun_coords_cache)
        
        if coord_orig[0] and coord_dest[0]:
            # Calcular distância em linha reta (fórmula de Haversine simplificada)
            lat1, lon1 = coord_orig
            lat2, lon2 = coord_dest
            import math
            
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            distancia_km = int(6371 * c)  # Raio da Terra em km
            
            # Determinar regiões
            origem_uf = origem_selecionada_nome.split(', ')[-1] if ', ' in origem_selecionada_nome else ""
            destino_uf = destino_selecionado_nome.split(', ')[-1] if ', ' in destino_selecionado_nome else ""
            
            # Classificar tipo de viagem
            if origem_uf == destino_uf:
                tipo_viagem = "🏠 Viagem Estadual"
            else:
                tipo_viagem = "🌎 Viagem Interestadual"
            
            # Classificar distância
            if distancia_km < 300:
                categoria_dist = "📍 Curta Distância"
            elif distancia_km < 800:
                categoria_dist = "🛣️ Média Distância"
            else:
                categoria_dist = "✈️ Longa Distância"
                
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #21273f 0%, #212266 100%);
                color: white;
                padding: 1.7rem;
                border-radius: 15px;
                margin: 1rem 0;
                text-align: center;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            ">
                <h3 style="margin: 0 0 1rem 0;">
                    {origem_selecionada_nome.split(',')[0]} → {destino_selecionado_nome.split(',')[0]}
                </h3>
                <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <div style="font-size: 1.2rem; font-weight: bold;">{distancia_km:,} km</div>
                        <div style="font-size: 0.9rem; opacity: 0.9;">Distância Direta</div>
                    </div>
                    <div>
                        <div style="font-size: 1.2rem; font-weight: bold;">{tipo_viagem}</div>
                        <div style="font-size: 0.9rem; opacity: 0.9;">{origem_uf} → {destino_uf}</div>
                    </div>
                    <div>
                        <div style="font-size: 1.2rem; font-weight: bold;">{categoria_dist}</div>
                        <div style="font-size: 0.9rem; opacity: 0.9;">Categoria</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        else:
            st.success(f"Rota: {origem_selecionada_nome.split(',')[0]} → {destino_selecionado_nome.split(',')[0]}")
    elif origem_selecionada_nome:
        st.info(f"Origem selecionada: {origem_selecionada_nome.split(',')[0]} • Selecione o destino para análise completa")
    
    
   

# Área principal
if origem_selecionada and destino_selecionado:
    # Obter nome dos municípios
    nome_origem = municipio_map.get(origem_selecionada, origem_selecionada)
    nome_destino = municipio_map.get(destino_selecionado, destino_selecionado)
    
    st.markdown(f"## Rota: {nome_origem} → {nome_destino}")
    
    # Verificar se é voo executivo ou comercial
    voos_executivos = executivos.filter(
        (pl.col('cod_mun_origem') == origem_selecionada) & 
        (pl.col('cod_mun_destino') == destino_selecionado)
    )
    
    voos_comerciais = comerciais.filter(
        (pl.col('cod_mun_origem') == origem_selecionada) & 
        (pl.col('cod_mun_destino') == destino_selecionado)
    )
    
    if voos_executivos.height > 0:
        # Voo executivo - Display especial e prominente
        voo = voos_executivos.row(0, named=True)
        
        # Caixa elegante e compacta para voo executivo
        st.markdown(f"""
         <div style="
             background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
             color: white;
             padding: 1.5rem;
             border-radius: 15px;
             margin: 1rem 0;
             box-shadow: 0 10px 25px rgba(231, 76, 60, 0.25);
             text-align: center;
             border: 2px solid rgba(255, 255, 255, 0.1);
             position: relative;
             overflow: hidden;
         ">
             <div style="position: absolute; top: -50%; right: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);"></div>
             <div style="position: relative; z-index: 2;">
                 <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">🛩️</div>
                 <h3 style="margin: 0; font-size: 1.6rem; font-weight: 600; text-shadow: 0 1px 2px rgba(0,0,0,0.3);">
                     VOO EXECUTIVO
                 </h3>
                 <p style="margin: 0.5rem 0; font-size: 1rem; opacity: 0.9;">
                     Rota Terrestre Direta
                 </p>
                 <div style="background: rgba(255, 255, 255, 0.15); padding: 0.8rem; border-radius: 8px; margin-top: 1rem; backdrop-filter: blur(10px);">
                     <p style="margin: 0; font-size: 0.95rem; font-weight: 500;">
                         <strong>Motivo:</strong> {voo['motivo']}
                     </p>
                 </div>
             </div>
         </div>
         """, unsafe_allow_html=True)
        
        # Métricas organizadas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="metric-container" style="background: linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%); color: white;">
                <p class="metric-label" style="color: rgba(255,255,255,0.9);">Tempo Terrestre</p>
                <p class="metric-value" style="color: white;">{format_time(voo['tempo_terrestre_direto'])}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-container">
                <p class="metric-label">Tipo de Transporte</p>
                <p class="metric-value">Terrestre</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="metric-container">
                <p class="metric-label">Viagens Realizadas</p>
                <p class="metric-value">{int(voo['viagens']):,}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Criar mapa
        coord_origem = get_mun_coord(origem_selecionada, mun_coords_cache)
        coord_destino = get_mun_coord(destino_selecionado, mun_coords_cache)
        
        if coord_origem[0] and coord_destino[0]:
            # Calcular centro do mapa
            center_lat = (coord_origem[0] + coord_destino[0]) / 2
            center_lon = (coord_origem[1] + coord_destino[1]) / 2
            
            # Criar mapa
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=6,
                tiles='CartoDB positron',
                control_scale=True
            )
            
            # Adicionar marcadores
            folium.Marker(
                coord_origem,
                popup=f"<b>{nome_origem}</b><br>Origem",
                tooltip=nome_origem,
                icon=folium.Icon(color='green', icon='play', prefix='fa')
            ).add_to(m)
            
            folium.Marker(
                coord_destino,
                popup=f"<b>{nome_destino}</b><br>Destino",
                tooltip=nome_destino,
                icon=folium.Icon(color='red', icon='stop', prefix='fa')
            ).add_to(m)
            
            # Linha direta para voo executivo
            folium.PolyLine(
                locations=[coord_origem, coord_destino],
                color='#ff6b6b',
                weight=4,
                opacity=0.8,
                dash_array='10',
                popup=f"Voo Executivo Direto<br>Tempo: {format_time(voo['tempo_terrestre_direto'])}",
            ).add_to(m)
            
            # Animação agora é feita via CSS na linha tracejada
            
            # Exibir mapa
            st_folium(m, height=600, width=None, returned_objects=[])
            
    elif voos_comerciais.height > 0:
        # Preparar dados das rotas
        rotas = []
        for i in range(voos_comerciais.height):
            voo = voos_comerciais.row(i, named=True)
            rotas.append({
                'index': i,
                'trajeto': voo['trajeto_aereo'],
                'tempo_total': voo['tempo_total'],
                'custo_total': voo['custo_total'],
                'percentual': voo['percentual_de_viagens_par_od'] * 100,
                'viagens': int(voo['viagens']),
                'conexoes': voo['num_conexoes'],
                'tempo_aereo': voo.get('tempo_aereo', 0),
                'tempo_terrestre_embarque': voo.get('tempo_terrestre_embarque', 0),
                'tempo_terrestre_desembarque': voo.get('tempo_terrestre_desembarque', 0),
                'custo_terrestre_embarque': voo.get('custo_terrestre_embarque', 0),
                'custo_terrestre_desembarque': voo.get('custo_terrestre_desembarque', 0)
            })
        
        # Ordenar por percentual
        rotas.sort(key=lambda x: x['percentual'], reverse=True)
        
        # Layout principal com duas colunas
        col_mapa, col_info = st.columns([2, 1])
        
        with col_info:
            # Título da seção de informações (compacto)
            st.markdown("""
            <div style="
                background: #f8f9fa;
                padding: 0rem 0.8rem;
                border-radius: 6px;
                margin-bottom: 0.8rem;
                border-left: 3px solid #1e3c72;
            ">
                <h4 style="margin: 0; color: #1e3c72; font-size: 1rem; font-weight: 600;">
                    Informações das Rotas
                </h4>
            </div>
            """, unsafe_allow_html=True)
            
            # Seleção de rota
            if not mostrar_todas_rotas:
                st.markdown("**Rota Específica:**")
                opcoes_rotas = [f"Rota {i+1} - {r['percentual']:.1f}% das viagens" for i, r in enumerate(rotas)]
                rota_selecionada = st.selectbox(
                    "Selecionar rota:",
                    opcoes_rotas,
                    label_visibility="collapsed"
                )
                indice_rota = opcoes_rotas.index(rota_selecionada)
                rotas_para_mostrar = [rotas[indice_rota]]
                rota_atual = rotas[indice_rota]
            else:
                rotas_para_mostrar = rotas
                rota_atual = rotas[0]
                
                # Mostrar indicador de rota principal
                st.markdown("**Rota Principal (maior percentual):**")
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    color: white;
                    padding: 0.5rem;
                    border-radius: 5px;
                    font-size: 0.9rem;
                    margin-bottom: 0.5rem;
                ">
                    Rota 1 - {rota_atual['percentual']:.1f}% das viagens
                </div>
                """, unsafe_allow_html=True)
            
            # Estatísticas da rota selecionada (design compacto e profissional)
            st.markdown(f"""
            <div style="
                background: white;
                border-radius: 10px;
                padding: 1rem;
                margin: 0.5rem 0;
                border: 1px solid #e9ecef;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            ">
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">TEMPO TOTAL</span>
                        <span style="font-size: 1.1rem; font-weight: 600; color: #1e3c72;">{format_time(rota_atual['tempo_total'])}</span>
                    </div>
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">CUSTO TOTAL</span>
                        <span style="font-size: 1.1rem; font-weight: 600; color: #e74c3c;">{format_currency(rota_atual['custo_total'])}</span>
                    </div>
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">TEMPO AÉREO</span>
                        <span style="font-size: 1rem; font-weight: 500; color: #495057;">{format_time(rota_atual['tempo_aereo'])}</span>
                    </div>
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">TEMPO EMBARQUE</span>
                        <span style="font-size: 1rem; font-weight: 500; color: #495057;">{format_time(rota_atual['tempo_terrestre_embarque'])}</span>
                    </div>
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">TEMPO DESEMBARQUE</span>
                        <span style="font-size: 1rem; font-weight: 500; color: #495057;">{format_time(rota_atual['tempo_terrestre_desembarque'])}</span>
                    </div>
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">CUSTO TERRESTRE</span>
                        <span style="font-size: 1rem; font-weight: 500; color: #28a745;">{format_currency(rota_atual['custo_terrestre_embarque'] + rota_atual['custo_terrestre_desembarque'])}</span>
                    </div>
                </div>
                <div style="margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 0.9rem; color: #6c757d; font-weight: 500;">CONEXÕES</span>
                        <span style="font-size: 1rem; font-weight: 500; color: #495057;">{rota_atual['conexoes']}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Detalhes do trajeto
            st.markdown(f"""
            <div style="
                background: #1e3c72;
                color: white;
                border-radius: 10px;
                padding: 1rem;
                margin: 0.5rem 0;
                box-shadow: 0 4px 12px rgba(30, 60, 114, 0.3);
            ">
                <div style="margin-bottom: 0.5rem;">
                    <span style="font-size: 0.85rem; opacity: 0.9;">DETALHES DO TRAJETO</span>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <strong>Viagens:</strong> {rota_atual['viagens']:,}
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <strong>Percentual:</strong> {rota_atual['percentual']:.1f}%
                </div>
                <div>
                    <strong>Rota Aérea:</strong> {rota_atual['trajeto']}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_mapa:
            st.markdown("""
            <div style="
                background: #f8f9fa;
                padding: 0rem 0.8rem;
                border-radius: 6px;
                margin-bottom: 0.8rem;
                border-left: 3px solid #1e3c72;
            ">
                <h4 style="margin: 0; color: #1e3c72; font-size: 1rem; font-weight: 600;">
                    Mapa de Rotas
                </h4>
            </div>
            """, unsafe_allow_html=True)
            
            # Criar mapa
            coord_origem = get_mun_coord(origem_selecionada, mun_coords_cache)
            coord_destino = get_mun_coord(destino_selecionado, mun_coords_cache)
            
            if coord_origem[0] and coord_destino[0]:
                # Calcular centro e zoom do mapa
                lats = [coord_origem[0], coord_destino[0]]
                lons = [coord_origem[1], coord_destino[1]]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                
                # Calcular zoom baseado na distância
                lat_diff = max(lats) - min(lats)
                lon_diff = max(lons) - min(lons)
                max_diff = max(lat_diff, lon_diff)
                zoom = 5 if max_diff > 10 else 6 if max_diff > 5 else 7
                
                # Criar mapa
                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=zoom,
                    tiles='CartoDB positron',
                    control_scale=True
                )
                
                # Cores para diferentes rotas - paleta mais diversificada
                cores_rotas = [
                    '#1e3c72',  # Azul escuro principal
                    '#e74c3c',  # Vermelho
                    '#27ae60',  # Verde
                    '#f39c12',  # Laranja
                    '#9b59b6',  # Roxo
                    '#3498db',  # Azul claro
                    '#e67e22',  # Laranja escuro
                    '#2ecc71',  # Verde claro
                    '#8e44ad',  # Roxo escuro
                    '#34495e'   # Cinza azulado
                ]
                
                                # Adicionar cada rota
                for idx, rota in enumerate(rotas_para_mostrar):
                    i = rota['index']
                    voo = voos_comerciais.row(i, named=True)
                    
                    # Coordenadas
                    coord_aeroporto_origem = get_aerodromo_coord(voo['icao_aeroporto_origem'], aero_coords_cache)
                    coord_aeroporto_destino = get_aerodromo_coord(voo['icao_aeroporto_destino'], aero_coords_cache)
                    
                    if not (coord_aeroporto_origem[0] and coord_aeroporto_destino[0]):
                        continue

                    # Configurações especiais para rota principal (idx == 0)
                    is_rota_principal = idx == 0
                    
                    # Cor e opacidade baseadas na posição da rota
                    if is_rota_principal:
                        # Rota principal: dourada/laranja para destaque
                        cor = '#FF6B35'  # Laranja vibrante para destaque
                        opacidade = 1.0
                        peso = 6  # Mais grosso
                        
                        # Animação especial para rota principal
                        delay_aereo = 400  # Mais rápido para chamar atenção
                        dash_array_aereo = [15, 30]  # Tracejado mais proeminente
                        
                        # Terrestre da rota principal também destacado
                        cor_terrestre = '#E55100'  # Laranja escuro
                        peso_terrestre = 5
                        opacidade_terrestre = 1.0
                        delay_terrestre = 1000  # Terrestre um pouco mais rápido para principal
                        dash_array_terrestre = [10, 20]
                    else:
                        # Rotas secundárias: cores normais
                        cor = cores_rotas[idx % len(cores_rotas)]
                        opacidade = 0.7
                        peso = 3
                        
                        # Animação normal para rotas secundárias
                        delay_aereo = 600
                        dash_array_aereo = [12, 25]
                        
                        # Terrestre das rotas secundárias
                        cor_terrestre = '#3498db' if idx == 1 else '#2980b9'
                        peso_terrestre = 2
                        opacidade_terrestre = 0.6
                        delay_terrestre = 1500
                        dash_array_terrestre = [8, 15]
                    
                    # Grupo para esta rota
                    route_group = folium.FeatureGroup(name=f"Rota {idx+1}")
                    
                    # Trajeto terrestre de embarque com animação
                    AntPath(
                        locations=[coord_origem, coord_aeroporto_origem],
                        color=cor_terrestre,
                        weight=peso_terrestre,
                        opacity=opacidade_terrestre,
                        delay=delay_terrestre,
                        dash_array=dash_array_terrestre,
                        pulse_color=cor_terrestre,
                        popup=f"""
                        <b>Trajeto Terrestre - Embarque</b><br>
                        Origem: {nome_origem}<br>
                        Aeroporto: {voo['icao_aeroporto_origem']}<br>
                        Tempo: {format_time(voo['tempo_terrestre_embarque'])}<br>
                        Custo: {format_currency(voo['custo_terrestre_embarque'])}
                        """,
                        tooltip=f"🚗 {nome_origem} → {voo['icao_aeroporto_origem']} | {format_time(voo['tempo_terrestre_embarque'])} | {format_currency(voo['custo_terrestre_embarque'])}"
                    ).add_to(route_group)
                    
                    # Processar trajeto aéreo
                    aeroportos_trajeto = voo['trajeto_aereo'].split(' -> ')
                    
                    if len(aeroportos_trajeto) > 2:
                        # Múltiplas conexões
                        coords_aeroportos = []
                        for icao in aeroportos_trajeto:
                            coord = get_aerodromo_coord(icao.strip(), aero_coords_cache)
                            if coord[0]:
                                coords_aeroportos.append(coord)
                        
                        # Desenhar conexões em zigzag
                        if len(coords_aeroportos) >= 2:
                            for j in range(len(coords_aeroportos) - 1):
                                # Curva suave entre aeroportos
                                pontos_curva = create_curved_line(
                                    coords_aeroportos[j], 
                                    coords_aeroportos[j+1],
                                    weight=0.15
                                )
                                                            
                                                                # Linha aérea com animação fluida AntPath
                                AntPath(
                                    locations=pontos_curva,
                                    color=cor,
                                    weight=peso,
                                    opacity=opacidade,
                                    delay=delay_aereo,
                                    dash_array=dash_array_aereo,
                                    pulse_color=cor,
                                    popup=f"""
                                    <b>Trajeto Aéreo - Segmento {j+1}</b><br>
                                    Trecho: {aeroportos_trajeto[j]} → {aeroportos_trajeto[j+1]}<br>
                                    Rota Completa: {voo['trajeto_aereo']}<br>
                                    Tempo Total: {format_time(voo['tempo_aereo'])}<br>
                                    Custo Total: {format_currency(voo['custo_aereo'])}<br>
                                    Conexões: {voo['num_conexoes']}
                                    """,
                                    tooltip=f"✈️ {aeroportos_trajeto[j]} → {aeroportos_trajeto[j+1]} | Tempo Total: {format_time(voo['tempo_aereo'])} | Custo Total: {format_currency(voo['custo_aereo'])}"
                                ).add_to(route_group)
                    else:
                        # Voo direto
                        pontos_curva = create_curved_line(
                            coord_aeroporto_origem,
                            coord_aeroporto_destino,
                            weight=0.2
                        )
                                            
                        # Voo direto com animação fluida AntPath
                        AntPath(
                            locations=pontos_curva,
                            color=cor,
                            weight=peso,
                            opacity=opacidade,
                            delay=delay_aereo,
                            dash_array=dash_array_aereo,
                            pulse_color=cor,
                            popup=f"""
                            <b>Voo Direto</b><br>
                            Trecho: {voo['icao_aeroporto_origem']} → {voo['icao_aeroporto_destino']}<br>
                            Rota: {voo['trajeto_aereo']}<br>
                            Tempo: {format_time(voo['tempo_aereo'])}<br>
                            Custo: {format_currency(voo['custo_aereo'])}
                            """,
                            tooltip=f"✈️ {voo['icao_aeroporto_origem']} → {voo['icao_aeroporto_destino']} | {format_time(voo['tempo_aereo'])} | {format_currency(voo['custo_aereo'])}"
                        ).add_to(route_group)
                    
                    # Trajeto terrestre de desembarque com animação
                    AntPath(
                        locations=[coord_aeroporto_destino, coord_destino],
                        color=cor_terrestre,
                        weight=peso_terrestre,
                        opacity=opacidade_terrestre,
                        delay=delay_terrestre,
                        dash_array=dash_array_terrestre,
                        pulse_color=cor_terrestre,
                                            popup=f"""
                        <b>Trajeto Terrestre - Desembarque</b><br>
                        Aeroporto: {voo['icao_aeroporto_destino']}<br>
                        Destino: {nome_destino}<br>
                        Tempo: {format_time(voo['tempo_terrestre_desembarque'])}<br>
                        Custo: {format_currency(voo['custo_terrestre_desembarque'])}
                        """,
                        tooltip=f"🚗 {voo['icao_aeroporto_destino']} → {nome_destino} | {format_time(voo['tempo_terrestre_desembarque'])} | {format_currency(voo['custo_terrestre_desembarque'])}"
                    ).add_to(route_group)
                    
                    # Adicionar grupo ao mapa
                    route_group.add_to(m)
            
            # Adicionar marcadores principais
            folium.Marker(
                coord_origem,
                popup=f"<b>{nome_origem}</b><br>Município de Origem",
                tooltip=nome_origem,
                icon=folium.Icon(color='green', icon='home', prefix='fa')
            ).add_to(m)
            
            folium.Marker(
                coord_destino,
                popup=f"<b>{nome_destino}</b><br>Município de Destino",
                tooltip=nome_destino,
                icon=folium.Icon(color='red', icon='flag-checkered', prefix='fa')
            ).add_to(m)
            
            # Adicionar marcadores de aeroportos
            aeroportos_unicos = set()
            for i in range(voos_comerciais.height):
                if not mostrar_todas_rotas and i != rotas_para_mostrar[0]['index']:
                    continue
                    
                voo = voos_comerciais.row(i, named=True)
                aeroportos_unicos.add(voo['icao_aeroporto_origem'])
                aeroportos_unicos.add(voo['icao_aeroporto_destino'])
                
                # Aeroportos de conexão
                for icao in voo['trajeto_aereo'].split(' -> '):
                    aeroportos_unicos.add(icao.strip())
            
            for icao in aeroportos_unicos:
                coord = get_aerodromo_coord(icao, aero_coords_cache)
                if coord[0]:
                    folium.Marker(
                        coord,
                        popup=f"<b>Aeroporto {icao}</b>",
                        tooltip=icao,
                        icon=folium.Icon(color='blue', icon='plane', prefix='fa')
                    ).add_to(m)
            
            # Adicionar controle de camadas se mostrar todas as rotas
            if mostrar_todas_rotas and len(rotas_para_mostrar) > 1:
                folium.LayerControl().add_to(m)
            
            # Exibir mapa
            st_folium(m, height=600, width=None, returned_objects=[])
            
        # Tabela comparativa de rotas (sempre exibida quando há múltiplas rotas)
        if len(rotas) > 1:
            st.markdown("---")
            st.markdown("### Comparação de Rotas")
            
            dados_tabela = []
            for i, rota in enumerate(rotas):
                dados_tabela.append({
                    'Rota': f"Rota {i+1}",
                    'Trajeto': rota['trajeto'],
                    'Tempo Total': format_time(rota['tempo_total']),
                    'Custo Total (R$)': format_currency_for_table(rota['custo_total']),
                    'Uso (%)': f"{rota['percentual']:.1f}%",
                    'Viagens': rota['viagens'],  # Mantém como número para ordenação
                    'Conexões': rota['conexoes']
                })
            
            df_tabela = pl.DataFrame(dados_tabela)
            st.dataframe(
                df_tabela,
                width='stretch',
                hide_index=True,
                column_config={
                    'Custo Total (R$)': st.column_config.NumberColumn(
                        'Custo Total (R$)',
                        format="R$ %.2f",
                        help="Custo total da rota em reais"
                    ),
                    'Viagens': st.column_config.NumberColumn(
                        'Viagens',
                        format="%d",
                        help="Número total de viagens"
                    ),
                    'Conexões': st.column_config.NumberColumn(
                        'Conexões',
                        format="%d",
                        help="Número de conexões na rota"
                    )
                }
            )
            st.markdown("---")
            
        # Insights inteligentes sobre as rotas
        if len(rotas) > 1:
            st.markdown("### Insights da Análise")
            
            # Calcular insights
            rota_mais_rapida = min(rotas, key=lambda x: x['tempo_total'])
            rota_mais_barata = min(rotas, key=lambda x: x['custo_total'])
            rota_mais_popular = max(rotas, key=lambda x: x['percentual'])
            
            # Estatísticas comparativas
            tempo_min = min(r['tempo_total'] for r in rotas)
            tempo_max = max(r['tempo_total'] for r in rotas)
            custo_min = min(r['custo_total'] for r in rotas)
            custo_max = max(r['custo_total'] for r in rotas)
            
            # Criar colunas para insights
            col_insight1, col_insight2, col_insight3 = st.columns(3)
            
            with col_insight1:
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg,   #1e3c72 0%, #212266 100%);
                    color: white;
                    padding: 1rem;
                    border-radius: 10px;
                    text-align: center;
                    margin-bottom: 1rem;
                ">
                    <h5 style="margin: 0;">⚡ Mais Rápida</h5>
                    <p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; font-weight: bold;">
                        {format_time(rota_mais_rapida['tempo_total'])}
                    </p>
                    <small>Rota {rotas.index(rota_mais_rapida) + 1}</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col_insight2:
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1e3c72 0%, #212266 100%);
                    color: white;
                    padding: 1rem;
                    border-radius: 10px;
                    text-align: center;
                    margin-bottom: 1rem;
                ">
                    <h5 style="margin: 0;">💰 Mais Barata</h5>
                    <p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; font-weight: bold;">
                        {format_currency(rota_mais_barata['custo_total'])}
                    </p>
                    <small>Rota {rotas.index(rota_mais_barata) + 1}</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col_insight3:
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1e3c72 0%, #212266 100%);
                    color: white;
                    padding: 1rem;
                    border-radius: 10px;
                    text-align: center;
                    margin-bottom: 1rem;
                ">
                    <h5 style="margin: 0;">🎯 Mais Popular</h5>
                    <p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; font-weight: bold;">
                        {rota_mais_popular['percentual']:.1f}%
                    </p>
                    <small>Rota {rotas.index(rota_mais_popular) + 1}</small>
                </div>
                """, unsafe_allow_html=True)
            
            
        
        # Gráfico de distribuição (sempre visível para múltiplas rotas)
        if len(rotas) > 1:
            st.markdown("---")
            
            st.markdown("### Distribuição de Uso das Rotas")
            
            # Gráfico donut
            fig = go.Figure(data=[
                go.Pie(
                    labels=[f"Rota {i+1}" for i in range(len(rotas))],
                    values=[r['percentual'] for r in rotas],
                    hole=.4,
                    marker_colors=cores_rotas[:len(rotas)],
                    textinfo='label+percent',
                    textposition='inside',
                    hovertemplate='<b>%{label}</b><br>' +
                                'Uso: %{percent}<br>' +
                                'Viagens: %{customdata:,}<br>' +
                                'Trajeto: %{text}<extra></extra>',
                    customdata=[r['viagens'] for r in rotas],
                    text=[r['trajeto'] for r in rotas]
                )
            ])
            
            fig.update_layout(
                title={
                    'text': "Distribuição de Uso das Rotas Aéreas",
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 18, 'color': '#1e3c72'}
                },
                showlegend=True,
                legend={
                    'orientation': 'v',
                    'yanchor': 'middle',
                    'y': 0.5,
                    'xanchor': 'left',
                    'x': 1.05
                },
                height=500,
                template="plotly_white",
                margin=dict(l=20, r=120, t=80, b=20)
            )
            
            # Adicionar texto central
            fig.add_annotation(
                text=f"Total<br>{sum(r['viagens'] for r in rotas):,.0f}<br>viagens",
                x=0.5, y=0.5,
                font_size=16,
                showarrow=False,
                font_color='#1e3c72'
            )
            
            st.plotly_chart(fig, width='stretch')

    else:
        st.warning("Não há rotas disponíveis entre os municípios selecionados.")
        
else:
    # Dashboard inicial com informações ricas
    st.markdown("### 📈 Panorama Geral do Sistema")
    
    # Estatísticas nacionais impressionantes
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    
    # Calcular estatísticas gerais
    total_municipios = len(get_unique_origins(comerciais, executivos))
    total_conexoes = comerciais.height + executivos.height
    media_viagens_comerciais = comerciais['viagens'].mean() if 'viagens' in comerciais.columns else 0
    
    with col_stat1:
        st.metric(
            label="🏙️ Municípios Conectados", 
            value=f"{total_municipios:,}".replace(",", "."),
            help="Total de municípios com conexões aéreas"
        )
        
    with col_stat2:
        st.metric(
            label="🛫 Total de Conexões", 
            value=f"{total_conexoes:,}".replace(",", "."),
            help="Soma de rotas comerciais e executivas"
        )
        
    with col_stat3:
        st.metric(
            label="📊 Média Viagens/Rota", 
            value=f"{media_viagens_comerciais:,.0f}".replace(",", "."),
            help="Média de viagens por rota comercial"
        )
        
    with col_stat4:
        percentual_comercial = (comerciais.height / total_conexoes) * 100 if total_conexoes > 0 else 0
        st.metric(
            label="✈️ Rotas Comerciais", 
            value=f"{percentual_comercial:.1f}%",
            help="Percentual de rotas comerciais vs. executivas"
        )
    
  
    # Call to action
    st.info("👆 Selecione uma origem e destino na barra lateral para explorar rotas específicas e suas análises detalhadas.")
    
    # Estatísticas gerais
    with st.expander("Estatísticas Gerais do Sistema", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_rotas_comerciais = comerciais.height
            st.metric("Total de Rotas Comerciais", f"{total_rotas_comerciais:,}")
        
        with col2:
            total_rotas_executivas = executivos.height
            st.metric("Total de Rotas Executivas", f"{total_rotas_executivas:,}")
        
        with col3:
            total_viagens = comerciais['viagens'].sum() + executivos['viagens'].sum()
            st.metric("Total de Viagens", f"{int(total_viagens):,}")
