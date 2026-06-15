# Extractor Oncológico — CENABAST / Mercado Público

## Qué hace
Extrae **todas las licitaciones adjudicadas de medicamentos oncológicos**
desde la API de Mercado Público, filtrando por:
- 15 organismos compradores (CENABAST + hospitales oncológicos clave)
- 16 búsquedas por nombre de medicamento
- 60+ palabras clave oncológicas sobre nombre/descripción

## Período extraído
01-01-2023 → hoy (configurable en el script)

## Instalación
```bash
pip install requests pandas openpyxl
```

## Ejecución
```bash
python extractor_cenabast.py
```

## Salida: Excel con 4 hojas
| Hoja | Contenido |
|---|---|
| Licitaciones | Detalle completo, una fila por licitación |
| Por organismo | Monto y cantidad por hospital/CENABAST |
| Por proveedor (lab) | Top 50 laboratorios por monto adjudicado |
| Por medicamento | Frecuencia y monto por principio activo |

## Columnas principales
- Organismo, Código, Nombre de la licitación
- Estado, Monto estimado (CLP)
- Fecha publicación, Fecha adjudicación
- Proveedor (laboratorio), RUT Proveedor

## Fuentes
- API: https://api.mercadopublico.cl
- Ticket: BE0418D7-09FD-4DD0-8DEC-C99030548482
- Documentación: http://api.mercadopublico.cl/modules/api.aspx
