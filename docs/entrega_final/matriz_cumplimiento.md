# Matriz de cumplimiento — Entrega final

Esta matriz resume el estado verificable de la plantilla oficial. La etiqueta **pendiente local** indica una acción que requiere ejecutar o comprobar el proyecto en el equipo de entrega.

| Requisito de la plantilla | Estado | Evidencia / acción |
|---|---|---|
| Resumen ejecutivo | Cubierto | `docs/informe_final.md` |
| Contexto, dominio y cargas | Cubierto | `docs/entrega_final/M1_contexto_requisitos.md` |
| Requisitos no funcionales y CAP | Cubierto con alcance declarado | M1 e informe principal; no afirmar SLA productivo no medido |
| Diagrama general | Cubierto | `arquitectura_general.svg` |
| Persistencia políglota | Cubierto con limitación | CockroachDB implementado; DuckDB/Parquet analíticos; Redis conceptual, no desplegado |
| Bronze / Silver / Gold | Cubierto | Informe principal y pipeline |
| Integración entre capas | Cubierto con limitación | Batch manual; no CDC/streaming; latencia igual a duración de corrida |
| Estructura y ejecución | Cubierto | `complemento_documental.md`, README |
| Cinco consultas SQL completas | Cubierto documentalmente | `consultas_sql_resultados.md`; validar ejecución local antes de entrega |
| Benchmark OLTP vs OLAP | Parcial / aclarado | SQLite vs DuckDB es OLAP-like; no es CockroachDB vs DuckDB |
| Dashboard | No implementado / N.A. | Declarado explícitamente; sin capturas ni KPIs ficticios |
| Diagnóstico y planes M4 | Cubierto | `docs/taller4/planes/` y documento M4 |
| Mediana y comparaciones M4 | Cubierto históricamente | M4; conservar protocolos distintos por experimento |
| Min, max y desviación estándar | Pendiente local | Ejecutar scripts de `estadistica_m4_reproducible.md` y anexar CSV generados |
| Lecciones aprendidas | Cubierto | `complemento_documental.md` |
| Trazabilidad M1 → M4 | Cubierto | `complemento_documental.md` |
| Anexos | Cubierto con verificación final | Rutas listadas en complemento documental |
| `python main.py` sin errores | Pendiente local | Ejecutar desde entorno limpio y guardar salida |
| PDF final y límite de páginas | Pendiente local | Regenerar PDF desde informe consolidado y contar páginas |
| Acceso docente al repositorio | Pendiente de confirmar | Confirmar repositorio público o compartir acceso |

## Orden mínimo antes de entregar

1. Ejecutar `python main.py` en el equipo que se usará para la entrega.
2. Ejecutar los laboratorios de estadísticas M4 y guardar los CSV; no estimar desviaciones a partir de medianas.
3. Regenerar el PDF final desde el informe actualizado y verificar extensión de 20–30 páginas sin anexos.
4. Abrir el PDF, revisar diagramas, tablas, saltos de página y enlaces.
5. Confirmar que el docente tenga acceso al repositorio.
