"""EXPORTACIÓN: serializa los resultados a JSON. Compartido por la CLI clásica y las skills."""
import json
import os

from . import metricas as modulo_metricas

NOMBRES = ("normalizadas.json", "invalidas.json", "metricas.json")


def metricas_a_dict(m):
    return {
        "total": m.total, "validas": m.validas, "invalidas": m.invalidas,
        "por_estado": m.por_estado, "por_fuente": m.por_fuente,
        "por_moneda": {mon: {"cantidad": f["cantidad"], "total": float(f["total"]),
                             "confirmado": float(f["confirmado"])} for mon, f in m.por_moneda.items()},
        "motivos_invalidas": m.motivos_invalidas,
    }


def armar_contenido(resultado, reglas):
    """Devuelve {nombre_de_archivo: datos} listo para escribir (no escribe nada)."""
    m = modulo_metricas.calcular(resultado.valid, resultado.invalid, reglas.estados)
    return {
        "normalizadas.json": [tx.to_dict() for tx in resultado.valid],
        "invalidas.json": [inv.to_dict() for inv in resultado.invalid],
        "metricas.json": metricas_a_dict(m),
    }


def archivos_existentes(carpeta, nombres):
    return [n for n in nombres if os.path.exists(os.path.join(carpeta, n))]


def escribir(carpeta, contenido):
    """Escribe cada archivo del contenido en la carpeta. Devuelve las rutas escritas."""
    os.makedirs(carpeta, exist_ok=True)
    rutas = []
    for nombre, datos in contenido.items():
        ruta = os.path.join(carpeta, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        rutas.append(ruta)
    return rutas
