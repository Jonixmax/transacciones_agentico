"""Skill diagnostico-invalidas (ver SKILL.md). Solo lee datos; no tiene efectos."""
import json
import os

from agentes.llm import normalizar
from agentes.skills import ResultadoSkill
from nucleo.metricas import categoria_motivo

OPERACIONES = ("resumen", "detalle", "por_motivo", "plan")
_RECURSOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recursos")
_ORDEN_SEVERIDAD = {"alta": 0, "media": 1, "baja": 2}

PARAMETROS = {
    "operacion": {"tipo": "texto", "descripcion": "resumen, detalle, por_motivo o plan"},
    "posicion": {"tipo": "entero", "descripcion": "número del registro en el archivo (con operacion=detalle)"},
    "motivo": {"tipo": "texto", "descripcion": "palabra del tipo de problema, por ejemplo fecha o monto"},
}

_guia_cache = None


def _guia():
    global _guia_cache
    if _guia_cache is None:
        with open(os.path.join(_RECURSOS, "guia_motivos.json"), encoding="utf-8") as f:
            _guia_cache = json.load(f)
    return _guia_cache


def _entrada(categoria):
    """Entrada de la guía para una categoría; si no existe, la genérica (nunca se inventa)."""
    return _guia()["categorias"].get(categoria, _guia()["otro"])


def _posiciones(registros):
    return ", ".join(f"#{r.position}" for r in registros)


def _acciones_de(registro):
    return {_entrada(categoria_motivo(m))["accion"] for m in registro.reasons}


def _resumen(sesion):
    invalidas, total = sesion.resultado.invalid, sesion.resultado.total
    por_categoria = {}
    for inv in invalidas:
        for categoria in {categoria_motivo(m) for m in inv.reasons}:
            por_categoria.setdefault(categoria, []).append(inv)
    orden = sorted(por_categoria.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    lineas = [f"Se rechazaron {len(invalidas)} de {total} registros ({100 * len(invalidas) / total:.1f}%). "
              f"Hay {len(orden)} tipos de problema:"]
    for categoria, regs in orden:
        e = _entrada(categoria)
        lineas += [f"  {len(regs)} x {e['titulo']}  [severidad {e['severidad']}]",
                   f"      Causa probable: {e['causa_probable']}",
                   f"      Cómo corregirlo: {e['correccion']}",
                   f"      Registros: {_posiciones(regs)}"]
    altas = sum(1 for c, r in orden if _entrada(c)["severidad"] == "alta")
    reco = "Empieza por los problemas de severidad alta" if altas else "Ninguno es de severidad alta"
    return ResultadoSkill(True, "\n".join(lineas), f"{reco}; usa «plan de corrección» para ver el orden sugerido.",
                          {"invalidas": len(invalidas), "tipos": len(orden), "por_categoria": {c: len(r) for c, r in orden}})


def _detalle(sesion, posicion):
    invalidas = sesion.resultado.invalid
    inv = next((i for i in invalidas if i.position == posicion), None)
    if inv is None:
        return ResultadoSkill(False, f"No hay un registro inválido en la posición {posicion}. "
                                     f"Posiciones inválidas: {_posiciones(invalidas)}.")
    lineas = [f"Registro #{inv.position} ({inv.source or 'fuente desconocida'}):"]
    for motivo in inv.reasons:
        e = _entrada(categoria_motivo(motivo))
        lineas += [f"  Motivo: {motivo}", f"    {e['explicacion']}",
                   f"    Causa probable: {e['causa_probable']}", f"    Cómo corregirlo: {e['correccion']}"]
    lineas.append("  Original: " + json.dumps(inv.raw, ensure_ascii=False))
    acciones = sorted(_acciones_de(inv))
    return ResultadoSkill(True, "\n".join(lineas), _guia()["acciones"][acciones[0]]["descripcion"],
                          {"posicion": inv.position, "motivos": inv.reasons})


def _por_motivo(sesion, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        return ResultadoSkill(False, "Indica el tipo de problema (por ejemplo: fecha, monto, moneda, duplicado).")
    clave = normalizar(motivo)
    regs = [i for i in sesion.resultado.invalid
            if any(clave in normalizar(categoria_motivo(m)) for m in i.reasons)]
    if not regs:
        return ResultadoSkill(True, f"No hay registros inválidos cuyo motivo contenga '{motivo}'.")
    lineas = [f"{len(regs)} registros inválidos tienen problemas de tipo '{motivo}':"]
    for r in regs:
        lineas.append(f"  #{r.position}: " + "; ".join(r.reasons))
    return ResultadoSkill(True, "\n".join(lineas), "Usa «explica el registro N» para ver la causa y la corrección.",
                          {"posiciones": [r.position for r in regs]})


def _plan(sesion):
    grupos = {}
    for inv in sesion.resultado.invalid:
        for accion in _acciones_de(inv):
            grupos.setdefault(accion, []).append(inv)
    orden = sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    lineas = ["Plan de corrección, de mayor a menor cantidad de registros:"]
    for n, (accion, regs) in enumerate(orden, start=1):
        a = _guia()["acciones"][accion]
        sustantivo = "registro" if len(regs) == 1 else "registros"
        lineas += [f"  {n}. {a['titulo']} ({len(regs)} {sustantivo}): {_posiciones(regs)}", f"     {a['descripcion']}"]
    return ResultadoSkill(True, "\n".join(lineas), "Corrige los datos y vuelve a procesar el archivo para comprobar el resultado.",
                          {"acciones": {a: [r.position for r in regs] for a, regs in orden}})


def ejecutar(sesion, operacion=None, posicion=None, motivo=None):
    if operacion is not None and operacion not in OPERACIONES:
        return ResultadoSkill(False, f"Operación no válida: '{operacion}'. Usa {', '.join(OPERACIONES)}.")
    if not sesion.resultado.invalid:
        return ResultadoSkill(True, "No hay registros inválidos: todos los registros del archivo se normalizaron correctamente.")
    if operacion is None:
        operacion = "detalle" if posicion is not None else "por_motivo" if motivo else "resumen"
    if operacion == "detalle" and posicion is None:
        operacion = "resumen"                     # «explica los errores» sin número = resumen
    if operacion == "resumen":
        return _resumen(sesion)
    if operacion == "detalle":
        return _detalle(sesion, posicion)
    if operacion == "por_motivo":
        return _por_motivo(sesion, motivo)
    return _plan(sesion)
