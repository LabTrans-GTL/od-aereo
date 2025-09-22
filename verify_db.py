#!/usr/bin/env python3
# Teste rápido do banco DuckDB regenerado

import os
import tempfile
import duckdb
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import base64
import hashlib

def _decode_b64_value(value: str) -> bytes:
    if isinstance(value, str) and value.startswith('b64:'):
        return base64.b64decode(value[4:])
    return (value or '').encode()

def _generate_fixed_entropy(config: dict) -> bytes:
    entropy_components = [
        config.get('SYSTEM_ENTROPY_FACTOR', ''),
        config.get('CRYPTO_SALT_PRIMARY', ''),
        config.get('CRYPTO_SALT_SECONDARY', ''),
        'od_aero_fixed_entropy_2024',
    ]
    combined = '_'.join(entropy_components)
    return hashlib.sha256(combined.encode()).digest()

def _derive_multilayer_key(password: str, config: dict) -> bytes:
    if not password:
        raise RuntimeError('FILES_PASSWORD não definido')

    salt_primary = _decode_b64_value(config.get('CRYPTO_SALT_PRIMARY', ''))
    salt_secondary = _decode_b64_value(config.get('CRYPTO_SALT_SECONDARY', ''))
    pepper = _decode_b64_value(config.get('CRYPTO_PEPPER', ''))
    integrity_key = _decode_b64_value(config.get('INTEGRITY_CHECK_KEY', ''))

    fixed_entropy = _generate_fixed_entropy(config)
    enhanced_password = f"{password}_{config.get('SYSTEM_ENTROPY_FACTOR','')}"

    kdf1 = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=64,
        salt=salt_primary + fixed_entropy[:16],
        iterations=200000,
    )
    intermediate_key1 = kdf1.derive(enhanced_password.encode())

    kdf2 = Scrypt(
        length=32,
        salt=salt_secondary + pepper[:16],
        n=2**14,
        r=8,
        p=1,
    )
    intermediate_key2 = kdf2.derive(intermediate_key1[:32])

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=integrity_key + fixed_entropy[16:],
        info=b"od_aero_final_key_derivation_2024",
    )
    final_key = hkdf.derive(intermediate_key2 + pepper)
    return base64.urlsafe_b64encode(final_key)

print("🔍 Verificando novo banco DuckDB...")

# Configuração básica para teste
config = {
    'FILES_PASSWORD': 'teste123',  # senha padrão do exemplo
    'CRYPTO_SALT_PRIMARY': '',
    'CRYPTO_SALT_SECONDARY': '',
    'CRYPTO_PEPPER': '',
    'SYSTEM_ENTROPY_FACTOR': '',
    'INTEGRITY_CHECK_KEY': ''
}

try:
    # Ler arquivo criptografado
    enc_path = 'Dados/od_aereo.duckdb.enc'
    with open(enc_path, 'rb') as f:
        enc_data = f.read()
    
    print(f"✓ Arquivo encontrado: {len(enc_data):,} bytes")
    
    # Descriptografar
    key = _derive_multilayer_key(config['FILES_PASSWORD'], config)
    fernet = Fernet(key)
    
    # Tentar descriptografar
    try:
        import gzip
        decrypted_compressed = fernet.decrypt(enc_data)
        plain_data = gzip.decompress(decrypted_compressed)
    except:
        # Fallback se não estiver comprimido
        plain_data = fernet.decrypt(enc_data)
    
    print(f"✓ Descriptografia bem-sucedida: {len(plain_data):,} bytes")
    
    # Criar arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb') as tmp_file:
        tmp_file.write(plain_data)
        tmp_db_path = tmp_file.name
    
    # Conectar ao DuckDB
    con = duckdb.connect(tmp_db_path)
    
    # Testar tabelas
    print("\n📊 Testando tabelas...")
    
    tables = con.execute("SHOW TABLES").fetchall()
    print(f"✓ Tabelas encontradas: {len(tables)}")
    
    # Testar tabela de centralidades
    try:
        count_comerciais = con.execute("SELECT COUNT(*) FROM mun_centralidade_voos_comerciais").fetchone()[0]
        count_executivos = con.execute("SELECT COUNT(*) FROM mun_centralidade_voos_executivos").fetchone()[0]
        count_classificacao = con.execute("SELECT COUNT(*) FROM mun_centralidade_classificacao").fetchone()[0]
        
        print(f"✓ Voos comerciais: {count_comerciais:,} registros")
        print(f"✓ Voos executivos: {count_executivos:,} registros")
        print(f"✓ Classificação: {count_classificacao:,} registros")
        
        # Testar query de exemplo
        sample_origem = con.execute("SELECT DISTINCT SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) AS cod FROM mun_centralidade_voos_comerciais LIMIT 1").fetchone()[0]
        sample_destino = con.execute("SELECT DISTINCT SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) AS cod FROM mun_centralidade_voos_comerciais WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ? LIMIT 1", [sample_origem]).fetchone()[0]
        
        route_count = con.execute("SELECT COUNT(*) FROM mun_centralidade_voos_comerciais WHERE SUBSTR(CAST(cod_mun_origem AS VARCHAR),1,6) = ? AND SUBSTR(CAST(cod_mun_destino AS VARCHAR),1,6) = ?", [sample_origem, sample_destino]).fetchone()[0]
        
        print(f"✓ Teste de rota {sample_origem} → {sample_destino}: {route_count} voos encontrados")
        
        if route_count > 0:
            print("\n🎉 SUCESSO: Banco DuckDB funcionando perfeitamente!")
            print("   As rotas podem ser encontradas corretamente!")
        else:
            print("\n⚠️ AVISO: Não encontrou rotas para o par testado")
            
    except Exception as e:
        print(f"❌ Erro ao testar queries: {e}")
    
    con.close()
    os.unlink(tmp_db_path)  # Limpar arquivo temporário
    
except Exception as e:
    print(f"❌ Erro ao verificar banco: {e}")
    print("   Verifique se a senha está correta ou se o arquivo está corrompido")
