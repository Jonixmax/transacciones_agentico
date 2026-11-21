---
name: exportar-reporte
description: Genera un reporte en Markdown y los archivos JSON de transacciones normalizadas, registros inválidos y métricas dentro de una carpeta de salida. Escribe archivos, por lo que siempre requiere confirmación del usuario antes de ejecutarse.
metadata:
  palabras_clave: exporta, exportar, exportame, reporte, informe, guarda, guardar, genera, generar, archivo, archivos, json, markdown, descarga, descargar
  efectos: escribe_archivos
---

# Exportar reporte

Escribe en disco los resultados del procesamiento actual. Es la **única skill con efectos** del sistema, por eso está sujeta a la política de confirmación.

## Cuándo usarla

- El usuario pide un reporte, un informe, exportar o guardar los resultados.
- No la uses para consultar datos en pantalla: para eso están `consulta-transacciones` y `diagnostico-invalidas`.

## Parámetros

| Parámetro | Tipo | Descripción |
|---|---|---|
| `carpeta` | texto | Carpeta de salida **relativa** (por defecto `salida_agente`) |

## Qué escribe

| Archivo | Contenido |
|---|---|
| `reporte.md` | Resumen legible: totales, estados, monedas, motivos de rechazo y avisos (plantilla en `recursos/`) |
| `normalizadas.json` | Transacciones válidas en el esquema común |
| `invalidas.json` | Registros inválidos con su original y sus motivos |
| `metricas.json` | Métricas calculadas |

## Reglas de seguridad

1. **Siempre `previsualizar` antes de `ejecutar`**: el usuario ve qué archivos se escribirán, dónde, y cuáles se sobrescribirán, y debe confirmar.
2. **Solo rutas relativas dentro de la carpeta de trabajo.** Se rechazan rutas absolutas, `..`, `~` y unidades de disco, para que ni una instrucción mal interpretada pueda escribir fuera del proyecto.
3. Si no hay datos cargados, no se hace nada.
4. Un error de escritura se informa; nunca se ignora.

## Pasos

1. Resuelve y valida la carpeta de destino (reglas de seguridad).
2. Arma el contenido con `nucleo.exportacion.armar_contenido` (el mismo código que usa la CLI clásica).
3. Escribe los tres JSON y genera `reporte.md` a partir de la plantilla.
4. Informa cuántos archivos se escribieron y dónde.

## Recursos

- `recursos/plantilla_reporte.md`: plantilla del reporte con marcadores `{{...}}`.
