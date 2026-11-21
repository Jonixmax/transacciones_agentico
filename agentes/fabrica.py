"""FÁBRICA: ensambla el sistema a partir de los archivos de configuración y las skills."""
import os
from dataclasses import dataclass
from typing import Any, Dict

from nucleo import config as config_motor

from .agente import Agente
from .config_agentes import cargar_agentes, cargar_sistema
from .llm import ClienteGemini, ModoSimulado
from .sesion import Sesion
from .skills import cargar_skills

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Ecosistema:
    sistema: dict
    registro: Any
    configs: Dict[str, Any]
    agentes: Dict[str, Agente]
    sesion: Sesion


def construir(raiz=RAIZ, cliente=None, sesion=None, reglas=None):
    """Carga sistema, skills y agentes. Lanza ConfigError o SkillError con un mensaje claro si algo falla."""
    sistema = cargar_sistema(os.path.join(raiz, "config", "sistema.json"))
    registro = cargar_skills(os.path.join(raiz, sistema.get("carpeta_skills", "skills")))
    configs = cargar_agentes(os.path.join(raiz, "config", "agentes"), registro)
    sesion = sesion or Sesion(reglas=reglas or config_motor.cargar_reglas(), max_filas=sistema["max_filas"])
    if cliente is None:
        cliente = ClienteGemini() if os.getenv("GEMINI_API_KEY") else ModoSimulado()
    agentes = {i: Agente(c, registro, cliente, sesion, sistema["confirmar_efectos"], configs) for i, c in configs.items()}
    return Ecosistema(sistema, registro, configs, agentes, sesion)
