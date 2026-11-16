"""Carga un snapshot operacional estructuralmente válido en CockroachDB.

No ejecuta limpieza Silver: conserva canal_id=NULL para que Bronze registre
el dato original y Silver lo impute con trazabilidad. Solo normaliza IDs y
aplica las restricciones estructurales indispensables para el esquema OLTP.
"""
from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from scripts import config, generate_synthetic

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "oltp" / "init" / "01_schema.sql"
BATCH = 5000

ID_COLUMNS = {
    "canales": ("canal_id",), "zonas": ("zona_id",), "eventos": ("evento_id",),
    "sillas": ("silla_id", "zona_id"), "usuarios": ("usuario_id",),
    "compras_confirmadas": ("compra_id", "silla_id", "evento_id", "usuario_id", "canal_id"),
    "intentos_compra": ("intento_id", "silla_id", "evento_id", "usuario_id", "canal_id", "compra_id"),
}
REQUIRED_COLUMNS = {
    "canales": ("canal_id", "nombre", "digital_flag"),
    "zonas": ("zona_id", "nombre_zona", "tipo_zona", "capacidad_zona", "precio_base", "valido_desde", "valido_hasta", "activo"),
    "eventos": ("evento_id", "nombre_evento", "tipo_evento", "recinto", "ciudad", "fecha_evento", "inicio_ventas", "aforo_total", "organizador"),
    "sillas": ("silla_id", "zona_id", "fila", "numero", "categoria"),
    "usuarios": ("usuario_id", "segmento", "canal_preferido"),
    "compras_confirmadas": ("compra_id", "silla_id", "evento_id", "usuario_id", "fecha_compra"),
    "intentos_compra": ("intento_id", "silla_id", "evento_id", "usuario_id", "fecha_intento", "resultado"),
}
PRIMARY_KEYS = {
    "canales": ("canal_id",), "zonas": ("zona_id", "valido_desde"),
    "eventos": ("evento_id",), "sillas": ("silla_id",), "usuarios": ("usuario_id",),
    "compras_confirmadas": ("compra_id",), "intentos_compra": ("intento_id",),
}


def ensure_database():
    admin = config.DB_URL.replace("/tuboleta?", "/defaultdb?").replace("/tuboleta", "/defaultdb")
    conn = psycopg2.connect(admin)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS tuboleta")
    finally:
        conn.close()


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def preparar_snapshot_oltp(tablas):
    """Normaliza estructura, pero nunca imputa los nulos de canal_id."""
    preparadas, resumen = {}, {}
    for nombre in config.TABLAS_OLTP:
        df = tablas[nombre].copy()
        original = len(df)
        for col in ID_COLUMNS[nombre]:
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

        df = df.dropna(subset=list(REQUIRED_COLUMNS[nombre]))
        sin_requeridos = original - len(df)

        antes_pk = len(df)
        df = df.drop_duplicates(subset=list(PRIMARY_KEYS[nombre]), keep="first")
        duplicados_pk = antes_pk - len(df)

        duplicados_unicos = 0
        if nombre == "compras_confirmadas":
            antes_unicos = len(df)
            df = df.drop_duplicates(subset=["evento_id", "silla_id"], keep="first")
            duplicados_unicos = antes_unicos - len(df)

        preparadas[nombre] = df.reset_index(drop=True)
        resumen[nombre] = {
            "entrada": original, "cargadas": len(df),
            "sin_requeridos": sin_requeridos, "duplicados_pk": duplicados_pk,
            "duplicados_evento_silla": duplicados_unicos,
            "canal_id_null": int(df["canal_id"].isna().sum()) if "canal_id" in df else 0,
        }
    return preparadas, resumen


def load_table(cur, name, df, conn):
    cols = list(df.columns)
    cur.execute(f"TRUNCATE TABLE {name}")
    conn.commit()
    sql = f"INSERT INTO {name} ({','.join(cols)}) VALUES %s"
    rows = (tuple(clean_value(v) for v in row) for row in df.itertuples(index=False, name=None))
    batch, total = [], 0
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            execute_values(cur, sql, batch, page_size=BATCH)
            total += len(batch)
            conn.commit()
            batch = []
    if batch:
        execute_values(cur, sql, batch, page_size=BATCH)
        total += len(batch)
        conn.commit()
    print(f"  {name}: {total:,} filas")


def main():
    ensure_database()
    tablas = generate_synthetic.generar()
    preparadas, resumen = preparar_snapshot_oltp(tablas)

    print("Preparación estructural (sin limpieza Silver ni imputación de canal):")
    for nombre, stats in resumen.items():
        print(
            f"  {nombre}: entrada={stats['entrada']:,}, cargadas={stats['cargadas']:,}, "
            f"sin requeridos={stats['sin_requeridos']:,}, duplicados PK={stats['duplicados_pk']:,}, "
            f"duplicados UNIQUE={stats['duplicados_evento_silla']:,}, "
            f"canal_id NULL={stats['canal_id_null']:,}"
        )

    with psycopg2.connect(config.DB_URL) as conn:
        with conn.cursor() as cur:
            ddl = SCHEMA.read_text(encoding="utf-8")
            for statement in ddl.split(";"):
                statement = "\n".join(
                    line for line in statement.splitlines()
                    if not line.strip().startswith("--")
                ).strip()
                if statement:
                    cur.execute(statement)
            conn.commit()
            for name in config.TABLAS_OLTP:
                load_table(cur, name, preparadas[name], conn)

    print("\nCockroachDB listo. canal_id NULL se conserva para que Silver lo resuelva.")
    print("  Windows PowerShell: $env:USE_SYNTHETIC='false'; python main.py")
    print("  Linux/macOS: USE_SYNTHETIC=false python main.py")


if __name__ == "__main__":
    main()
