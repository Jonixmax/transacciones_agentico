# Reporte de transacciones

- **Archivo analizado:** transacciones_con_errores.json
- **Generado:** 2026-11-20 02:01

## Resumen

Se procesaron **24** registros: **7** válidos (29.2%) y **17** inválidos.

## Transacciones válidas por estado

- SUCCESS: 5
- FAILED: 2
- PENDING: 0

## Totales por moneda

| Moneda | Cantidad | Total | Confirmado (SUCCESS) |
|---|---:|---:|---:|
| EUR | 2 | 1,294.56 | 1,234.56 |
| USD | 5 | 2,270.00 | 2,230.00 |

## Motivos de rechazo

- 2 × monto no numérico
- 2 × falta campo obligatorio
- 2 × monto no positivo
- 2 × fecha no reconocida
- 1 × moneda no soportada
- 1 × id duplicado
- 1 × fecha con tipo no soportado
- 1 × monto con más de 2 decimales
- 1 × moneda no determinable
- 1 × fuente no reconocida
- 1 × el registro no es un objeto JSON
- 1 × fuente ambigua
- 1 × conflicto de moneda

## Avisos de normalización

- Registro #8 (id e_008): estado no reconocido 'refunded': se asignó FAILED
- Registro #9 (id e_009): estado ausente: se asignó FAILED

---
*Reporte generado por el agente del sistema de transacciones.*
