"""FILTROS: criterios de exploración sobre las transacciones normalizadas."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class Filtros:
    estado: Optional[str] = None
    moneda: Optional[str] = None
    fuente: Optional[str] = None
    monto_min: Optional[Decimal] = None
    monto_max: Optional[Decimal] = None
    fecha_desde: Optional[str] = None     # 'AAAA-MM-DD'
    fecha_hasta: Optional[str] = None     # 'AAAA-MM-DD'

    def activos(self):
        nombres = {"estado": "estado", "moneda": "moneda", "fuente": "fuente", "monto_min": "monto >=",
                   "monto_max": "monto <=", "fecha_desde": "desde", "fecha_hasta": "hasta"}
        return [f"{etiqueta}: {getattr(self, campo)}" for campo, etiqueta in nombres.items()
                if getattr(self, campo) is not None]

    def limpiar(self):
        for campo in self.__dataclass_fields__:
            setattr(self, campo, None)


def aplicar(transacciones, f):
    """Devuelve las transacciones que cumplen TODOS los filtros activos."""
    salida = []
    for tx in transacciones:
        if f.estado and tx.status != f.estado:
            continue
        if f.moneda and tx.currency != f.moneda:
            continue
        if f.fuente and tx.source != f.fuente:
            continue
        if f.monto_min is not None and tx.amount < f.monto_min:
            continue
        if f.monto_max is not None and tx.amount > f.monto_max:
            continue
        # Los timestamps tienen formato fijo (UTC), así que se pueden comparar como texto.
        if f.fecha_desde and tx.timestamp < f"{f.fecha_desde}T00:00:00Z":
            continue
        if f.fecha_hasta and tx.timestamp > f"{f.fecha_hasta}T23:59:59Z":
            continue
        salida.append(tx)
    return salida


# ----------------------------------------------------------------------
# Análisis y validación de los valores de los filtros.
# Antes esta lógica estaba dentro de la CLI; se extrajo aquí para que la CLI y las
# skills de los agentes validen EXACTAMENTE igual (sin duplicar código).
# Cada analizador devuelve None si el texto está vacío (= quitar el filtro) o lanza
# ValueError con un mensaje listo para mostrar al usuario.
# ----------------------------------------------------------------------
def parsear_estado(reglas, texto):
    texto = str(texto).strip()
    if not texto:
        return None
    valor = texto.upper()
    if valor not in reglas.estados:
        raise ValueError(f"Estado no válido: '{texto}'. Usa {', '.join(reglas.estados)}.")
    return valor


def parsear_moneda(reglas, texto):
    texto = str(texto).strip()
    if not texto:
        return None
    valor = texto.upper()
    if valor not in reglas.monedas:
        raise ValueError(f"Moneda no soportada: '{texto}'. Usa {', '.join(sorted(reglas.monedas))}.")
    return valor


def parsear_fuente(reglas, texto):
    texto = str(texto).strip()
    if not texto:
        return None
    coincidencias = {n.lower(): n for n in reglas.fuentes}
    if texto.lower() not in coincidencias:
        raise ValueError(f"Fuente no reconocida: '{texto}'. Usa {', '.join(sorted(reglas.fuentes))}.")
    return coincidencias[texto.lower()]


def parsear_monto(texto):
    texto = str(texto).strip()
    if not texto:
        return None
    try:
        numero = Decimal(texto.replace(",", "."))
        if not numero.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        raise ValueError("Monto no válido: escribe un número, por ejemplo 100 o 99.50.")
    return numero


def parsear_fecha(texto):
    texto = str(texto).strip()
    if not texto:
        return None
    try:
        datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Fecha no válida: usa el formato AAAA-MM-DD (por ejemplo 2025-03-10).")
    return texto


def construir_filtros(reglas, **criterios):
    """Crea un Filtros a partir de valores en texto/número. Devuelve (Filtros, lista_de_errores).

    Acepta: estado, moneda, fuente, monto_min, monto_max, fecha_desde, fecha_hasta.
    Un criterio None se ignora. Un criterio desconocido o inválido se informa como error.
    """
    analizadores = {
        "estado": lambda v: parsear_estado(reglas, v),
        "moneda": lambda v: parsear_moneda(reglas, v),
        "fuente": lambda v: parsear_fuente(reglas, v),
        "monto_min": parsear_monto,
        "monto_max": parsear_monto,
        "fecha_desde": parsear_fecha,
        "fecha_hasta": parsear_fecha,
    }
    filtros = Filtros()
    errores = []
    for nombre, valor in criterios.items():
        if nombre not in analizadores:
            errores.append(f"Criterio desconocido: '{nombre}'.")
            continue
        if valor is None:
            continue
        if isinstance(valor, bool):
            errores.append(f"Valor no válido para '{nombre}'.")
            continue
        try:
            setattr(filtros, nombre, analizadores[nombre](valor))
        except ValueError as e:
            errores.append(str(e))
    if filtros.monto_min is not None and filtros.monto_max is not None and filtros.monto_min > filtros.monto_max:
        errores.append("El monto mínimo es mayor que el máximo.")
    if filtros.fecha_desde and filtros.fecha_hasta and filtros.fecha_desde > filtros.fecha_hasta:
        errores.append("La fecha 'desde' es posterior a la fecha 'hasta'.")
    return filtros, errores
