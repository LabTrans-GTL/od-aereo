import os
import base64
import hashlib
import tempfile
import duckdb

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _read_secrets():
    secrets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.streamlit', 'secrets.toml')
    data = {}
    if os.path.exists(secrets_path):
        try:
            try:
                import tomllib  # py311+
                with open(secrets_path, 'rb') as f:
                    data = tomllib.load(f)
            except Exception:
                import tomli
                with open(secrets_path, 'rb') as f:
                    data = tomli.load(f)
        except Exception:
            data = {}
    # fallback envs
    data.setdefault('FILES_PASSWORD', os.getenv('FILES_PASSWORD'))
    data.setdefault('CRYPTO_SALT_PRIMARY', os.getenv('CRYPTO_SALT_PRIMARY', ''))
    data.setdefault('CRYPTO_SALT_SECONDARY', os.getenv('CRYPTO_SALT_SECONDARY', ''))
    data.setdefault('CRYPTO_PEPPER', os.getenv('CRYPTO_PEPPER', ''))
    data.setdefault('SYSTEM_ENTROPY_FACTOR', os.getenv('SYSTEM_ENTROPY_FACTOR', ''))
    data.setdefault('INTEGRITY_CHECK_KEY', os.getenv('INTEGRITY_CHECK_KEY', ''))
    return data


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


def _encrypt_bytes(data: bytes, password: str, config: dict) -> bytes:
    key = _derive_multilayer_key(password, config)
    fernet = Fernet(key)
    try:
        import gzip
        compressed = gzip.compress(data)
    except Exception:
        compressed = data
    return fernet.encrypt(compressed)


def _create_duckdb_and_import_all_data(temp_db_path: str) -> None:
    con = duckdb.connect(temp_db_path)
    try:
        dados_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Dados')

        # CSVs
        csv_mun_utps = os.path.join(dados_base, 'Entrada', 'mun_UTPs.csv')
        if os.path.exists(csv_mun_utps):
            con.execute("DROP TABLE IF EXISTS mun_utps")
            con.execute("CREATE TABLE mun_utps AS SELECT * FROM read_csv_auto(?, header=true)", [csv_mun_utps])

        csv_centralidades = os.path.join(dados_base, 'Entrada', 'centralidades.csv')
        if os.path.exists(csv_centralidades):
            con.execute("DROP TABLE IF EXISTS centralidades")
            con.execute("CREATE TABLE centralidades AS SELECT * FROM read_csv_auto(?, header=true)", [csv_centralidades])

        # Parquet aeroportos
        pq_aeroportos = os.path.join(dados_base, 'Entrada', 'aeroportos.parquet')
        if os.path.exists(pq_aeroportos):
            con.execute("DROP TABLE IF EXISTS aeroportos")
            con.execute("CREATE TABLE aeroportos AS SELECT * FROM read_parquet(?)", [pq_aeroportos])

        # Resultados parquet
        mapas = [
            (
                os.path.join(dados_base, 'Resultados', 'Pares OD - Por Municipio - Matriz Infra S.A. - 2019'),
                {
                    'Voos Comerciais.parquet': 'por_municipio_voos_comerciais',
                    'Voos Executivos.parquet': 'por_municipio_voos_executivos',
                    'classificacao_pares.parquet': 'por_municipio_classificacao',
                },
            ),
            (
                os.path.join(dados_base, 'Resultados', 'Pares OD - Agregação UTP - Matriz Infra S.A. - 2019'),
                {
                    'Voos Comerciais.parquet': 'utp_voos_comerciais',
                    'Voos Executivos.parquet': 'utp_voos_executivos',
                    'classificacao_pares.parquet': 'utp_classificacao',
                },
            ),
            (
                os.path.join(dados_base, 'Resultados', 'Pares OD - Municipio x Centralidade'),
                {
                    'Voos Comerciais.parquet': 'mun_centralidade_voos_comerciais',
                    'Voos Executivos.parquet': 'mun_centralidade_voos_executivos',
                    'classificacao_pares.parquet': 'mun_centralidade_classificacao',
                },
            ),
        ]

        for pasta, nomes in mapas:
            for arquivo, tabela in nomes.items():
                caminho = os.path.join(pasta, arquivo)
                if os.path.exists(caminho):
                    con.execute(f"DROP TABLE IF EXISTS {tabela}")
                    con.execute(f"CREATE TABLE {tabela} AS SELECT * FROM read_parquet(?)", [caminho])

        con.commit()
    finally:
        con.close()


def build_encrypted_db():
    secrets = _read_secrets()
    password = secrets.get('FILES_PASSWORD')
    if not password:
        raise RuntimeError('FILES_PASSWORD ausente em secrets.toml ou variáveis de ambiente')

    enc_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Dados')
    os.makedirs(enc_dir, exist_ok=True)
    enc_path = os.path.join(enc_dir, 'od_aereo.duckdb.enc')

    with tempfile.TemporaryDirectory() as td:
        tmp_db = os.path.join(td, 'od_aereo.duckdb')
        _create_duckdb_and_import_all_data(tmp_db)
        with open(tmp_db, 'rb') as f:
            plain = f.read()
    enc = _encrypt_bytes(plain, password, secrets)
    with open(enc_path, 'wb') as f:
        f.write(enc)
    print(f'DB criptografado gerado em: {enc_path}')


if __name__ == '__main__':
    build_encrypted_db()


