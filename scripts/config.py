"""Configuración central del Mini-Lakehouse TuBoleta.

Todas las rutas, variables de entorno y parámetros de volumen viven aquí
para que el resto de scripts no tengan valores "mágicos".
"""
import os
from pathlib import Path

# --- Rutas -------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
BRONZE = RAIZ / "lakehouse" / "bronze"
SILVER = RAIZ / "lakehouse" / "silver"
GOLD = RAIZ / "lakehouse" / "gold"
# Verdad de terreno del generador (perfil latente de cada usuario). No es parte del
# lakehouse: solo sirve para validar si los modelos recuperan la estructura simulada.
VALIDACION = RAIZ / "lakehouse" / "validacion"
DOCS = RAIZ / "docs"

# --- Fuente de datos (variables de entorno) ----------------------------
# Modo sintético por defecto: no requiere CockroachDB.
USE_SYNTHETIC = os.getenv("USE_SYNTHETIC", "true").strip().lower() in {"1", "true", "yes", "si"}
DB_URL = os.getenv("DB_URL", "postgresql://root@localhost:26257/tuboleta?sslmode=disable")

# --- Reproducibilidad --------------------------------------------------
SEED = 42  # misma semilla -> mismos datos en cada ejecución

# --- Reglas del flujo operacional --------------------------------------
TTL_LOCK_SEG = 600  # vida del lock de la silla en Redis (SET NX EX)
FRACCION_PAGO_TARDIO = 0.80  # pago en el último 20 % del TTL = pago tardío
UMBRAL_PAGO_TARDIO_SEG = int(TTL_LOCK_SEG * FRACCION_PAGO_TARDIO)

# --- Volúmenes de los datos sintéticos ---------------------------------
N_USUARIOS = 60_000  # ~3,5 compras por usuario: perfiles con historia suficiente para segmentar
TASA_ABANDONO = 0.17  # abandonos por cada venta confirmada
TASA_RECHAZO_UNIQUE = 0.08  # rechazos por UNIQUE por cada venta confirmada

# --- Tablas operacionales que viajan a Bronze --------------------------
TABLAS_OLTP = (
    "canales",
    "zonas",
    "eventos",
    "sillas",
    "usuarios",
    "compras_confirmadas",
    "intentos_compra",
)
