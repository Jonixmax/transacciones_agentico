"""CONFIGURACIÓN: carga y valida config/sistema.json y config/agentes/*.json.

El comportamiento de cada agente (rol, tono, reglas, skills permitidas y mensajes) vive en
estos archivos, NO en el código: personalizar un agente es editar su JSON.
"""
import json
import os
from dataclasses import dataclass
from typing import Dict, List

POLITICAS_EFECTOS = ("siempre", "nunca", "solo_sobrescribir")
CLAVES_AGENTE = ("id", "nombre", "rol", "objetivo", "tono", "reglas_comportamiento",
                 "skills_permitidas", "respuesta", "mensajes")
CLAVES_RESPUESTA = ("prefijo", "cierre", "mostrar_recomendacion", "etiqueta_recomendacion")
MENSAJES_REQUERIDOS = ("saludo", "fuera_de_alcance", "no_entendido", "sin_datos", "aclarar", "cancelado")


class ConfigError(Exception):
    """Un archivo de configuración falta, es inválido o está incompleto."""


@dataclass
class ConfigAgente:
    id: str
    nombre: str
    rol: str
    objetivo: str
    tono: str
    reglas_comportamiento: List[str]
    skills_permitidas: List[str]
    respuesta: dict
    mensajes: dict


def _leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"no se encontró '{ruta}'")
    except json.JSONDecodeError as e:
        raise ConfigError(f"'{ruta}' no es un JSON válido (línea {e.lineno}, columna {e.colno}): {e.msg}")


def cargar_sistema(ruta):
    datos = _leer_json(ruta)
    if not isinstance(datos, dict):
        raise ConfigError("config/sistema.json debe contener un objeto")
    if datos.get("confirmar_efectos") not in POLITICAS_EFECTOS:
        raise ConfigError(f"'confirmar_efectos' debe ser uno de: {', '.join(POLITICAS_EFECTOS)}")
    filas = datos.get("max_filas")
    if not isinstance(filas, int) or isinstance(filas, bool) or filas <= 0:
        raise ConfigError("'max_filas' debe ser un entero mayor que 0")
    datos.setdefault("decisiones", [])
    return datos


def cargar_agente(ruta, registro):
    datos = _leer_json(ruta)
    nombre_archivo = os.path.basename(ruta)
    if not isinstance(datos, dict):
        raise ConfigError(f"{nombre_archivo}: debe contener un objeto")
    for clave in CLAVES_AGENTE:
        if clave not in datos:
            raise ConfigError(f"{nombre_archivo}: falta '{clave}'")
    if datos["id"] != os.path.splitext(nombre_archivo)[0]:
        raise ConfigError(f"{nombre_archivo}: 'id' debe coincidir con el nombre del archivo")
    if not datos["skills_permitidas"]:
        raise ConfigError(f"{nombre_archivo}: 'skills_permitidas' no puede estar vacía")
    for s in datos["skills_permitidas"]:
        if s not in registro:
            raise ConfigError(f"{nombre_archivo}: la skill '{s}' no existe en la carpeta de skills")
    for clave in CLAVES_RESPUESTA:
        if clave not in datos["respuesta"]:
            raise ConfigError(f"{nombre_archivo}: falta 'respuesta.{clave}'")
    for clave in MENSAJES_REQUERIDOS:
        if clave not in datos["mensajes"]:
            raise ConfigError(f"{nombre_archivo}: falta 'mensajes.{clave}'")
    return ConfigAgente(**{k: datos[k] for k in CLAVES_AGENTE})


def cargar_agentes(directorio, registro) -> Dict[str, ConfigAgente]:
    if not os.path.isdir(directorio):
        raise ConfigError(f"no existe la carpeta de agentes '{directorio}'")
    archivos = sorted(f for f in os.listdir(directorio) if f.endswith(".json"))
    if not archivos:
        raise ConfigError(f"no hay agentes definidos en '{directorio}'")
    return {os.path.splitext(f)[0]: cargar_agente(os.path.join(directorio, f), registro) for f in archivos}
