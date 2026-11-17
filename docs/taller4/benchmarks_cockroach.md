# Benchmark OLTP — CockroachDB

- Filas experimentales: **1,000,000**
- Motor verificado: **CockroachDB CCL v25.4.0**, nodo único en Docker.
- Carga inicial sin índice secundario: **28754.46 ms**
- Lectura: rango temporal de septiembre de 2026; calentamiento y mediana de 7 corridas.
- Escritura: mediana de 3 lotes de 20,000 filas en tabla aislada.
- Filas expandidas sintéticas y reproducibles; no representan ventas reales ni alteran Gold.
- Los tiempos `execution time` de los planes son capturas instrumentadas individuales; la tabla compara las medianas de consulta medidas por separado.

| Medición | Sin índice | Con índice compuesto |
|---|---:|---:|
| Consulta (ms) | 687.713 | 331.261 |
| Inserción (20,000 filas, ms) | 460.19 | 508.56 |
| Costo relativo de escritura | 1.00x | 1.11x |

Factor lectura: **2.08x**. Interpretar con planes, filas procesadas, caché y configuración local.

## Evidencia
- planes/cockroach_Q1_antes_full_scan.txt
- planes/cockroach_Q1_despues_index_scan.txt

## Plan antes
planning time: 499µs
execution time: 983ms
distribution: local
vectorized: true
plan type: custom
rows decoded from KV: 1,000,000 (73 MiB, 8 gRPC calls)
cumulative time spent in KV: 599ms
cumulative time spent due to contention: 11ms
cumulative time spent waiting to acquire latches: 11ms
maximum memory usage: 17 MiB
DistSQL network usage: 0 B (0 messages)
sql cpu time: 744ms
isolation level: serializable
priority: normal
quality of service: regular

• group (hash)
│ sql nodes: n1
│ actual row count: 23
│ execution time: 282ms
│ estimated max memory allocated: 7.1 MiB
│ estimated max sql temp disk usage: 0 B
│ sql cpu time: 282ms
│ estimated row count: 1
│ group by: evento_sk
│
└── • filter
    │ sql nodes: n1
    │ actual row count: 163,137
    │ execution time: 101ms
    │ sql cpu time: 100ms
    │ estimated row count: 1
    │ filter: (tiempo_sk >= 2026090100) AND (tiempo_sk <= 2026093023)
    │
    └── • scan
          sql nodes: n1
          kv nodes: n1
          actual row count: 1,000,000
          KV time: 599ms
          KV contention time: 11ms
          KV latch wait time: 11ms
          KV rows decoded: 1,000,000
          KV bytes read: 73 MiB
          KV gRPC calls: 8
          estimated max memory allocated: 10 MiB
          sql cpu time: 363ms
          estimated row count: 1 (100% of the table; stats collected 6 hours ago)
          table: fact_ventas_boletas@fact_ventas_boletas_pkey  ----------------------  WARNING: the row count estimate is inaccurate, consider running 'ANALYZE fact_ventas_boletas'
          spans: FULL SCAN

WARNING: the row count estimate on table "fact_ventas_boletas" is inaccurate, consider running 'ANALYZE fact_ventas_boletas'
## Plan después
planning time: 343µs
execution time: 404ms
distribution: local
vectorized: true
plan type: custom
rows decoded from KV: 163,137 (9.7 MiB, 1 gRPC calls)
cumulative time spent in KV: 108ms
maximum memory usage: 17 MiB
DistSQL network usage: 0 B (0 messages)
sql cpu time: 359ms
isolation level: serializable
priority: normal
quality of service: regular

• group (hash)
│ sql nodes: n1
│ actual row count: 23
│ execution time: 296ms
│ estimated max memory allocated: 7.1 MiB
│ estimated max sql temp disk usage: 0 B
│ sql cpu time: 292ms
│ estimated row count: 1
│ group by: evento_sk
│
└── • scan
      sql nodes: n1
      kv nodes: n1
      actual row count: 163,137
      KV time: 108ms
      KV rows decoded: 163,137
      KV bytes read: 9.7 MiB
      KV gRPC calls: 1
      estimated max memory allocated: 9.7 MiB
      sql cpu time: 67ms
      estimated row count: 1 (100% of the table; stats collected 6 hours ago)
      table: fact_ventas_boletas@idx_fact_ventas_tiempo_evento  ----------------------  WARNING: the row count estimate is inaccurate, consider running 'ANALYZE fact_ventas_boletas'
      spans: [/2026090100 - /2026093023]

WARNING: the row count estimate on table "fact_ventas_boletas" is inaccurate, consider running 'ANALYZE fact_ventas_boletas'