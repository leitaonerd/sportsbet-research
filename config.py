"""
Centraliza a configuração do banco de dados MySQL.

As credenciais sao lidas de variaveis de ambiente (arquivo `.env` opcional) 
para que o script rode em qualquer maquina sem codigo-fonte hardcoded.
Ex.::

    DB_HOST=localhost
    DB_PORT=3306
    DB_USER=sportsbet
    DB_PASSWORD=segredo
    DB_NAME=brasiliaodb
"""
from typing import Optional

from dotenv import load_dotenv
import os

# Carrega o arquivo .env (se existir) para o ambiente do processo.
load_dotenv()


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Le uma variavel do ambiente, retornando o default se ausente/vazia."""
    value = os.getenv(key)
    return value if value else default


# Credenciais MySQL. Todos configuraveis por variavel de ambiente.
DB_HOST: str = get_env("DB_HOST", "localhost") or "localhost"
DB_PORT: int = int(get_env("DB_PORT", "3306")) or 3306
# Usuario padrao do MySQL instalado localmente.
DB_USER: str = get_env("DB_USER", "root") or "root"
DB_PASSWORD: str = get_env("DB_PASSWORD", "") or ""
DB_NAME: str = get_env("DB_NAME", "brasiliaodb") or "brasiliaodb"


def connection_params(*, include_db: bool = True) -> dict:
    """Devolve os parametros de conexao padrao do mysql-connector-python.

    Se include_db for False, omite o banco (usado para o bootstrap que
    cria o banco de dados caso ainda nao exista).
    """
    params = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "charset": "utf8mb4",
        "use_unicode": True,
        "autocommit": False,
        "collation": "utf8mb4_unicode_ci",
    }
    if include_db:
        params["database"] = DB_NAME
    return params