# Estadística reproducible de M4

## Qué cambió

Los scripts de medición conservan ahora cada tiempo individual, además de seguir generando las medianas utilizadas en las tablas de benchmark. Los calentamientos no se incluyen en los CSV.

| Experimento | Comando | Archivos generados |
|---|---|---|
| Ordenamiento, Hive y control ANALYZE | `python -m scripts.taller4_optimizacion` | `docs/taller4/mediciones_crudas_duckdb.csv`, `estadisticas_duckdb.csv` |
| VARCHAR frente a TIMESTAMP | `python -m scripts.taller4_tipos` | `docs/taller4/mediciones_crudas_tipos.csv`, `estadisticas_tipos.csv` |
| Índice e inserciones CockroachDB | `python -m scripts.oltp.benchmark_cockroach` | `docs/taller4/mediciones_crudas_cockroach.csv`, `estadisticas_cockroach.csv` |

Cada archivo crudo contiene una fila por repetición. Los archivos de resumen incluyen n, mediana, mínimo, máximo y desviación estándar muestral (ddof=1). No combinar los grupos: cada técnica tiene un número de repeticiones distinto y los controles complementarios usan otro protocolo.

## Orden recomendado de ejecución en Windows PowerShell

Primero, desde la raíz del repositorio, activar el entorno Python que ya utiliza el proyecto e instalar dependencias si fuera necesario.

```powershell
# Generar Bronze, Silver y Gold funcionales si no están disponibles
python main.py

# Asegurar CockroachDB y cargar el snapshot sintético del laboratorio
docker compose up -d
python -m scripts.oltp.load_cockroach

# Ejecutar el laboratorio OLTP de índice (1 millón de filas por defecto)
python -m scripts.oltp.benchmark_cockroach

# Ejecutar las pruebas analíticas de ordenamiento y Hive
python -m scripts.taller4_optimizacion

# Ejecutar la comparación de tipo temporal
python -m scripts.taller4_tipos

# Ejecutar los controles complementarios (15 corridas)
python -m scripts.taller4_complementario
```

Si la base CockroachDB ya está cargada, no es necesario repetir la carga. El laboratorio de índice utiliza filas sintéticas de prueba con prefijo BENCH y una tabla aislada para inserciones. No representa ventas reales.

## Cómo incorporar los resultados al informe

1. Abrir los CSV `estadisticas_*.csv` generados en `docs/taller4/`.
2. Verificar que cada medición tenga el n esperado: cinco corridas en el laboratorio principal DuckDB, nueve en tipos, siete lecturas CockroachDB y tres lotes de inserción.
3. Copiar mediana, mínimo, máximo y desviación estándar en la tabla consolidada del informe, manteniendo las unidades en milisegundos.
4. Mantener separadas las mediciones de quince corridas del análisis complementario; su protocolo y propósito son distintos.
5. Guardar los CSV crudos junto con los planes para que la estadística sea auditable.

## Interpretación estadística

La desviación estándar reportada es muestral. Con cinco, siete o nueve observaciones es un indicador descriptivo de dispersión, no una estimación robusta del rendimiento de producción. Los tiempos dependen de caché, carga del equipo, versión del motor, sistema operativo y volumen de datos. Registrar el entorno y conservar las repeticiones es parte del resultado experimental.

**Estado tras la ejecución final (26-11-2026):** los seis CSV (`mediciones_crudas_*.csv` y `estadisticas_*.csv`) se generaron en `docs/taller4/` con los comandos de arriba y las cifras de los informes se actualizaron a esa corrida (Python 3.14.6, DuckDB 2.0.0, CockroachDB v25.4.0 de un solo nodo en Docker, Windows 11, AMD64; pipeline con `USE_SYNTHETIC=false`). Las medianas de corridas de desarrollo anteriores fueron distintas (por ejemplo, 2,08x en la lectura con índice y 3,98x en tipos) y ya no se reportan como resultado. Al repetir los experimentos, copiar siempre las cifras de los CSV recién generados; no completar la desviación estándar con valores inferidos.
