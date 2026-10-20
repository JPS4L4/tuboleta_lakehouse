"""Generador de datos sintéticos del dominio TuBoleta (Estadio Atanasio Girardot).

Simula lo que entregaría el sistema operacional (CockroachDB) cuando no hay una
base disponible. Es determinista: la misma semilla (`config.SEED`) produce los
mismos datos en cada ejecución.

Qué se genera:
  * 4 zonas con 45.000 sillas en total. VIP y Occidental suben de precio el
    2026-07-01 (dos versiones de zona, material para SCD Tipo 2).
  * 5 eventos repartidos en 2026, cada uno con varias semanas de venta.
    Dos de ellos tienen ventanas de venta que cruzan el 2026-07-01.
  * Ventas confirmadas (>= 200.000) sin silla repetida por evento.
  * Intentos de compra: cada venta tiene su intento COMPRA, más abandonos
    (TTL del lock vencido) y rechazos por UNIQUE (silla ya vendida).
  * "Suciedad" intencional en las tablas de ventas, intentos y usuarios para que
    Silver tenga trabajo real (ver `_ensuciar_transaccional`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import config

# --- Catálogos del dominio ---------------------------------------------
# (canal_id, nombre, digital_flag) y su peso en la preferencia de los usuarios.
CANALES = [("C-APP", "app", True), ("C-WEB", "web", True), ("C-TAQ", "taquilla", False)]
PESO_CANAL = np.array([0.45, 0.40, 0.15])

# Hora del día más probable de compra, por canal (24 pesos). Los canales
# digitales tienen pico nocturno; la taquilla solo atiende en horario de oficina.
PESO_HORA = [
    np.array([2, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 9, 10, 9, 8, 8, 8, 9, 11, 14, 15, 14, 10, 5], float),
    np.array([2, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 9, 10, 9, 8, 8, 8, 9, 11, 14, 15, 14, 10, 5], float),
    np.array([0] * 9 + [6, 9, 10, 7, 6, 9, 10, 9, 6] + [0] * 6, float),
]
HORA_APERTURA_VENTAS = 10  # el primer día las ventas abren a las 10:00

# segmento -> (probabilidad en la población, tasa de descuento, probabilidad de aplicarlo)
SEGMENTOS = {
    "general": (0.55, 0.00, 0.0),
    "frecuente": (0.15, 0.05, 0.7),
    "estudiante": (0.12, 0.10, 0.8),
    "corporativo": (0.08, 0.15, 0.5),
    "fan_club": (0.10, 0.10, 0.6),
}
DESCUENTO_PREVENTA = 0.10  # descuento de los primeros 3 días de venta
PROB_PREVENTA = 0.25

# zona_id, nombre, tipo, prefijo de fila, filas, sillas por fila, [(precio_base, desde, hasta)]
ZONAS = [
    ("Z-VIP", "VIP", "premium", "V", 30, 100,
     [(250_000, "2026-01-01", "2026-06-30"), (280_000, "2026-07-01", "9999-12-31")]),
    ("Z-OCC", "Occidental", "preferencial", "O", 60, 200,
     [(150_000, "2026-01-01", "2026-06-30"), (165_000, "2026-07-01", "9999-12-31")]),
    ("Z-NOR", "Norte", "popular", "N", 70, 200, [(90_000, "2026-01-01", "9999-12-31")]),
    ("Z-GEN", "General", "general", "G", 80, 200, [(60_000, "2026-01-01", "9999-12-31")]),
]

# evento_id, nombre, tipo, fecha del evento, inicio de ventas, ocupación objetivo, organizador
EVENTOS = [
    ("E-001", "Concierto Noche Latina", "concierto", "2026-04-18", "2026-02-23", 0.86, "TuBoleta Producciones"),
    ("E-002", "Clásico Paisa Nacional vs Medellín", "partido", "2026-07-11", "2026-05-25", 0.98, "Liga Profesional"),
    ("E-003", "Festival Sonidos del Valle", "concierto", "2026-08-08", "2026-06-15", 0.93, "Valle Live"),
    ("E-004", "Gira Urbana Medellín", "concierto", "2026-09-12", "2026-07-20", 0.90, "TuBoleta Producciones"),
    ("E-005", "Final del Fútbol Colombiano", "partido", "2026-10-17", "2026-08-31", 0.95, "Liga Profesional"),
]
RECINTO = "Estadio Atanasio Girardot"
CIUDAD = "Medellín"

# --- Suciedad intencional de Bronze ------------------------------------
TASA_ESPACIOS = 0.015  # IDs con espacios sobrantes
TASA_CANAL_NULO = 0.015  # canal_id nulo
TASA_DUPLICADOS = 0.010  # filas repetidas exactas
FILAS_SIN_CLAVE = 40  # filas con una clave de negocio nula
TASA_DUPLICADOS_USUARIOS = 0.005
TASA_ESPACIOS_USUARIOS = 0.010

TASA_PAGO_TARDIO = 0.08  # fracción de ventas pagadas en el último tramo del TTL


# --- Catálogos ----------------------------------------------------------
def generar_canales() -> pd.DataFrame:
    """Devuelve el catálogo de canales de venta."""
    return pd.DataFrame(CANALES, columns=["canal_id", "nombre", "digital_flag"])


def generar_zonas() -> pd.DataFrame:
    """Devuelve el tarifario de zonas: una fila por versión de precio."""
    filas = []
    for zona_id, nombre, tipo, _, filas_z, por_fila, versiones in ZONAS:
        for precio, desde, hasta in versiones:
            filas.append((zona_id, nombre, tipo, filas_z * por_fila, precio, desde, hasta, hasta == "9999-12-31"))
    columnas = ["zona_id", "nombre_zona", "tipo_zona", "capacidad_zona", "precio_base",
                "valido_desde", "valido_hasta", "activo"]
    return pd.DataFrame(filas, columns=columnas)


def generar_eventos() -> pd.DataFrame:
    """Devuelve los eventos del estadio con su fecha y su inicio de ventas."""
    filas = [(i, n, t, RECINTO, CIUDAD, f, v, aforo_total(), o) for i, n, t, f, v, _, o in EVENTOS]
    columnas = ["evento_id", "nombre_evento", "tipo_evento", "recinto", "ciudad", "fecha_evento",
                "inicio_ventas", "aforo_total", "organizador"]
    return pd.DataFrame(filas, columns=columnas)


def aforo_total() -> int:
    """Aforo total del estadio: suma de las capacidades de todas las zonas."""
    return sum(filas * por_fila for _, _, _, _, filas, por_fila, _ in ZONAS)


def generar_sillas() -> pd.DataFrame:
    """Devuelve las 45.000 sillas físicas, con fila, número y categoría."""
    partes = []
    for zona_id, _, _, prefijo, n_filas, por_fila, _ in ZONAS:
        fila = np.repeat(np.arange(1, n_filas + 1), por_fila)
        numero = np.tile(np.arange(1, por_fila + 1), n_filas)
        categoria = np.select([fila <= n_filas / 3, fila <= 2 * n_filas / 3], ["frente", "centro"], "fondo")
        partes.append(pd.DataFrame({
            "zona_id": zona_id,
            "fila": [f"{prefijo}{f:02d}" for f in fila],
            "numero": numero,
            "categoria": categoria,
        }))
    sillas = pd.concat(partes, ignore_index=True)
    sillas.insert(0, "silla_id", [f"S-{i:05d}" for i in range(1, len(sillas) + 1)])
    return sillas


def generar_usuarios(rng: np.random.Generator) -> pd.DataFrame:
    """Devuelve la población de usuarios con segmento y canal preferido."""
    segmentos = rng.choice(list(SEGMENTOS), config.N_USUARIOS, p=[v[0] for v in SEGMENTOS.values()])
    canal_pref = rng.choice([c[1] for c in CANALES], config.N_USUARIOS, p=PESO_CANAL)
    return pd.DataFrame({
        "usuario_id": [f"U-{i:06d}" for i in range(1, config.N_USUARIOS + 1)],
        "segmento": segmentos,
        "canal_preferido": canal_pref,
    })


# --- Ventas -------------------------------------------------------------
def _fecha_a_entero(fechas: pd.Series) -> np.ndarray:
    """Convierte fechas a enteros AAAAMMDD (comparables con las vigencias de zona)."""
    return (fechas.dt.year * 10000 + fechas.dt.month * 100 + fechas.dt.day).to_numpy()


def _precio_vigente(zonas: pd.DataFrame, zona_id: np.ndarray, fecha: pd.Series) -> np.ndarray:
    """Precio base de la versión de zona vigente en la fecha de cada fila."""
    fecha_int = _fecha_a_entero(fecha)
    precio = np.zeros(len(fecha), dtype=np.int64)
    for v in zonas.itertuples():
        desde, hasta = int(v.valido_desde.replace("-", "")), int(v.valido_hasta.replace("-", ""))
        mask = (zona_id == v.zona_id) & (fecha_int >= desde) & (fecha_int <= hasta)
        precio[mask] = v.precio_base
    return precio


def _pesos_dias(inicio: pd.Timestamp, n_dias: int) -> np.ndarray:
    """Peso de venta por día: pico el día de apertura, repunte final y fines de semana."""
    k = np.arange(n_dias)
    peso = 0.6 + 6.0 * np.exp(-k / 2.5) + 3.0 * np.exp(-(n_dias - 1 - k) / 4.0)
    fin_semana = pd.date_range(inicio, periods=n_dias).dayofweek >= 5
    peso = np.where(fin_semana, peso * 1.3, peso)
    return peso / peso.sum()


def _elegir_sillas(rng: np.random.Generator, sillas: pd.DataFrame, ocupacion: float) -> np.ndarray:
    """Elige, sin repetir, las posiciones de las sillas vendidas de un evento."""
    elegidas = []
    for zona_id, *_ in ZONAS:
        posiciones = np.flatnonzero((sillas["zona_id"] == zona_id).to_numpy())
        ocupacion_zona = min(1.0, max(0.80, ocupacion + rng.uniform(-0.04, 0.04)))
        vendidas = int(round(len(posiciones) * ocupacion_zona))
        elegidas.append(rng.choice(posiciones, vendidas, replace=False))
    return np.concatenate(elegidas)


def _momento_compra(rng: np.random.Generator, inicio: pd.Timestamp, n_dias: int,
                    canal_idx: np.ndarray) -> tuple[np.ndarray, pd.Series]:
    """Genera la fecha-hora de cada compra y devuelve también el día relativo a la apertura."""
    n = len(canal_idx)
    dia = rng.choice(n_dias, n, p=_pesos_dias(inicio, n_dias))
    hora = np.zeros(n, dtype=np.int64)
    for i, pesos in enumerate(PESO_HORA):
        mask = canal_idx == i
        hora[mask] = rng.choice(24, int(mask.sum()), p=pesos / pesos.sum())
    hora = np.where(dia == 0, np.maximum(hora, HORA_APERTURA_VENTAS), hora)
    segundos = dia * 86400 + hora * 3600 + rng.integers(0, 3600, n)
    momento = inicio.to_datetime64() + segundos.astype("timedelta64[s]")
    return pd.Series(momento), dia


def _tiempo_hasta_pago(rng: np.random.Generator, n: int) -> np.ndarray:
    """Segundos entre el lock y el pago; una minoría paga en el último tramo del TTL."""
    normal = np.minimum(np.round(rng.gamma(3.0, 55.0, n) + 20), config.UMBRAL_PAGO_TARDIO_SEG - 1)
    tardio = rng.integers(config.UMBRAL_PAGO_TARDIO_SEG, config.TTL_LOCK_SEG, n)
    return np.where(rng.random(n) < TASA_PAGO_TARDIO, tardio, normal).astype(np.int64)


def _descuento(rng: np.random.Generator, precio_base: np.ndarray, segmento: np.ndarray,
               dia: np.ndarray) -> np.ndarray:
    """Descuento en pesos según segmento del usuario y preventa (primeros 3 días)."""
    tasa_seg = np.array([SEGMENTOS[s][1] for s in segmento])
    prob_seg = np.array([SEGMENTOS[s][2] for s in segmento])
    tasa = np.where(rng.random(len(segmento)) < prob_seg, tasa_seg, 0.0)
    preventa = (dia < 3) & (tasa == 0) & (rng.random(len(segmento)) < PROB_PREVENTA)
    tasa = np.where(preventa, DESCUENTO_PREVENTA, tasa)
    return (np.round(precio_base * tasa / 100) * 100).astype(np.int64)


def generar_ventas(rng: np.random.Generator, cat: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Genera las compras confirmadas limpias (una por silla y evento).

    Devuelve además las columnas auxiliares `zona_id`, `dia_venta` y
    `fecha_intento` que se usan para construir los intentos de compra.
    """
    sillas, usuarios, zonas = cat["sillas"], cat["usuarios"], cat["zonas"]
    pref = usuarios["canal_preferido"].map({c[1]: i for i, c in enumerate(CANALES)}).to_numpy()
    partes = []
    for evento_id, _, _, fecha_evento, inicio_ventas, ocupacion, _ in EVENTOS:
        inicio = pd.Timestamp(inicio_ventas)
        n_dias = (pd.Timestamp(fecha_evento) - inicio).days
        pos_silla = _elegir_sillas(rng, sillas, ocupacion)
        n = len(pos_silla)
        pos_usuario = rng.integers(0, config.N_USUARIOS, n)
        canal_idx = np.where(rng.random(n) < 0.8, pref[pos_usuario], rng.choice(3, n, p=PESO_CANAL))
        fecha_compra, dia = _momento_compra(rng, inicio, n_dias, canal_idx)
        zona_id = sillas["zona_id"].to_numpy()[pos_silla]
        precio_base = _precio_vigente(zonas, zona_id, fecha_compra)
        descuento = _descuento(rng, precio_base, usuarios["segmento"].to_numpy()[pos_usuario], dia)
        tiempo_pago = _tiempo_hasta_pago(rng, n)
        partes.append(pd.DataFrame({
            "silla_id": sillas["silla_id"].to_numpy()[pos_silla],
            "evento_id": evento_id,
            "usuario_id": usuarios["usuario_id"].to_numpy()[pos_usuario],
            "canal_id": np.array([c[0] for c in CANALES])[canal_idx],
            "fecha_compra": fecha_compra,
            "precio_pagado": precio_base - descuento,
            "descuento_aplicado": descuento,
            "tiempo_hasta_pago_seg": tiempo_pago,
            "zona_id": zona_id,
            "dia_venta": dia,
            "fecha_intento": fecha_compra - pd.to_timedelta(tiempo_pago, unit="s"),
        }))
    ventas = pd.concat(partes, ignore_index=True).sort_values("fecha_compra", ignore_index=True)
    ventas.insert(0, "compra_id", [f"C-{i:07d}" for i in range(1, len(ventas) + 1)])
    return ventas


# --- Intentos de compra --------------------------------------------------
def _intentos_abandono(rng: np.random.Generator, ventas: pd.DataFrame, sillas: pd.DataFrame,
                       usuarios: pd.DataFrame) -> pd.DataFrame:
    """Intentos cuyo lock venció sin pago: la silla volvió al inventario."""
    base = ventas.iloc[rng.integers(0, len(ventas), int(len(ventas) * config.TASA_ABANDONO))].reset_index(drop=True)
    silla = np.empty(len(base), dtype=object)
    for zona_id, *_ in ZONAS:
        mask = (base["zona_id"] == zona_id).to_numpy()
        silla[mask] = rng.choice(sillas.loc[sillas["zona_id"] == zona_id, "silla_id"].to_numpy(), int(mask.sum()))
    return pd.DataFrame({
        "silla_id": silla,
        "evento_id": base["evento_id"],
        "usuario_id": rng.choice(usuarios["usuario_id"].to_numpy(), len(base)),
        "canal_id": base["canal_id"],
        "fecha_intento": base["fecha_intento"] + pd.to_timedelta(rng.integers(0, 3600, len(base)), unit="s"),
        "resultado": "ABANDONO",
        "compra_id": None,
    })


def _intentos_rechazo(rng: np.random.Generator, ventas: pd.DataFrame, usuarios: pd.DataFrame) -> pd.DataFrame:
    """Intentos sobre una silla ya vendida: el UNIQUE rechaza el INSERT."""
    base = ventas.iloc[rng.integers(0, len(ventas), int(len(ventas) * config.TASA_RECHAZO_UNIQUE))].reset_index(drop=True)
    espera = np.clip(1 + rng.exponential(300, len(base)), 1, 3600).astype(np.int64)
    return pd.DataFrame({
        "silla_id": base["silla_id"],
        "evento_id": base["evento_id"],
        "usuario_id": rng.choice(usuarios["usuario_id"].to_numpy(), len(base)),
        "canal_id": np.array([c[0] for c in CANALES])[rng.choice(3, len(base), p=PESO_CANAL)],
        "fecha_intento": base["fecha_compra"] + pd.to_timedelta(espera, unit="s"),
        "resultado": "RECHAZO_UNIQUE",
        "compra_id": None,
    })


def generar_intentos(rng: np.random.Generator, ventas: pd.DataFrame, cat: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Une los intentos COMPRA (uno por venta), ABANDONO y RECHAZO_UNIQUE."""
    compras = ventas[["silla_id", "evento_id", "usuario_id", "canal_id", "fecha_intento", "compra_id"]].copy()
    compras["resultado"] = "COMPRA"
    intentos = pd.concat([
        compras,
        _intentos_abandono(rng, ventas, cat["sillas"], cat["usuarios"]),
        _intentos_rechazo(rng, ventas, cat["usuarios"]),
    ], ignore_index=True).sort_values("fecha_intento", ignore_index=True)

    inicio = intentos["evento_id"].map({e[0]: pd.Timestamp(e[4]) for e in EVENTOS})
    dias = (intentos["fecha_intento"] - inicio).dt.total_seconds() / 86400
    espera = rng.lognormal(np.log(45), 0.8, len(intentos)) * (1 + 3 * np.exp(-dias / 2.5))
    intentos["tiempo_en_fila_seg"] = np.round(espera).astype(np.int64)
    intentos.insert(0, "intento_id", [f"I-{i:07d}" for i in range(1, len(intentos) + 1)])
    return intentos


# --- Suciedad intencional ------------------------------------------------
def _agregar_espacios(rng: np.random.Generator, serie: pd.Series, tasa: float) -> pd.Series:
    """Agrega espacios al inicio o al final de una fracción de los valores."""
    mask = rng.random(len(serie)) < tasa
    lado = rng.random(len(serie)) < 0.5
    valores = serie.astype(object).copy()
    for i in np.flatnonzero(mask):
        valores.iloc[i] = f"  {valores.iloc[i]}" if lado[i] else f"{valores.iloc[i]} "
    return valores


def _ensuciar_transaccional(rng: np.random.Generator, df: pd.DataFrame, col_fecha: str,
                            ids: list[str], claves: list[str]) -> pd.DataFrame:
    """Aplica a una tabla transaccional los problemas típicos de un volcado operacional.

    * Fechas como texto (el volcado no conserva el tipo).
    * IDs con espacios sobrantes.
    * `canal_id` nulo en una fracción de las filas.
    * Filas duplicadas exactas (reintentos del extractor).
    * Filas extra a las que les falta una clave de negocio (se descartan en Silver).
    """
    df = df.copy()
    df[col_fecha] = df[col_fecha].dt.strftime("%Y-%m-%d %H:%M:%S")
    for col in ids:
        df[col] = _agregar_espacios(rng, df[col], TASA_ESPACIOS)
    df.loc[rng.random(len(df)) < TASA_CANAL_NULO, "canal_id"] = None

    sin_clave = df.iloc[rng.integers(0, len(df), FILAS_SIN_CLAVE)].copy()
    for pos, col in enumerate(rng.choice(claves, FILAS_SIN_CLAVE)):
        sin_clave.iloc[pos, sin_clave.columns.get_loc(col)] = None
    duplicados = df.iloc[rng.choice(len(df), int(len(df) * TASA_DUPLICADOS), replace=False)]

    sucio = pd.concat([df, duplicados, sin_clave], ignore_index=True)
    return sucio.iloc[rng.permutation(len(sucio))].reset_index(drop=True)


def _ensuciar_usuarios(rng: np.random.Generator, usuarios: pd.DataFrame) -> pd.DataFrame:
    """Agrega espacios a algunos IDs de usuario y repite algunas filas."""
    usuarios = usuarios.copy()
    usuarios["usuario_id"] = _agregar_espacios(rng, usuarios["usuario_id"], TASA_ESPACIOS_USUARIOS)
    duplicados = usuarios.iloc[rng.choice(len(usuarios), int(len(usuarios) * TASA_DUPLICADOS_USUARIOS), replace=False)]
    sucio = pd.concat([usuarios, duplicados], ignore_index=True)
    return sucio.iloc[rng.permutation(len(sucio))].reset_index(drop=True)


# --- Punto de entrada ----------------------------------------------------
def generar() -> dict[str, pd.DataFrame]:
    """Genera todas las tablas operacionales tal como llegarían a Bronze."""
    rng = np.random.default_rng(config.SEED)
    cat = {
        "canales": generar_canales(),
        "zonas": generar_zonas(),
        "eventos": generar_eventos(),
        "sillas": generar_sillas(),
        "usuarios": generar_usuarios(rng),
    }
    ventas = generar_ventas(rng, cat)
    intentos = generar_intentos(rng, ventas, cat)

    compras = ventas[["compra_id", "silla_id", "evento_id", "usuario_id", "canal_id", "fecha_compra",
                      "precio_pagado", "descuento_aplicado", "tiempo_hasta_pago_seg"]]
    intentos = intentos[["intento_id", "silla_id", "evento_id", "usuario_id", "canal_id", "fecha_intento",
                         "resultado", "tiempo_en_fila_seg", "compra_id"]]
    tablas = dict(cat)
    tablas["usuarios"] = _ensuciar_usuarios(rng, cat["usuarios"])
    tablas["compras_confirmadas"] = _ensuciar_transaccional(
        rng, compras, "fecha_compra", ["compra_id", "silla_id", "evento_id", "usuario_id"],
        ["compra_id", "silla_id", "evento_id"])
    tablas["intentos_compra"] = _ensuciar_transaccional(
        rng, intentos, "fecha_intento", ["intento_id", "silla_id", "evento_id", "usuario_id"],
        ["intento_id", "silla_id", "evento_id"])
    return tablas


def ejecutar() -> dict[str, pd.DataFrame]:
    """Genera los datos e imprime un resumen de volúmenes."""
    tablas = generar()
    for nombre, df in tablas.items():
        print(f"  {nombre}: {len(df):,} filas")
    return tablas


if __name__ == "__main__":
    ejecutar()
