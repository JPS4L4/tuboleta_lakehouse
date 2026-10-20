# Resultados de las consultas analíticas

Generado por `scripts/analyze.py` (2026-10-20 11:08) sobre el esquema en estrella de Gold.

## 1. Ingresos y boletas por evento y mes

*¿Cómo se reparten las ventas de cada evento a lo largo de los meses de su ventana de venta?*

| nombre_evento | anio | mes | mes_nombre | boletas | ingresos |
|---|---|---|---|---|---|
| Concierto Noche Latina | 2026 | 2 | febrero | 12.007 | 1.210.903.000 |
| Concierto Noche Latina | 2026 | 3 | marzo | 13.193 | 1.358.401.000 |
| Concierto Noche Latina | 2026 | 4 | abril | 14.220 | 1.460.951.000 |
| Clásico Paisa Nacional vs Medellín | 2026 | 5 | mayo | 15.149 | 1.555.757.000 |
| Clásico Paisa Nacional vs Medellín | 2026 | 6 | junio | 15.188 | 1.579.414.500 |
| Clásico Paisa Nacional vs Medellín | 2026 | 7 | julio | 13.288 | 1.470.511.900 |
| Festival Sonidos del Valle | 2026 | 6 | junio | 18.063 | 1.850.558.000 |
| Festival Sonidos del Valle | 2026 | 7 | julio | 14.108 | 1.546.309.700 |
| Festival Sonidos del Valle | 2026 | 8 | agosto | 10.284 | 1.130.216.500 |
| Gira Urbana Medellín | 2026 | 7 | julio | 15.466 | 1.666.940.100 |
| Gira Urbana Medellín | 2026 | 8 | agosto | 12.689 | 1.386.978.000 |
| Gira Urbana Medellín | 2026 | 9 | septiembre | 11.914 | 1.286.744.700 |
| Final del Fútbol Colombiano | 2026 | 8 | agosto | 4.296 | 463.376.500 |
| Final del Fútbol Colombiano | 2026 | 9 | septiembre | 22.125 | 2.402.970.800 |
| Final del Fútbol Colombiano | 2026 | 10 | octubre | 16.246 | 1.756.091.100 |

## 2. Ocupación e ingresos por evento y zona

*¿Qué porcentaje de la capacidad de cada zona se vendió en cada evento y cuánto dinero generó?*

| nombre_evento | nombre_zona | capacidad_zona | vendidas | ocupacion_pct | ingresos |
|---|---|---|---|---|---|
| Concierto Noche Latina | Occidental | 12.000 | 10.332 | 86,10 | 1.503.637.500 |
| Concierto Noche Latina | Norte | 14.000 | 12.387 | 88,48 | 1.080.391.500 |
| Concierto Noche Latina | General | 16.000 | 14.126 | 88,29 | 821.901.000 |
| Concierto Noche Latina | VIP | 3.000 | 2.575 | 85,83 | 624.325.000 |
| Clásico Paisa Nacional vs Medellín | Occidental | 12.000 | 12.000 | 100,00 | 1.798.896.900 |
| Clásico Paisa Nacional vs Medellín | Norte | 14.000 | 13.336 | 95,26 | 1.163.808.000 |
| Clásico Paisa Nacional vs Medellín | General | 16.000 | 15.289 | 95,56 | 888.825.000 |
| Clásico Paisa Nacional vs Medellín | VIP | 3.000 | 3.000 | 100,00 | 754.153.500 |
| Festival Sonidos del Valle | Occidental | 12.000 | 11.568 | 96,40 | 1.779.518.200 |
| Festival Sonidos del Valle | Norte | 14.000 | 13.209 | 94,35 | 1.152.144.000 |
| Festival Sonidos del Valle | General | 16.000 | 14.855 | 92,84 | 863.484.000 |
| Festival Sonidos del Valle | VIP | 3.000 | 2.823 | 94,10 | 731.938.000 |
| Gira Urbana Medellín | Occidental | 12.000 | 10.527 | 87,73 | 1.684.002.800 |
| Gira Urbana Medellín | Norte | 14.000 | 12.205 | 87,18 | 1.064.007.000 |
| Gira Urbana Medellín | General | 16.000 | 14.599 | 91,24 | 848.847.000 |
| Gira Urbana Medellín | VIP | 3.000 | 2.738 | 91,27 | 743.806.000 |
| Final del Fútbol Colombiano | Occidental | 12.000 | 11.489 | 95,74 | 1.835.284.900 |
| Final del Fútbol Colombiano | Norte | 14.000 | 13.377 | 95,55 | 1.166.809.500 |
| Final del Fútbol Colombiano | General | 16.000 | 15.062 | 94,14 | 876.048.000 |
| Final del Fútbol Colombiano | VIP | 3.000 | 2.739 | 91,30 | 744.296.000 |

## 3. Volumen, ingresos y ticket promedio por canal

*¿Qué canal vende más y cuánto paga en promedio quien compra por cada uno?*

| canal | boletas | boletas_pct | ingresos | ticket_promedio | descuento_promedio |
|---|---|---|---|---|---|
| app | 92.066 | 44,21 | 9.779.126.100 | 106.219 | 3.371 |
| web | 82.058 | 39,41 | 8.716.875.500 | 106.228 | 3.333 |
| taquilla | 31.011 | 14,89 | 3.301.901.100 | 106.475 | 3.378 |
| DESCONOCIDO | 3.101 | 1,49 | 328.221.100 | 105.844 | 3.442 |

## 4. Distribución por franja horaria y día de la semana

*¿A qué hora y en qué día compra la gente? Boletas por franja horaria, abiertas por día de la semana.*

| franja_horaria | boletas | pct | lunes | martes | miercoles | jueves | viernes | sabado | domingo |
|---|---|---|---|---|---|---|---|---|---|
| madrugada | 7.586 | 3,64 | 723 | 1.364 | 1.211 | 1.197 | 1.212 | 930 | 949 |
| mañana | 53.826 | 25,85 | 10.664 | 8.525 | 7.772 | 7.571 | 7.675 | 5.859 | 5.760 |
| tarde | 74.651 | 35,85 | 13.943 | 12.065 | 10.807 | 10.489 | 10.639 | 8.365 | 8.343 |
| noche | 72.173 | 34,66 | 13.605 | 11.415 | 10.625 | 10.173 | 10.351 | 8.123 | 7.881 |

## 5a. Embudo de conversión por evento

*De cada 100 intentos de compra (lock de silla), ¿cuántos terminan en compra, abandono o rechazo UNIQUE? ¿Qué porcentaje de las ventas se pagó en el último tramo del TTL?*

| evento | intentos | compras | abandonos | rechazos_unique | conversion_pct | abandono_pct | rechazo_unique_pct | pago_tardio_pct |
|---|---|---|---|---|---|---|---|---|
| Clásico Paisa Nacional vs Medellín | 54.577 | 43.625 | 7.468 | 3.484 | 79,93 | 13,68 | 6,38 | 7,73 |
| Festival Sonidos del Valle | 53.295 | 42.455 | 7.373 | 3.467 | 79,66 | 13,83 | 6,51 | 8,12 |
| Final del Fútbol Colombiano | 53.161 | 42.667 | 7.174 | 3.320 | 80,26 | 13,49 | 6,25 | 8,07 |
| Gira Urbana Medellín | 49.947 | 40.069 | 6.752 | 3.126 | 80,22 | 13,52 | 6,26 | 7,80 |
| Concierto Noche Latina | 49.314 | 39.420 | 6.633 | 3.261 | 79,94 | 13,45 | 6,61 | 8,19 |

## 5b. Embudo de conversión por canal

*Misma lectura del embudo, ahora por canal de venta.*

| canal | intentos | compras | abandonos | rechazos_unique | conversion_pct | abandono_pct | rechazo_unique_pct | pago_tardio_pct |
|---|---|---|---|---|---|---|---|---|
| app | 115.157 | 92.094 | 15.715 | 7.348 | 79,97 | 13,65 | 6,38 | 7,97 |
| web | 102.536 | 82.024 | 13.885 | 6.627 | 80,00 | 13,54 | 6,46 | 7,95 |
| taquilla | 38.695 | 30.991 | 5.241 | 2.463 | 80,09 | 13,54 | 6,37 | 8,11 |
| DESCONOCIDO | 3.906 | 3.127 | 559 | 220 | 80,06 | 14,31 | 5,63 | 7,80 |

## 6. SCD Tipo 2: ingresos VIP por versión de precio

*El 2026-07-01 sube el precio VIP. ¿Cómo cambian boletas, ingresos y descuentos entre las dos versiones?*

| zona_sk | nombre_zona | precio_base | valido_desde | valido_hasta | boletas | ingresos | ticket_promedio | descuento_promedio |
|---|---|---|---|---|---|---|---|---|
| 1 | VIP | 250.000 | 2026-01-01 | 2026-06-30 | 5.834 | 1.411.662.500 | 241.972 | 8.028 |
| 2 | VIP | 280.000 | 2026-07-01 | 9999-12-31 | 8.041 | 2.186.856.000 | 271.963 | 8.037 |

## 7. Tiempo hasta el pago por zona (promedio, mediana y p95)

*¿Cuánto tarda en pagar cada zona desde que bloquea la silla (TTL de 600 s)? ¿Cuántos pagan al límite?*

| nombre_zona | boletas | promedio_seg | mediana_seg | p95_seg | pago_tardio_pct |
|---|---|---|---|---|---|
| General | 73.931 | 212,90 | 177,00 | 526,00 | 8,12 |
| Occidental | 55.916 | 212,80 | 178,00 | 524,00 | 7,97 |
| VIP | 13.875 | 212,30 | 177,00 | 528,00 | 8,02 |
| Norte | 64.514 | 211,50 | 176,00 | 523,00 | 7,82 |

## 8. Ventas en el día de apertura

*¿Qué parte de las boletas de cada evento se vende el primer día y en los tres primeros días de venta?*

| nombre_evento | inicio_ventas | boletas | primer_dia | primer_dia_pct | tres_dias_pct | ingresos_primer_dia |
|---|---|---|---|---|---|---|
| Concierto Noche Latina | 2026-02-23 | 39.420 | 3.930 | 9,97 | 21,42 | 399.073.000 |
| Clásico Paisa Nacional vs Medellín | 2026-05-25 | 43.625 | 4.510 | 10,34 | 22,79 | 459.802.500 |
| Festival Sonidos del Valle | 2026-06-15 | 42.455 | 4.044 | 9,53 | 21,25 | 411.062.500 |
| Gira Urbana Medellín | 2026-07-20 | 40.069 | 3.992 | 9,96 | 21,81 | 425.890.900 |
| Final del Fútbol Colombiano | 2026-08-31 | 42.667 | 4.296 | 10,07 | 22,58 | 463.376.500 |

## 9. Ingreso potencial perdido por abandono, por zona

*Cada abandono libera una silla que pudo venderse. ¿Cuánto dinero de lista se asocia a esos abandonos? Es una cota superior: parte de esas sillas se vendió después a otro usuario.*

| nombre_zona | intentos | abandonos | abandono_pct | ingreso_potencial_perdido |
|---|---|---|---|---|
| Occidental | 69.816 | 9.406 | 13,47 | 1.494.180.000 |
| Norte | 80.596 | 11.048 | 13,71 | 994.320.000 |
| General | 92.557 | 12.617 | 13,63 | 757.020.000 |
| VIP | 17.325 | 2.329 | 13,44 | 622.660.000 |
