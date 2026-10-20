# TuBoleta Mini-Lakehouse

Mini-Lakehouse **Bronze / Silver / Gold** (Parquet + DuckDB) para analizar la venta de boletería de TuBoleta en el Estadio Atanasio Girardot (Medellín). Taller 3 de Tópicos Avanzados en Bases de Datos, ITM.

Con un solo comando (`python main.py`) el pipeline genera los datos, los limpia, los modela en estrella, ejecuta nueve consultas de negocio y mide un benchmark OLTP vs columnar.

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

El diagrama de la estrella está en [`docs/modelo_dimensional.dbml`](docs/modelo_dimensional.dbml). La imagen `docs/modelo_dimensional.png` **la renderiza el equipo** pegando ese DBML en [dbdiagram.io](https://dbdiagram.io) (aún no está incluida en el repositorio).

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

## 4. Requisitos

- Python 3.10 o superior (probado con 3.12).
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

`main.py` corre extracción, Silver, Gold y análisis; imprime el tiempo de cada paso y termina con código 1 si alguno falla. Tarda unos 8 segundos. Los Parquet no se versionan: se regeneran en cada ejecución. Cada paso también se puede correr solo, por ejemplo `python -m scripts.transform_silver`.

Variables de entorno (opcionales):

| Variable | Por defecto | Efecto |
|---|---|---|
| `USE_SYNTHETIC` | `true` | `false` extrae de CockroachDB en lugar de generar datos |
| `DB_URL` | `postgresql://root@localhost:26257/tuboleta?sslmode=disable` | conexión SQLAlchemy usada si `USE_SYNTHETIC=false` |

La rama de CockroachDB espera tablas con los mismos nombres y columnas que las de Bronze (`zonas`, `eventos`, `sillas`, `usuarios`, `canales`, `compras_confirmadas`, `intentos_compra`). No se probó contra un clúster real. Si la base no responde, el paso de extracción termina con un mensaje que sugiere el modo sintético.

## 6. Estructura

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
│   └── benchmark.py              # OLTP vs columnar
└── docs/
    ├── diseno_dimensional.md     # las 5 preguntas, SCD2, limitaciones
    ├── modelo_dimensional.dbml   # modelo para dbdiagram.io
    ├── reporte_calidad_silver.txt
    ├── resultados_consultas.md
    └── benchmark.md
```

## 7. Volúmenes de la última ejecución

| Tabla | Filas |
|---|---:|
| Ventas confirmadas (`fact_ventas_boletas`) | 208.236 |
| Intentos de compra (`fact_intentos_compra`) | 260.294 (+25 % sobre las ventas) |
| Sillas / usuarios | 45.000 / 150.000 |
| Eventos / versiones de zona | 5 / 6 |
| `dim_tiempo` (granularidad de hora) | 5.656 |

## 8. Benchmark

Agregación: boletas e ingresos por **evento x zona x mes** (60 grupos), con 208.236 ventas. No se mide la carga; se hace un calentamiento y se toma la mediana de 5 corridas. Los tres motores devuelven exactamente las mismas cifras (el pipeline lo verifica con una aserción). Detalle y condiciones en [`docs/benchmark.md`](docs/benchmark.md).

| Motor | Fuente | Mediana (ms) | Mejora vs (a) |
|---|---|---:|---:|
| (a) SQLite, almacén por filas (OLTP-like) | Silver normalizado + índices típicos | 368,89 | 1,0x |
| (b) DuckDB sobre Bronze crudo | Parquet sucio, limpieza dentro de la consulta | 67,14 | 5,5x |
| (c) DuckDB sobre Gold (estrella) | Parquet columnar modelado | 17,57 | 21,0x |

**Análisis.** DuckDB sobre Gold fue unas 21 veces más rápido que el almacén por filas, y buena parte de la ventaja ya aparece solo por leer Parquet columnar sin modelar (5,5x en Bronze); el modelado en estrella aporta otro factor de casi 4 sobre Bronze, porque evita limpiar al vuelo y trabaja con claves enteras y dimensiones pequeñas. La comparación no es perfectamente "manzanas con manzanas": DuckDB usa varios hilos (12 en esta máquina) y SQLite solo uno, y SQLite corre en memoria con índices pensados para buscar filas, no para recorrer 208.000 ventas. Además, con este volumen todas las consultas responden en menos de medio segundo; la diferencia se vuelve decisiva a millones de filas y no cambia el resultado de negocio. Los tiempos varían unos milisegundos entre ejecuciones.

## 9. Resultados destacados

Salidas completas en [`docs/resultados_consultas.md`](docs/resultados_consultas.md).

- **Ingresos:** 22.126 millones de COP con 208.236 boletas. El canal app vende 44 %, web 39 %, taquilla 15 % y 1,5 % no tiene canal registrado.
- **Ocupación:** entre 85,8 % y 100 %; el Clásico Paisa agotó VIP y Occidental.
- **Embudo:** de cada 100 intentos, cerca de 80 terminan en compra, 14 en abandono y 6 en rechazo `UNIQUE`; alrededor del 8 % de las ventas se paga en el último tramo del TTL. (Estas tasas salen de los parámetros del generador, no son datos reales.)
- **SCD2 (VIP):** con el precio de 250.000 COP se vendieron 5.834 boletas (1.412 millones de COP) y con el de 280.000 COP, 8.041 (2.187 millones de COP); sin SCD2 esa diferencia de precio se perdería.
- **Horarios:** tarde y noche concentran cerca del 70 % de las ventas; el primer día de venta de cada evento concentra alrededor del 10 %.
- **Abandono:** los abandonos suman 3.869 millones de COP de precio de lista (cota superior del ingreso potencial perdido).

## 10. Limitaciones

- Los datos son sintéticos y las tasas (conversión, descuentos, pago tardío) son parámetros del generador.
- Cada ejecución reconstruye Silver y Gold (carga completa, sin incrementales).
- `dim_usuario` es Tipo 1; historizarla (Tipo 2) queda como mejora.
- La rama de CockroachDB no se probó contra un clúster real.
- El estado de Redis (fila, locks vivos) no se analiza: no es un hecho persistido.

Evolución futura (CDC con Kafka, CockroachDB real, cargas incrementales, SCD2 en usuarios): ver [`docs/diseno_dimensional.md`](docs/diseno_dimensional.md).

## Integrantes

- Luis Manuel Contreras
- Juan Pablo Salazar

## Docente

Roberto Carlos Rahamut Suteu — ITM 2026
