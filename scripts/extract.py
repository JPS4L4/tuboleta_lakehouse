"""Paso 2: OLTP -> Bronze.

Bronze guarda los datos tal cual llegan de la fuente (sin limpiar ni modelar),
más dos columnas de trazabilidad: `_extraido_en` y `_fuente`. Cada tabla se
escribe como `{tabla}_{YYYYMMDD_HHMM}.parquet`, de modo que las extracciones
quedan versionadas y Silver toma siempre la más reciente.

Fuentes:
  * Modo sintético (por defecto, `USE_SYNTHETIC=true`): `generate_synthetic`.
  * CockroachDB (`USE_SYNTHETIC=false`): lee con SQLAlchemy desde `DB_URL`.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from scripts import config, generate_synthetic


def extraer_cockroachdb() -> dict[str, pd.DataFrame]:
    """Lee las tablas operacionales de CockroachDB con `SELECT *`."""
    try:
        motor = create_engine(config.DB_URL)
        with motor.connect() as conexion:
            return {t: pd.read_sql_query(f"SELECT * FROM {t}", conexion) for t in config.TABLAS_OLTP}
    except SQLAlchemyError as error:
        raise RuntimeError(
            "No se pudo leer CockroachDB con DB_URL. Verifica que la base esté arriba o usa el modo "
            f"sintético (USE_SYNTHETIC=true). Detalle: {type(error).__name__}"
        ) from error


def escribir_bronze(tablas: dict[str, pd.DataFrame], fuente: str) -> dict[str, int]:
    """Escribe cada tabla en Bronze con su marca de extracción y devuelve las filas por tabla."""
    ahora = datetime.now()
    sufijo = ahora.strftime("%Y%m%d_%H%M")
    config.BRONZE.mkdir(parents=True, exist_ok=True)
    filas = {}
    for nombre, df in tablas.items():
        df = df.assign(_extraido_en=pd.Timestamp(ahora), _fuente=fuente)
        df.to_parquet(config.BRONZE / f"{nombre}_{sufijo}.parquet", index=False)
        filas[nombre] = len(df)
        print(f"  bronze/{nombre}_{sufijo}.parquet: {len(df):,} filas")
    return filas


def ejecutar() -> dict[str, int]:
    """Extrae de la fuente configurada y escribe Bronze."""
    if config.USE_SYNTHETIC:
        print("Fuente: datos sintéticos (USE_SYNTHETIC=true)")
        return escribir_bronze(generate_synthetic.generar(), "sintetico")
    print("Fuente: CockroachDB (USE_SYNTHETIC=false)")
    return escribir_bronze(extraer_cockroachdb(), "cockroachdb")


if __name__ == "__main__":
    ejecutar()
