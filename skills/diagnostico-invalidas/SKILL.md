---
name: diagnostico-invalidas
description: Explica por qué se rechazaron registros inválidos: resume los motivos agrupados, detalla un registro concreto, lista los registros con un tipo de problema y propone un plan de corrección priorizado, apoyándose en una guía de causas y soluciones. Úsala para auditar la calidad de los datos, no para consultar transacciones válidas.
metadata:
  palabras_clave: explica, explicame, explicar, motivo, motivos, porque, razon, razones, invalida, invalidas, invalido, invalidos, rechazo, rechazado, rechazados, rechazadas, rechazaron, error, errores, corregir, correccion, corrige, problema, problemas, plan, resumen, diagnostico, auditar, auditoria, registro, registros, descartados, descartadas
  efectos: ninguno
---

# Diagnóstico de registros inválidos

Audita los registros que el sistema **separó como inválidos** durante la normalización y explica, en lenguaje claro, qué falló y cómo arreglarlo. Solo lee datos: no corrige ni modifica nada.

## Cuándo usarla

- El usuario pregunta por qué se rechazaron registros, cuántos fueron o de qué tipo.
- El usuario quiere entender un registro concreto («explica el registro 7»).
- El usuario quiere saber qué hacer para recuperar los datos.
- **No** la uses para consultar o sumar transacciones válidas: eso es de `consulta-transacciones`.

## Parámetros

| Parámetro | Tipo | Descripción |
|---|---|---|
| `operacion` | texto | `resumen`, `detalle`, `por_motivo` o `plan` |
| `posicion` | entero | Número del registro en el archivo (con `detalle`) |
| `motivo` | texto | Palabra del tipo de problema, por ejemplo `fecha` o `monto` (con `por_motivo`) |

Si no se indica `operacion`: con `posicion` se usa `detalle`; con `motivo`, `por_motivo`; si no, `resumen`.

## Operaciones

- **resumen**: total rechazado, tipos de problema ordenados por frecuencia, y para cada uno su severidad, causa probable y cómo corregirlo.
- **detalle**: motivos de un registro, su explicación y el registro original. Sin `posicion`, se hace un `resumen`.
- **por_motivo**: los registros cuyo motivo contiene la palabra indicada.
- **plan**: los registros agrupados por el tipo de acción que requieren (corregir el dato, revisar con la fuente, ajustar las reglas o descartar), de mayor a menor cantidad.

## Pasos

1. Si no hay registros inválidos, dilo y termina: es una buena noticia, no un error.
2. Agrupa los motivos con `nucleo.metricas.categoria_motivo` (la misma agrupación que usan las métricas).
3. Busca cada categoría en `recursos/guia_motivos.json`. Si una categoría no está en la guía, usa la entrada genérica `otro`; **nunca inventes** una explicación.
4. Presenta el resultado y añade una recomendación breve.

## Casos borde y límites

- Un registro puede tener varios motivos; se muestran todos.
- La guía propone causas **probables**, no certezas: la decisión de corregir, descartar o ajustar reglas es del usuario.
- Esta skill no modifica los datos ni `reglas.json`.

## Ejemplos

- «resumen de los registros inválidos» → `resumen`
- «explica el registro 7» → `detalle`, `posicion=7`
- «qué registros tienen problemas de fecha» → `por_motivo`, `motivo=fecha`
- «plan de corrección» → `plan`

## Recursos

- `recursos/guia_motivos.json`: para cada tipo de rechazo, título, explicación, causa probable, corrección, severidad y tipo de acción. También describe cada tipo de acción.
- `recursos/vocabulario.json`: sinónimos de operaciones y de tipos de problema para el modo simulado.
