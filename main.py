"""
Sistema de transacciones con agentes personalizados y skills propias.

Uso:
    python main.py                                   chat con el agente Analista
    python main.py datos/transacciones_con_errores.json
    python main.py --agente auditor datos/transacciones_con_errores.json
    python main.py clasico [archivo]                 CLI clásica con menú (sin agentes)

Estructura:
    nucleo/      motor: reglas, normalización, validación, métricas, filtros, exportación
    skills/      capacidades del agente (cada una: SKILL.md + skill.py + recursos/)
    config/      sistema.json y agentes/*.json (rol, tono, reglas y skills de cada agente)
    agentes/     runtime: cargador de skills, guardas, cliente LLM, agente y fábrica
    chat_agente.py   interfaz de conversación        interfaz_clasica.py   CLI con menú
"""
import sys

from agentes import fabrica
from agentes.config_agentes import ConfigError
from agentes.skills import SkillError
from chat_agente import Chat
from nucleo.config import ReglasError, cargar_reglas


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    modo, agente = "chat", "analista"
    llm_real = None
    if "--llm" in argv:
        i = argv.index("--llm")
        if i + 1 >= len(argv):
            print("Error: --llm necesita 'gemini' o 'simulado'.")
            return 1
        llm_real = argv[i + 1].lower()
        if llm_real not in ("gemini", "simulado"):
            print("Error: modo LLM desconocido. Usa 'gemini' o 'simulado'.")
            return 1
        del argv[i:i + 2]
    if argv and argv[0] in ("chat", "clasico"):
        modo = argv.pop(0)
    if "--agente" in argv:
        i = argv.index("--agente")
        if i + 1 >= len(argv):
            print("Error: --agente necesita un nombre (por ejemplo: --agente auditor).")
            return 1
        agente = argv[i + 1]
        del argv[i:i + 2]
    ruta = argv[0] if argv else None

    try:
        if modo == "clasico":
            from interfaz_clasica import Interfaz
            Interfaz(cargar_reglas()).ejecutar(ruta)
            return 0
        if llm_real == "gemini":
            from agentes.llm import ClienteGemini
            cliente = ClienteGemini()
        elif llm_real == "simulado":
            from agentes.llm import ModoSimulado
            cliente = ModoSimulado()
        else:
            cliente = None
        eco = fabrica.construir(cliente=cliente)
    except (ReglasError, ConfigError, SkillError, ValueError) as e:
        print(f"Error de configuración: {e}")
        return 1
    if agente not in eco.agentes:
        print(f"Error: no existe el agente '{agente}'. Disponibles: {', '.join(eco.agentes)}.")
        return 1
    Chat(eco, agente).ejecutar(ruta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
