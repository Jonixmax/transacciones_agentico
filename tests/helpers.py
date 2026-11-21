"""Utilidades comunes de las pruebas de la capa agéntica."""
import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from agentes import fabrica
from agentes.llm import ClienteLLM
from agentes.sesion import Sesion
from nucleo import config as config_motor

DATOS = os.path.join(RAIZ, "datos")
REGLAS = config_motor.cargar_reglas()


def ruta_datos(nombre):
    return os.path.join(DATOS, nombre)


def crear_sesion(archivo=None, salida=None, max_filas=10):
    s = Sesion(reglas=REGLAS, directorio_salida=salida or os.getcwd(), max_filas=max_filas)
    if archivo:
        s.cargar_archivo(ruta_datos(archivo))
    return s


def crear_ecosistema(archivo=None, salida=None, cliente=None):
    eco = fabrica.construir(sesion=crear_sesion(archivo, salida), cliente=cliente)
    return eco


class ClienteFalso(ClienteLLM):
    """Cliente que devuelve una acción fija (o falla): simula un modelo que se equivoca."""

    def __init__(self, accion=None, error=None):
        self.accion, self.error = accion, error

    def decidir(self, prompt_sistema, historial, catalogo):
        if self.error:
            raise self.error
        return self.accion

    def redactar(self, prompt_sistema, historial, resultado, comportamiento):
        return resultado.texto
