"""Carga .env ANTES de que los tests evaluen skipif(DATABASE_URL)."""
from dotenv import load_dotenv

load_dotenv()
