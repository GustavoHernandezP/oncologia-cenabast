import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import date

# ── Configuración ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Mercado Oncológico Chile",
    page_icon="🏥",
    layout="wide",
)

# ── Formato de números ─────────────────────────────────────────────────────────

def fmt_mm(v):
    """Convierte CLP a formato MM (millones chilenos)"""
    if v >= 1_000_000:
        return f"${v / 1_000_000:,.0f} MM"
    return f"${v:,.0f}"

def col_clp(label):
    return st.column_config.NumberColumn(label, format="$ %,.0f")

# ── Carga de datos ─────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "oncologia.db"

@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    lics  = pd.read_sql("SELECT * FROM licitaciones", conn)
    items = pd.read_sql("SELECT * FROM items", conn)
    conn.close()

    lics["Fecha_adjudicacion"] = pd.to_datetime(lics["Fecha_adjudicacion"], errors="coerce")
    lics["Fecha_publicacion"]  = pd.to_datetime(lics["Fecha_publicacion"],  errors="coerce")
    lics["Año"] = lics["Fecha_adjudicacion"].dt.year.astype("Int64")
    lics["Monto_estimado"] = pd.to_numeric(lics["Monto_estimado"], errors="coerce").fillna(0)

    items["Monto_total_item"]    = pd.to_numeric(items["Monto_total_item"],    errors="coerce").fillna(0)
    items["Cantidad_adjudicada"] = pd.to_numeric(items["Cantidad_adjudicada"], errors="coerce").fillna(0)
    items["Monto_unitario"]      = pd.to_numeric(items["Monto_unitario"],      errors="coerce").fillna(0)

    return lics, items

lics, items = load_data()

ESTADOS_ABIERTOS = {"Publicada", "Cerrada", "Suspendida"}
AÑOS_DASHBOARD   = [2024, 2025, 2026]

# ── Título ─────────────────────────────────────────────────────────────────────

st.title("🏥 Mercado Oncológico Chile — Mercado Público")
st.caption(f"Actualizado: {date.today().strftime('%d/%m/%Y')}  |  Fuente: API Mercado Público / CENABAST")

tabs = st.tabs(["📊 Resumen", "💊 Medicamentos & Labs", "🔓 Procesos abiertos", "📋 Todos los procesos"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════════════════════

with tabs[0]:

    # ── KPIs globales ──────────────────────────────────────────────────────────
    st.subheader("Total histórico")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total licitaciones",    f"{len(lics):,}")
    k2.metric("Adjudicadas",           f"{len(lics[lics['Estado']=='Adjudicada']):,}")
    k3.metric("Abiertas",              f"{len(lics[lics['Estado'].isin(ESTADOS_ABIERTOS)]):,}")
    k4.metric("Monto estimado total",  fmt_mm(lics["Monto_estimado"].sum()))
    k5.metric("Monto real adjudicado", fmt_mm(items["Monto_total_item"].sum()))

    st.divider()

    # ── Por año ────────────────────────────────────────────────────────────────
    st.subheader("Licitaciones por año")

    resumen_años = []
    for año in AÑOS_DASHBOARD:
        sub   = lics[lics["Año"] == año]
        adj   = sub[sub["Estado"] == "Adjudicada"]
        abi   = sub[sub["Estado"].isin(ESTADOS_ABIERTOS)]
        total = len(sub)
        n_adj = len(adj)
        pct   = round(n_adj / total * 100, 1) if total > 0 else 0
        resumen_años.append({
            "Año":             str(año),
            "Total":           total,
            "Adjudicadas":     n_adj,
            "% Adjudicadas":   pct,
            "Abiertas":        len(abi),
            "Monto_MM":        round(sub["Monto_estimado"].sum() / 1e6, 1),
        })

    df_años = pd.DataFrame(resumen_años)

    cols_año = st.columns(len(AÑOS_DASHBOARD))
    for i, row in df_años.iterrows():
        with cols_año[i]:
            st.markdown(f"### {row['Año']}")
            st.metric("Licitaciones",   f"{row['Total']:,}")
            st.metric("Adjudicadas",    f"{row['Adjudicadas']:,}",
                      delta=f"{row['% Adjudicadas']}% del total")
            st.metric("Abiertas",       f"{row['Abiertas']:,}")
            st.metric("Monto (MM CLP)", f"${row['Monto_MM']:,.0f} MM")

    st.divider()

    # ── Evolución adjudicadas ──────────────────────────────────────────────────
    st.subheader("Evolución de adjudicaciones por año")
    col_a, col_b = st.columns(2)

    with col_a:
        fig_evo = go.Figure()
        fig_evo.add_trace(go.Bar(
            x=df_años["Año"],
            y=df_años["Adjudicadas"],
            name="Adjudicadas",
            marker_color="#21c354",
            text=df_años["Adjudicadas"],
            textposition="outside",
        ))
        fig_evo.add_trace(go.Bar(
            x=df_años["Año"],
            y=df_años["Total"] - df_años["Adjudicadas"],
            name="Otras",
            marker_color="#d3d3d3",
        ))
        fig_evo.update_layout(
            barmode="stack",
            title="Adjudicadas vs Total",
            yaxis_title="N° licitaciones",
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(fig_evo, use_container_width=True)

    with col_b:
        fig_pct = px.bar(
            df_años, x="Año", y="% Adjudicadas",
            title="% Adjudicadas por año",
            text=df_años["% Adjudicadas"].apply(lambda v: f"{v}%"),
            color="% Adjudicadas",
            color_continuous_scale=["#ffe0e0", "#ff4b4b"],
        )
        fig_pct.update_traces(textposition="outside")
        fig_pct.update_layout(yaxis_title="% Adjudicadas", coloraxis_showscale=False)
        st.plotly_chart(fig_pct, use_container_width=True)

    # ── Monto por año ──────────────────────────────────────────────────────────
    st.subheader("Monto estimado por año")
    df_monto_año = (
        lics[lics["Año"].isin(AÑOS_DASHBOARD)]
        .groupby("Año")["Monto_estimado"]
        .sum()
        .reset_index()
    )
    df_monto_año["Año"]      = df_monto_año["Año"].astype(str)
    df_monto_año["Monto_MM"] = df_monto_año["Monto_estimado"] / 1e6
    df_monto_año["Etiqueta"] = df_monto_año["Monto_MM"].apply(lambda v: f"${v:,.0f} MM")

    fig_monto = px.bar(
        df_monto_año, x="Año", y="Monto_MM",
        text="Etiqueta",
        labels={"Monto_MM": "Monto (MM CLP)", "Año": "Año"},
        color_discrete_sequence=["#0068c9"],
    )
    fig_monto.update_traces(textposition="outside")
    fig_monto.update_layout(yaxis_title="Monto (MM CLP)", yaxis_tickformat="$,.0f")
    st.plotly_chart(fig_monto, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MEDICAMENTOS & LABORATORIOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[1]:

    items_con_med = items[items["Medicamento"].str.strip() != ""]
    items_con_lab = items[items["Proveedor"].str.strip()  != ""]

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Top 15 medicamentos por monto adjudicado")
        if items_con_med.empty:
            st.info("Sin datos de medicamentos en ítems.")
        else:
            top_med = (
                items_con_med
                .groupby("Medicamento")["Monto_total_item"]
                .sum()
                .sort_values(ascending=True)
                .tail(15)
                .reset_index()
            )
            top_med["Monto_MM"] = top_med["Monto_total_item"] / 1e6
            top_med["Etiqueta"] = top_med["Monto_MM"].apply(lambda v: f"${v:,.0f} MM")

            fig_med = px.bar(
                top_med, x="Monto_MM", y="Medicamento",
                orientation="h", text="Etiqueta",
                labels={"Monto_MM": "Monto (MM CLP)", "Medicamento": ""},
                color_discrete_sequence=["#ff4b4b"],
            )
            fig_med.update_traces(textposition="outside")
            fig_med.update_layout(xaxis_tickformat="$,.0f", height=520)
            st.plotly_chart(fig_med, use_container_width=True)

    with col_d:
        st.subheader("Top 15 laboratorios por monto adjudicado")
        if items_con_lab.empty:
            st.info("Sin datos de proveedores en ítems.")
        else:
            top_lab = (
                items_con_lab
                .groupby("Proveedor")["Monto_total_item"]
                .sum()
                .sort_values(ascending=True)
                .tail(15)
                .reset_index()
            )
            top_lab["Monto_MM"] = top_lab["Monto_total_item"] / 1e6
            top_lab["Etiqueta"] = top_lab["Monto_MM"].apply(lambda v: f"${v:,.0f} MM")

            fig_lab = px.bar(
                top_lab, x="Monto_MM", y="Proveedor",
                orientation="h", text="Etiqueta",
                labels={"Monto_MM": "Monto (MM CLP)", "Proveedor": ""},
                color_discrete_sequence=["#21c354"],
            )
            fig_lab.update_traces(textposition="outside")
            fig_lab.update_layout(xaxis_tickformat="$,.0f", height=520)
            st.plotly_chart(fig_lab, use_container_width=True)

    st.divider()
    st.subheader("Detalle por medicamento")
    if not items_con_med.empty:
        resumen_med = (
            items_con_med
            .groupby("Medicamento")
            .agg(
                Licitaciones   = ("Codigo_licitacion", "nunique"),
                Cantidad_total = ("Cantidad_adjudicada", "sum"),
                Monto_total    = ("Monto_total_item", "sum"),
            )
            .sort_values("Monto_total", ascending=False)
            .reset_index()
        )
        st.dataframe(
            resumen_med,
            use_container_width=True,
            column_config={
                "Monto_total":    col_clp("Monto total (CLP)"),
                "Cantidad_total": st.column_config.NumberColumn("Cantidad total", format="%,.0f"),
            },
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PROCESOS ABIERTOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[2]:

    abiertos = lics[lics["Estado"].isin(ESTADOS_ABIERTOS)].copy()

    st.subheader(f"🔓 Procesos abiertos — {len(abiertos):,} licitaciones")

    a1, a2, a3 = st.columns(3)
    a1.metric("Publicadas",  len(abiertos[abiertos["Estado"] == "Publicada"]))
    a2.metric("Cerradas",    len(abiertos[abiertos["Estado"] == "Cerrada"]))
    a3.metric("Suspendidas", len(abiertos[abiertos["Estado"] == "Suspendida"]))

    st.divider()

    f1, f2 = st.columns(2)
    estado_ab = f1.selectbox("Estado", ["Todos"] + sorted(abiertos["Estado"].unique().tolist()), key="est_ab")
    buscar_ab = f2.text_input("Buscar por nombre o medicamento", key="bus_ab")

    df_ab = abiertos.copy()
    if estado_ab != "Todos":
        df_ab = df_ab[df_ab["Estado"] == estado_ab]
    if buscar_ab:
        mask = (
            df_ab["Nombre"].str.contains(buscar_ab, case=False, na=False) |
            df_ab["Medicamento"].str.contains(buscar_ab, case=False, na=False)
        )
        df_ab = df_ab[mask]

    COLS_AB = ["Codigo", "Nombre", "Medicamento", "Estado",
               "Monto_estimado", "Organismo", "Region",
               "Fecha_publicacion", "Fecha_adjudicacion"]

    st.dataframe(
        df_ab[COLS_AB].reset_index(drop=True),
        use_container_width=True,
        height=500,
        column_config={
            "Monto_estimado":     col_clp("Monto estimado (CLP)"),
            "Fecha_publicacion":  st.column_config.DateColumn("Fecha publicación",  format="DD/MM/YYYY"),
            "Fecha_adjudicacion": st.column_config.DateColumn("Fecha adjudicación", format="DD/MM/YYYY"),
        },
    )
    st.caption(f"{len(df_ab):,} procesos mostrados")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — TODOS LOS PROCESOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[3]:

    st.subheader(f"📋 Todos los procesos — {len(lics):,} licitaciones")

    f1, f2, f3, f4 = st.columns(4)
    estados_opc = ["Todos"] + sorted(lics["Estado"].dropna().unique().tolist())
    estado_sel  = f1.selectbox("Estado", estados_opc, key="est_all")
    años_opc    = ["Todos"] + [str(a) for a in sorted(
        [int(a) for a in lics["Año"].dropna().unique()], reverse=True
    )]
    año_sel    = f2.selectbox("Año", años_opc, key="año_all")
    buscar_all = f3.text_input("Buscar nombre o medicamento", key="bus_all")
    org_opc    = ["Todos"] + sorted(lics["Organismo"].dropna().unique().tolist())
    org_sel    = f4.selectbox("Organismo", org_opc, key="org_all")

    df_all = lics.copy()
    if estado_sel != "Todos":
        df_all = df_all[df_all["Estado"] == estado_sel]
    if año_sel != "Todos":
        df_all = df_all[df_all["Año"] == int(año_sel)]
    if buscar_all:
        mask = (
            df_all["Nombre"].str.contains(buscar_all, case=False, na=False) |
            df_all["Medicamento"].str.contains(buscar_all, case=False, na=False)
        )
        df_all = df_all[mask]
    if org_sel != "Todos":
        df_all = df_all[df_all["Organismo"] == org_sel]

    COLS_ALL = ["Codigo", "Nombre", "Medicamento", "Estado",
                "Monto_estimado", "Organismo", "Region",
                "Fecha_publicacion", "Fecha_adjudicacion"]

    st.dataframe(
        df_all[COLS_ALL].reset_index(drop=True),
        use_container_width=True,
        height=550,
        column_config={
            "Monto_estimado":     col_clp("Monto estimado (CLP)"),
            "Fecha_publicacion":  st.column_config.DateColumn("Fecha publicación",  format="DD/MM/YYYY"),
            "Fecha_adjudicacion": st.column_config.DateColumn("Fecha adjudicación", format="DD/MM/YYYY"),
        },
    )
    st.caption(f"{len(df_all):,} procesos mostrados de {len(lics):,} totales")
