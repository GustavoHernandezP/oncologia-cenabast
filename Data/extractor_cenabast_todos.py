"""
Extractor oncológico — API Mercado Público  (modo incremental + SQLite)
Basado en: Diccionario de Datos Licitaciones API v1
Ticket: BE0418D7-09FD-4DD0-8DEC-C99030548482

Modos de operación
──────────────────
  Normal (incremental):
      python3 extractor_cenabast_todos.py
      → procesa desde la última fecha guardada hasta ayer

  Rango fijo (re-extracción):
      Ajustar MODO_RANGO = True y FECHA_DESDE / FECHA_HASTA
      → borra y re-importa solo licitaciones de ese período
      → aplica automáticamente parche de Cantidad_adjudicada

Campos capturados (todos los disponibles en la API v1)
───────────────────────────────────────────────────────
  Licitaciones : 46 columnas
  Ítems        : 19 columnas

Archivos de estado:
  estado_extractor.json  → última fecha procesada (solo modo incremental)
  oncologia.db           → base SQLite
"""

import requests
import pandas as pd
import json
import sqlite3
import time
import re
from datetime import date, timedelta
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────

TICKET                 = "BE0418D7-09FD-4DD0-8DEC-C99030548482"
BASE                   = "https://api.mercadopublico.cl/servicios/v1/publico"
PAUSA_LISTA            = 2.5
PAUSA_DETALLE          = 1.5

FECHA_INICIO_HISTORICO = date(2024, 1, 1)

# ── Modo rango (re-extracción acotada) ────────────────────────────────────────
# Cambiar a True para procesar solo el período indicado.
# Los registros existentes en ese rango se sobreescriben.
MODO_RANGO  = False
FECHA_DESDE = date(2024, 1, 1)
FECHA_HASTA = date(2026, 6, 17)

ESTADO_FILE = Path("estado_extractor.json")
DB_SQLITE   = Path("oncologia.db")

# Estados definitivos: no volverán a cambiar → no se re-consultan
ESTADOS_FINALES = {"Adjudicada", "Desierta", "Revocada"}

# ── Tablas de decodificación ──────────────────────────────────────────────────

TIPO_LIC = {
    "L1": "Pública <100 UTM",    "LE": "Pública 100-1.000 UTM",
    "LP": "Pública 1.000-2.000", "LQ": "Pública 2.000-5.000 UTM",
    "LR": "Pública >5.000 UTM",  "LS": "Pública Servicios Personales",
    "E2": "Privada <100 UTM",    "CO": "Privada 100-1.000 UTM",
    "B2": "Privada 1.000-2.000", "H2": "Privada 2.000-5.000 UTM",
    "I2": "Privada >5.000 UTM",
}
CONVOCATORIA   = {"1": "Abierta", "0": "Cerrada", 1: "Abierta", 0: "Cerrada"}
MONEDA         = {"CLP": "Peso CLP", "CLF": "UF", "USD": "Dólar", "UTM": "UTM", "EUR": "Euro"}
ESTIMACION     = {"1": "Presupuesto Disponible", "2": "Precio Referencial", "3": "No estimable"}
MODALIDAD_PAGO = {
    "1": "30 días", "2": "30-60-90 días", "3": "Al día", "4": "Anual",
    "5": "Bimensual", "6": "Contra entrega", "7": "Mensual",
    "8": "Estado de avance", "9": "Trimestral", "10": "60 días",
}
UNIDAD_TIEMPO  = {"1": "Horas", "2": "Días", "3": "Semanas", "4": "Meses", "5": "Años"}
TIPO_ACTO_ADJ  = {"1": "Autorización", "2": "Resolución", "3": "Acuerdo", "4": "Decreto", "5": "Otros"}
ESTADO_CODIGO  = {
    "5": "Publicada", "6": "Cerrada", "7": "Desierta",
    "8": "Adjudicada", "18": "Revocada", "19": "Suspendida",
}
ORDEN_ESTADOS = ["Adjudicada", "Publicada", "Cerrada", "Desierta", "Revocada", "Suspendida", "Otro"]

def dec(tabla, valor, fallback=None):
    v = str(valor) if valor is not None else ""
    return tabla.get(v, fallback if fallback is not None else v)

# ── Keywords oncológicos ──────────────────────────────────────────────────────

KEYWORDS = [
    "oncol", "quimio", "antineoplas",
    "cisplatino", "carboplatino", "oxaliplatino",
    "paclitaxel", "docetaxel", "vincristina", "vinblastina",
    "ciclofosfamida", "ifosfamida",
    "fluorouracilo", "5-fu", "capecitabina",
    "metotrexato", "metrotexato",
    "doxorubicina", "doxorrubicina", "epirubicina",
    "irinotecan", "topotecan", "gemcitabina", "pemetrexed",
    "bevacizumab", "trastuzumab", "rituximab", "cetuximab",
    "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab",
    "imatinib", "dasatinib", "erlotinib", "gefitinib", "lapatinib",
    "sorafenib", "lenvatinib", "cabozantinib", "sunitinib",
    "enzalutamida", "abiraterona", "bicalutamida",
    "tamoxifeno", "letrozol", "anastrozol", "exemestano",
    "bortezomib", "lenalidomida", "talidomida",
    "citarabina", "ara-c", "azacitidina", "leucovorina", "folinico",
    "filgrastim", "pegfilgrastim",
    "tumor maligno", "neoplasia", "leucemia", "linfoma", "mieloma",
]

MED_RE = re.compile(
    r"cisplatino|carboplatino|oxaliplatino|paclitaxel|docetaxel|vincristina|"
    r"ciclofosfamida|fluorouracilo|capecitabina|metotrexato|doxorubicina|"
    r"epirubicina|irinotecan|gemcitabina|pemetrexed|bevacizumab|trastuzumab|"
    r"rituximab|lenvatinib|imatinib|letrozol|tamoxifeno|anastrozol|"
    r"enzalutamida|abiraterona|bortezomib|lenalidomida|citarabina|filgrastim|"
    r"sorafenib|cabozantinib|sunitinib|pembrolizumab|nivolumab|dasatinib|"
    r"erlotinib|gefitinib|vinblastina|ifosfamida|topotecan|cetuximab|"
    r"atezolizumab|durvalumab|lapatinib|bicalutamida|exemestano|talidomida|"
    r"azacitidina|leucovorina|pegfilgrastim",
    re.IGNORECASE,
)

def es_oncologico(texto):
    t = (texto or "").lower()
    return any(k in t for k in KEYWORDS)

def inferir_med(texto):
    m = MED_RE.search(str(texto or ""))
    return m.group(0).lower() if m else ""

def s(v, maxlen=None):
    r = str(v).strip() if v is not None else ""
    return r[:maxlen] if maxlen else r

def f(v):
    """Convierte a float. Maneja None, cadenas vacías y formato chileno (1.234,56)."""
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        try:
            clean = str(v).strip().replace(".", "").replace(",", ".")
            return float(clean)
        except Exception:
            return 0.0

# ── HTTP helper ───────────────────────────────────────────────────────────────

def get_json(params, reintentos=3):
    url = f"{BASE}/licitaciones.json"
    for i in range(reintentos):
        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code == 429:
                print(" ⏳ rate-limit 20s...", end="", flush=True)
                time.sleep(20)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i < reintentos - 1:
                time.sleep(3)
            else:
                print(f" ⚠ {e}", end="")
    return {}

# ── Parsers ───────────────────────────────────────────────────────────────────

def parsear_licitacion(lic, verificar_oncologico=True):
    """
    Parsea una licitación. Captura todos los campos disponibles en API v1.
    Si verificar_oncologico=False no filtra keywords (para re-checks).
    """
    nombre = s(lic.get("Nombre"))
    desc   = s(lic.get("Descripcion"), 250)
    if verificar_oncologico and not es_oncologico(nombre + " " + desc):
        return None

    comp   = lic.get("Comprador") or {}
    if not isinstance(comp, dict):
        comp = {}

    fechas = lic.get("Fechas") or {}
    if not isinstance(fechas, dict):
        fechas = {}

    adj    = lic.get("Adjudicacion") or {}
    if not isinstance(adj, dict):
        adj = {}

    items_obj = lic.get("Items") or {}
    if not isinstance(items_obj, dict):
        items_obj = {}

    cod_estado = s(lic.get("CodigoEstado"))
    estado_txt = dec(ESTADO_CODIGO, cod_estado, s(lic.get("Estado")) or "Otro")

    return {
        # ── Identificación ────────────────────────────────────────────────────
        "Codigo":                  s(lic.get("CodigoExterno")),
        "Nombre":                  nombre,
        "Medicamento":             inferir_med(nombre),
        "Descripcion":             desc,

        # ── Estado y tipo ─────────────────────────────────────────────────────
        "Estado":                  estado_txt,
        "CodigoEstado":            cod_estado,
        "Tipo":                    s(lic.get("Tipo")),
        "Tipo_desc":               dec(TIPO_LIC, s(lic.get("Tipo"))),
        "CodigoTipo":              s(lic.get("CodigoTipo")),
        "Informada":               s(lic.get("Informada")),
        "TipoConvocatoria":        dec(CONVOCATORIA, lic.get("TipoConvocatoria")),

        # ── Montos ────────────────────────────────────────────────────────────
        "Moneda":                  dec(MONEDA, s(lic.get("Moneda")), s(lic.get("Moneda"))),
        "Monto_estimado":          f(lic.get("MontoEstimado")),
        "Estimacion":              dec(ESTIMACION, s(lic.get("Estimacion"))),
        "Modalidad_pago":          dec(MODALIDAD_PAGO, s(lic.get("Modalidad"))),

        # ── Fechas ────────────────────────────────────────────────────────────
        "Fecha_publicacion":       s(fechas.get("FechaPublicacion") or lic.get("FechaCierre")),
        "Fecha_cierre":            s(fechas.get("FechaCierre")      or lic.get("FechaCierre")),
        "Fecha_adjudicacion":      s(fechas.get("FechaAdjudicacion") or lic.get("FechaAdjudicacion")),
        "Fecha_inicio_contrato":   s(fechas.get("FechaInicio")),         # ← NUEVO
        "Fecha_fin_contrato":      s(fechas.get("FechaFinal")),          # ← NUEVO
        "Fecha_est_firma":         s(fechas.get("FechaEstimadaFirma")),  # ← NUEVO

        # ── Contrato ──────────────────────────────────────────────────────────
        "Dias_cierre":             s(lic.get("DiasCierreLicitacion")),
        "Duracion_contrato":       s(lic.get("TiempoDuracionContrato")),
        "Unidad_duracion":         dec(UNIDAD_TIEMPO, s(lic.get("UnidadTiempoDuracionContrato"))),
        "Renovable":               "Sí" if lic.get("EsRenovable")       == 1 else "No",
        "Subcontratacion":         "Sí" if lic.get("SubContratacion")   == 1 else "No",
        "RequiereFirmaContrato":   "Sí" if lic.get("RequiereFirmaContrato") == 1 else "No",  # ← NUEVO
        "PermisoContratacion":     s(lic.get("PermisoContratacion")),    # ← NUEVO

        # ── Adjudicación ──────────────────────────────────────────────────────
        "N_oferentes":             s(adj.get("NumeroOferentes")),
        "Tipo_acto_adj":           dec(TIPO_ACTO_ADJ, s(adj.get("Tipo"))),
        "Fecha_pub_adjudicacion":  s(adj.get("FechaPublicacion")),       # ← NUEVO
        "URL_acta":                s(adj.get("UrlActa") or adj.get("Url")),

        # ── Comprador ─────────────────────────────────────────────────────────
        "Organismo":               s(comp.get("NombreOrganismo")),
        "Codigo_organismo":        s(comp.get("CodigoOrganismo")),
        "RUT_organismo":           s(comp.get("RutUnidad")),
        "Unidad_compra":           s(comp.get("NombreUnidad")),
        "Direccion":               s(comp.get("DireccionUnidad")),
        "Comuna":                  s(comp.get("ComunaUnidad")),
        "Region":                  s(comp.get("RegionUnidad")),
        "Responsable":             s(comp.get("NombreUsuario")),
        "Cargo_responsable":       s(comp.get("CargoUsuario")),

        # ── Responsable contrato ──────────────────────────────────────────────
        "Nombre_resp_contrato":    s(lic.get("NombreResponsableContrato")),
        "Email_resp_contrato":     s(lic.get("EmailResponsableContrato")),
        "Fono_resp_contrato":      s(lic.get("FonoResponsableContrato")),

        # ── Otros ─────────────────────────────────────────────────────────────
        "Cantidad_reclamos":       s(lic.get("CantidadReclamos")),
        "TomaRazon":               "Sí" if lic.get("TomaRazon") == 1 else "No",
        "Total_items_declarados":  int(items_obj.get("Cantidad") or 0),  # ← NUEVO
    }


def parsear_items(codigo, detalle, estado_lic, organismo, region):
    """
    Parsea los ítems de una licitación.
    Cuando CantidadAdjudicada = 0 pero MontoUnitario > 0, usa Cantidad_licitada
    como estimación (la API de Mercado Público frecuentemente no retorna la cantidad
    adjudicada en convenios marco aunque sí el precio unitario).
    """
    items_obj = detalle.get("Items") or {}
    if not isinstance(items_obj, dict):
        return []
    listado = items_obj.get("Listado") or []
    if not isinstance(listado, list):
        return []

    filas = []
    for item in listado:
        if not isinstance(item, dict):
            continue
        adj = item.get("Adjudicacion") or {}
        if not isinstance(adj, dict):
            adj = {}

        cant_lic   = f(item.get("Cantidad"))
        cant_adj   = f(adj.get("CantidadAdjudicada"))
        monto_unit = f(adj.get("MontoUnitario"))

        # ── Parche CantidadAdjudicada ─────────────────────────────────────────
        # La API frecuentemente devuelve CantidadAdjudicada = 0 en convenios marco
        # aunque sí entrega el precio unitario. Usamos Cantidad_licitada como proxy.
        if cant_adj == 0 and monto_unit > 0 and cant_lic > 0:
            cant_adj = cant_lic

        monto_tot = round(cant_adj * monto_unit, 2)

        nombre_prod = s(item.get("NombreProducto"))
        desc_item   = s(item.get("Descripcion"), 200)

        filas.append({
            "Codigo_licitacion":      codigo,
            "Estado_licitacion":      estado_lic,
            "Organismo":              organismo,
            "Region":                 region,
            "CodigoEstadoLicitacion": s(item.get("CodigoEstadoLicitacion")),
            "Correlativo":            s(item.get("Correlativo")),
            "CodigoProducto":         s(item.get("CodigoProducto")),
            "CodigoCategoria":        s(item.get("CodigoCategoria")),
            "Categoria":              s(item.get("Categoria")),
            "NombreProducto":         nombre_prod,
            "Descripcion":            desc_item,
            "UnidadMedida":           s(item.get("UnidadMedida")),
            "Cantidad_licitada":      cant_lic,
            "RUT_proveedor":          s(adj.get("RutProveedor")),
            "Proveedor":              s(adj.get("NombreProveedor")),
            "Cantidad_adjudicada":    cant_adj,
            "Monto_unitario":         monto_unit,
            "Monto_total_item":       monto_tot,
            "Medicamento":            inferir_med(nombre_prod + " " + desc_item),
        })
    return filas


# ── SQLite: conexión e inicialización ─────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_SQLITE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    """Crea tablas si no existen y agrega columnas nuevas si faltan (migración)."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS licitaciones (
        Codigo                  TEXT PRIMARY KEY,
        Nombre                  TEXT,
        Medicamento             TEXT,
        Descripcion             TEXT,
        Estado                  TEXT,
        CodigoEstado            TEXT,
        Tipo                    TEXT,
        Tipo_desc               TEXT,
        CodigoTipo              TEXT,
        Informada               TEXT,
        TipoConvocatoria        TEXT,
        Moneda                  TEXT,
        Monto_estimado          REAL,
        Estimacion              TEXT,
        Modalidad_pago          TEXT,
        Fecha_publicacion       TEXT,
        Fecha_cierre            TEXT,
        Fecha_adjudicacion      TEXT,
        Fecha_inicio_contrato   TEXT,
        Fecha_fin_contrato      TEXT,
        Fecha_est_firma         TEXT,
        Dias_cierre             TEXT,
        Duracion_contrato       TEXT,
        Unidad_duracion         TEXT,
        Renovable               TEXT,
        Subcontratacion         TEXT,
        RequiereFirmaContrato   TEXT,
        PermisoContratacion     TEXT,
        N_oferentes             TEXT,
        Tipo_acto_adj           TEXT,
        Fecha_pub_adjudicacion  TEXT,
        URL_acta                TEXT,
        Organismo               TEXT,
        Codigo_organismo        TEXT,
        RUT_organismo           TEXT,
        Unidad_compra           TEXT,
        Direccion               TEXT,
        Comuna                  TEXT,
        Region                  TEXT,
        Responsable             TEXT,
        Cargo_responsable       TEXT,
        Nombre_resp_contrato    TEXT,
        Email_resp_contrato     TEXT,
        Fono_resp_contrato      TEXT,
        Cantidad_reclamos       TEXT,
        TomaRazon               TEXT,
        Total_items_declarados  INTEGER,
        ultima_actualizacion    TEXT
    );

    CREATE TABLE IF NOT EXISTS items (
        Codigo_licitacion       TEXT,
        Correlativo             TEXT,
        Estado_licitacion       TEXT,
        Organismo               TEXT,
        Region                  TEXT,
        CodigoEstadoLicitacion  TEXT,
        CodigoProducto          TEXT,
        CodigoCategoria         TEXT,
        Categoria               TEXT,
        NombreProducto          TEXT,
        Descripcion             TEXT,
        UnidadMedida            TEXT,
        Cantidad_licitada       REAL,
        RUT_proveedor           TEXT,
        Proveedor               TEXT,
        Cantidad_adjudicada     REAL,
        Monto_unitario          REAL,
        Monto_total_item        REAL,
        Medicamento             TEXT,
        PRIMARY KEY (Codigo_licitacion, Correlativo)
    );
    """)
    conn.commit()

    # ── Migración: agregar columnas nuevas si la BD ya existía sin ellas ──────
    columnas_nuevas_lics = [
        ("Fecha_inicio_contrato",  "TEXT"),
        ("Fecha_fin_contrato",     "TEXT"),
        ("Fecha_est_firma",        "TEXT"),
        ("RequiereFirmaContrato",  "TEXT"),
        ("PermisoContratacion",    "TEXT"),
        ("Fecha_pub_adjudicacion", "TEXT"),
        ("Total_items_declarados", "INTEGER"),
    ]
    existentes = {row[1] for row in conn.execute("PRAGMA table_info(licitaciones)")}
    for col, tipo in columnas_nuevas_lics:
        if col not in existentes:
            conn.execute(f"ALTER TABLE licitaciones ADD COLUMN {col} {tipo}")
            print(f"  ✚ Columna añadida: licitaciones.{col}")
    conn.commit()


# ── SQLite: carga y guardado ──────────────────────────────────────────────────

def cargar_db():
    """Carga licitaciones e ítems desde SQLite a dicts en memoria."""
    conn = get_conn()
    init_db(conn)

    db_lics = {}
    for row in conn.execute("SELECT * FROM licitaciones"):
        d = dict(row)
        d.pop("ultima_actualizacion", None)
        db_lics[d["Codigo"]] = d

    db_items = {}
    for row in conn.execute("SELECT * FROM items"):
        d = dict(row)
        cod = d["Codigo_licitacion"]
        db_items.setdefault(cod, []).append(d)

    conn.close()
    return db_lics, db_items


def guardar_db(db_lics, db_items):
    """UPSERT de licitaciones e ítems en SQLite."""
    conn = get_conn()
    hoy  = date.today().isoformat()

    cols_lic = [
        "Codigo", "Nombre", "Medicamento", "Descripcion", "Estado", "CodigoEstado",
        "Tipo", "Tipo_desc", "CodigoTipo", "Informada", "TipoConvocatoria", "Moneda",
        "Monto_estimado", "Estimacion", "Modalidad_pago",
        "Fecha_publicacion", "Fecha_cierre", "Fecha_adjudicacion",
        "Fecha_inicio_contrato", "Fecha_fin_contrato", "Fecha_est_firma",
        "Dias_cierre", "Duracion_contrato", "Unidad_duracion",
        "Renovable", "Subcontratacion", "RequiereFirmaContrato", "PermisoContratacion",
        "N_oferentes", "Tipo_acto_adj", "Fecha_pub_adjudicacion", "URL_acta",
        "Organismo", "Codigo_organismo", "RUT_organismo", "Unidad_compra",
        "Direccion", "Comuna", "Region", "Responsable", "Cargo_responsable",
        "Nombre_resp_contrato", "Email_resp_contrato", "Fono_resp_contrato",
        "Cantidad_reclamos", "TomaRazon", "Total_items_declarados",
        "ultima_actualizacion",
    ]
    ph      = ",".join(["?"] * len(cols_lic))
    sql_lic = f"INSERT OR REPLACE INTO licitaciones ({','.join(cols_lic)}) VALUES ({ph})"

    for fila in db_lics.values():
        vals = [fila.get(c, "") for c in cols_lic[:-1]] + [hoy]
        conn.execute(sql_lic, vals)

    cols_item = [
        "Codigo_licitacion", "Correlativo", "Estado_licitacion", "Organismo", "Region",
        "CodigoEstadoLicitacion", "CodigoProducto", "CodigoCategoria", "Categoria",
        "NombreProducto", "Descripcion", "UnidadMedida", "Cantidad_licitada",
        "RUT_proveedor", "Proveedor", "Cantidad_adjudicada", "Monto_unitario",
        "Monto_total_item", "Medicamento",
    ]
    ph2      = ",".join(["?"] * len(cols_item))
    sql_item = f"INSERT OR REPLACE INTO items ({','.join(cols_item)}) VALUES ({ph2})"

    for items_list in db_items.values():
        for item in items_list:
            vals = [item.get(c, "") for c in cols_item]
            conn.execute(sql_item, vals)

    conn.commit()
    conn.close()


# ── Estado (última fecha procesada) ──────────────────────────────────────────

def cargar_estado():
    if ESTADO_FILE.exists():
        data = json.loads(ESTADO_FILE.read_text("utf-8"))
        return date.fromisoformat(data["ultima_fecha"])
    return FECHA_INICIO_HISTORICO - timedelta(days=1)

def guardar_estado(ultima_fecha):
    ESTADO_FILE.write_text(
        json.dumps({"ultima_fecha": ultima_fecha.isoformat()}, ensure_ascii=False),
        "utf-8",
    )


# ── FASE 1: consulta de fechas ────────────────────────────────────────────────

def fase1_nuevas_fechas(fecha_ini, fecha_fin):
    """Itera día a día y retorna dict {codigo: fila} con licitaciones oncológicas."""
    print(f"\n[FASE 1] Fechas: {fecha_ini} → {fecha_fin}")
    filas      = {}
    d          = fecha_ini
    total      = (fecha_fin - fecha_ini).days + 1
    procesados = 0

    while d <= fecha_fin:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        procesados += 1
        pct = min(100, round(procesados / max(1, total * 5/7) * 100))
        print(f"  [{pct:3d}%] {d.strftime('%d-%m-%Y')} ", end="", flush=True)

        data = get_json({"ticket": TICKET, "fecha": d.strftime("%d%m%Y"), "estado": "todos"})
        lics = data.get("Listado") or []
        enc  = 0
        for lic in lics:
            fila = parsear_licitacion(lic, verificar_oncologico=True)
            if fila:
                filas[fila["Codigo"]] = fila
                enc += 1

        print(f"→ {len(lics):4d} lics | {enc} oncológicas")
        time.sleep(PAUSA_LISTA)
        d += timedelta(days=1)

    return filas


# ── FASE 2: detalle por código ────────────────────────────────────────────────

def fase2_detalle(codigos, db_lics, es_recheck=False):
    """Fetchea detalle, actualiza db_lics y extrae ítems."""
    label    = "re-check estados" if es_recheck else "licitaciones nuevas"
    print(f"\n[FASE 2] Actualizando {len(codigos)} {label}...")
    items_db = {}

    for i, codigo in enumerate(sorted(codigos)):
        pct = round((i + 1) / len(codigos) * 100) if codigos else 100
        print(f"  [{pct:3d}%] {codigo} ", end="", flush=True)

        data    = get_json({"ticket": TICKET, "codigo": codigo})
        listado = data.get("Listado") or []
        detalle = listado[0] if listado and isinstance(listado[0], dict) else {}

        fila_nueva = parsear_licitacion(detalle, verificar_oncologico=False)
        if fila_nueva and fila_nueva.get("Codigo"):
            db_lics[codigo] = fila_nueva

        fila_ref = db_lics.get(codigo, {})
        nuevos   = parsear_items(
            codigo,
            detalle,
            estado_lic = fila_ref.get("Estado", ""),
            organismo  = fila_ref.get("Organismo", ""),
            region     = fila_ref.get("Region", ""),
        )
        items_db[codigo] = nuevos
        print(f"→ estado: {fila_ref.get('Estado','?')} | {len(nuevos)} ítems")
        time.sleep(PAUSA_DETALLE)

    return items_db


# ── Parche ítems existentes ───────────────────────────────────────────────────

def parchear_items_existentes(conn):
    """
    Corrige registros en la tabla items donde CantidadAdjudicada = 0
    pero Monto_unitario y Cantidad_licitada están disponibles.
    Idempotente: se puede ejecutar múltiples veces sin efecto secundario.
    """
    conn.execute("""
        UPDATE items
        SET Cantidad_adjudicada = Cantidad_licitada,
            Monto_total_item    = ROUND(Monto_unitario * Cantidad_licitada, 2)
        WHERE Cantidad_adjudicada = 0
          AND Monto_unitario      > 0
          AND Cantidad_licitada   > 0
    """)
    n = conn.execute("SELECT changes()").fetchone()[0]
    if n:
        print(f"  🩹 Parche ítems: {n:,} registros corregidos (Cantidad_adjudicada ← Cantidad_licitada)")
    conn.commit()


# ── Generar Excel ─────────────────────────────────────────────────────────────

COLS_LIC = [
    "Codigo", "Nombre", "Medicamento", "Descripcion",
    "Estado", "CodigoEstado", "Tipo", "Tipo_desc", "TipoConvocatoria",
    "Moneda", "Monto_estimado", "Estimacion", "Modalidad_pago",
    "Fecha_publicacion", "Fecha_cierre", "Fecha_adjudicacion",
    "Fecha_inicio_contrato", "Fecha_fin_contrato", "Fecha_est_firma",
    "Fecha_pub_adjudicacion",
    "Dias_cierre", "Duracion_contrato", "Unidad_duracion",
    "Renovable", "Subcontratacion", "RequiereFirmaContrato", "PermisoContratacion",
    "N_oferentes", "Tipo_acto_adj", "URL_acta", "Total_items_declarados",
    "Organismo", "Codigo_organismo", "RUT_organismo", "Unidad_compra",
    "Direccion", "Comuna", "Region",
    "Responsable", "Cargo_responsable",
    "Nombre_resp_contrato", "Email_resp_contrato", "Fono_resp_contrato",
    "Cantidad_reclamos", "TomaRazon",
]

COLS_ITEMS = [
    "Codigo_licitacion", "Estado_licitacion", "Organismo", "Region",
    "CodigoEstadoLicitacion", "Correlativo",
    "CodigoProducto", "CodigoCategoria", "Categoria",
    "NombreProducto", "Descripcion", "UnidadMedida",
    "Cantidad_licitada", "RUT_proveedor", "Proveedor",
    "Cantidad_adjudicada", "Monto_unitario", "Monto_total_item",
    "Medicamento",
]

def ordenar_estado(df):
    df = df.copy()
    df["_ord"] = df["Estado"].apply(
        lambda e: ORDEN_ESTADOS.index(e) if e in ORDEN_ESTADOS else len(ORDEN_ESTADOS)
    )
    return (df.sort_values(["_ord", "Monto_estimado"], ascending=[True, False])
              .drop(columns=["_ord"])
              .reset_index(drop=True))

def generar_excel(db_lics, db_items):
    print("\nGenerando Excel...")

    filas_lista = list(db_lics.values())
    filas_items = [item for items in db_items.values() for item in items]

    df = pd.DataFrame(filas_lista)
    df = df.drop_duplicates(subset=["Codigo"]).reset_index(drop=True)
    df["Monto_estimado"] = pd.to_numeric(df.get("Monto_estimado"), errors="coerce").fillna(0)
    for c in COLS_LIC:
        if c not in df.columns:
            df[c] = ""
    df = df[COLS_LIC]
    df = ordenar_estado(df)

    if filas_items:
        di = pd.DataFrame(filas_items)
    else:
        di = pd.DataFrame(columns=COLS_ITEMS)
    for col in ["Cantidad_licitada", "Cantidad_adjudicada", "Monto_unitario", "Monto_total_item"]:
        di[col] = pd.to_numeric(di.get(col, pd.Series(dtype=float)), errors="coerce").fillna(0)
    for c in COLS_ITEMS:
        if c not in di.columns:
            di[c] = ""

    sufijo = f"_{FECHA_DESDE}_{FECHA_HASTA}" if MODO_RANGO else f"_{date.today().isoformat()}"
    fname  = f"oncologia{sufijo}.xlsx"

    with pd.ExcelWriter(fname, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Licitaciones (por estado)", index=False)

        for estado in ORDEN_ESTADOS:
            sub = df[df["Estado"] == estado]
            if not sub.empty:
                sub.to_excel(w, sheet_name=estado, index=False)

        di[COLS_ITEMS].to_excel(w, sheet_name="Ítems detalle", index=False)

        med = di[di["Medicamento"] != ""]
        if not med.empty:
            (med.groupby("Medicamento")
                .agg(Licitaciones    =("Codigo_licitacion", "nunique"),
                     Cantidad_total  =("Cantidad_adjudicada", "sum"),
                     Monto_total     =("Monto_total_item", "sum"))
                .sort_values("Monto_total", ascending=False)
                .reset_index()
                .to_excel(w, sheet_name="Medicamentos (ítems)", index=False))

        if not di.empty and "Proveedor" in di.columns:
            (di[di["Proveedor"] != ""]
                .groupby(["Proveedor", "RUT_proveedor"])
                .agg(Licitaciones =("Codigo_licitacion", "nunique"),
                     Items        =("Correlativo", "count"),
                     Monto_total  =("Monto_total_item", "sum"))
                .sort_values("Monto_total", ascending=False)
                .head(60)
                .reset_index()
                .to_excel(w, sheet_name="Laboratorios (ítems)", index=False))

        (df.groupby(["Organismo", "Region", "Comuna"])
            .agg(N=("Codigo", "count"), Monto=("Monto_estimado", "sum"))
            .sort_values("Monto", ascending=False)
            .reset_index()
            .to_excel(w, sheet_name="Por organismo", index=False))

        reg = df[df["Region"] != ""]
        if not reg.empty:
            (reg.groupby("Region")
                .agg(N=("Codigo", "count"), Monto=("Monto_estimado", "sum"))
                .sort_values("Monto", ascending=False)
                .reset_index()
                .to_excel(w, sheet_name="Por región", index=False))

        (df.groupby(["Tipo", "Tipo_desc"])
            .agg(N=("Codigo", "count"), Monto=("Monto_estimado", "sum"))
            .sort_values("Monto", ascending=False)
            .reset_index()
            .to_excel(w, sheet_name="Por tipo licitación", index=False))

    print(f"\n✅ Archivo: {fname}")
    print(f"   Licitaciones únicas : {len(df)}")
    print(f"   Ítems               : {len(di)}")
    print(f"   Monto total         : $ {df['Monto_estimado'].sum():,.0f}")
    print(f"\nDistribución por estado:")
    for e in ORDEN_ESTADOS:
        n = len(df[df["Estado"] == e])
        if n:
            print(f"  {e:<15} {n:>4}")
    if not med.empty:
        print(f"\nTop 10 medicamentos por monto (ítems reales):")
        top = (med.groupby("Medicamento")["Monto_total_item"]
                  .sum().sort_values(ascending=False).head(10))
        for m, v in top.items():
            print(f"  {m:<28} $ {v:>15,.0f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("EXTRACTOR ONCOLÓGICO — MODO INCREMENTAL + SQLite")
    if MODO_RANGO:
        print(f"⚠  MODO RANGO  : {FECHA_DESDE} → {FECHA_HASTA}")
    print(f"Base de datos    : {DB_SQLITE.resolve()}")
    print(f"Ticket           : {TICKET[:8]}…")
    print("=" * 62)

    db_lics, db_items = cargar_db()
    total_items_acum  = sum(len(v) for v in db_items.values())
    print(f"\nBase actual  : {len(db_lics)} licitaciones | {total_items_acum} ítems")

    if MODO_RANGO:
        # ── Re-extracción de un período acotado ──────────────────────────────
        print(f"\n[MODO RANGO] Procesando {FECHA_DESDE} → {FECHA_HASTA}")
        print(f"  Los registros existentes de ese período serán sobreescritos.\n")

        filas_rango = fase1_nuevas_fechas(FECHA_DESDE, FECHA_HASTA)
        print(f"\n  → {len(filas_rango)} licitaciones oncológicas encontradas en el rango")

        # Borrar ítems de los códigos que vamos a re-importar
        for codigo in filas_rango:
            db_lics[codigo]  = filas_rango[codigo]
            db_items.pop(codigo, None)

        # Obtener detalle + ítems de todos (no solo nuevos)
        items_rango = fase2_detalle(set(filas_rango.keys()), db_lics, es_recheck=False)
        db_items.update(items_rango)

        guardar_db(db_lics, db_items)

        # Aplicar parche de ítems (idempotente)
        conn = get_conn()
        parchear_items_existentes(conn)
        conn.close()

        total_nuevo = sum(len(v) for v in db_items.values())
        print(f"\n💾 SQLite guardado : {len(db_lics)} licitaciones | {total_nuevo} ítems")

    else:
        # ── Modo incremental normal ───────────────────────────────────────────
        ultima_fecha = cargar_estado()
        fecha_ini    = ultima_fecha + timedelta(days=1)
        fecha_fin    = date.today() - timedelta(days=1)
        print(f"Última fecha : {ultima_fecha}")

        codigos_nuevos    = set()
        hay_fechas_nuevas = fecha_ini <= fecha_fin

        if hay_fechas_nuevas:
            filas_nuevas = fase1_nuevas_fechas(fecha_ini, fecha_fin)
            for codigo, fila in filas_nuevas.items():
                if codigo not in db_lics:
                    db_lics[codigo] = fila
                    codigos_nuevos.add(codigo)
            print(f"\n  → {len(filas_nuevas)} encontradas | {len(codigos_nuevos)} verdaderamente nuevas")
        else:
            print(f"\n[FASE 1] Sin fechas nuevas (base al día hasta {ultima_fecha})")

        codigos_no_finales = {
            cod for cod, fila in db_lics.items()
            if fila.get("Estado") not in ESTADOS_FINALES
            and cod not in codigos_nuevos
        }
        print(f"\n  → {len(codigos_no_finales)} licitaciones en estado no-final (re-check)")

        if codigos_nuevos:
            items_nuevos = fase2_detalle(codigos_nuevos, db_lics, es_recheck=False)
            db_items.update(items_nuevos)

        if codigos_no_finales:
            items_recheck = fase2_detalle(codigos_no_finales, db_lics, es_recheck=True)
            db_items.update(items_recheck)

        if not codigos_nuevos and not codigos_no_finales:
            print("\n  Nada que actualizar.")

        guardar_db(db_lics, db_items)

        # Aplicar parche de ítems (idempotente, corre siempre)
        conn = get_conn()
        parchear_items_existentes(conn)
        conn.close()

        total_nuevo = sum(len(v) for v in db_items.values())
        print(f"\n💾 SQLite guardado : {len(db_lics)} licitaciones | {total_nuevo} ítems")

        if hay_fechas_nuevas:
            guardar_estado(fecha_fin)
            print(f"📅 Estado actualizado → última fecha: {fecha_fin}")

    # ── Generar Excel ──────────────────────────────────────────────────────────
    generar_excel(db_lics, db_items)


if __name__ == "__main__":
    main()
