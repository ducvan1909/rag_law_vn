import os
from pathlib import Path

from dotenv import load_dotenv
from peewee import MySQLDatabase


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def getenv_int(name, default):
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc


db = MySQLDatabase(
    database=os.getenv("DB_NAME", "law_db"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    host=os.getenv("DB_HOST", "localhost"),
    port=getenv_int("DB_PORT", 2402),
)
