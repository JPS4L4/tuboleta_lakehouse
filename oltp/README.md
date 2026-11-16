# OLTP con CockroachDB

CockroachDB es la fuente OLTP de ventas confirmadas. El pipeline extrae sus datos hacia Bronze en Parquet; Silver limpia y tipa; Gold modela el esquema estrella; DuckDB consulta el lakehouse. CockroachDB no sustituye a DuckDB.

## Levantar el nodo local

Desde la raíz del repositorio:

```bash
docker compose up -d
docker compose ps
docker compose exec cockroach ./cockroach sql --insecure --host=localhost:26257 --file=/dev/stdin < oltp/init/01_schema.sql
```

Consola web: http://localhost:8080

Conexión local: postgresql://root@localhost:26257/tuboleta?sslmode=disable

El modo --insecure es exclusivamente para laboratorio local, nunca para producción.

## Ejecutar el experimento

1. Genera Gold: python main.py (o verifica que lakehouse/gold/fact_ventas_boletas.parquet exista).
2. Instala dependencias: pip install -r requirements.txt.
3. Ejecuta: python -m scripts.oltp.benchmark_cockroach

Por defecto se generan un millón de filas reproducibles a partir de Gold. La expansión sintética asigna pares evento/silla únicos para respetar la regla de no doble venta. No representa ventas adicionales reales ni altera el dataset funcional. Cambia OLTP_BENCH_ROWS para probar 200000, 1000000 o 3000000.

El script carga fact_ventas_boletas sin índice secundario temporal, captura EXPLAIN ANALYZE, crea un índice compuesto (tiempo_sk, evento_sk), repite la consulta con index hint y mide inserciones con y sin índice en una tabla aislada. Los planes quedan en docs/taller4/planes y las métricas en docs/taller4/benchmarks_cockroach.md.

Las mediciones dependen del equipo, caché y configuración del nodo; no son resultados de producción.

## Reiniciar el laboratorio

docker compose down -v elimina el volumen y todos los datos del nodo. Después ejecuta docker compose up -d.
