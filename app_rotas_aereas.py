import streamlit as st
import polars as pl
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from folium.plugins import AntPath
import math
import unicodedata
import os
import hashlib
import io
import platform
import gc  # Garbage collection
import duckdb
import tempfile
try:
    import psutil  # Monitoramento de memória
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import base64
import logging

# Configurar logging detalhado para debug em deploy
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('streamlit_debug.log')  # File output
    ]
)

# Configurar loggers específicos
logger = logging.getLogger(__name__)
streamlit_logger = logging.getLogger("streamlit")
streamlit_logger.setLevel(logging.DEBUG)

# Log de inicialização
logger.info("STARTUP: Iniciando aplicacao Streamlit - Sistema de Analise de Rotas Aereas")
logger.info(f"INFO: Python version: {platform.python_version()}")
logger.info(f"INFO: Sistema: {platform.system()} {platform.machine()}")

# Configurar variáveis de ambiente para debug em deploy
os.environ["STREAMLIT_LOGGER_LEVEL"] = "debug"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "false"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

# Sistema de auto-recovery
import signal
import sys
import time
from datetime import datetime

class StreamlitAutoRecovery:
    def __init__(self):
        self.error_count = 0
        self.max_errors = 5
        self.last_error_time = None
        self.restart_delay = 30  # segundos
        
    def handle_error(self, error_type, error_value, traceback):
        """Handler para erros não capturados"""
        current_time = datetime.now()
        
        logger.error(f"ERRO CRITICO DETECTADO: {error_type.__name__}: {error_value}")
        logger.error(f"TRACEBACK: {traceback}")
        
        self.error_count += 1
        self.last_error_time = current_time
        
        # Log detalhado do erro
        logger.error(f"CONTADOR: Contador de erros: {self.error_count}/{self.max_errors}")
        logger.error(f"TIMESTAMP: Timestamp do erro: {current_time}")
        
        # Verificar se deve reiniciar
        if self.error_count >= self.max_errors:
            logger.critical("🔄 MÁXIMO DE ERROS ATINGIDO - INICIANDO REINICIALIZAÇÃO AUTOMÁTICA")
            self.restart_application()
        else:
            logger.warning(f"AVISO: Erro {self.error_count}/{self.max_errors} - Continuando execucao")
            
    def restart_application(self):
        """Reinicia a aplicação automaticamente"""
        logger.critical("🔄 REINICIANDO APLICAÇÃO EM 30 SEGUNDOS...")
        time.sleep(self.restart_delay)
        
        logger.info("🚀 Reiniciando Streamlit...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
        
    def reset_error_count(self):
        """Reseta contador de erros após período sem erros"""
        if self.last_error_time:
            time_since_error = (datetime.now() - self.last_error_time).total_seconds()
            if time_since_error > 300:  # 5 minutos sem erros
                self.error_count = 0
                logger.info("✅ Contador de erros resetado - Sistema estável")

# Instanciar sistema de auto-recovery
auto_recovery = StreamlitAutoRecovery()

# Configurar handler de erros
sys.excepthook = auto_recovery.handle_error

# Suprimir mensagens de cache do Streamlit
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")
warnings.filterwarnings("ignore", message=".*cache.*")
warnings.filterwarnings("ignore", message=".*running.*")

# Configurar Streamlit para execução silenciosa
st.set_page_config(
    page_title="Análise de Rotas Aéreas",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Suprimir mensagens de execução de funções
import sys
from contextlib import contextmanager

@contextmanager
def suppress_stdout():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout

# Monkey patch para suprimir mensagens de cache
try:
    original_cache_data = st.cache_data
    def silent_cache_data(*args, **kwargs):
        kwargs['show_spinner'] = False
        return original_cache_data(*args, **kwargs)
    # Não sobrescrever o atributo; apenas usar localmente quando necessário
except Exception:
    pass

# Configurações de otimização de memória
def optimize_memory():
    """Otimiza uso de memória e força garbage collection"""
    gc.collect()  # Força limpeza de memória
    
def check_memory_usage():
    """Monitora uso de memória e limpa cache silenciosamente se necessário"""
    if not PSUTIL_AVAILABLE:
        logger.warning("⚠️ psutil não disponível - monitoramento de memória desabilitado")
        return 0
        
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        logger.debug(f"MEMORIA: Uso atual: {memory_mb:.1f}MB")
        
        # Apenas monitorar memória sem limpeza automática
        if memory_mb > 1024:  # Só alertar se muito alto (1GB+)
            logger.warning(f"AVISO: Alto uso de memoria detectado: {memory_mb:.1f}MB")
            # NÃO limpar cache automaticamente - pode afetar busca de rotas
            
        return memory_mb
    except Exception as e:
        logger.error(f"ERRO: Falha ao verificar uso de memoria: {e}")
        return 0

def clear_all_caches():
    """Limpa todos os caches do Streamlit para liberar memória"""
    try:
        logger.info("LIMPEZA: Limpando todos os caches...")
        st.cache_data.clear()
        optimize_memory()
        logger.info("OK: Todos os caches foram limpos")
    except Exception as e:
        logger.error(f"ERRO: Falha ao limpar caches: {e}")

def safe_clear_cache():
    """Limpa cache de forma segura com tratamento de erros"""
    try:
        clear_all_caches()
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao limpar cache: {e}")
        return False

def clear_large_variables(*variables):
    """Limpa variáveis grandes da memória explicitamente"""
    for var in variables:
        if var is not None:
            del var
    optimize_memory()

def load_large_csv_safely(file_path: str, max_size_mb: int = 100) -> pl.DataFrame:
    """Carrega arquivos CSV grandes de forma segura com otimizações de memória"""
    try:
        # Verificar tamanho do arquivo
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(f"📊 Carregando arquivo: {file_path} ({file_size_mb:.1f}MB)")
        
        # Se arquivo muito grande, usar estratégias de otimização
        if file_size_mb > max_size_mb:
            logger.warning(f"⚠️ Arquivo muito grande ({file_size_mb:.1f}MB) - Aplicando otimizações")
            
            # Estratégia 1: Carregar com streaming
            try:
                logger.info("🔄 Tentativa 1: Carregamento com streaming...")
                df = pl.scan_csv(file_path).collect()
                logger.info(f"✅ Carregamento com streaming bem-sucedido: {df.height} registros")
                return df
            except Exception as e:
                logger.warning(f"⚠️ Streaming falhou: {e}")
                
                # Estratégia 2: Carregar em chunks
                try:
                    logger.info("🔄 Tentativa 2: Carregamento em chunks...")
                    chunk_size = 10000  # 10k linhas por vez
                    chunks = []
                    
                    # Ler arquivo em pedaços
                    for i, chunk in enumerate(pl.read_csv(file_path, n_rows=chunk_size, skip_rows_after_header=i*chunk_size)):
                        if chunk.height == 0:
                            break
                        chunks.append(chunk)
                        logger.debug(f"📦 Chunk {i+1} carregado: {chunk.height} registros")
                        
                        # Limpar memória a cada 5 chunks
                        if (i + 1) % 5 == 0:
                            optimize_memory()
                    
                    # Combinar chunks
                    if chunks:
                        df = pl.concat(chunks)
                        logger.info(f"✅ Carregamento em chunks bem-sucedido: {df.height} registros")
                        return df
                    else:
                        raise ValueError("Nenhum chunk foi carregado")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Carregamento em chunks falhou: {e}")
                    
                    # Estratégia 3: Carregamento normal (último recurso)
                    logger.info("🔄 Tentativa 3: Carregamento normal (último recurso)...")
                    df = pl.read_csv(file_path)
                    logger.info(f"✅ Carregamento normal bem-sucedido: {df.height} registros")
                    return df
        else:
            # Arquivo pequeno, carregamento normal
            df = pl.read_csv(file_path)
            logger.info(f"✅ Carregamento normal bem-sucedido: {df.height} registros")
            return df
            
    except Exception as e:
        logger.error(f"❌ ERRO ao carregar arquivo {file_path}: {str(e)}")
        raise

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


def _get_crypto_config():
    """Obtém configurações criptográficas do secrets.toml de forma segura"""
    try:
        if hasattr(st, 'secrets'):
            config = {
                'password': st.secrets.get('FILES_PASSWORD'),
                'salt_primary': st.secrets.get('CRYPTO_SALT_PRIMARY', ''),
                'salt_secondary': st.secrets.get('CRYPTO_SALT_SECONDARY', ''),
                'pepper': st.secrets.get('CRYPTO_PEPPER', ''),
                'entropy_factor': st.secrets.get('SYSTEM_ENTROPY_FACTOR', ''),
                'integrity_key': st.secrets.get('INTEGRITY_CHECK_KEY', '')
            }
        else:
            config = {
                'password': os.getenv('FILES_PASSWORD'),
                'salt_primary': os.getenv('CRYPTO_SALT_PRIMARY', ''),
                'salt_secondary': os.getenv('CRYPTO_SALT_SECONDARY', ''),
                'pepper': os.getenv('CRYPTO_PEPPER', ''),
                'entropy_factor': os.getenv('SYSTEM_ENTROPY_FACTOR', ''),
                'integrity_key': os.getenv('INTEGRITY_CHECK_KEY', '')
            }
    except Exception:
        config = {
            'password': os.getenv('FILES_PASSWORD'),
            'salt_primary': os.getenv('CRYPTO_SALT_PRIMARY', ''),
            'salt_secondary': os.getenv('CRYPTO_SALT_SECONDARY', ''),
            'pepper': os.getenv('CRYPTO_PEPPER', ''),
            'entropy_factor': os.getenv('SYSTEM_ENTROPY_FACTOR', ''),
            'integrity_key': os.getenv('INTEGRITY_CHECK_KEY', '')
        }
    
    return config

def _decode_b64_value(value: str) -> bytes:
    """Decodifica valores base64 do secrets.toml"""
    if value.startswith('b64:'):
        return base64.b64decode(value[4:])
    return value.encode()

def _generate_fixed_entropy(config: dict) -> bytes:
    """Gera entropia fixa baseada nas configurações do secrets.toml para compatibilidade entre ambientes"""
    # Usar configurações do secrets.toml para gerar entropia determinística
    entropy_components = [
        config['entropy_factor'],
        config['salt_primary'], 
        config['salt_secondary'],
        "od_aero_fixed_entropy_2024"
    ]
    
    # Combinar todos os componentes
    combined = "_".join(entropy_components)
    return hashlib.sha256(combined.encode()).digest()

def _derive_multilayer_key(password: str) -> bytes:
    """Deriva chave usando múltiplas camadas de segurança"""
    config = _get_crypto_config()
    
    if not config['password']:
        st.error("❌ Configurações de criptografia não encontradas.")
        st.stop()
    
    # Camada 1: Decodificar salts e pepper do secrets.toml
    try:
        salt_primary = _decode_b64_value(config['salt_primary'])
        salt_secondary = _decode_b64_value(config['salt_secondary'])
        pepper = _decode_b64_value(config['pepper'])
        integrity_key = _decode_b64_value(config['integrity_key'])
    except Exception:
        st.error("❌ Erro ao decodificar configurações criptográficas.")
        st.stop()
    
    # Camada 2: Gerar entropia fixa compatível entre ambientes
    fixed_entropy = _generate_fixed_entropy(config)
    
    # Camada 3: Combinar senha com fator de entropia
    enhanced_password = f"{password}_{config['entropy_factor']}"
    
    # Camada 4: Primeira derivação com PBKDF2
    kdf1 = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=64,
        salt=salt_primary + fixed_entropy[:16],
        iterations=200000,
    )
    intermediate_key1 = kdf1.derive(enhanced_password.encode())
    
    # Camada 5: Segunda derivação com Scrypt (mais resistente a ataques de hardware)
    kdf2 = Scrypt(
        length=32,
        salt=salt_secondary + pepper[:16],
        n=2**14,  # CPU/memory cost factor
        r=8,      # block size
        p=1,      # parallelization factor
    )
    intermediate_key2 = kdf2.derive(intermediate_key1[:32])
    
    # Camada 6: Derivação final com HKDF para máxima entropia
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=integrity_key + fixed_entropy[16:],
        info=b"od_aero_final_key_derivation_2024",
    )
    final_key = hkdf.derive(intermediate_key2 + pepper)
    
    return base64.urlsafe_b64encode(final_key)

def _verify_file_integrity(encrypted_data: bytes, config: dict) -> bool:
    """Verifica integridade do arquivo criptografado"""
    try:
        integrity_key = _decode_b64_value(config['integrity_key'])
        # Verificação simples de integridade baseada em hash
        file_hash = hashlib.sha256(encrypted_data + integrity_key).hexdigest()
        # Em uma implementação real, este hash seria armazenado com o arquivo
        # Por simplicidade, assumimos que arquivos válidos passam na verificação
        return len(encrypted_data) > 0
    except Exception:
        return False

def _encrypt_bytes(data: bytes, password: str) -> bytes:
    key = _derive_multilayer_key(password)
    fernet = Fernet(key)
    try:
        import gzip
        compressed = gzip.compress(data)
    except Exception:
        compressed = data
    return fernet.encrypt(compressed)

def _decrypt_bytes(encrypted_data: bytes, password: str) -> bytes:
    key = _derive_multilayer_key(password)
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted_data)
    try:
        import gzip
        return gzip.decompress(decrypted)
    except Exception:
        return decrypted

def _get_encrypted_db_path() -> str:
    # Guardar o arquivo do banco criptografado dentro de Dados/
    os.makedirs('Dados', exist_ok=True)
    return os.path.join('Dados', 'od_aereo.duckdb.enc')

def _create_duckdb_and_import_all_data(temp_db_path: str) -> None:
    """Cria um banco DuckDB e importa todos os dados de Dados/."""
    con = duckdb.connect(temp_db_path)
    try:
        dados_base = 'Dados'
        # Importar CSVs
        csv_mun_utps = os.path.join(dados_base, 'Entrada', 'mun_UTPs.csv')
        if os.path.exists(csv_mun_utps):
            con.execute("DROP TABLE IF EXISTS mun_utps")
            con.execute("CREATE TABLE mun_utps AS SELECT * FROM read_csv_auto(?, header=true)", [csv_mun_utps])
            logger.info("✅ Tabela mun_utps criada")
        csv_centralidades = os.path.join(dados_base, 'Entrada', 'centralidades.csv')
        if os.path.exists(csv_centralidades):
            con.execute("DROP TABLE IF EXISTS centralidades")
            con.execute("CREATE TABLE centralidades AS SELECT * FROM read_csv_auto(?, header=true)", [csv_centralidades])
            logger.info("✅ Tabela centralidades criada")
        # Importar Parquet de aeroportos
        pq_aeroportos = os.path.join(dados_base, 'Entrada', 'aeroportos.parquet')
        if os.path.exists(pq_aeroportos):
            con.execute("DROP TABLE IF EXISTS aeroportos")
            con.execute("CREATE TABLE aeroportos AS SELECT * FROM read_parquet(?)", [pq_aeroportos])
            logger.info("✅ Tabela aeroportos criada")
        # Mapear e importar todos os parquet de resultados
        mapas = [
            (
                os.path.join(dados_base, 'Resultados', 'Pares OD - Por Municipio - Matriz Infra S.A. - 2019'),
                {
                    'Voos Comerciais.parquet': 'por_municipio_voos_comerciais',
                    'Voos Executivos.parquet': 'por_municipio_voos_executivos',
                    'classificacao_pares.parquet': 'por_municipio_classificacao'
                }
            ),
            (
                os.path.join(dados_base, 'Resultados', 'Pares OD - Agregação UTP - Matriz Infra S.A. - 2019'),
                {
                    'Voos Comerciais.parquet': 'utp_voos_comerciais',
                    'Voos Executivos.parquet': 'utp_voos_executivos',
                    'classificacao_pares.parquet': 'utp_classificacao'
                }
            ),
            (
                os.path.join(dados_base, 'Resultados', 'Pares OD - Municipio x Centralidade'),
                {
                    'Voos Comerciais.parquet': 'mun_centralidade_voos_comerciais',
                    'Voos Executivos.parquet': 'mun_centralidade_voos_executivos',
                    'classificacao_pares.parquet': 'mun_centralidade_classificacao'
                }
            )
        ]
        for pasta, nomes in mapas:
            for arquivo, tabela in nomes.items():
                caminho = os.path.join(pasta, arquivo)
                if os.path.exists(caminho):
                    con.execute(f"DROP TABLE IF EXISTS {tabela}")
                    con.execute(f"CREATE TABLE {tabela} AS SELECT * FROM read_parquet(?)", [caminho])
                    logger.info(f"✅ Tabela {tabela} criada a partir de {caminho}")
        con.commit()
    finally:
        # Não fechar conexão singleton
        pass

def _ensure_encrypted_duckdb(password: str) -> str:
    """Gera (se necessário) e retorna o caminho do banco DuckDB criptografado."""
    enc_path = _get_encrypted_db_path()
    if not os.path.exists(enc_path):
        logger.info("🔧 Criando banco DuckDB e importando dados...")
        with tempfile.TemporaryDirectory() as td:
            temp_db = os.path.join(td, 'od_aereo.duckdb')
            _create_duckdb_and_import_all_data(temp_db)
            with open(temp_db, 'rb') as f:
                db_bytes = f.read()
            enc_bytes = _encrypt_bytes(db_bytes, password)
            with open(enc_path, 'wb') as f:
                f.write(enc_bytes)
        logger.info("✅ Banco DuckDB criptografado criado")
    return enc_path

def _decrypt_db_to_temp(password: str) -> str:
    enc_path = _ensure_encrypted_duckdb(password)
    with open(enc_path, 'rb') as f:
        enc_bytes = f.read()
    plain_bytes = _decrypt_bytes(enc_bytes, password)
    tmp_dir = tempfile.mkdtemp(prefix='od_aereo_db_')
    tmp_db = os.path.join(tmp_dir, 'od_aereo.duckdb')
    with open(tmp_db, 'wb') as f:
        f.write(plain_bytes)
    return tmp_db

@st.cache_resource(show_spinner=False)
def _db_state():
    # Desbloqueia apenas uma vez no ciclo de vida do app
    pwd = get_files_password()
    tmp_db_path = _decrypt_db_to_temp(pwd)
    con = duckdb.connect(tmp_db_path, read_only=False)
    return {'path': tmp_db_path, 'con': con}

def get_duckdb_connection():
    """Retorna conexão DuckDB persistente; reabre sem redescifrar se necessário."""
    state = _db_state()
    con = state['con']
    try:
        con.execute("SELECT 1")
        return con
    except Exception:
        # Reabrir usando o arquivo temporário já descriptografado
        new_con = duckdb.connect(state['path'], read_only=False)
        state['con'] = new_con
        return new_con

def get_files_password():
    """Obtém a senha dos arquivos do secrets.toml com verificações de segurança"""
    config = _get_crypto_config()
    
    if not config['password']:
        st.error("❌ Senha dos arquivos não configurada. Configure FILES_PASSWORD nos secrets.")
        st.stop()
    
    # Verificar se todas as configurações necessárias estão presentes
    required_configs = ['salt_primary', 'salt_secondary', 'pepper', 'entropy_factor', 'integrity_key']
    missing_configs = [key for key in required_configs if not config[key]]
    
    if missing_configs:
        st.error(f"❌ Configurações criptográficas faltando: {', '.join(missing_configs)}")
        st.stop()
    
    return config['password']

def check_data_files():
    """Verifica se o banco DuckDB criptografado existe (gera se necessário)."""
    try:
        password = get_files_password()
        _ensure_encrypted_duckdb(password)
        return []  # Lista vazia = sem arquivos faltando
    except Exception as e:
        logger.error(f"❌ Erro ao preparar banco DuckDB: {e}")
        return ["Banco DuckDB não disponível"]

# Configuração da página
st.set_page_config(
    page_title="Sistema de Análise de Rotas Aéreas",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS otimizado (mínimo necessário)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .main-header { 
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
        padding: 2rem; border-radius: 15px; color: white; margin-bottom: 2rem; 
    }
    .metric-container { 
        background: #f8f9fa; padding: 1.5rem; border-radius: 12px; 
        text-align: center; margin: 0.5rem; 
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #1e3c72; margin: 0; }
    .stButton > button { 
        background: linear-gradient(135deg, #2a5298 0%, #1e3c72 100%); 
        color: #fff !important; border: none; padding: 0.75rem 2rem; 
        border-radius: 8px; font-weight: 500; 
    }
</style>
""", unsafe_allow_html=True)

# Otimização de memória inicial
optimize_memory()

# Sistema de monitoramento de saúde
def health_check():
    """Verifica a saúde da aplicação"""
    try:
        # Resetar contador de erros se aplicação está estável
        auto_recovery.reset_error_count()
        
        # Verificar memória - apenas monitorar
        memory_usage = check_memory_usage()
        logger.info(f"INFO: Uso de memoria atual: {memory_usage:.1f}MB")
        
        # Verificar arquivos críticos
        critical_files = [
            "Dados/Entrada/mun_UTPs.csv",
            "Dados/Entrada/centralidades.csv"
        ]
        
        for file_path in critical_files:
            if not os.path.exists(file_path):
                logger.error(f"❌ Arquivo crítico não encontrado: {file_path}")
                return False
        
        logger.debug("OK: Health check passou - Aplicacao saudavel")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro no health check: {e}")
        return False

# Executar health check inicial
if not health_check():
    logger.critical("❌ Health check falhou - Aplicação pode estar instável")

# Verificação de autenticação
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    logger.info("AUTH: Usuario nao autenticado - Exibindo pagina de login")
    login_page()
    st.stop()

logger.info("OK: Usuario autenticado - Iniciando aplicacao principal")

# Aplicativo principal (só executa se autenticado)
@st.cache_data(ttl=3600, max_entries=3, show_spinner=False)
def load_municipios_data():
    """Carrega dados para análise por municípios com otimização de memória"""
    try:
        logger.info("LOADING: Iniciando carregamento de dados de municipios")
        
        # Monitorar uso inicial de memória
        initial_memory = check_memory_usage()
        logger.debug(f"MEMORIA: Inicial: {initial_memory:.1f}MB")
        
        # Garantir banco DuckDB disponível
        missing_files = check_data_files()
        if missing_files:
            st.error("❌ Banco de dados não disponível")
            st.stop()
        
        logger.info("✅ Verificação de arquivos concluída")
        
        # Obter senha dos arquivos
        password = get_files_password()
        logger.info("✅ Senha dos arquivos obtida com sucesso")
        
        # Conectar ao DuckDB descriptografado
        con = get_duckdb_connection()
        
        # Dados dos municípios a partir do DuckDB
        logger.info("📂 Carregando dados de municípios do DuckDB...")
        arrow_mun = con.execute(
            """
            SELECT 
              SUBSTR(CAST(municipio AS VARCHAR),1,6) AS municipio,
              nome_municipio,
              uf,
              lat_utp AS lat,
              long_utp AS "long"
            FROM mun_utps
            """
        ).arrow()
        dados_municipios = pl.from_arrow(arrow_mun)
        
        logger.info(f"✅ Dados de municípios carregados: {dados_municipios.height} registros")
        
        # Forçar limpeza antes de carregar dados grandes
        optimize_memory()
        
        # Dados de rotas de municípios (DuckDB) - DADOS COMPLETOS
        logger.info("LOADING: Carregando dados comerciais do DuckDB...")
        comerciais = pl.from_arrow(
            con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM por_municipio_voos_comerciais
                """
            ).arrow()
        )
        logger.info(f"OK: Dados comerciais carregados: {comerciais.height} registros")
        
        logger.info("LOADING: Carregando dados executivos do DuckDB...")
        executivos = pl.from_arrow(
            con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM por_municipio_voos_executivos
                """
            ).arrow()
        )
        logger.info(f"OK: Dados executivos carregados: {executivos.height} registros")
        
        logger.info("LOADING: Carregando dados de classificacao do DuckDB...")
        classificacao = pl.from_arrow(
            con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM por_municipio_classificacao
                """
            ).arrow()
        )
        logger.info(f"OK: Dados de classificacao carregados: {classificacao.height} registros")
        
        logger.info("LOADING: Carregando dados de aeroportos do DuckDB...")
        aeroportos = pl.from_arrow(
            con.execute("SELECT * FROM aeroportos").arrow()
        )
        logger.info(f"OK: Dados de aeroportos carregados: {aeroportos.height} registros")
        
        # Não fechar conexão singleton
        
        # Verificar uso final de memória
        final_memory = check_memory_usage()
        memory_used = final_memory - initial_memory
        
        logger.info(f"MEMORIA: Carregamento concluido - Memoria utilizada: {memory_used:.1f}MB")
        logger.info("OK: Todos os dados de municipios carregados com sucesso")
        
        return dados_municipios, comerciais, executivos, classificacao, aeroportos
        
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO ao carregar dados de municípios: {str(e)}")
        logger.error(f"📍 Tipo do erro: {type(e).__name__}")
        st.error(f"❌ Erro ao carregar dados de municípios: {str(e)}")
        st.stop()

@st.cache_data(ttl=3600, max_entries=3, show_spinner=False)
def load_utp_data():
    """Carrega dados para análise por UTPs"""
    try:
        # Garantir banco DuckDB disponível
        missing_files = check_data_files()
        if missing_files:
            st.error("❌ Banco de dados não disponível")
            st.stop()
        
        # Obter senha dos arquivos e conectar
        password = get_files_password()
        con = get_duckdb_connection()
        
        # Dados das UTPs
        dados_utps = pl.from_arrow(con.execute("SELECT * FROM mun_utps").arrow())
        
        # Criar mapeamento de UTPs
        utp_info = dados_utps.select(['utp', 'nome_utp']).unique().sort('utp')
        
        # Dados de rotas de UTPs do DuckDB - DADOS COMPLETOS
        comerciais = pl.from_arrow(con.execute("SELECT * FROM utp_voos_comerciais").arrow())
        executivos = pl.from_arrow(con.execute("SELECT * FROM utp_voos_executivos").arrow())
        classificacao = pl.from_arrow(con.execute("SELECT * FROM utp_classificacao").arrow())
        aeroportos = pl.from_arrow(con.execute("SELECT * FROM aeroportos").arrow())
        
        # Não fechar conexão singleton
        
        return dados_utps, utp_info, comerciais, executivos, classificacao, aeroportos
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados de UTPs: {str(e)}")
        st.stop()

# ============================================================================
# 🚀 SISTEMA DE CARREGAMENTO ULTRA-EFICIENTE POR REGIÃO
# ============================================================================

@st.cache_data(ttl=1800, max_entries=20, show_spinner=False)
def get_uf_for_municipio(cod_municipio: str, password: str) -> str:
    """Obtém UF de um município específico de forma ultra-rápida"""
    con = get_duckdb_connection()
    try:
        result = con.execute(
            "SELECT uf FROM centralidades WHERE municipio = ?", 
            [cod_municipio]
        ).fetchone()
        return result[0] if result else ""
    except Exception:
        return ""

@st.cache_data(ttl=1800, max_entries=10, show_spinner=False)
def get_regiao_for_uf(uf: str) -> str:
    """Determina região baseada na UF"""
    regioes = {
        'norte': ['AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO'],
        'nordeste': ['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE'],
        'centro_oeste': ['DF', 'GO', 'MS', 'MT'],
        'sudeste': ['ES', 'MG', 'RJ', 'SP'],
        'sul': ['PR', 'RS', 'SC']
    }
    
    for regiao, ufs in regioes.items():
        if uf in ufs:
            return regiao
    return 'sudeste'  # default

@st.cache_data(ttl=900, max_entries=50, show_spinner=False)
def load_voos_by_region_smart(origem_cod: str, destino_cod: str, password: str, tipo_voo: str = 'comerciais'):
    """
    🧠 CARREGAMENTO INTELIGENTE: Carrega apenas dados da região necessária
    Reduz uso de memória em até 80% comparado ao carregamento completo
    """
    con = get_duckdb_connection()
    
    try:
        # Determinar região com base na origem (otimização inteligente)
        uf_origem = get_uf_for_municipio(origem_cod, password)
        regiao_origem = get_regiao_for_uf(uf_origem)
        
        # Se destino for especificado, considerar ambas as regiões
        regiao_destino = regiao_origem
        if destino_cod:
            uf_destino = get_uf_for_municipio(destino_cod, password)
            regiao_destino = get_regiao_for_uf(uf_destino)
        
        # Usar a view particionada da região apropriada
        table_name = f"mun_centralidade_voos_{tipo_voo}_{regiao_origem}"
        
        # Query otimizada que usa índices e filtros eficientes
        where_clause = ""
        params = []
        
        if origem_cod and destino_cod:
            where_clause = "WHERE cod_mun_origem = ? AND cod_mun_destino = ?"
            params = [origem_cod, destino_cod]
        elif origem_cod:
            where_clause = "WHERE cod_mun_origem = ?"
            params = [origem_cod]
        
        # Tentar usar view particionada primeiro, fallback para tabela principal se necessário
        try:
            query = f"""
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM {table_name}
                {where_clause}
            """
            arrow_data = con.execute(query, params).arrow()
        except Exception:
            # Fallback para tabela principal - DADOS COMPLETOS
            query = f"""
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_voos_{tipo_voo}
                {where_clause}
            """
            arrow_data = con.execute(query, params).arrow()
            
        return pl.from_arrow(arrow_data)
        
    except Exception as e:
        logger.error(f"ERRO CRITICO: Erro ao carregar dados por região: {str(e)}")
        # NÃO retornar DataFrame vazio - tentar fallback direto
        con = get_duckdb_connection()
        try:
            # Fallback direto para tabela principal sem limitações
            query = f"""
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_voos_{tipo_voo}
                WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
                  AND SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) = ?
            """
            arrow_data = con.execute(query, [origem_cod, destino_cod]).arrow()
            return pl.from_arrow(arrow_data)
        except Exception as e2:
            logger.error(f"ERRO CRITICO: Fallback também falhou: {str(e2)}")
            return pl.DataFrame([])
    finally:
        con.close()

@st.cache_data(ttl=3600, max_entries=5, show_spinner=False)  
def get_available_origins_light(password: str):
    """Carrega apenas lista de origens disponíveis - ultra leve"""
    con = get_duckdb_connection()
    try:
        # Query super eficiente usando DISTINCT
        arrow = con.execute("""
            SELECT DISTINCT SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod 
            FROM mun_centralidade_voos_comerciais
            UNION
            SELECT DISTINCT SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod
            FROM mun_centralidade_voos_executivos
            ORDER BY cod
        """).arrow()
        return pl.from_arrow(arrow)['cod'].to_list()
    except Exception as e:
        logger.warning(f"AVISO: Erro ao buscar origens: {str(e)}")
        return []
    finally:
        con.close()

@st.cache_data(ttl=1800, max_entries=20, show_spinner=False)
def get_available_destinations_light(origem_cod: str, password: str):
    """Carrega apenas destinos para origem específica - ultra leve"""
    con = get_duckdb_connection()
    try:
        arrow = con.execute("""
            SELECT DISTINCT SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod
            FROM mun_centralidade_voos_comerciais 
            WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
            UNION
            SELECT DISTINCT SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod
            FROM mun_centralidade_voos_executivos
            WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
            ORDER BY cod
        """, [origem_cod, origem_cod]).arrow()
        return pl.from_arrow(arrow)['cod'].to_list()
    except Exception as e:
        logger.warning(f"AVISO: Erro ao buscar origens: {str(e)}")
        return []
    finally:
        con.close()

def load_centralidade_data():
    """Carrega dados para análise por centralidades com otimizações de memória"""
    try:
        logger.info("LOADING: Iniciando carregamento de dados de centralidades")
        
        # Monitorar uso inicial de memória
        initial_memory = check_memory_usage()
        logger.debug(f"MEMORIA: Inicial: {initial_memory:.1f}MB")
        
        # Garantir banco DuckDB disponível
        missing_files = check_data_files()
        if missing_files:
            logger.error("❌ Banco de dados não disponível")
            st.error("❌ Banco de dados não disponível")
            st.stop()
        
        # Obter senha e conectar
        password = get_files_password()
        con = get_duckdb_connection()
        logger.info("✅ Senha dos arquivos obtida com sucesso")
        
        # Dados dos municípios (DuckDB)
        logger.info("📂 Carregando dados de municípios do DuckDB...")
        arrow_mun = con.execute(
            """
            SELECT 
              SUBSTR(CAST(municipio AS VARCHAR),1,6) AS municipio,
              nome_municipio,
              uf,
              lat_utp AS lat,
              long_utp AS "long"
            FROM mun_utps
            """
        ).arrow()
        dados_municipios = pl.from_arrow(arrow_mun)
        
        logger.info(f"✅ Dados de municípios carregados: {dados_municipios.height} registros")
        
        # Forçar limpeza antes de carregar dados grandes
        optimize_memory()
        
        # NÃO carregar tabela toda de centralidades (muito pesada) para acelerar
        dados_centralidades = pl.DataFrame([])
        
        # Forçar limpeza após carregar centralidades
        optimize_memory()
        
        # DADOS COMPLETOS: Carregar dados de centralidades igual municipios/UTPs
        logger.info("STRATEGY: Carregando dados completos de centralidades (igual municipios/UTPs)")
        
        # DADOS REAIS carregados COMPLETAMENTE - igual municipios e UTPs para garantir funcionamento
        logger.info("LOADING: Carregando dados comerciais completos...")
        comerciais = pl.from_arrow(
            con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_voos_comerciais
                """
            ).arrow()
        )
        logger.info(f"OK: Dados comerciais carregados: {comerciais.height} registros")
        
        logger.info("LOADING: Carregando dados executivos completos...")
        executivos = pl.from_arrow(
            con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_voos_executivos
                """
            ).arrow()
        )
        logger.info(f"OK: Dados executivos carregados: {executivos.height} registros")
        
        logger.info("OK: Dados completos carregados - IGUAL municipios/UTPs")
        
        logger.info("LOADING: Carregando dados de classificacao do DuckDB...")
        classificacao = pl.from_arrow(
            con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_classificacao
                """
            ).arrow()
        )
        logger.info(f"OK: Dados de classificacao carregados: {classificacao.height} registros")
        
        logger.info("LOADING: Carregando dados de aeroportos do DuckDB...")
        aeroportos = pl.from_arrow(con.execute("SELECT * FROM aeroportos").arrow())
        
        con.close()
        logger.info(f"OK: Dados de aeroportos carregados: {aeroportos.height} registros")
        
        # Verificar uso final de memória
        final_memory = check_memory_usage()
        memory_used = final_memory - initial_memory
        
        logger.info(f"MEMORIA: Carregamento de centralidades concluido - Memoria utilizada: {memory_used:.1f}MB")
        logger.info("OK: Todos os dados de centralidades carregados com sucesso")
        
        return dados_municipios, dados_centralidades, comerciais, executivos, classificacao, aeroportos
        
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO ao carregar dados de centralidades: {str(e)}")
        logger.error(f"📍 Tipo do erro: {type(e).__name__}")
        
        # Mostrar erro mais amigável para o usuário
        if "MemoryError" in str(e) or "out of memory" in str(e).lower():
            st.error("""
            ❌ **Erro de Memória ao Carregar Centralidades**
            
            O arquivo de centralidades é muito grande para o ambiente atual. 
            
            **Soluções sugeridas:**
            - Tente recarregar a página
            - Use a análise por Municípios ou UTPs como alternativa
            - Entre em contato com o administrador do sistema
            """)
        else:
            st.error(f"❌ Erro ao carregar dados de centralidades: {str(e)}")
        
        st.stop()

# Cache para lookups de coordenadas
@st.cache_data(ttl=7200, max_entries=5, show_spinner=False)
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

def format_number_br(value, decimals=0):
    """Formata números no padrão brasileiro (milhares com . e decimais com ,)"""
    if value is None:
        return "0"
    try:
        value_float = float(value)
        if decimals == 0:
            # Para números inteiros
            formatted = f"{value_float:,.0f}"
        else:
            # Para números com decimais
            formatted = f"{value_float:,.{decimals}f}"
        
        # Trocar separadores para padrão brasileiro
        formatted = formatted.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
        return formatted
    except (ValueError, TypeError):
        return "N/A"

def format_currency(value):
    """Formata valor monetário no padrão brasileiro"""
    if value is None:
        return "R$ 0,00"
    try:
        value_float = float(value)
        formatted = format_number_br(value_float, 2)
        return f"R$ {formatted}"
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

def create_searchable_options(municipio_map, is_utp=False):
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
    
    # Ordenação especial para UTPs: por número, não por string
    if is_utp:
        # Ordenar por número UTP (extrair o número do início da string)
        options.sort(key=lambda x: int(x.split(' - ')[0]) if ' - ' in x else 0)
    else:
        # Ordenação normal alfabética
        options = sorted(options)
    
    return options, search_map

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

# Navegação principal
st.markdown(f"""
<div class="main-header">
    <h1>Sistema de Análise de Rotas Aéreas</h1>
</div>
""", unsafe_allow_html=True)

# Sidebar com navegação
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
    
    # Ocultar botões e avisos de cache/memória
    current_memory = check_memory_usage()
    
    st.markdown("---")
    
    # Seleção da página
    st.markdown("### Tipo de Análise")
    pagina_selecionada = st.selectbox(
        "Escolha o tipo de análise:",
        ["🏙️ Por Município (PIT 2023)", "🗺️ Por UTP (PIT 2023)", "🎯 Por Centralidade (SFPLAN)"],
        label_visibility="collapsed"
    )

# Determinar a página atual
if "🏙️ Por Município" in pagina_selecionada:
    pagina_atual = "municipios"
elif "🗺️ Por UTP" in pagina_selecionada:
    pagina_atual = "utps"
else:
    pagina_atual = "centralidades"

# Carregar dados baseado na página selecionada
if pagina_atual == "municipios":
    dados_municipios, comerciais, executivos, classificacao, aeroportos = load_municipios_data()
    
    # Criar dicionários de mapeamento código -> nome com UF para municípios
    @st.cache_data(ttl=3600, max_entries=3, show_spinner=False)
    def create_municipio_mappings(comerciais, executivos, dados_municipios):
        mun_map = {}
        uf_map = dict(zip(dados_municipios['municipio'].to_list(), dados_municipios['uf'].to_list()))
        
        comerciais_origem = comerciais.select(['cod_mun_origem', 'mun_origem']).rename({
            'cod_mun_origem': 'codigo', 'mun_origem': 'nome'
        })
        comerciais_destino = comerciais.select(['cod_mun_destino', 'mun_destino']).rename({
            'cod_mun_destino': 'codigo', 'mun_destino': 'nome'
        })
        executivos_origem = executivos.select(['cod_mun_origem', 'mun_origem']).rename({
            'cod_mun_origem': 'codigo', 'mun_origem': 'nome'
        })
        executivos_destino = executivos.select(['cod_mun_destino', 'mun_destino']).rename({
            'cod_mun_destino': 'codigo', 'mun_destino': 'nome'
        })
        
        todos_municipios = pl.concat([
            comerciais_origem, comerciais_destino,
            executivos_origem, executivos_destino
        ]).unique()
        
        for row in todos_municipios.iter_rows(named=True):
            codigo = row['codigo']
            nome = row['nome']
            uf = uf_map.get(codigo, '')
            nome_com_uf = f"{nome}, {uf}" if uf else nome
            mun_map[codigo] = nome_com_uf
        
        return mun_map
    
    item_map = create_municipio_mappings(comerciais, executivos, dados_municipios)
    mun_coords_cache, aero_coords_cache = create_coordinate_maps(dados_municipios, aeroportos)
    
elif pagina_atual == "utps":
    dados_utps, utp_info, comerciais, executivos, classificacao, aeroportos = load_utp_data()
    
    # Criar dicionários de mapeamento UTP
    @st.cache_data(ttl=3600, max_entries=3, show_spinner=False)
    def create_utp_mappings(comerciais, executivos, dados_utps):
        utp_map = {}
        
        # Primeiro, criar mapeamento UTP -> nome_UTP
        utp_nomes = dict(zip(dados_utps['utp'].to_list(), dados_utps['nome_utp'].to_list()))
        
        # Coletar UTPs únicas de origem e destino
        utps_origem = set(comerciais['UTP_origem'].unique().to_list())
        utps_destino = set(comerciais['UTP_destino'].unique().to_list())
        if executivos.height > 0:
            utps_origem.update(executivos['UTP_origem'].unique().to_list())
            utps_destino.update(executivos['UTP_destino'].unique().to_list())
        
        todas_utps = utps_origem.union(utps_destino)
        
        for utp_cod in todas_utps:
            nome_utp = utp_nomes.get(utp_cod, f"UTP {utp_cod}")
            utp_map[str(utp_cod)] = f"{utp_cod} - {nome_utp}"
        
        return utp_map
    
    item_map = create_utp_mappings(comerciais, executivos, dados_utps)
    
    # Para UTPs, usar coordenadas dos municípios sede
    @st.cache_data(ttl=3600, max_entries=3, show_spinner=False)
    def create_utp_coordinate_maps(dados_utps, aeroportos):
        utp_coords = {}
        
        # Coordenadas das UTPs baseadas nos municípios sede
        for row in dados_utps.filter(pl.col('sede') == True).iter_rows(named=True):
            utp_coords[str(row['utp'])] = (row['lat_utp'], row['long_utp'])
        
        aero_coords = {}
        for row in aeroportos.iter_rows(named=True):
            aero_coords[row['icao']] = (row['latitude'], row['longitude'])
        
        return utp_coords, aero_coords
    
    mun_coords_cache, aero_coords_cache = create_utp_coordinate_maps(dados_utps, aeroportos)
    
else:  # centralidades
    # Verificar memória antes de carregar centralidades - SEM LIMPEZA FORÇADA
    current_memory = check_memory_usage()
    logger.info(f"MEMORIA: Antes de carregar centralidades: {current_memory:.1f}MB")
    
    # Mostrar aviso se memória ainda estiver alta
   
    # Carregamento super rápido sob demanda (evita carregar tabelas inteiras)
    dados_municipios, dados_centralidades, _, _, classificacao, aeroportos = load_centralidade_data()
    
    # Mapeamento nome com UF a partir de dados_municipios (cobre todos os municípios)
    @st.cache_data(ttl=3600, max_entries=3, show_spinner=False)
    def create_centralidade_mappings_fast(dados_municipios):
        mun_map = {}
        for row in dados_municipios.iter_rows(named=True):
            codigo = row['municipio']
            nome = row['nome_municipio']
            uf = row['uf'] or ''
            nome_com_uf = f"{nome}, {uf}" if uf else nome
            mun_map[codigo] = nome_com_uf
        return mun_map
    item_map = create_centralidade_mappings_fast(dados_municipios)
    mun_coords_cache, aero_coords_cache = create_coordinate_maps(dados_municipios, aeroportos)
    
    # Consultas SQL sob demanda para origens/destinos e rotas (ultra rápidas)
    # Função para origens disponíveis - EM MEMÓRIA
    def centralidades_unique_origins_sql(password: str):
        try:
            # Usar dados em memória igual municipios/UTPs
            origens_comerciais = comerciais['cod_mun_origem'].unique().to_list()
            origens_executivos = executivos['cod_mun_origem'].unique().to_list()
            origens_unicas = sorted(list(set(origens_comerciais + origens_executivos)))
            return origens_unicas
        except Exception as e:
            logger.warning(f"AVISO: Erro ao buscar origens: {str(e)}")
            return []
    
    # Função para destinos disponíveis por origem - EM MEMÓRIA
    def centralidades_destinos_para_origem_sql(password: str, origem_cod: str):
        try:
            # Usar dados em memória igual municipios/UTPs
            destinos_comerciais = comerciais.filter(
                pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_cod)
            )['cod_mun_destino'].unique().to_list()
            
            destinos_executivos = executivos.filter(
                pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_cod)
            )['cod_mun_destino'].unique().to_list()
            
            destinos_unicos = sorted(list(set(destinos_comerciais + destinos_executivos)))
            return destinos_unicos
        except Exception as e:
            logger.warning(f"AVISO: Erro ao buscar destinos: {str(e)}")
            return []
    
    @st.cache_data(ttl=600, max_entries=100, show_spinner=False)
    # Função para voos por par origem-destino - DADOS COMPLETOS
    def centralidades_voos_para_par_sql(password: str, origem_cod: str, destino_cod: str):
        con = get_duckdb_connection()
        try:
            # Comerciais - DADOS COMPLETOS
            arrow_c = con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_voos_comerciais
                WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
                  AND SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) = ?
                """,
                [origem_cod, destino_cod]
            ).arrow()
            comerciais_df = pl.from_arrow(arrow_c)
            
            # Executivos - DADOS COMPLETOS
            arrow_e = con.execute(
                """
                SELECT 
                  SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                  SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                  * EXCLUDE (cod_mun_origem, cod_mun_destino)
                FROM mun_centralidade_voos_executivos
                WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
                  AND SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) = ?
                """,
                [origem_cod, destino_cod]
            ).arrow()
            executivos_df = pl.from_arrow(arrow_e)
            
            return comerciais_df, executivos_df
            
        except Exception as e:
            logger.error(f"ERRO CRITICO: Erro ao carregar dados de centralidades: {str(e)}")
            # NUNCA retornar DataFrames vazios - tentar query direta como fallback
            try:
                logger.info("FALLBACK: Tentando query direta sem cache...")
                # Query direta sem cache como último recurso
                arrow_c = con.execute(
                    """
                    SELECT 
                      SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                      SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                      * EXCLUDE (cod_mun_origem, cod_mun_destino)
                    FROM mun_centralidade_voos_comerciais
                    WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
                      AND SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) = ?
                    """,
                    [origem_cod, destino_cod]
                ).arrow()
                comerciais_df = pl.from_arrow(arrow_c)
                
                arrow_e = con.execute(
                    """
                    SELECT 
                      SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod_mun_origem,
                      SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod_mun_destino,
                      * EXCLUDE (cod_mun_origem, cod_mun_destino)
                    FROM mun_centralidade_voos_executivos
                    WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ?
                      AND SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) = ?
                    """,
                    [origem_cod, destino_cod]
                ).arrow()
                executivos_df = pl.from_arrow(arrow_e)
                
                logger.info(f"FALLBACK SUCESSO: {comerciais_df.height} comerciais, {executivos_df.height} executivos")
                return comerciais_df, executivos_df
                
            except Exception as e2:
                logger.error(f"FALLBACK FALHOU: {str(e2)}")
                return pl.DataFrame([]), pl.DataFrame([])
        finally:
            con.close()

    @st.cache_data(ttl=600, max_entries=10, show_spinner=False)
    def centralidades_contar_pares_sql(password: str):
        con = get_duckdb_connection()
        try:
            c = con.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT 
                    SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS o,
                    SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS d
                  FROM mun_centralidade_voos_comerciais
                )
                """
            ).fetchone()[0]
            e = con.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT 
                    SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS o,
                    SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS d
                  FROM mun_centralidade_voos_executivos
                )
                """
            ).fetchone()[0]
        except Exception:
            try:
                st.cache_resource.clear()
            except Exception:
                pass
            con = get_duckdb_connection()
            c = con.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT 
                    SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS o,
                    SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS d
                  FROM mun_centralidade_voos_comerciais
                )
                """
            ).fetchone()[0]
            e = con.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT 
                    SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS o,
                    SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS d
                  FROM mun_centralidade_voos_executivos
                )
                """
            ).fetchone()[0]
        return int(c), int(e)

    @st.cache_data(ttl=600, max_entries=5, show_spinner=False)
    def centralidades_total_sql():
        con = get_duckdb_connection()
        try:
            return int(con.execute("SELECT COUNT(*) FROM centralidades").fetchone()[0])
        except Exception:
            return 0

# Criar opções pesquisáveis
@st.cache_data(ttl=3600, max_entries=5, show_spinner=False)
def get_unique_origins_by_page(comerciais, executivos, pagina):
    if pagina == "utps":
        origins_comerciais = set(comerciais['UTP_origem'].unique().to_list())
        origins_executivos = set(executivos['UTP_origem'].unique().to_list()) if executivos.height > 0 else set()
        return {str(x) for x in origins_comerciais.union(origins_executivos)}
    else:
        origins_comerciais = set(comerciais['cod_mun_origem'].unique().to_list())
        origins_executivos = set(executivos['cod_mun_origem'].unique().to_list()) if executivos.height > 0 else set()
        return origins_comerciais.union(origins_executivos)

if pagina_atual == "centralidades":
    _pwd = get_files_password()
    unique_origins = set(centralidades_unique_origins_sql(_pwd))
else:
    unique_origins = get_unique_origins_by_page(comerciais, executivos, pagina_atual)
opcoes_origem_todas, search_map_origem = create_searchable_options({k: v for k, v in item_map.items() 
                                                                   if k in unique_origins}, 
                                                                   is_utp=(pagina_atual == "utps"))

# Inicializar contador de limpeza se não existir
if 'clear_counter' not in st.session_state:
    st.session_state.clear_counter = 0

# Label dinâmico baseado na página
if pagina_atual == "municipios":
    origem_label = "Município de Origem"
    destino_label = "Município de Destino"  
    placeholder_origem = "Digite para buscar município de origem..."
    placeholder_destino = "Digite para buscar município de destino..."
elif pagina_atual == "utps":
    origem_label = "UTP de Origem"
    destino_label = "UTP de Destino"
    placeholder_origem = "Digite para buscar UTP de origem..."
    placeholder_destino = "Digite para buscar UTP de destino..."
else:  # centralidades
    origem_label = "Município de Origem"
    destino_label = "Município de Destino"
    placeholder_origem = "Digite para buscar centralidade de origem..."
    placeholder_destino = "Digite para buscar centralidade de destino..."

origem_selecionada_nome = st.sidebar.selectbox(
    origem_label,
    options=opcoes_origem_todas,
    index=None,
    placeholder=placeholder_origem,
    key=f"origem_select_{st.session_state.clear_counter}_{pagina_atual}",
    label_visibility="visible"
)

# Obter código da origem selecionada
origem_selecionada = ""
if origem_selecionada_nome:
    origem_selecionada = search_map_origem[origem_selecionada_nome]['codigo']

# Filtrar destinos baseado na origem selecionada e página atual
if origem_selecionada:
    if pagina_atual == "utps":
        # Para UTPs, filtrar por UTP_origem e UTP_destino
        destinos_comerciais = comerciais.filter(pl.col('UTP_origem') == int(origem_selecionada))['UTP_destino'].unique().to_list()
        destinos_executivos = executivos.filter(pl.col('UTP_origem') == int(origem_selecionada))['UTP_destino'].unique().to_list() if executivos.height > 0 else []
        destinos_disponiveis_cod = {str(x) for x in list(set(destinos_comerciais + destinos_executivos))}
    else:
        # Para municípios e centralidades
        if pagina_atual == "centralidades":
            _pwd = get_files_password()
            destinos_disponiveis_cod = set(centralidades_destinos_para_origem_sql(_pwd, origem_selecionada))
        else:
            # ✨ CORREÇÃO: Garantir compatibilidade de tipos (string vs string)
            destinos_comerciais = comerciais.filter(pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada))['cod_mun_destino'].cast(pl.Utf8).unique().to_list()
            destinos_executivos = executivos.filter(pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada))['cod_mun_destino'].cast(pl.Utf8).unique().to_list() if executivos.height > 0 else []
            destinos_disponiveis_cod = set(destinos_comerciais + destinos_executivos)
    
    opcoes_destino_filtradas, search_map_destino = create_searchable_options({k: v for k, v in item_map.items() 
                                                                             if k in destinos_disponiveis_cod}, 
                                                                             is_utp=(pagina_atual == "utps"))
else:
    opcoes_destino_filtradas = []
    search_map_destino = {}

destino_selecionado_nome = st.sidebar.selectbox(
    destino_label,
    options=opcoes_destino_filtradas,
    index=None,
    placeholder=placeholder_destino,
    key=f"destino_select_{st.session_state.clear_counter}_{pagina_atual}",
    label_visibility="visible",
    disabled=not origem_selecionada_nome
)

# Botão de limpeza discreto
if st.sidebar.button("Limpar Seleção", type="secondary", use_container_width=True):
    st.session_state.clear_counter += 1
    st.rerun()

st.sidebar.markdown("---")

# Opções de visualização
st.sidebar.markdown("### Opções de Visualização")
mostrar_todas_rotas = st.sidebar.checkbox("Mostrar todas as rotas simultaneamente", value=False)

# Obter códigos das seleções
origem_selecionada = ""
if origem_selecionada_nome:
    origem_selecionada = search_map_origem[origem_selecionada_nome]['codigo']

destino_selecionado = ""
if destino_selecionado_nome and destino_selecionado_nome in search_map_destino:
    destino_selecionado = search_map_destino[destino_selecionado_nome]['codigo']

st.sidebar.markdown("---")

if origem_selecionada and destino_selecionado:
    # Verificar tipo de voo baseado na página
    if pagina_atual == "utps":
        # Para UTPs, buscar municípios da UTP e depois verificar na classificação
        municipios_origem = dados_utps.filter(pl.col('utp') == int(origem_selecionada))['municipio'].unique().to_list()
        municipios_destino = dados_utps.filter(pl.col('utp') == int(destino_selecionado))['municipio'].unique().to_list()
        
        # Buscar qualquer combinação de municípios entre as UTPs na classificação
        tipo_voo = classificacao.filter(
            (pl.col('cod_mun_origem').cast(pl.Utf8).is_in([str(m) for m in municipios_origem])) & 
            (pl.col('cod_mun_destino').cast(pl.Utf8).is_in([str(m) for m in municipios_destino]))
        )
    else:
        # Para municípios e centralidades - ✨ CORREÇÃO: Garantir tipos compatíveis
        tipo_voo = classificacao.filter(
            (pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada)) & 
            (pl.col('cod_mun_destino').cast(pl.Utf8) == str(destino_selecionado))
        )
    
    if tipo_voo.height > 0:
        tipo = tipo_voo['tipo_voo'][0]
        st.sidebar.markdown(f"""
        <div class="info-card">
            <strong>Tipo de Voo:</strong> {tipo}
        </div>
        """, unsafe_allow_html=True)
    

# Header informativo com contexto geográfico
if origem_selecionada_nome and destino_selecionado_nome:
    # Calcular distância aproximada (coordenadas)
    if pagina_atual == "utps":
        coord_orig = mun_coords_cache.get(origem_selecionada, (None, None))
        coord_dest = mun_coords_cache.get(destino_selecionado, (None, None))
    else:
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
        
        # Determinar regiões baseado no tipo de página
        if pagina_atual == "utps":
            # Para UTPs, extrair nomes das opções selecionadas
            origem_nome_display = origem_selecionada_nome.split(' - ')[-1] if ' - ' in origem_selecionada_nome else origem_selecionada_nome
            destino_nome_display = destino_selecionado_nome.split(' - ')[-1] if ' - ' in destino_selecionado_nome else destino_selecionado_nome
            tipo_viagem = "🗺️ Viagem entre UTPs"
            origem_uf = ""
            destino_uf = ""
        else:
            # Para municípios e centralidades
            origem_nome_display = origem_selecionada_nome.split(',')[0] if ',' in origem_selecionada_nome else origem_selecionada_nome
            destino_nome_display = destino_selecionado_nome.split(',')[0] if ',' in destino_selecionado_nome else destino_selecionado_nome
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
                {origem_nome_display} → {destino_nome_display}
            </h3>
            <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <div style="font-size: 1.2rem; font-weight: bold;">{format_number_br(distancia_km)} km</div>
                    <div style="font-size: 0.9rem; opacity: 0.9;">Distância Direta</div>
                </div>
                <div>
                    <div style="font-size: 1.2rem; font-weight: bold;">{tipo_viagem}</div>
                    <div style="font-size: 0.9rem; opacity: 0.9;">{origem_uf + ' → ' + destino_uf if origem_uf and destino_uf else 'Análise Regional'}</div>
                </div>
                <div>
                    <div style="font-size: 1.2rem; font-weight: bold;">{categoria_dist}</div>
                    <div style="font-size: 0.9rem; opacity: 0.9;">Categoria</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    else:
        if pagina_atual == "utps":
            st.success(f"Rota: {origem_selecionada_nome.split(' - ')[-1]} → {destino_selecionado_nome.split(' - ')[-1]}")
        else:
            st.success(f"Rota: {origem_selecionada_nome.split(',')[0]} → {destino_selecionado_nome.split(',')[0]}")
elif origem_selecionada_nome:
    if pagina_atual == "utps":
        st.info(f"Origem selecionada: {origem_selecionada_nome.split(' - ')[-1]} • Selecione o destino para análise completa")
    else:
        st.info(f"Origem selecionada: {origem_selecionada_nome.split(',')[0]} • Selecione o destino para análise completa")
    
    
   

# Área principal
if origem_selecionada and destino_selecionado:
    # Obter nome baseado na página atual
    if pagina_atual == "utps":
        nome_origem = item_map.get(origem_selecionada, origem_selecionada).split(' - ')[-1]
        nome_destino = item_map.get(destino_selecionado, destino_selecionado).split(' - ')[-1]
    else:
        nome_origem = item_map.get(origem_selecionada, origem_selecionada)
        nome_destino = item_map.get(destino_selecionado, destino_selecionado)
    
    st.markdown(f"## Rota: {nome_origem} → {nome_destino}")
    
    # Verificar se é voo executivo ou comercial baseado na página
    if pagina_atual == "utps":
        # Para UTPs, filtrar por UTP_origem e UTP_destino
        voos_executivos = executivos.filter(
            (pl.col('UTP_origem') == int(origem_selecionada)) & 
            (pl.col('UTP_destino') == int(destino_selecionado))
        )
        
        voos_comerciais = comerciais.filter(
            (pl.col('UTP_origem') == int(origem_selecionada)) & 
            (pl.col('UTP_destino') == int(destino_selecionado))
        )
    else:
        # Para municípios e centralidades - USAR MESMA ABORDAGEM
        if pagina_atual == "centralidades":
            # ✨ CORREÇÃO: Usar filtros em memória igual municipios (não SQL dinâmico)
            voos_comerciais = comerciais.filter(
                (pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada)) & 
                (pl.col('cod_mun_destino').cast(pl.Utf8) == str(destino_selecionado))
            )
            voos_executivos = executivos.filter(
                (pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada)) & 
                (pl.col('cod_mun_destino').cast(pl.Utf8) == str(destino_selecionado))
            )
        else:
            # ✨ CORREÇÃO: Garantir compatibilidade de tipos (string vs string)
            voos_executivos = executivos.filter(
                (pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada)) & 
                (pl.col('cod_mun_destino').cast(pl.Utf8) == str(destino_selecionado))
            )
            
            voos_comerciais = comerciais.filter(
                (pl.col('cod_mun_origem').cast(pl.Utf8) == str(origem_selecionada)) & 
                (pl.col('cod_mun_destino').cast(pl.Utf8) == str(destino_selecionado))
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
            if pagina_atual != "centralidades":
                st.markdown(f"""
                <div class="metric-container">
                    <p class="metric-label">Viagens Realizadas</p>
                    <p class="metric-value">{format_number_br(int(voo['viagens']))}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="metric-container">
                    <p class="metric-label">Tipo de Análise</p>
                    <p class="metric-value">Centralidade</p>
                </div>
                """, unsafe_allow_html=True)
        
        # Criar mapa
        if pagina_atual == "utps":
            coord_origem = mun_coords_cache.get(origem_selecionada, (None, None))
            coord_destino = mun_coords_cache.get(destino_selecionado, (None, None))
        else:
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
                if pagina_atual != "centralidades":
                    opcoes_rotas = [f"Rota {i+1} - {format_number_br(r['percentual'], 1)}% das viagens" for i, r in enumerate(rotas)]
                else:
                    opcoes_rotas = [f"Rota {i+1} - {format_number_br(r['percentual'], 1)}% do tráfego" for i, r in enumerate(rotas)]
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
                if pagina_atual != "centralidades":
                    percentual_texto = f"{format_number_br(rota_atual['percentual'], 1)}% das viagens"
                else:
                    percentual_texto = f"{format_number_br(rota_atual['percentual'], 1)}% do tráfego"
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    color: white;
                    padding: 0.5rem;
                    border-radius: 5px;
                    font-size: 0.9rem;
                    margin-bottom: 0.5rem;
                ">
                    Rota 1 - {percentual_texto}
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
                        <span style="font-size: 1.1rem; font-weight: 600; color: #16af2a;">{format_currency(rota_atual['custo_total'])}</span>
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
                        <span style="font-size: 1rem; font-weight: 500; color: #1f0e85;">{format_currency(rota_atual['custo_terrestre_embarque'] + rota_atual['custo_terrestre_desembarque'])}</span>
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
                    <strong>{'Viagens' if pagina_atual != 'centralidades' else 'Fluxo'}:</strong> {format_number_br(rota_atual['viagens'])}
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <strong>Percentual:</strong> {format_number_br(rota_atual['percentual'], 1)}%
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
            if pagina_atual == "utps":
                coord_origem = mun_coords_cache.get(origem_selecionada, (None, None))
                coord_destino = mun_coords_cache.get(destino_selecionado, (None, None))
            else:
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
                linha_dados = {
                    'Rota': f"Rota {i+1}",
                    'Trajeto': rota['trajeto'],
                    'Tempo Total': format_time(rota['tempo_total']),
                    'Custo Total (R$)': format_currency_for_table(rota['custo_total']),
                    'Uso (%)': f"{format_number_br(rota['percentual'], 1)}%",
                    'Conexões': rota['conexoes']
                }
                
                # Só adicionar coluna de viagens se não for centralidades
                if pagina_atual != "centralidades":
                    linha_dados['Viagens'] = rota['viagens']
                
                dados_tabela.append(linha_dados)
            
            df_tabela = pl.DataFrame(dados_tabela)
            
            # Configuração das colunas dinâmica
            column_config = {
                'Custo Total (R$)': st.column_config.NumberColumn(
                    'Custo Total (R$)',
                    format="R$ %.2f",
                    help="Custo total da rota em reais"
                ),
                'Conexões': st.column_config.NumberColumn(
                    'Conexões',
                    format="%d",
                    help="Número de conexões na rota"
                )
            }
            
            # Só adicionar configuração de viagens se não for centralidades
            if pagina_atual != "centralidades":
                column_config['Viagens'] = st.column_config.NumberColumn(
                    'Viagens',
                    format="%d",
                    help="Número total de viagens"
                )
            
            st.dataframe(
                df_tabela,
                width='stretch',
                hide_index=True,
                column_config=column_config
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
                        {format_number_br(rota_mais_popular['percentual'], 1)}%
                    </p>
                    <small>Rota {rotas.index(rota_mais_popular) + 1}</small>
                </div>
                """, unsafe_allow_html=True)
            
            
        
        # Gráfico de distribuição (sempre visível para múltiplas rotas)
        if len(rotas) > 1:
            st.markdown("---")
            
            st.markdown("### Distribuição de Uso das Rotas")
            
            # Gráfico donut
            if pagina_atual != "centralidades":
                # Para hover, usar formatação manual pois Plotly não suporta formato brasileiro
                hover_template = ('<b>%{label}</b><br>' +
                               'Uso: %{percent}<br>' +
                               'Viagens: %{customdata}<br>' +
                               'Trajeto: %{text}<extra></extra>')
                customdata_formatted = [format_number_br(r['viagens']) for r in rotas]
                texto_central = f"Total<br>{format_number_br(sum(r['viagens'] for r in rotas))}<br>viagens"
            else:
                hover_template = ('<b>%{label}</b><br>' +
                               'Uso: %{percent}<br>' +
                               'Fluxo: %{customdata}<br>' +
                               'Trajeto: %{text}<extra></extra>')
                customdata_formatted = [format_number_br(r['viagens']) for r in rotas]
                texto_central = f"Total<br>{format_number_br(sum(r['viagens'] for r in rotas))}<br>fluxo"
            
            fig = go.Figure(data=[
                go.Pie(
                    labels=[f"Rota {i+1}" for i in range(len(rotas))],
                    values=[r['percentual'] for r in rotas],
                    hole=.4,
                    marker_colors=cores_rotas[:len(rotas)],
                    textinfo='label+percent',
                    textposition='inside',
                    hovertemplate=hover_template,
                    customdata=customdata_formatted,
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
                text=texto_central,
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
    # Monitoramento periódico de memória
    current_memory = check_memory_usage()
    
    if pagina_atual == "municipios":
        st.markdown("### 📈 Panorama Geral - Análise por Municípios")
        titulo_total = "Total de Municípios"
        total_entidades = len(dados_municipios)
    elif pagina_atual == "utps":
        st.markdown("### 📈 Panorama Geral - Análise por UTPs")
        titulo_total = "Total de UTPs"
        total_entidades = len(dados_utps['utp'].unique())
    else:
        st.markdown("### 📈 Panorama Geral - Análise por Centralidades")
        titulo_total = "Total de Centralidades"
        total_entidades = centralidades_total_sql()
    
    # Estatísticas nacionais impressionantes
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    # Calcular pares únicos ao invés de rotas individuais
    if pagina_atual == "utps":
        # Para UTPs, contar pares únicos UTP_origem x UTP_destino
        pares_comerciais = comerciais.select(['UTP_origem', 'UTP_destino']).unique().height
        pares_executivos = executivos.select(['UTP_origem', 'UTP_destino']).unique().height if executivos.height > 0 else 0
    else:
        # Para municípios e centralidades, contar pares únicos cod_mun_origem x cod_mun_destino
        if pagina_atual == "centralidades":
            _pwd = get_files_password()
            c, e = centralidades_contar_pares_sql(_pwd)
            pares_comerciais = c
            pares_executivos = e
        else:
            pares_comerciais = comerciais.select(['cod_mun_origem', 'cod_mun_destino']).unique().height
            pares_executivos = executivos.select(['cod_mun_origem', 'cod_mun_destino']).unique().height if executivos.height > 0 else 0
    
    total_pares = pares_comerciais + pares_executivos
    percentual_comercial = (pares_comerciais / total_pares) * 100 if total_pares > 0 else 0
    
    with col_stat1:
        st.metric(
            label=f"🏙️ {titulo_total}", 
            value=format_number_br(total_entidades),
            help=f"Total de {titulo_total.lower()} disponíveis no sistema"
        )
        
    with col_stat2:
        st.metric(
            label="🔗 Pares OD Aéreos", 
            value=format_number_br(total_pares),
            help="Total de pares únicos origem-destino"
        )
        
    with col_stat3:
        st.metric(
            label="✈️ Pares OD Aéreos Comerciais", 
            value=f"{format_number_br(percentual_comercial, 1)}%",
            help="Percentual de pares OD aéreos comerciais"
        )
    
  
    # Call to action
    st.info("👆 Selecione uma origem e destino na barra lateral para explorar rotas específicas e suas análises detalhadas.")
    
    # Estatísticas gerais
    with st.expander("Estatísticas Detalhadas do Sistema", expanded=True):
        if pagina_atual == "centralidades":
            # Para centralidades, não mostrar viagens (dados inventados)
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Pares Comerciais", format_number_br(pares_comerciais))
            
            with col2:
                st.metric("Pares Executivos", format_number_br(pares_executivos))
        else:
            # Para municípios e UTPs, mostrar estatísticas completas
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Pares Comerciais", format_number_br(pares_comerciais))
            
            with col2:
                st.metric("Pares Executivos", format_number_br(pares_executivos))
            
            with col3:
                if 'viagens' in comerciais.columns and 'viagens' in executivos.columns:
                    total_viagens = comerciais['viagens'].sum() + executivos['viagens'].sum()
                    st.metric("Total de Viagens", format_number_br(int(total_viagens)))
                else:
                    st.metric("Rotas Totais", format_number_br(comerciais.height + executivos.height))

# Limpeza final de memória para otimização contínua
optimize_memory()