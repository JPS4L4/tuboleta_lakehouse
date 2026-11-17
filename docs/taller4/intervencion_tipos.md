# Intervención de tipos — texto frente a TIMESTAMP

- Control: mismas filas Silver; fecha_compra se serializa como VARCHAR.
- Fuente: Parquet de Silver; el control serializa esa columna en una vista para aislar el efecto del tipo, no es una extracción de CockroachDB.
- Antes: fecha serializada como VARCHAR; la consulta convierte con CAST para comparar.
- Después: Silver conserva fecha_compra como TIMESTAMP; el predicado opera directamente sobre el tipo temporal.
- Método: calentamiento y mediana de 9 ejecuciones en la misma conexión DuckDB.
- Resultado validado en ambos escenarios: 34,039 ventas; ingresos 3,689,715,500.00 COP.

| Escenario | Mediana (ms) |
|---|---:|
| Control VARCHAR + CAST | 19.887 |
| Silver TIMESTAMP | 4.996 |
| Factor antes/después | 3.98x |

La conversión de tipo evita aplicar CAST fila por fila en la consulta y deja el dato tipado para filtros y operaciones temporales. El tiempo puede ser similar o incluso mayor por caché, costo de lectura, optimizaciones del motor y tamaño del conjunto; se reporta sin ocultar el resultado.

## Evidencia
- planes/Q3_tipos_antes_texto.txt
- planes/Q3_tipos_despues_timestamp.txt