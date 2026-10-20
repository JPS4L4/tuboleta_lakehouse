"""Paso 4: Silver -> Gold (modelo dimensional en estrella).

Construye seis dimensiones conformadas y dos tablas de hechos:
  * `fact_ventas_boletas`: una fila = una silla vendida y pagada en un evento.
  * `fact_intentos_compra`: una fila = un intento de compra (compra, abandono
    o rechazo por UNIQUE). Los abandonos NO son ventas.
  * `dim_zona` es SCD Tipo 2: cada hecho recibe el `zona_sk` de la versión de
    zona vigente en su fecha (`fecha BETWEEN valido_desde AND valido_hasta`).

El paso verifica con aserciones que no hay double-booking, que cada hecho
resolvió exactamente una versión de zona y que toda venta tiene su intento COMPRA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import config

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
CANAL_DESCONOCIDO = ("DESCONOCIDO", "DESCONOCIDO", False)


def leer_silver(tabla: str) -> pd.DataFrame:
    """Lee una tabla de la capa Silver."""
    return pd.read_parquet(config.SILVER / f"{tabla}_silver.parquet")


def _afirmar(condicion: bool, mensaje: str) -> None:
    """Verifica una regla del modelo: falla con AssertionError o imprime OK."""
    if not condicion:
        raise AssertionError(f"Regla incumplida: {mensaje}")
    print(f"  [OK] {mensaje}")


def _con_sk(df: pd.DataFrame, nombre_sk: str) -> pd.DataFrame:
    """Agrega una clave sustituta entera secuencial (desde 1) como primera columna."""
    df = df.reset_index(drop=True)
    df.insert(0, nombre_sk, np.arange(1, len(df) + 1, dtype="int32"))
    return df


def _fecha_a_entero(fechas: pd.Series) -> np.ndarray:
    """Convierte fechas-hora a enteros AAAAMMDD."""
    return (fechas.dt.year * 10000 + fechas.dt.month * 100 + fechas.dt.day).to_numpy()


def calcular_tiempo_sk(fechas: pd.Series) -> np.ndarray:
    """Clave de DIM_TIEMPO: entero AAAAMMDDHH de la hora en que ocurrió el hecho."""
    return (_fecha_a_entero(fechas) * 100 + fechas.dt.hour.to_numpy()).astype("int64")


# --- Dimensiones ---------------------------------------------------------
def construir_dim_tiempo(minimo: pd.Timestamp, maximo: pd.Timestamp) -> pd.DataFrame:
    """DIM_TIEMPO (Tipo 0) con granularidad de hora entre las fechas mínima y máxima."""
    horas = pd.date_range(minimo.floor("h"), maximo.floor("h"), freq="h")
    hora = horas.hour.to_numpy()
    dia_semana = horas.dayofweek.to_numpy()
    return pd.DataFrame({
        "tiempo_sk": calcular_tiempo_sk(pd.Series(horas)),
        "fecha": horas.date,
        "anio": horas.year.to_numpy(),
        "trimestre": horas.quarter.to_numpy(),
        "mes": horas.month.to_numpy(),
        "mes_nombre": [MESES[m - 1] for m in horas.month],
        "dia": horas.day.to_numpy(),
        "dia_semana": dia_semana + 1,  # 1 = lunes ... 7 = domingo
        "dia_nombre": [DIAS[d] for d in dia_semana],
        "es_fin_semana": dia_semana >= 5,
        "hora": hora,
        "franja_horaria": np.select([hora < 6, hora < 12, hora < 18], ["madrugada", "mañana", "tarde"], "noche"),
    })


def construir_dim_evento(eventos: pd.DataFrame) -> pd.DataFrame:
    """DIM_EVENTO (Tipo 1)."""
    return _con_sk(eventos.sort_values("evento_id"), "evento_sk")


def construir_dim_zona(zonas: pd.DataFrame) -> pd.DataFrame:
    """DIM_ZONA (Tipo 2): una fila por versión de la zona, con su vigencia."""
    zonas = zonas.assign(_orden=zonas.groupby("zona_id", sort=False).ngroup())
    zonas = zonas.sort_values(["_orden", "valido_desde"]).drop(columns="_orden")
    return _con_sk(zonas, "zona_sk")


def construir_dim_silla(sillas: pd.DataFrame) -> pd.DataFrame:
    """DIM_SILLA (Tipo 1)."""
    return _con_sk(sillas.sort_values("silla_id"), "silla_sk")


def construir_dim_usuario(usuarios: pd.DataFrame) -> pd.DataFrame:
    """DIM_USUARIO (Tipo 1)."""
    return _con_sk(usuarios.sort_values("usuario_id"), "usuario_sk")


def construir_dim_canal(canales: pd.DataFrame) -> pd.DataFrame:
    """DIM_CANAL (Tipo 1), con el miembro 'DESCONOCIDO' para canales nulos en origen."""
    base = canales[["canal_id", "nombre", "digital_flag"]]
    desconocido = pd.DataFrame([CANAL_DESCONOCIDO], columns=base.columns)
    return _con_sk(pd.concat([base, desconocido], ignore_index=True), "canal_sk")


# --- Resolución de claves sustitutas ------------------------------------
def _buscar_sk(valores: pd.Series, dim: pd.DataFrame, clave: str, sk: str) -> np.ndarray:
    """Traduce claves de negocio a claves sustitutas; falla si alguna no existe en la dimensión."""
    resultado = valores.map(dim.set_index(clave)[sk])
    if resultado.isna().any():
        raise AssertionError(f"Regla incumplida: hay filas sin {sk} (clave de negocio inexistente en la dimensión)")
    return resultado.to_numpy(dtype="int32")


def resolver_zona_sk(hechos: pd.DataFrame, col_fecha: str, sillas: pd.DataFrame,
                     dim_zona: pd.DataFrame) -> np.ndarray:
    """Asigna a cada hecho el `zona_sk` de la versión vigente en su fecha (SCD Tipo 2).

    La zona de un hecho se obtiene de su silla; luego se elige la versión con
    `fecha BETWEEN valido_desde AND valido_hasta`. Debe haber exactamente una.
    """
    candidatos = pd.DataFrame({
        "fila": np.arange(len(hechos)),
        "zona_id": hechos["silla_id"].map(sillas.set_index("silla_id")["zona_id"]).to_numpy(),
        "fecha": _fecha_a_entero(hechos[col_fecha]),
    })
    versiones = pd.DataFrame({
        "zona_id": dim_zona["zona_id"],
        "zona_sk": dim_zona["zona_sk"],
        "desde": dim_zona["valido_desde"].map(lambda d: d.year * 10000 + d.month * 100 + d.day),
        "hasta": dim_zona["valido_hasta"].map(lambda d: d.year * 10000 + d.month * 100 + d.day),
    })
    vigentes = candidatos.merge(versiones, on="zona_id", how="left")
    vigentes = vigentes[(vigentes["fecha"] >= vigentes["desde"]) & (vigentes["fecha"] <= vigentes["hasta"])]
    _afirmar(len(vigentes) == len(hechos) and vigentes["fila"].is_unique,
             f"SCD2: cada fila de {col_fecha} resolvió exactamente una versión de zona")
    return vigentes.sort_values("fila")["zona_sk"].to_numpy(dtype="int32")


# --- Hechos ---------------------------------------------------------------
def construir_fact_ventas(compras: pd.DataFrame, dims: dict[str, pd.DataFrame], sillas: pd.DataFrame) -> pd.DataFrame:
    """FACT_VENTAS_BOLETAS: una fila por silla vendida y pagada."""
    return pd.DataFrame({
        "compra_id": compras["compra_id"],
        "tiempo_sk": calcular_tiempo_sk(compras["fecha_compra"]),
        "evento_sk": _buscar_sk(compras["evento_id"], dims["evento"], "evento_id", "evento_sk"),
        "zona_sk": resolver_zona_sk(compras, "fecha_compra", sillas, dims["zona"]),
        "silla_sk": _buscar_sk(compras["silla_id"], dims["silla"], "silla_id", "silla_sk"),
        "usuario_sk": _buscar_sk(compras["usuario_id"], dims["usuario"], "usuario_id", "usuario_sk"),
        "canal_sk": _buscar_sk(compras["canal_id"], dims["canal"], "canal_id", "canal_sk"),
        "precio_pagado": compras["precio_pagado"],
        "cantidad": np.ones(len(compras), dtype="int32"),
        "descuento_aplicado": compras["descuento_aplicado"],
        "tiempo_hasta_pago_seg": compras["tiempo_hasta_pago_seg"],
        "es_pago_tardio": (compras["tiempo_hasta_pago_seg"] >= config.UMBRAL_PAGO_TARDIO_SEG).astype("int8"),
    })


def construir_fact_intentos(intentos: pd.DataFrame, dims: dict[str, pd.DataFrame], sillas: pd.DataFrame) -> pd.DataFrame:
    """FACT_INTENTOS_COMPRA: una fila por intento de compra (lock de una silla)."""
    zona_sk = resolver_zona_sk(intentos, "fecha_intento", sillas, dims["zona"])
    precio_lista = pd.Series(zona_sk).map(dims["zona"].set_index("zona_sk")["precio_base"]).to_numpy()
    return pd.DataFrame({
        "intento_id": intentos["intento_id"],
        "compra_id": intentos["compra_id"],
        "tiempo_sk": calcular_tiempo_sk(intentos["fecha_intento"]),
        "evento_sk": _buscar_sk(intentos["evento_id"], dims["evento"], "evento_id", "evento_sk"),
        "zona_sk": zona_sk,
        "silla_sk": _buscar_sk(intentos["silla_id"], dims["silla"], "silla_id", "silla_sk"),
        "usuario_sk": _buscar_sk(intentos["usuario_id"], dims["usuario"], "usuario_id", "usuario_sk"),
        "canal_sk": _buscar_sk(intentos["canal_id"], dims["canal"], "canal_id", "canal_sk"),
        "resultado": intentos["resultado"],
        "es_compra": (intentos["resultado"] == "COMPRA").astype("int8"),
        "es_abandono": (intentos["resultado"] == "ABANDONO").astype("int8"),
        "es_rechazo_unique": (intentos["resultado"] == "RECHAZO_UNIQUE").astype("int8"),
        "tiempo_en_fila_seg": intentos["tiempo_en_fila_seg"],
        "precio_lista": precio_lista,
    })


def verificar_modelo(ventas: pd.DataFrame, intentos: pd.DataFrame, dim_zona: pd.DataFrame) -> None:
    """Aserciones de integridad del modelo (no double-booking, precios y enlace venta-intento)."""
    _afirmar(not ventas.duplicated(["evento_sk", "silla_sk"]).any(),
             "sin double-booking: UNIQUE(evento_sk, silla_sk) en fact_ventas_boletas")
    _afirmar(bool(ventas["compra_id"].is_unique), "compra_id único en fact_ventas_boletas")

    precio_base = ventas["zona_sk"].map(dim_zona.set_index("zona_sk")["precio_base"])
    _afirmar(bool((precio_base == ventas["precio_pagado"] + ventas["descuento_aplicado"]).all()),
             "precio_pagado + descuento = precio_base de la versión de zona resuelta")

    compras = intentos[intentos["es_compra"] == 1]
    _afirmar(bool(compras["compra_id"].notna().all() and compras["compra_id"].is_unique)
             and set(compras["compra_id"]) == set(ventas["compra_id"]),
             "cada venta confirmada enlaza con exactamente un intento COMPRA")
    _afirmar(bool(intentos.loc[intentos["es_compra"] == 0, "compra_id"].isna().all()),
             "los intentos ABANDONO y RECHAZO_UNIQUE no tienen compra asociada")


def escribir_gold(tablas: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Escribe cada tabla Gold con nombre fijo (sobrescribe) y devuelve las filas por tabla."""
    config.GOLD.mkdir(parents=True, exist_ok=True)
    for nombre, df in tablas.items():
        df.to_parquet(config.GOLD / f"{nombre}.parquet", index=False)
        print(f"  gold/{nombre}.parquet: {len(df):,} filas")
    return {nombre: len(df) for nombre, df in tablas.items()}


def ejecutar() -> dict[str, int]:
    """Construye dimensiones y hechos del modelo en estrella a partir de Silver."""
    compras = leer_silver("compras_confirmadas")
    intentos = leer_silver("intentos_compra")
    sillas = leer_silver("sillas")

    fechas = pd.concat([compras["fecha_compra"], intentos["fecha_intento"]])
    dims = {
        "tiempo": construir_dim_tiempo(fechas.min(), fechas.max()),
        "evento": construir_dim_evento(leer_silver("eventos")),
        "zona": construir_dim_zona(leer_silver("zonas")),
        "silla": construir_dim_silla(sillas),
        "usuario": construir_dim_usuario(leer_silver("usuarios")),
        "canal": construir_dim_canal(leer_silver("canales")),
    }
    print("Verificaciones del modelo:")
    ventas = construir_fact_ventas(compras, dims, sillas)
    fact_intentos = construir_fact_intentos(intentos, dims, sillas)
    verificar_modelo(ventas, fact_intentos, dims["zona"])

    tablas = {f"dim_{nombre}": df for nombre, df in dims.items()}
    tablas["fact_ventas_boletas"] = ventas
    tablas["fact_intentos_compra"] = fact_intentos
    return escribir_gold(tablas)


if __name__ == "__main__":
    ejecutar()
