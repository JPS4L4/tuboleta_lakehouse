# TuBoleta Mini-Lakehouse

Mini-Lakehouse **Bronze / Silver / Gold** (Parquet + DuckDB) para analizar la venta de boletería de TuBoleta en el Estadio Atanasio Girardot (Medellín). Talleres 3 y 4 de Tópicos Avanzados en Bases de Datos, ITM (Taller 3: pipeline y modelo; Taller 4: optimización de consultas, ver sección 12).

Con un solo comando (`python main.py`) el pipeline genera los datos, los limpia, los modela en estrella, ejecuta nueve consultas de negocio y mide un benchmark OLTP vs columnar.

## Alcance: qué es real y qué es simulado

Este proyecto entrega la **capa analítica (OLAP)** de TuBoleta. El sistema operacional se representa con CockroachDB para las ventas transaccionales. El modo sintético sigue disponible para reproducir el pipeline sin infraestructura. El laboratorio OLTP de CockroachDB y el benchmark de índice se documentan en [oltp/README.md](oltp/README.md); las mediciones se generan al ejecutar el experimento y no se simulan.

| Componente | En producción | En este proyecto |
|---|---|---|
| Redis | Fila virtual y locks con TTL (estado efímero) | No se ejecuta; su efecto aparece como TTL y abandonos en el generador |
| CockroachDB | Fuente de verdad (`UNIQUE(evento, silla)` bajo `SERIALIZABLE`) | Snapshot sintético reproducible cargable en CockroachDB con `python -m scripts.oltp.load_cockroach`; extracción disponible con `USE_SYNTHETIC=false` |
| Parquet + DuckDB | Capa analítica y de consulta | Se ejecuta de verdad: Bronze, Silver, Gold, consultas y Taller 4 |

DuckDB **no reemplaza** a CockroachDB: es el motor de la capa analítica, que se alimenta del sistema operacional. Guía completa del proyecto en [`docs/guia_proyecto.pdf`](docs/guia_proyecto.pdf).

## 1. Dominio y proceso analizado

TuBoleta vende boletería masiva. Su sistema operacional combina:

- **Redis (AP):** fila virtual, locks temporales de silla con TTL (600 s) y contadores. Es estado **efímero**.
- **CockroachDB (CP):** fuente de verdad. Guarda las compras confirmadas y evita el *double-booking* con `UNIQUE(evento, silla)` bajo `SERIALIZABLE`.

Flujo de una compra: entrar a la fila, ser admitido, bloquear una silla (lock con TTL), pagar a tiempo (`INSERT` en CockroachDB) o dejar vencer el TTL (abandono, la silla se libera). Si otro usuario ya compró la silla, el `UNIQUE` rechaza el `INSERT`.

**Procesos analizados** (detalle en [`docs/diseno_dimensional.md`](docs/diseno_dimensional.md)):

1. **Ventas:** cuántas boletas y cuánto dinero se vendió por evento, zona, canal y período. Una fila = una silla vendida y pagada.
2. **Embudo de compra:** cómo terminan los intentos de compra (compra, abandono o rechazo `UNIQUE`). Una fila = un intento.

## 2. Arquitectura

```
 OLTP (CockroachDB + Redis)         datos sintéticos (por defecto)
            |                                  |
            +----------------+-----------------+
                             v
                  BRONZE  lakehouse/bronze   Parquet crudo y sucio, versionado por extracción
                             |  scripts/transform_silver.py  (limpieza técnica)
                             v
                  SILVER  lakehouse/silver   Parquet limpio y tipado
                             |  scripts/transform_gold.py    (modelo en estrella + SCD2)
                             v
                  GOLD    lakehouse/gold     2 hechos + 6 dimensiones
                             |  DuckDB (read_parquet)
                             v
                  scripts/analyze.py         9 consultas + benchmark -> docs/
```

![Modelo dimensional en estrella](docs/modelo_dimensional.png)

El modelo fuente está en [`docs/modelo_dimensional.dbml`](docs/modelo_dimensional.dbml) (se puede abrir en [dbdiagram.io](https://dbdiagram.io)); la imagen se generó a partir de ese mismo DBML.

```
DIM_TIEMPO --+                    +-- DIM_CANAL
DIM_EVENTO --+--> FACT_VENTAS_BOLETAS <--+-- DIM_USUARIO
DIM_ZONA ----+    FACT_INTENTOS_COMPRA   +-- DIM_SILLA
 (SCD Tipo 2)       (dimensiones conformadas)
```

## 3. Decisiones de diseño

### Dos tablas de hechos: los abandonos no son ventas

| Tabla | Una fila = | Para qué sirve |
|---|---|---|
| `fact_ventas_boletas` | una silla vendida y **pagada** en un evento | ingresos, boletas, ticket promedio, ocupación. Tiene `UNIQUE(evento, silla)`: el pipeline verifica que no hay *double-booking*. |
| `fact_intentos_compra` | un intento de compra (lock de una silla) con resultado `COMPRA`, `ABANDONO` o `RECHAZO_UNIQUE` | embudo y tasa de conversión. Cada venta enlaza con exactamente un intento `COMPRA`. |

Un pago hecho en el último 20 % del TTL (`es_pago_tardio`) **sigue siendo una venta válida**. Lo que se persiste en el sistema operacional (resultado del intento) sí es un hecho; la posición en la fila o los locks vivos de Redis **no**.

### SCD Tipo 2 en `dim_zona`

Los datos incluyen un cambio real de precio el **2026-07-01** (VIP: 250.000 a 280.000 COP; Occidental: 150.000 a 165.000 COP). `dim_zona` conserva ambas versiones (`valido_desde`, `valido_hasta`, `activo`) y cada hecho recibe el `zona_sk` de la versión vigente en su fecha (`fecha BETWEEN valido_desde AND valido_hasta`). El pipeline verifica que cada fila resolvió exactamente una versión y que `precio_pagado + descuento = precio_base` de esa versión. Los análisis por zona agrupan por `zona_id`, nunca por versión.

### Suciedad intencional en Bronze

Bronze es el dato crudo. Para que Silver tenga trabajo real, el generador sintético imita los problemas típicos de un volcado operacional:

| Problema inyectado | Dónde | Por qué | Qué hace Silver |
|---|---|---|---|
| Filas duplicadas (~1 %) | compras, intentos, usuarios | reintentos del extractor | deduplica por clave de negocio |
| IDs con espacios sobrantes (~1,5 %) | compras, intentos, usuarios | texto capturado sin normalizar | `strip` antes de comparar |
| Fechas como texto | compras, intentos | el volcado no conserva el tipo | convierte a fecha-hora |
| `canal_id` nulo (~1,5 %) | compras, intentos | canal no registrado | lo reemplaza por `DESCONOCIDO` |
| 40 filas sin clave de negocio | compras, intentos | registros corruptos | las descarta |

El detalle de cada ejecución queda en [`docs/reporte_calidad_silver.txt`](docs/reporte_calidad_silver.txt).

**Las rutas de ejecución no deben confundirse.** En modo sintético directo (`USE_SYNTHETIC=true`), Bronze contiene duplicados, filas sin clave y NULL de `canal_id`; Silver demuestra su limpieza e imputación. En modo CockroachDB (`USE_SYNTHETIC=false`), la extracción refleja lo almacenado. Una corrida anterior no tenía NULL, pero la repetición verificada de las 23:19 conservó 3.101 NULL de compras y 3.906 de intentos en CockroachDB y Bronze; Silver los imputó como `DESCONOCIDO`. La base contiene el snapshot sintético del laboratorio, no ventas reales. Los conteos y corridas se separan en [docs/taller4/ejecuciones_pipeline.md](docs/taller4/ejecuciones_pipeline.md).

## 4. Requisitos

- Python 3.10 o superior para el pipeline del Taller 3 (probado con 3.12).
- `requirements.txt` fija las versiones con las que se midió el Taller 4 (Python 3.14, DuckDB 2.0.0). Para reproducir esos números use Python 3.14; con otras versiones el pipeline funciona, pero los tiempos y el formato de los planes pueden variar.
- Paquetes: `duckdb`, `pandas`, `pyarrow`, `numpy`, `sqlalchemy`, `psycopg2-binary` (ver `requirements.txt`).
- **No necesita CockroachDB:** por defecto genera datos sintéticos deterministas (semilla fija: mismos datos en cada ejecución).

## 5. Cómo ejecutar

```bash
git clone https://github.com/JPS4L4/tuboleta_lakehouse.git
cd tuboleta_lakehouse
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

`main.py` corre extracción, Silver, Gold y análisis; imprime el tiempo de cada paso y termina con código 1 si alguno falla. Las corridas medidas tardaron alrededor de 10 segundos en este entorno. Los Parquet no se versionan: se regeneran en cada ejecución. Cada paso también se puede correr solo, por ejemplo `python -m scripts.transform_silver`.

Variables de entorno (opcionales):

| Variable | Por defecto | Efecto |
|---|---|---|
| `USE_SYNTHETIC` | `true` | `false` extrae de CockroachDB en lugar de generar datos |
| `DB_URL` | `postgresql://root@localhost:26257/tuboleta?sslmode=disable` | conexión SQLAlchemy usada si `USE_SYNTHETIC=false` |

El laboratorio define las siete tablas operacionales requeridas por la extracción y un snapshot sintético se carga con `scripts/oltp/load_cockroach.py`. La ruta CockroachDB se verificó con `USE_SYNTHETIC=false`. El benchmark de índice trabaja sobre una tabla OLTP experimental separada. Las mediciones y sus límites están documentados en [docs/taller4/benchmarks_cockroach.md](docs/taller4/benchmarks_cockroach.md) y [docs/taller4/intervencion_tipos.md](docs/taller4/intervencion_tipos.md).

## 6. Consultas en vivo (exposición)

`scripts/consultar.py` abre DuckDB en memoria sobre los Parquet de Gold (requiere haber ejecutado antes `python main.py`) e imprime el resultado y el tiempo en milisegundos.

```bash
python -m scripts.consultar --lista        # consultas listas: ocupacion, embudo, vip, canales
python -m scripts.consultar ocupacion      # ocupación e ingresos por evento y zona
python -m scripts.consultar embudo         # embudo de conversión por evento
python -m scripts.consultar vip            # SCD2: ingresos VIP por versión de precio
python -m scripts.consultar "SELECT e.nombre_evento, COUNT(*) AS boletas FROM fact_ventas_boletas f JOIN dim_evento e USING (evento_sk) GROUP BY 1 ORDER BY 2 DESC"
```

Las tablas disponibles son las de Gold: `fact_ventas_boletas`, `fact_intentos_compra`, `dim_tiempo`, `dim_evento`, `dim_zona`, `dim_silla`, `dim_usuario` y `dim_canal`.

## 7. Estructura

```
tuboleta_lakehouse/
├── main.py                       # orquestador: extract -> silver -> gold -> analyze
├── requirements.txt
├── lakehouse/
│   ├── bronze/                   # Parquet crudo (no versionado)
│   ├── silver/                   # Parquet limpio (no versionado)
│   └── gold/                     # estrella: hechos y dimensiones (no versionado)
├── scripts/
│   ├── config.py                 # rutas, variables de entorno, semilla, TTL, volúmenes
│   ├── generate_synthetic.py     # datos sintéticos del dominio
│   ├── extract.py                # OLTP / sintético -> Bronze
│   ├── transform_silver.py       # Bronze -> Silver + reporte de calidad
│   ├── transform_gold.py         # Silver -> Gold (estrella, SCD2)
│   ├── analyze.py                # consultas de negocio (DuckDB)
│   ├── consultar.py              # consultas en vivo sobre Gold (exposición)
│   ├── benchmark.py              # OLTP vs columnar
│   ├── taller4_optimizacion.py   # Taller 4: ordenamiento y particionado Hive
│   ├── taller4_complementario.py # Taller 4: controles (paralelismo, Hive, ANALYZE), mediana de 15
│   └── taller4_pdf.py            # Taller 4: renderiza el informe a PDF (requiere Edge o Chrome)
├── docker-compose.yml             # Nodo local CockroachDB
├── oltp/                           # Esquema y guía del motor transaccional
└── docs/
    ├── diseno_dimensional.md     # las 5 preguntas, SCD2, limitaciones
    ├── modelo_dimensional.dbml   # modelo para dbdiagram.io
    ├── modelo_dimensional.png    # diagrama en estrella
    ├── reporte_calidad_silver.txt
    ├── resultados_consultas.md
    ├── benchmark.md
    ├── informe_final.md          # informe final (fuente versionada)
    ├── informe_final.pdf         # informe final renderizado
    ├── guia_proyecto.pdf         # guía: qué es, cómo instalarlo, estado y propuesta de diapositivas
    ├── entregables_tuboleta_lakehouse.zip  # paquete de entregables (Talleres 3 y 4)
    └── taller4/
        ├── diagnostico_baseline.md   # diagnóstico de Q1, Q2 y Q3
        ├── intervenciones.md         # fichas de I-3, I-6 e I-2
        ├── benchmarks.md             # tabla consolidada de benchmarks
        ├── analisis_complementario.md
        ├── informe_taller4.md / .pdf # informe técnico
        └── planes/                   # EXPLAIN ANALYZE completos (antes y después) y perfiles por operador
```

## 8. Volúmenes de la última ejecución

| Tabla | Filas |
|---|---:|
| Ventas confirmadas (`fact_ventas_boletas`) | 208.236 |
| Intentos de compra (`fact_intentos_compra`) | 260.294 (+25 % sobre las ventas) |
| Sillas / usuarios | 45.000 / 150.000 |
| Eventos / versiones de zona | 5 / 6 |
| `dim_tiempo` (granularidad de hora) | 5.656 |

## 9. Benchmark

Agregación: boletas e ingresos por **evento x zona x mes** (60 grupos), con 208.236 ventas. No se mide la carga; se hace un calentamiento y se toma la mediana de 5 corridas. Los tres motores devuelven exactamente las mismas cifras (el pipeline lo verifica con una aserción). Detalle y condiciones en [`docs/benchmark.md`](docs/benchmark.md).

| Motor | Fuente | Mediana (ms) | Mejora vs (a) |
|---|---|---:|---:|
| (a) SQLite, almacén por filas (OLTP-like) | Silver normalizado + índices típicos | 444,01 | 1,0x |
| (b) DuckDB sobre Bronze crudo | Parquet sucio, limpieza dentro de la consulta | 169,22 | 2,6x |
| (c) DuckDB sobre Gold (estrella) | Parquet columnar modelado | 16,97 | 26,2x |

**Análisis.** DuckDB sobre Gold fue unas 26 veces más rápido que el almacén por filas, y parte de la ventaja aparece al leer Parquet columnar sin modelar (2,6x en Bronze); el modelado en estrella aporta otro factor de 10 sobre Bronze, porque evita limpiar al vuelo y trabaja con claves enteras y dimensiones pequeñas. La comparación no es perfectamente "manzanas con manzanas": DuckDB usa varios hilos y SQLite solo uno; SQLite corre en memoria con índices pensados para buscar filas, no para recorrer 208.000 ventas. Los tiempos dependen de la máquina y de la corrida. Las cifras de arriba son las de `docs/benchmark.md`, ejecutadas el 16-11-2026 23:20.

## 10. Resultados destacados

Salidas completas en [`docs/resultados_consultas.md`](docs/resultados_consultas.md).

- **Ingresos:** 22.126 millones de COP con 208.236 boletas. El canal app vende 44 %, web 39 %, taquilla 15 % y 1,5 % no tiene canal registrado.
- **Ocupación:** entre 85,8 % y 100 %; el Clásico Paisa agotó VIP y Occidental.
- **Embudo:** de cada 100 intentos, cerca de 80 terminan en compra, 14 en abandono y 6 en rechazo `UNIQUE`; alrededor del 8 % de las ventas se paga en el último tramo del TTL. (Estas tasas salen de los parámetros del generador, no son datos reales.)
- **SCD2 (VIP):** con el precio de 250.000 COP se vendieron 5.834 boletas (1.412 millones de COP) y con el de 280.000 COP, 8.041 (2.187 millones de COP); sin SCD2 esa diferencia de precio se perdería.
- **Horarios:** tarde y noche concentran cerca del 70 % de las ventas; el primer día de venta de cada evento concentra alrededor del 10 %.
- **Abandono:** los abandonos suman 3.868 millones de COP de precio de lista (cota superior del ingreso potencial perdido).

## 11. Limitaciones

- El pipeline analítico puede ejecutarse en modo sintético; el laboratorio OLTP incorpora CockroachDB local en Docker.
- Los datos son sintéticos y las tasas (conversión, descuentos, pago tardío) son parámetros del generador.
- Cada ejecución reconstruye Silver y Gold (carga completa, sin incrementales).
- `dim_usuario` es Tipo 1; historizarla (Tipo 2) queda como mejora.
- Las mediciones OLTP están ejecutadas en un CockroachDB local de un solo nodo y sobre filas experimentales sintéticas; no representan una instalación distribuida ni rendimiento de producción.
- El estado de Redis (fila, locks vivos) no se analiza: no es un hecho persistido.

Evolución futura (CDC con Kafka, cargas incrementales, SCD2 en usuarios): ver [`docs/diseno_dimensional.md`](docs/diseno_dimensional.md).

## 13. Entrega final del proyecto

- [Informe final](docs/informe_final.md)
- [M4 — optimización y rendimiento](docs/entrega_final/M4_optimizacion_rendimiento.md)
- [Consultas SQL completas y resultados de referencia](docs/entrega_final/consultas_sql_resultados.md)
- [Estadística M4 reproducible: comandos y CSV](docs/entrega_final/estadistica_m4_reproducible.md)
- [Matriz de evidencia y reproducibilidad](docs/taller4/estado_evidencia.md)


## Entrega final (plantilla ITM)

- [Complemento documental: implementación, metodología, lecciones y trazabilidad](docs/entrega_final/complemento_documental.md)
- [Matriz de cumplimiento y pendientes locales](docs/entrega_final/matriz_cumplimiento.md)
- [Diagrama general de arquitectura](docs/entrega_final/arquitectura_general.svg)
- [Informe principal](docs/informe_final.md)
