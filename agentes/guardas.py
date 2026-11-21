"""
GUARDAS: validan la acción que propone el modelo ANTES de ejecutar nada.

Un modelo (simulado o real) puede equivocarse o ser manipulado. Por eso el agente no
ejecuta a ciegas: la acción debe tener forma válida, apuntar a una skill que exista y esté
permitida para ese agente, y usar solo argumentos declarados, con el tipo correcto.
"""

TIPOS_ACCION = ("skill", "saludo", "ayuda", "aclarar", "fuera_de_alcance", "no_entendido")


class AccionInvalida(Exception):
    """La acción propuesta por el modelo no es segura o no está bien formada."""


def _tipo_correcto(valor, tipo):
    if tipo == "texto":
        return isinstance(valor, str)
    if tipo == "entero":
        return isinstance(valor, int) and not isinstance(valor, bool)
    if tipo == "texto_o_numero":
        return isinstance(valor, (str, int, float)) and not isinstance(valor, bool)
    return False


def validar_accion(accion, registro, permitidas):
    """Devuelve la acción si es válida; si no, lanza AccionInvalida con el motivo."""
    if not isinstance(accion, dict) or "accion" not in accion:
        raise AccionInvalida("la respuesta del modelo no tiene el formato esperado (falta 'accion')")
    tipo = accion["accion"]
    if tipo not in TIPOS_ACCION:
        raise AccionInvalida(f"tipo de acción desconocido: '{tipo}'")
    if tipo == "fuera_de_alcance" and accion.get("skill") not in registro:
        raise AccionInvalida("'fuera_de_alcance' debe indicar una skill existente")
    if tipo != "skill":
        return accion

    nombre = accion.get("skill")
    if nombre not in registro:
        raise AccionInvalida(f"la skill '{nombre}' no existe")
    if nombre not in permitidas:
        raise AccionInvalida(f"la skill '{nombre}' no está permitida para este agente")
    args = accion.get("args", {})
    if not isinstance(args, dict):
        raise AccionInvalida("'args' debe ser un objeto")
    esquema = registro.get(nombre).parametros
    for clave, valor in args.items():
        if clave not in esquema:
            raise AccionInvalida(f"argumento no declarado en la skill '{nombre}': '{clave}'")
        if not _tipo_correcto(valor, esquema[clave]["tipo"]):
            raise AccionInvalida(f"el argumento '{clave}' de '{nombre}' debe ser de tipo {esquema[clave]['tipo']}")
    return accion
