"""Benchmark OLTP CockroachDB: full scan, indice compuesto y costo de escritura."""
from __future__ import annotations
import csv, os, statistics, time
from pathlib import Path
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

ROOT=Path(__file__).resolve().parents[2]
GOLD=ROOT/"lakehouse"/"gold"/"fact_ventas_boletas.parquet"
OUT=ROOT/"docs"/"taller4"
PLANS=OUT/"planes"
DB_URL=os.getenv("DB_URL","postgresql://root@localhost:26257/tuboleta?sslmode=disable")
N_ROWS=int(os.getenv("OLTP_BENCH_ROWS","1000000"))
N_INSERT=int(os.getenv("OLTP_INSERT_ROWS","20000"))
BATCH=5000
INDEX="idx_fact_ventas_tiempo_evento"
OBSERVACIONES=[]
INSERT_SQL="""INSERT INTO fact_ventas_boletas
(compra_id,tiempo_sk,evento_sk,zona_sk,silla_sk,usuario_sk,canal_sk,precio_pagado,cantidad)
VALUES %s"""

def load_source():
    if not GOLD.exists(): raise FileNotFoundError("Ejecuta python main.py primero.")
    df=pd.read_parquet(GOLD)
    cols=["compra_id","tiempo_sk","evento_sk","zona_sk","silla_sk","usuario_sk","canal_sk","precio_pagado","cantidad"]
    missing=sorted(set(cols)-set(df.columns))
    if missing: raise ValueError(f"Columnas ausentes en Gold: {missing}")
    if df.empty: raise ValueError("Gold no contiene ventas.")
    return df[cols]

def batches(base,n,prefix):
    rng=np.random.default_rng(42)
    for start in range(0,n,BATCH):
        stop=min(start+BATCH,n); ids=np.arange(start,stop,dtype=np.int64)
        b=base.iloc[rng.integers(0,len(base),size=len(ids))]
        event=(ids//45000+1).astype(np.int32); seat=(ids%45000+1).astype(np.int32)
        yield [(f"{prefix}-{i:012d}",int(t),int(e),int(z),int(s),int(u),int(c),float(p),int(q))
               for i,t,e,z,s,u,c,p,q in zip(ids,b.tiempo_sk,event,b.zona_sk,seat,b.usuario_sk,b.canal_sk,b.precio_pagado,b.cantidad)]

def load_fact(base):
    started=time.perf_counter()
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE fact_ventas_boletas")
            cur.execute(f"DROP INDEX IF EXISTS {INDEX}")
            for rows in batches(base,N_ROWS,"BENCH"):
                execute_values(cur,INSERT_SQL,rows,page_size=BATCH)
                conn.commit()
    return (time.perf_counter()-started)*1000

def capture_plan(sql,filename):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("EXPLAIN ANALYZE "+sql)
            rows=cur.fetchall()
    plan="\n".join(" | ".join(str(v) for v in row) for row in rows)
    PLANS.mkdir(parents=True,exist_ok=True); (PLANS/filename).write_text(plan+"\n",encoding="utf-8")
    return plan

def median_query(sql,label):
    values=[]
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql); cur.fetchall()
            for _ in range(7):
                started=time.perf_counter(); cur.execute(sql); cur.fetchall()
                values.append((time.perf_counter()-started)*1000)
    OBSERVACIONES.extend((label,i,v) for i,v in enumerate(values,1))
    return statistics.median(values)

def write_batches(n):
    rng=np.random.default_rng(7)
    for start in range(0,n,BATCH):
        ids=np.arange(start,min(start+BATCH,n)); times=rng.integers(2026010100,2026123123,size=len(ids))
        yield [(f"WRITE-{i:010d}",int(t),1000+int(i//45000),1,int(i%45000+1),1,1,125000.0,1) for i,t in zip(ids,times)]

def measure_insert(indexed):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE fact_ventas_insert_bench")
            cur.execute("DROP INDEX IF EXISTS idx_insert_bench_tiempo_evento")
            if indexed: cur.execute("CREATE INDEX idx_insert_bench_tiempo_evento ON fact_ventas_insert_bench (tiempo_sk,evento_sk)")
        started=time.perf_counter()
        with conn.cursor() as cur:
            sql=INSERT_SQL.replace("fact_ventas_boletas","fact_ventas_insert_bench")
            for rows in write_batches(N_INSERT): execute_values(cur,sql,rows,page_size=BATCH)
        conn.commit()
    return (time.perf_counter()-started)*1000

def ensure_database():
    # DB_URL apunta a tuboleta; crearla desde defaultdb antes de abrir conexiones de trabajo.
    admin_url=DB_URL.replace("/tuboleta?", "/defaultdb?").replace("/tuboleta","/defaultdb")
    conn=psycopg2.connect(admin_url)
    conn.autocommit=True
    try:
        with conn.cursor() as cur: cur.execute("CREATE DATABASE IF NOT EXISTS tuboleta")
    finally:
        conn.close()

def main():
    ensure_database()
    print(f"Preparando {N_ROWS:,} filas experimentales...")
    base=load_source()
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS fact_ventas_boletas (
                compra_id STRING PRIMARY KEY, tiempo_sk INT8 NOT NULL, evento_sk INT4 NOT NULL,
                zona_sk INT4 NOT NULL, silla_sk INT4 NOT NULL, usuario_sk INT4 NOT NULL,
                canal_sk INT4 NOT NULL, precio_pagado DECIMAL(14,2) NOT NULL, cantidad INT4 NOT NULL DEFAULT 1,
                CONSTRAINT uq_evento_silla UNIQUE(evento_sk,silla_sk))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS fact_ventas_insert_bench (
                compra_id STRING PRIMARY KEY, tiempo_sk INT8 NOT NULL, evento_sk INT4 NOT NULL,
                zona_sk INT4 NOT NULL, silla_sk INT4 NOT NULL, usuario_sk INT4 NOT NULL,
                canal_sk INT4 NOT NULL, precio_pagado DECIMAL(14,2) NOT NULL, cantidad INT4 NOT NULL DEFAULT 1)""")
    load_ms=load_fact(base)
    query="""SELECT evento_sk,COUNT(*) AS boletas,SUM(precio_pagado) AS ingresos
             FROM fact_ventas_boletas WHERE tiempo_sk BETWEEN 2026090100 AND 2026093023 GROUP BY evento_sk"""
    plan_before=capture_plan(query,"cockroach_Q1_antes_full_scan.txt")
    before=median_query(query,"lectura_sin_indice")
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE INDEX {INDEX} ON fact_ventas_boletas (tiempo_sk,evento_sk) STORING (precio_pagado)")
    indexed=query.replace("FROM fact_ventas_boletas",f"FROM fact_ventas_boletas@{{FORCE_INDEX={INDEX}}}")
    plan_after=capture_plan(indexed,"cockroach_Q1_despues_index_scan.txt")
    after=median_query(indexed,"lectura_con_indice")
    insert_without_values=[measure_insert(False) for _ in range(3)]
    insert_with_values=[measure_insert(True) for _ in range(3)]
    OBSERVACIONES.extend(("insert_sin_indice",i,v) for i,v in enumerate(insert_without_values,1))
    OBSERVACIONES.extend(("insert_con_indice",i,v) for i,v in enumerate(insert_with_values,1))
    insert_without=statistics.median(insert_without_values)
    insert_with=statistics.median(insert_with_values)
    factor=insert_with/insert_without if insert_without else float("nan")
    OUT.mkdir(parents=True,exist_ok=True)
    report=["# Benchmark OLTP — CockroachDB","",f"- Filas experimentales: **{N_ROWS:,}**",
      f"- Carga inicial sin índice secundario: **{load_ms:.2f} ms**",
      "- Lectura: rango temporal de septiembre de 2026; calentamiento y mediana de 7 corridas.",
      f"- Escritura: mediana de 3 lotes de {N_INSERT:,} filas en tabla aislada.",
      "- Filas expandidas sintéticas y reproducibles; no representan ventas reales ni alteran Gold.","",
      "| Medición | Sin índice | Con índice compuesto |","|---|---:|---:|",
      f"| Consulta (ms) | {before:.3f} | {after:.3f} |",
      f"| Inserción ({N_INSERT:,} filas, ms) | {insert_without:.2f} | {insert_with:.2f} |",
      f"| Costo relativo de escritura | 1.00x | {factor:.2f}x |","",
      f"Factor lectura: **{before/after:.2f}x**. Interpretar con planes, filas procesadas, caché y configuración local.","",
      "## Evidencia","- planes/cockroach_Q1_antes_full_scan.txt","- planes/cockroach_Q1_despues_index_scan.txt","",
      "## Plan antes",plan_before[:4500],"## Plan después",plan_after[:4500]]
    (OUT/"benchmarks_cockroach.md").write_text("\n".join(report),encoding="utf-8")
    with (OUT/"mediciones_crudas_cockroach.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["medicion","repeticion","tiempo_ms"]); w.writerows(OBSERVACIONES)
    with (OUT/"estadisticas_cockroach.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["medicion","n","mediana_ms","min_ms","max_ms","desviacion_estandar_muestral_ms"])
        for label in sorted({x[0] for x in OBSERVACIONES}):
            vals=[v for name,_,v in OBSERVACIONES if name==label]
            w.writerow([label,len(vals),f"{statistics.median(vals):.4f}",f"{min(vals):.4f}",f"{max(vals):.4f}",f"{statistics.stdev(vals):.4f}"])
    print("\n".join(report[:18]))

if __name__=="__main__": main()
