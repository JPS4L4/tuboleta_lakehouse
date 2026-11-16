"""Carga las tablas OLTP de CockroachDB con un snapshot sintético limpio y reproducible.

Después de cargar, ejecutar USE_SYNTHETIC=false para que scripts.extract lea CockroachDB.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from scripts import config, generate_synthetic
from scripts.transform_silver import ESPECIFICACIONES, limpiar_tabla

ROOT=Path(__file__).resolve().parents[2]
SCHEMA=ROOT/"oltp"/"init"/"01_schema.sql"
BATCH=5000

def ensure_database():
    admin=config.DB_URL.replace("/tuboleta?","/defaultdb?").replace("/tuboleta","/defaultdb")
    conn=psycopg2.connect(admin)
    conn.autocommit=True
    try:
        with conn.cursor() as cur: cur.execute("CREATE DATABASE IF NOT EXISTS tuboleta")
    finally:
        conn.close()

def clean_value(value):
    if value is None: return None
    try:
        if pd.isna(value): return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value,"item") else value

def load_table(cur,name,df):
    cols=list(df.columns)
    cur.execute(f"TRUNCATE TABLE {name}")
    sql=f"INSERT INTO {name} ({','.join(cols)}) VALUES %s"
    rows=(tuple(clean_value(v) for v in row) for row in df.itertuples(index=False,name=None))
    batch=[]
    total=0
    for row in rows:
        batch.append(row)
        if len(batch)>=BATCH:
            execute_values(cur,sql,batch,page_size=BATCH); total+=len(batch); batch=[]
    if batch:
        execute_values(cur,sql,batch,page_size=BATCH); total+=len(batch)
    print(f"  {name}: {total:,} filas")

def main():
    ensure_database()
    tablas=generate_synthetic.generar()
    limpias={}
    for name,df in tablas.items():
        clean,_=limpiar_tabla(df,ESPECIFICACIONES[name])
        limpias[name]=clean
    with psycopg2.connect(config.DB_URL) as conn:
        with conn.cursor() as cur:
            ddl=SCHEMA.read_text(encoding="utf-8")
            for statement in ddl.split(";"):
                statement="\n".join(line for line in statement.splitlines()
                                    if not line.strip().startswith("--")).strip()
                if statement: cur.execute(statement)
            for name in config.TABLAS_OLTP:
                load_table(cur,name,limpias[name])
    print("\nCockroachDB listo. Para extraer desde OLTP:")
    print("  Windows PowerShell: $env:USE_SYNTHETIC='false'; python main.py")
    print("  Linux/macOS: USE_SYNTHETIC=false python main.py")

if __name__=="__main__": main()
