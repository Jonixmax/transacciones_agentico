---
name: consulta-transacciones
description: Lista, filtra, cuenta y suma transacciones válidas ya normalizadas, por estado, moneda, fuente, rango de montos o rango de fechas, y busca una transacción por su id. Úsala para consultas sobre las transacciones aceptadas; no sirve para explicar registros rechazados.
metadata:
  palabras_clave: lista, listar, muestra, muestrame, mostrar, ver, filtrar, filtra, busca, buscar, cuantas, cuantos, cuanto, suman, suma, total, totales, transaccion, transacciones, monto, montos, moneda, fuente, id, detalle, mayores, menores, exitosas, fallidas, pendientes
  efectos: ninguno
---

# Consulta de transacciones

Consulta las transacciones **válidas** que ya pasaron por la normalización. Solo lee datos: no modifica nada ni escribe archivos.

## Cuándo usarla

- El usuario quiere ver, filtrar, contar o sumar transacciones aceptadas.
- El usuario busca una transacción concreta por su id.
- **No** la uses para explicar por qué un registro fue rechazado: eso es de `diagnostico-invalidas`.

## Parámetros

| Parámetro | Tipo | Descripción |
|---|---|---|
| `operacion` | texto | `listar` (por defecto), `contar`, `totales` o `buscar` |
| `estado` | texto | `SUCCESS`, `FAILED` o `PENDING` |
| `moneda` | texto | Código soportado por `reglas.json` (USD, EUR, GBP) |
| `fuente` | texto | Nombre de la fuente, por ejemplo `fuente_B` |
| `monto_min` / `monto_max` | texto o número | Límites **inclusivos** del monto |
| `fecha_desde` / `fecha_hasta` | texto | Formato `AAAA-MM-DD`, ambos días **incluidos** |
| `id` | texto | Identificador a buscar (solo con `buscar`) |

Todos los filtros son opcionales y se combinan con **Y** (deben cumplirse todos).

## Pasos

1. Verifica que la operación sea válida.
2. Si es `buscar`, exige un `id`; busca sin distinguir mayúsculas y muestra la transacción normalizada junto con su registro original.
3. Si no, valida los filtros con `nucleo.filtros.construir_filtros` (la misma validación que usa la CLI clásica). Si algún valor es inválido, **no ejecutes la consulta**: informa todos los errores.
4. Aplica los filtros sobre las transacciones válidas y presenta el resultado según la operación.

## Formato de salida

- `listar`: cuántas coinciden, una tabla con las primeras filas (límite configurable, 10 por defecto) y la suma por moneda de lo mostrado.
- `contar`: «N de M transacciones válidas cumplen: filtros».
- `totales`: por moneda, la cantidad, el total de todas las coincidentes y el monto confirmado (solo `SUCCESS`).
- `buscar`: campos normalizados y registro original; si no existe entre las válidas, indica si el id aparece en un registro inválido.

## Casos borde y límites

- Las monedas **no se mezclan ni se convierten**: los totales siempre van por moneda.
- Sin coincidencias, informa los filtros aplicados en lugar de mostrar una tabla vacía.
- Un rango de montos o de fechas invertido es un error, no un resultado vacío.
- Los números se escriben sin separador de miles (`1000`, no `1,000`).

## Ejemplos

- «lista las transacciones exitosas» → `listar`, `estado=SUCCESS`
- «cuántas transacciones en euros hay» → `contar`, `moneda=EUR`
- «cuánto suman las transacciones en dólares» → `totales`, `moneda=USD`
- «transacciones mayores a 1000» → `listar`, `monto_min=1000`
- «busca el id A-77» → `buscar`, `id=A-77`

## Recursos

- `recursos/vocabulario.json`: sinónimos (estados, monedas, operaciones) que el modo simulado usa para interpretar el texto.
