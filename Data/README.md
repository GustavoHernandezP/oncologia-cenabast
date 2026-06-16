# 🏥 Mercado Oncológico Chile — Mercado Público

Dashboard interactivo y extractor de datos de licitaciones oncológicas publicadas en la plataforma [Mercado Público](https://www.mercadopublico.cl) del gobierno de Chile.

---

## Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `dashboard.py` | Aplicación Streamlit — visualización y análisis |
| `extractor_cenabast_todos.py` | Extractor de datos desde la API de Mercado Público |
| `oncologia.db` | Base de datos SQLite (generada por el extractor, no se sube a GitHub) |
| `parchear_items.py` | Script de corrección puntual (ya integrado en el extractor) |
| `setup_github.sh` | Inicialización del repositorio git (solo se usa una vez) |
| `push_github.sh` | Script para publicar cambios a GitHub |

---

## Requisitos

```bash
pip install streamlit pandas plotly openpyxl requests
```

---

## 1 — Extractor de datos

### ¿Qué hace?
Consulta la API pública de Mercado Público, filtra licitaciones relacionadas con medicamentos oncológicos (por palabras clave en nombre y descripción), y guarda todo en `oncologia.db` (SQLite).

En cada ejecución:
- **Fase 1:** busca licitaciones nuevas día a día desde la última fecha procesada
- **Fase 2:** actualiza el detalle e ítems de licitaciones aún en estado no-final (Publicada, Cerrada, Suspendida)
- Al finalizar genera un Excel con resúmenes por estado, medicamento, laboratorio, organismo y región

### Modos de operación

**Modo incremental** (uso normal — procesa solo lo nuevo desde la última ejecución):
```bash
cd ".../Data"
python3 extractor_cenabast_todos.py
```

**Modo rango** (re-extrae un período específico, por ejemplo para corregir datos):

Editar al inicio del script:
```python
MODO_RANGO  = True
FECHA_DESDE = date(2025, 12, 1)
FECHA_HASTA = date(2026, 3, 31)
```
Luego ejecutar normalmente. Los registros de ese período se sobreescriben.

### Rate-limit
Si aparece `⏳ rate-limit 20s...` durante la ejecución, la API está limitando las consultas. El script espera automáticamente y reintenta. Si ocurre con frecuencia, aumentar las pausas al inicio del archivo:

```python
PAUSA_LISTA   = 2.5   # segundos entre consultas de lista
PAUSA_DETALLE = 1.5   # segundos entre consultas de detalle
```

### Campos capturados

**Licitaciones (46 columnas)**

| Grupo | Campos |
|---|---|
| Identificación | Codigo, Nombre, Medicamento, Descripcion |
| Estado y tipo | Estado, CodigoEstado, Tipo, Tipo_desc, TipoConvocatoria |
| Montos | Moneda, Monto_estimado, Estimacion, Modalidad_pago |
| Fechas | Fecha_publicacion, Fecha_cierre, Fecha_adjudicacion, Fecha_inicio_contrato, Fecha_fin_contrato, Fecha_est_firma, Fecha_pub_adjudicacion |
| Contrato | Dias_cierre, Duracion_contrato, Renovable, Subcontratacion, RequiereFirmaContrato, PermisoContratacion |
| Adjudicación | N_oferentes, Tipo_acto_adj, URL_acta, Total_items_declarados |
| Comprador | Organismo, Codigo_organismo, RUT_organismo, Unidad_compra, Direccion, Comuna, Region, Responsable, Cargo_responsable |
| Responsable contrato | Nombre_resp_contrato, Email_resp_contrato, Fono_resp_contrato |
| Otros | Cantidad_reclamos, TomaRazon |

**Ítems (19 columnas)**

| Grupo | Campos |
|---|---|
| Licitación | Codigo_licitacion, Estado_licitacion, Organismo, Region |
| Producto | CodigoProducto, CodigoCategoria, Categoria, NombreProducto, Descripcion, UnidadMedida |
| Cantidades | Cantidad_licitada, Cantidad_adjudicada¹ |
| Adjudicación | RUT_proveedor, Proveedor, Monto_unitario, Monto_total_item |
| Inferido | Medicamento |

> ¹ Cuando la API no devuelve `CantidadAdjudicada` (frecuente en convenios marco), el extractor usa `Cantidad_licitada` como estimación.

---

## 2 — Dashboard Streamlit

### Ejecución local
```bash
cd ".../Data"
streamlit run dashboard.py
```
Abre automáticamente en `http://localhost:8501`

### Pestañas del dashboard

**📊 Resumen**
Métricas generales por año: total de licitaciones, monto estimado (con indicador de variación respecto al año anterior), distribución por estado. Activa el toggle *Solo medicamentos* para filtrar únicamente licitaciones con medicamento identificado.

**🔍 Análisis comparativo**
Comparación entre dos años seleccionables: gráfico de distribución de montos (box plot), monto total por organismo (top 15, horizontal), top 10 licitaciones por monto de cada año. Solo adjudicadas: montos totales con delta entre años.

**💊 Medicamentos & Labs**
- Top 15 medicamentos y laboratorios por monto adjudicado (ítems reales)
- Tabla de laboratorios: haz clic en una fila para ver todas sus licitaciones y métricas
- Dentro de cada medicamento: detalle de ítems, cantidades y proveedores

**🔓 Procesos abiertos**
Licitaciones en estado Publicada o Suspendida: métricas de monto estimado total, tabla filtrable por organismo y región.

**📋 Todos los procesos**
Tabla completa de licitaciones con búsqueda libre, filtro por estado y año. Tabla de ítems con búsqueda por medicamento.

**🗄️ Modelo de datos**
Diagrama de la base de datos (tablas y relaciones) + acceso a los datos crudos de licitaciones e ítems con búsqueda y filtros.

### Nota sobre formato numérico
El dashboard usa formato chileno (`.` como separador de miles, `,` como decimal). Las columnas de monto en tablas son numéricas para permitir ordenamiento correcto.

---

## 3 — Control de versiones (GitHub)

### Primera vez
```bash
# 1. Editar REPO_URL en setup_github.sh con tu URL de GitHub
# 2. Ejecutar:
chmod +x setup_github.sh push_github.sh
./setup_github.sh
```

### Guardar cambios
```bash
./push_github.sh "descripción del cambio"
```

El archivo `.gitignore` excluye automáticamente `oncologia.db` y los Excel generados.

---

## Fuente de datos

API pública de [Mercado Público Chile](https://api.mercadopublico.cl) — requiere ticket de autenticación gratuito disponible en [developers.mercadopublico.cl](https://developers.mercadopublico.cl).
