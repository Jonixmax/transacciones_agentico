"""Skill consulta-transacciones (ver SKILL.md). Solo lee datos; no tiene efectos."""
import json

from agentes.skills import ResultadoSkill
from nucleo import filtros as modulo_filtros
from nucleo import presentacion as pres
from decimal import Decimal

OPERACIONES = ("listar", "contar", "totales", "buscar")

PARAMETROS = {
    "operacion": {"tipo": "texto", "descripcion": "listar (por defecto), contar, totales o buscar"},
    "estado": {"tipo": "texto", "descripcion": "SUCCESS, FAILED o PENDING"},
    "moneda": {"tipo": "texto", "descripcion": "código de moneda soportado (USD, EUR, GBP)"},
    "fuente": {"tipo": "texto", "descripcion": "fuente de origen, por ejemplo fuente_B"},
    "monto_min": {"tipo": "texto_o_numero", "descripcion": "monto mínimo (inclusivo)"},
    "monto_max": {"tipo": "texto_o_numero", "descripcion": "monto máximo (inclusivo)"},
    "fecha_desde": {"tipo": "texto", "descripcion": "fecha inicial AAAA-MM-DD (inclusiva)"},
    "fecha_hasta": {"tipo": "texto", "descripcion": "fecha final AAAA-MM-DD (inclusiva)"},
    "id": {"tipo": "texto", "descripcion": "id de la transacción a buscar (con operacion=buscar)"},
}


def _invalidas_con_id(sesion, buscado):
    """Posiciones de registros inválidos cuyo id (en cualquier fuente) coincide con el buscado."""
    posiciones = []
    for inv in sesion.resultado.invalid:
        if not isinstance(inv.raw, dict):
            continue
        for cfg in sesion.reglas.fuentes.values():
            valor = inv.raw.get(cfg["campo_identificador"])
            if valor is not None and str(valor).strip().lower() == buscado.lower():
                posiciones.append(inv.position)
    return posiciones


def _buscar(sesion, buscado):
    buscado = (buscado or "").strip()
    if not buscado:
        return ResultadoSkill(False, "Indica el id de la transacción que quieres buscar.")
    encontradas = [tx for tx in sesion.resultado.valid if tx.id.lower() == buscado.lower()]
    if not encontradas:
        posiciones = _invalidas_con_id(sesion, buscado)
        if posiciones:
            lugar = ", ".join(f"#{p}" for p in posiciones)
            return ResultadoSkill(True, f"No hay una transacción válida con id '{buscado}', pero aparece en el registro inválido {lugar}.",
                                  recomendacion="Pide al agente Auditor que explique ese registro.")
        return ResultadoSkill(True, f"No hay ninguna transacción con id '{buscado}' entre las válidas.")
    lineas = []
    for tx in encontradas:
        lineas.append(f"Transacción {tx.id}:")
        for campo, valor in tx.to_dict().items():
            lineas.append(f"  {campo:<10} {pres.dinero(tx.amount) if campo == 'amount' else valor}")
        original = sesion.resultado.raw_by_key.get((tx.source, tx.id))
        lineas.append("  original:  " + json.dumps(original, ensure_ascii=False))
    return ResultadoSkill(True, "\n".join(lineas), datos={"ids": [t.id for t in encontradas]})


def ejecutar(sesion, operacion="listar", id=None, **criterios):
    if operacion not in OPERACIONES:
        return ResultadoSkill(False, f"Operación no válida: '{operacion}'. Usa {', '.join(OPERACIONES)}.")
    if operacion == "buscar":
        return _buscar(sesion, id)

    filtros, errores = modulo_filtros.construir_filtros(sesion.reglas, **criterios)
    if errores:
        return ResultadoSkill(False, "No ejecuté la consulta porque hay criterios inválidos:\n  - " + "\n  - ".join(errores))

    validas = sesion.resultado.valid
    visibles = modulo_filtros.aplicar(validas, filtros)
    criterios_txt = ", ".join(filtros.activos()) or "sin filtros"
    datos = {"coincidencias": len(visibles), "total_validas": len(validas), "ids": [t.id for t in visibles]}

    if not visibles:
        return ResultadoSkill(True, f"No hay transacciones válidas que cumplan: {criterios_txt}.", datos=datos)

    if operacion == "contar":
        return ResultadoSkill(True, f"{len(visibles)} de {len(validas)} transacciones válidas cumplen: {criterios_txt}.", datos=datos)

    if operacion == "totales":
        filas = {}
        for tx in visibles:
            f = filas.setdefault(tx.currency, {"cantidad": 0, "total": Decimal("0"), "confirmado": Decimal("0")})
            f["cantidad"] += 1
            f["total"] += tx.amount
            if tx.status == "SUCCESS":
                f["confirmado"] += tx.amount
        lineas = [f"{len(visibles)} transacciones cumplen: {criterios_txt}.",
                  f"  {'Moneda':<8}{'Cant.':>6}{'Total':>16}{'Confirmado (SUCCESS)':>24}"]
        for moneda, f in sorted(filas.items()):
            lineas.append(f"  {moneda:<8}{f['cantidad']:>6}{pres.dinero(f['total']):>16}{pres.dinero(f['confirmado']):>24}")
        datos["por_moneda"] = {m: {k: (str(v) if isinstance(v, Decimal) else v) for k, v in f.items()} for m, f in filas.items()}
        return ResultadoSkill(True, "\n".join(lineas), datos=datos)

    # listar
    mostradas = visibles[:sesion.max_filas]
    lineas = [f"{len(visibles)} transacciones válidas cumplen: {criterios_txt}."]
    lineas += pres.tabla_tx(mostradas)
    if len(visibles) > len(mostradas):
        lineas.append(f"(se muestran las primeras {len(mostradas)} de {len(visibles)})")
    lineas.append(f"Suma por moneda de lo mostrado: {pres.texto_totales(pres.totales_por_moneda(mostradas))}")
    datos["mostradas"] = len(mostradas)
    return ResultadoSkill(True, "\n".join(lineas), datos=datos)
