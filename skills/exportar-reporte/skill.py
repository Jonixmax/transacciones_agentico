"""Skill exportar-reporte (ver SKILL.md). ÚNICA skill con efectos: escribe archivos."""
import os
import re
from datetime import datetime

from agentes.skills import Previsualizacion, ResultadoSkill
from nucleo import exportacion
from nucleo import metricas as modulo_metricas
from nucleo.presentacion import dinero

CARPETA_POR_DEFECTO = "salida_agente"
ARCHIVOS = ("reporte.md",) + exportacion.NOMBRES
_PLANTILLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recursos", "plantilla_reporte.md")

PARAMETROS = {
    "carpeta": {"tipo": "texto", "descripcion": "carpeta de salida relativa (por defecto salida_agente)"},
}


def _resolver_carpeta(sesion, carpeta):
    """Devuelve la ruta absoluta de destino, o lanza ValueError si no es segura."""
    carpeta = (carpeta or CARPETA_POR_DEFECTO).strip()
    if not carpeta:
        raise ValueError("la carpeta de salida no puede estar vacía")
    if os.path.isabs(carpeta) or carpeta.startswith(("~", "\\", "/")) or re.match(r"^[A-Za-z]:", carpeta):
        raise ValueError("solo se permiten carpetas relativas dentro del proyecto (no rutas absolutas)")
    if ".." in carpeta.replace("\\", "/").split("/"):
        raise ValueError("la carpeta no puede usar '..' para salir del proyecto")
    base = os.path.realpath(sesion.directorio_salida)
    destino = os.path.realpath(os.path.join(base, carpeta))
    if os.path.commonpath([base, destino]) != base:
        raise ValueError("la carpeta de salida queda fuera del proyecto")
    return destino


def previsualizar(sesion, carpeta=None):
    destino = _resolver_carpeta(sesion, carpeta)
    existentes = exportacion.archivos_existentes(destino, ARCHIVOS)
    texto = f"Voy a escribir {len(ARCHIVOS)} archivos en '{carpeta or CARPETA_POR_DEFECTO}' ({destino}): {', '.join(ARCHIVOS)}."
    if existentes:
        texto += f" Se sobrescribirán: {', '.join(existentes)}."
    return Previsualizacion(texto, sobrescribe=bool(existentes))


def _bloque_estados(m):
    return "\n".join(f"- {estado}: {n}" for estado, n in m.por_estado.items())


def _bloque_monedas(m):
    if not m.por_moneda:
        return "_Sin transacciones válidas._"
    filas = ["| Moneda | Cantidad | Total | Confirmado (SUCCESS) |", "|---|---:|---:|---:|"]
    for moneda, f in sorted(m.por_moneda.items()):
        filas.append(f"| {moneda} | {f['cantidad']} | {dinero(f['total'])} | {dinero(f['confirmado'])} |")
    return "\n".join(filas)


def _reporte(sesion, m):
    with open(_PLANTILLA, encoding="utf-8") as f:
        plantilla = f.read()
    r = sesion.resultado
    motivos = "\n".join(f"- {n} × {motivo}" for motivo, n in m.motivos_invalidas.items()) or "_Ningún registro fue rechazado._"
    avisos = "\n".join(f"- Registro #{a.position} (id {a.id}): {a.message}" for a in r.avisos) or "_Sin avisos._"
    valores = {
        "archivo": os.path.basename(sesion.ruta) if sesion.ruta else "(desconocido)",   # solo el nombre: la ruta completa no es portable
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "resumen": f"Se procesaron **{m.total}** registros: **{m.validas}** válidos ({m.porcentaje_validas:.1f}%) y **{m.invalidas}** inválidos.",
        "estados": _bloque_estados(m), "monedas": _bloque_monedas(m), "motivos": motivos, "avisos": avisos,
    }
    for clave, valor in valores.items():
        plantilla = plantilla.replace("{{" + clave + "}}", valor)
    return plantilla


def ejecutar(sesion, carpeta=None):
    try:
        destino = _resolver_carpeta(sesion, carpeta)
    except ValueError as e:                       # defensa: aunque alguien salte previsualizar
        return ResultadoSkill(False, f"No escribí nada: {e}.")
    r = sesion.resultado
    m = modulo_metricas.calcular(r.valid, r.invalid, sesion.reglas.estados)
    try:
        rutas = exportacion.escribir(destino, exportacion.armar_contenido(r, sesion.reglas))
        with open(os.path.join(destino, "reporte.md"), "w", encoding="utf-8") as f:
            f.write(_reporte(sesion, m))
    except OSError as e:
        return ResultadoSkill(False, f"No pude escribir los archivos: {e}")
    nombre = carpeta or CARPETA_POR_DEFECTO
    return ResultadoSkill(True, f"Listo: escribí {len(rutas) + 1} archivos en '{nombre}': {', '.join(ARCHIVOS)}.",
                          datos={"carpeta": destino, "archivos": list(ARCHIVOS)})
