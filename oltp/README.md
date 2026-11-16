# OLTP con CockroachDB

CockroachDB representa la fuente operacional del laboratorio. El pipeline extrae sus tablas hacia Bronze en Parquet; Silver limpia y tipa; Gold modela el esquema estrella; DuckDB consulta el lakehouse. CockroachDB no sustituye a DuckDB.

## Levantar el nodo local

Desde la raíz del repositorio:

~~~bash
docker compose up -d
docker compose ps
~~~

Consola web: http://localhost:8080

Conexión local: postgresql://root@localhost:26257/tuboleta?sslmode=disable

El modo --insecure es exclusivamente para laboratorio local, nunca para producción.

## Cargar el snapshot operacional

Instala dependencias con pip install -r requirements.txt y ejecuta:

~~~bash
python -m scripts.oltp.load_cockroach
~~~

El cargador genera un snapshot sintético determinista y aplica solo preparación estructural para satisfacer las restricciones OLTP: normaliza espacios de identificadores, descarta filas sin columnas obligatorias y elimina duplicados que violarían la PK o la restricción UNIQUE(evento_id, silla_id).

Importante: el cargador no llama a limpiar_tabla() ni ejecuta la limpieza de Silver. Los valores canal_id=NULL se insertan como SQL NULL en CockroachDB. De este modo, la extracción a Bronze conserva el dato ausente y Silver puede medirlo e imputarlo a DESCONOCIDO. No se debe reemplazar ese NULL en el cargador: hacerlo ocultaría el problema de calidad y produciría un contador de nulos resueltos igual a cero.

Para validar el flujo completo:

Windows PowerShell:
~~~powershell
$env:USE_SYNTHETIC = "false"
python main.py
~~~

Linux/macOS:
~~~bash
USE_SYNTHETIC=false python main.py
~~~

En docs/reporte_calidad_silver.txt, comprueba que compras_confirmadas e intentos_compra tengan nulos resueltos mayores que cero. Los conteos exactos pueden variar si cambia la semilla o la preparación de datos; lo importante es que Bronze conserve los NULL y Silver los impute.

## Benchmark del índice compuesto

Genera primero Gold con python main.py. Luego ejecuta:

~~~bash
python -m scripts.oltp.benchmark_cockroach
~~~

El benchmark OLTP genera por defecto un millón de filas reproducibles a partir de Gold. La expansión sintética asigna pares evento/silla únicos para respetar la regla de no doble venta. No representa ventas adicionales reales ni altera el dataset funcional. Cambia OLTP_BENCH_ROWS para probar 200000, 1000000 o 3000000.

El script carga fact_ventas_boletas sin índice secundario temporal, captura EXPLAIN ANALYZE, crea un índice compuesto (tiempo_sk, evento_sk), repite la consulta con index hint y mide inserciones con y sin índice en una tabla aislada. Los planes quedan en docs/taller4/planes y las métricas en docs/taller4/benchmarks_cockroach.md.

Las mediciones dependen del equipo, caché y configuración del nodo; no son resultados de producción.

## Reiniciar el laboratorio

docker compose down -v elimina el volumen y todos los datos del nodo. Después ejecuta docker compose up -d.
