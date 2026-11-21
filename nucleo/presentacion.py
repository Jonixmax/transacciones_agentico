"""PRESENTACIÓN: formato de texto compartido por la CLI clásica y por las skills del agente."""
from decimal import Decimal


def dinero(valor):
    """Dinero siempre con 2 decimales y separador de miles: 1,234.50"""
    return format(valor, ",.2f")


def corto(texto, ancho):
    texto = str(texto)
    return texto if len(texto) <= ancho else texto[: ancho - 3] + "..."


ENCABEZADO_TX = (f" {'ID':<10} {'FUENTE':<9} {'MONTO':>13} {'MON.':<4} {'ESTADO':<8} FECHA (UTC)\n"
                 " " + "-" * 68)


def fila_tx(tx):
    return f" {corto(tx.id, 10):<10} {tx.source:<9} {dinero(tx.amount):>13} {tx.currency:<4} {tx.status:<8} {tx.timestamp}"


def tabla_tx(transacciones):
    """Líneas de texto de una tabla de transacciones (encabezado + filas)."""
    return ENCABEZADO_TX.split("\n") + [fila_tx(tx) for tx in transacciones]


def totales_por_moneda(transacciones):
    """{moneda: suma} de una lista de transacciones (las monedas no se mezclan)."""
    totales = {}
    for tx in transacciones:
        totales[tx.currency] = totales.get(tx.currency, Decimal("0")) + tx.amount
    return totales


def texto_totales(totales):
    return "  ".join(f"{m} {dinero(t)}" for m, t in sorted(totales.items()))
