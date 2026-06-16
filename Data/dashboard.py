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

# ── Formato numérico chileno ───────────────────────────────────────────────────

def fmt_num(v, dec=0, prefijo="$ "):
    """Formato chileno: miles=punto, decimal=coma. Ej: $ 1.234.567,500"""
    if pd.isna(v):
        return ""
    v = float(v)
    formatted = f"{v:,.{dec}f}"          # US: 1,234,567.500
    if dec > 0:
        int_p, dec_p = formatted.split(".")
        return prefijo + int_p.replace(",", ".") + "," + dec_p
    return prefijo + formatted.replace(",", ".")

def fmt_mm(v):
    """Convierte CLP a MM con formato chileno. Ej: $ 1.234 MM"""
    if v >= 1_000_000:
        return fmt_num(v / 1_000_000, dec=0) + " MM"
    return fmt_num(v, dec=0)

PLOTLY_LOCALE = dict(separators=",.")   # decimal=",", miles="."

# ── Carga de datos ─────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "oncologia.db"

@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    lics  = pd.read_sql("SELECT * FROM licitaciones", conn)
    items = pd.read_sql("SELECT * FROM items", conn)
    conn.close()

    # Fechas: tomar solo YYYY-MM-DD para evitar problemas con milisegundos
    lics["Fecha_adjudicacion"] = pd.to_datetime(lics["Fecha_adjudicacion"].str[:10], errors="coerce")
    lics["Fecha_publicacion"]  = pd.to_datetime(lics["Fecha_publicacion"].str[:10],  errors="coerce")
    # Año_pub: año en que se publicó la licitación (para estadísticas generales)
    lics["Año_pub"] = lics["Fecha_publicacion"].dt.year.astype("Int64")
    # Año: año de adjudicación REAL (solo tiene valor en adjudicadas)
    lics["Año"] = lics["Fecha_adjudicacion"].dt.year.astype("Int64")
    lics["Monto_estimado"] = pd.to_numeric(lics["Monto_estimado"], errors="coerce").fillna(0)

    items["Monto_total_item"]    = pd.to_numeric(items["Monto_total_item"],    errors="coerce").fillna(0)
    items["Cantidad_adjudicada"] = pd.to_numeric(items["Cantidad_adjudicada"], errors="coerce").fillna(0)
    items["Cantidad_licitada"]   = pd.to_numeric(items["Cantidad_licitada"],   errors="coerce").fillna(0)
    items["Monto_unitario"]      = pd.to_numeric(items["Monto_unitario"],      errors="coerce").fillna(0)

    return lics, items

lics_raw, items_raw = load_data()

# Estados
ESTADOS_ABIERTOS      = {"Publicada", "Suspendida"}
ESTADO_EN_EVALUACION  = "Cerrada"
ESTADOS_FINALES       = {"Adjudicada", "Desierta", "Revocada"}
AÑOS_DASHBOARD        = [2024, 2025, 2026]

# ── Título ─────────────────────────────────────────────────────────────────────

total_med = (lics_raw["Medicamento"].str.strip() != "").sum()
total_all = len(lics_raw)

col_titulo, col_toggle = st.columns([4, 1])
with col_titulo:
    st.title("🏥 Mercado Oncológico Chile — Mercado Público")
    st.caption(f"Actualizado: {date.today().strftime('%d/%m/%Y')}  |  Fuente: API Mercado Público / CENABAST")
with col_toggle:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    solo_med = st.toggle(
        "Solo medicamentos",
        value=False,
        key="filtro_tipo",
        help=f"{total_med:,} de {total_all:,} licitaciones tienen medicamento identificado ({round(total_med/total_all*100,1)}%)".replace(",",".")
    )

st.divider()

# Aplicar filtro global
if solo_med:
    lics      = lics_raw[lics_raw["Medicamento"].str.strip() != ""].copy()
    items     = items_raw[items_raw["Medicamento"].str.strip() != ""].copy()
else:
    lics      = lics_raw.copy()
    items     = items_raw.copy()

items_ext = items.merge(
    lics[["Codigo", "Monto_estimado", "Region", "Organismo"]],
    left_on="Codigo_licitacion", right_on="Codigo", how="left", suffixes=("", "_lic")
)
items_ext["Monto_efectivo"] = items_ext["Monto_total_item"].where(
    items_ext["Monto_total_item"] > 0, items_ext["Monto_estimado"]
)

st.divider()

# ── Locale chileno para tablas (JS: convierte US→CL sin romper el ordenamiento) ──
st.components.v1.html("""
<script>
(function() {
    function toChilean(t) {
        t = (t || '').trim();
        // Patrón: "$ 1,234,567" o "$ 1,234,567.890"
        var m = t.match(/^\$ ([\d,]+)(?:\.(\d+))?$/);
        if (!m) return null;
        var intPart = m[1].replace(/,/g, '.');  // comas→puntos (miles)
        var decPart = m[2];
        return '$ ' + intPart + (decPart ? ',' + decPart : '');
    }
    function run() {
        try {
            var doc = window.parent.document;
            // Selectores AG Grid (varias versiones de Streamlit)
            var selectors = [
                '[data-testid="stDataFrame"] .ag-cell-value',
                '[data-testid="stDataFrameResizable"] .ag-cell-value',
                '.stDataFrame .ag-cell-value',
                '[data-testid="stDataFrame"] [col-id] span'
            ];
            selectors.forEach(function(sel) {
                doc.querySelectorAll(sel).forEach(function(el) {
                    var r = toChilean(el.textContent);
                    if (r) el.textContent = r;
                });
            });
        } catch(e) {}
    }
    setInterval(run, 200);
    try {
        new MutationObserver(run).observe(
            window.parent.document.body, {childList: true, subtree: true});
    } catch(e) {}
})();
</script>
""", height=0)

tabs = st.tabs(["📊 Resumen", "🔍 Análisis comparativo", "💊 Medicamentos & Labs", "🔓 Procesos abiertos", "📋 Todos los procesos", "🗄️ Modelo de datos"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════════════════════

with tabs[0]:

    st.subheader("Total histórico")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total licitaciones",   f"{len(lics):,}".replace(",", "."))
    k2.metric("Adjudicadas",          f"{len(lics[lics['Estado']=='Adjudicada']):,}".replace(",", "."))
    k3.metric("Abiertas",             f"{len(lics[lics['Estado'].isin(ESTADOS_ABIERTOS)]):,}".replace(",", "."))
    k4.metric("Monto estimado total", fmt_mm(lics["Monto_estimado"].sum()))

    st.divider()

    # ── Por año ────────────────────────────────────────────────────────────────
    st.subheader("Licitaciones por año")

    resumen_años = []
    for año in AÑOS_DASHBOARD:
        # Total publicadas ese año (usa fecha publicación)
        sub   = lics[lics["Año_pub"] == año]
        # Adjudicadas reales ese año (usa fecha adjudicación)
        adj   = lics[(lics["Año"] == año) & (lics["Estado"] == "Adjudicada")]
        abi   = sub[sub["Estado"].isin(ESTADOS_ABIERTOS)]
        total = len(sub)
        n_adj = len(adj)
        pct   = round(n_adj / total * 100, 1) if total > 0 else 0
        resumen_años.append({
            "Año":          str(año),
            "Total":        total,
            "Adjudicadas":  n_adj,
            "% Adj":        pct,
            "Abiertas":     len(abi),
            "Monto_num":    sub["Monto_estimado"].sum(),
        })

    df_años = pd.DataFrame(resumen_años)

    cols_año = st.columns(len(AÑOS_DASHBOARD))
    for i, row in df_años.iterrows():
        with cols_año[i]:
            st.markdown(f"### {row['Año']}")
            st.metric("Licitaciones",   f"{row['Total']:,}".replace(",", "."))
            st.metric("Adjudicadas",    f"{row['Adjudicadas']:,}".replace(",", "."),
                      delta=f"{row['% Adj']}% del total")
            st.metric("Abiertas",       f"{row['Abiertas']:,}".replace(",", "."))
            if i > 0:
                prev   = df_años.iloc[i - 1]["Monto_num"]
                delta_val = row["Monto_num"] - prev
                delta_str = ("+" if delta_val >= 0 else "−") + fmt_mm(abs(delta_val))
                st.metric("Monto estimado", fmt_mm(row["Monto_num"]), delta=delta_str)
            else:
                st.metric("Monto estimado", fmt_mm(row["Monto_num"]))

    st.divider()

    # ── Evolución adjudicadas ──────────────────────────────────────────────────
    st.subheader("Evolución de adjudicaciones por año")
    col_a, col_b = st.columns(2)

    with col_a:
        fig_evo = go.Figure()
        fig_evo.add_trace(go.Bar(
            x=df_años["Año"], y=df_años["Adjudicadas"],
            name="Adjudicadas", marker_color="#21c354",
            text=df_años["Adjudicadas"].apply(lambda v: f"{v:,}".replace(",", ".")),
            textposition="outside",
        ))
        fig_evo.add_trace(go.Bar(
            x=df_años["Año"], y=df_años["Total"] - df_años["Adjudicadas"],
            name="Otras", marker_color="#d3d3d3",
        ))
        fig_evo.update_layout(
            barmode="stack", title="Adjudicadas vs Total",
            yaxis_title="N° licitaciones",
            legend=dict(orientation="h", y=-0.2),
            **PLOTLY_LOCALE,
        )
        st.plotly_chart(fig_evo, use_container_width=True)

    with col_b:
        df_años["Etiqueta_pct"] = df_años["% Adj"].apply(lambda v: f"{v}%".replace(".", ","))
        fig_pct = px.bar(
            df_años, x="Año", y="% Adj",
            title="% Adjudicadas por año",
            text="Etiqueta_pct",
            color="% Adj",
            color_continuous_scale=["#ffe0e0", "#ff4b4b"],
        )
        fig_pct.update_traces(textposition="outside")
        fig_pct.update_layout(
            yaxis_title="% Adjudicadas", coloraxis_showscale=False,
            **PLOTLY_LOCALE,
        )
        st.plotly_chart(fig_pct, use_container_width=True)

    # ── Monto por año ──────────────────────────────────────────────────────────
    st.subheader("Monto estimado por año (publicación)")
    df_monto_año = (
        lics[lics["Año_pub"].isin(AÑOS_DASHBOARD)]
        .groupby("Año_pub")["Monto_estimado"].sum()
        .reset_index()
        .rename(columns={"Año_pub": "Año"})
    )
    df_monto_año["Año"]      = df_monto_año["Año"].astype(str)
    df_monto_año["Monto_MM"] = df_monto_año["Monto_estimado"] / 1e6
    df_monto_año["Etiqueta"] = df_monto_año["Monto_estimado"].apply(fmt_mm)

    fig_monto = px.bar(
        df_monto_año, x="Año", y="Monto_MM",
        text="Etiqueta",
        labels={"Monto_MM": "Monto (MM CLP)", "Año": "Año"},
        color_discrete_sequence=["#0068c9"],
    )
    fig_monto.update_traces(textposition="outside")
    fig_monto.update_layout(yaxis_title="Monto (MM CLP)", **PLOTLY_LOCALE)
    st.plotly_chart(fig_monto, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ANÁLISIS COMPARATIVO
# ══════════════════════════════════════════════════════════════════════════════

with tabs[1]:

    st.subheader("🔍 Análisis comparativo entre años")

    ca, cb = st.columns(2)
    año_a = ca.selectbox("Año base",       [str(a) for a in AÑOS_DASHBOARD], index=0, key="comp_a")
    año_b = cb.selectbox("Año a comparar", [str(a) for a in AÑOS_DASHBOARD], index=1, key="comp_b")

    adj_a = lics[(lics["Año_pub"] == int(año_a)) & (lics["Estado"] == "Adjudicada")]
    adj_b = lics[(lics["Año_pub"] == int(año_b)) & (lics["Estado"] == "Adjudicada")]

    # ── Visión completa: adjudicadas vs no adjudicadas ────────────────────────
    st.divider()
    st.markdown("#### Adjudicadas vs No adjudicadas — visión completa")

    COLORES_ESTADO = {
        "Adjudicada":  "#21c354",
        "Cerrada":     "#f0a500",
        "Publicada":   "#0068c9",
        "Desierta":    "#d3d3d3",
        "Revocada":    "#ff4b4b",
        "Suspendida":  "#9b59b6",
        "Otro":        "#cccccc",
    }

    sub_a_pub = lics[lics["Año_pub"] == int(año_a)]
    sub_b_pub = lics[lics["Año_pub"] == int(año_b)]

    # Gráfico conteo por estado
    cnt_a = sub_a_pub["Estado"].value_counts().rename("N").reset_index()
    cnt_a.columns = ["Estado", "N"]
    cnt_a["Año"] = año_a
    cnt_b = sub_b_pub["Estado"].value_counts().rename("N").reset_index()
    cnt_b.columns = ["Estado", "N"]
    cnt_b["Año"] = año_b
    df_cnt = pd.concat([cnt_a, cnt_b])

    # Gráfico monto por estado
    mon_a = sub_a_pub.groupby("Estado")["Monto_estimado"].sum().reset_index()
    mon_a["Año"] = año_a
    mon_b = sub_b_pub.groupby("Estado")["Monto_estimado"].sum().reset_index()
    mon_b["Año"] = año_b
    df_mon = pd.concat([mon_a, mon_b])
    df_mon["Monto_MM"] = df_mon["Monto_estimado"] / 1e6
    df_mon["Etiqueta"] = df_mon["Monto_estimado"].apply(fmt_mm)

    vc1, vc2 = st.columns(2)
    with vc1:
        fig_cnt = px.bar(
            df_cnt, x="Año", y="N", color="Estado", barmode="stack",
            title="Cantidad de licitaciones por estado",
            color_discrete_map=COLORES_ESTADO,
            text="N",
        )
        fig_cnt.update_traces(textposition="inside")
        fig_cnt.update_layout(yaxis_title="N° licitaciones", **PLOTLY_LOCALE)
        ev_cnt = st.plotly_chart(fig_cnt, use_container_width=True, on_select="rerun", key="ev_cnt")

    with vc2:
        fig_mon = px.bar(
            df_mon, x="Año", y="Monto_MM", color="Estado", barmode="stack",
            title="Monto estimado por estado",
            color_discrete_map=COLORES_ESTADO,
            text="Etiqueta",
        )
        fig_mon.update_traces(textposition="inside")
        fig_mon.update_layout(yaxis_title="Monto (MM CLP)", **PLOTLY_LOCALE)
        ev_mon = st.plotly_chart(fig_mon, use_container_width=True, on_select="rerun", key="ev_mon")

    # Detectar selección en cualquiera de los dos gráficos
    sel_año    = None
    sel_estado = None
    for ev in [ev_cnt, ev_mon]:
        pts = getattr(getattr(ev, "selection", None), "points", [])
        if pts:
            sel_año    = str(pts[0].get("x", ""))
            sel_estado = pts[0].get("legendgroup") or pts[0].get("label") or pts[0].get("name")
            break

    # Tabla resumen por estado y año
    resumen_estado = []
    for año_iter, sub_iter in [(año_a, sub_a_pub), (año_b, sub_b_pub)]:
        for estado, grp in sub_iter.groupby("Estado"):
            resumen_estado.append({
                "Año":     año_iter,
                "Estado":  estado,
                "N":       len(grp),
                "% Total": round(len(grp) / len(sub_iter) * 100, 1) if len(sub_iter) else 0,
                "Monto":   grp["Monto_estimado"].sum(),
            })
    df_res = pd.DataFrame(resumen_estado).sort_values(["Año", "Monto"], ascending=[True, False])
    df_res["Monto_fmt"] = df_res["Monto"].apply(fmt_mm)
    df_res["% Total"]   = df_res["% Total"].apply(lambda v: f"{v}%".replace(".", ","))

    # Aplicar filtro de selección
    df_res_show = df_res.copy()
    if sel_año:    df_res_show = df_res_show[df_res_show["Año"]    == sel_año]
    if sel_estado: df_res_show = df_res_show[df_res_show["Estado"] == sel_estado]

    filtro_activo = f"Año: {sel_año or 'todos'}  |  Estado: {sel_estado or 'todos'}"
    st.caption(f"🔍 Filtro activo → {filtro_activo}  {'— haz clic en el gráfico para filtrar, doble clic para limpiar' if not (sel_año or sel_estado) else '— doble clic en el gráfico para limpiar'}")

    st.dataframe(
        df_res_show[["Año","Estado","N","% Total","Monto"]].rename(columns={"Monto":"Monto estimado"}),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Monto estimado": st.column_config.NumberColumn("Monto estimado", format="$ %,.0f"),
        },
    )

    # ── KPIs comparativos ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Solo adjudicadas — análisis de profundidad")
    st.info("ℹ️ Todos los valores usan **año de publicación** como base — igual que el gráfico apilado de arriba. "
            "Así 2024 vs 2025 compara el mismo universo de licitaciones.", icon="ℹ️")
    k1, k2, k3 = st.columns(3)
    k1.metric(f"N° adjudicadas {año_a}", f"{len(adj_a):,}".replace(",","."))
    k2.metric(f"N° adjudicadas {año_b}", f"{len(adj_b):,}".replace(",","."),
              delta=f"{len(adj_b)-len(adj_a):+,}".replace(",","."))
    monto_a = adj_a["Monto_estimado"].sum()
    monto_b = adj_b["Monto_estimado"].sum()
    k3.metric("Diferencia de licitaciones", f"{len(adj_b)-len(adj_a):+,}".replace(",","."))

    st.markdown("#### Montos estimados (adjudicadas)")
    m1, m2 = st.columns(2)
    m1.metric(f"Total {año_a}", fmt_mm(monto_a))
    delta_m = monto_b - monto_a
    delta_m_str = ("+" if delta_m >= 0 else "−") + fmt_mm(abs(delta_m))
    m2.metric(f"Total {año_b}", fmt_mm(monto_b), delta=delta_m_str)

    st.divider()

    # ── Distribución de montos: detectar outliers ──────────────────────────────
    st.markdown("#### Distribución de montos — ¿hay licitaciones muy grandes?")
    st.caption("Si la caja de un año está más arriba o tiene puntos muy alejados, hay outliers que explican la diferencia.")

    df_box = pd.concat([
        adj_a[adj_a["Monto_estimado"] > 0][["Monto_estimado"]].assign(Año=año_a),
        adj_b[adj_b["Monto_estimado"] > 0][["Monto_estimado"]].assign(Año=año_b),
    ])
    df_box["Monto_MM"] = df_box["Monto_estimado"] / 1e6

    fig_box = px.box(
        df_box, x="Año", y="Monto_MM", color="Año",
        points="outliers",
        labels={"Monto_MM": "Monto estimado (MM CLP)", "Año": ""},
        color_discrete_map={año_a: "#0068c9", año_b: "#ff4b4b"},
    )
    fig_box.update_layout(**PLOTLY_LOCALE)
    st.plotly_chart(fig_box, use_container_width=True)

    st.divider()

    # ── Top licitaciones por monto ─────────────────────────────────────────────
    st.markdown("#### Top 10 licitaciones por monto — las que más pesan")
    t1, t2 = st.columns(2)

    with t1:
        st.markdown(f"**{año_a}**")
        top_a = adj_a.nlargest(10, "Monto_estimado")[
            ["Nombre","Medicamento","Organismo","Monto_estimado"]
        ].reset_index(drop=True)
        st.dataframe(top_a, use_container_width=True,
                     column_config={"Monto_estimado": st.column_config.NumberColumn("Monto", format="$ %,.0f")})

    with t2:
        st.markdown(f"**{año_b}**")
        top_b = adj_b.nlargest(10, "Monto_estimado")[
            ["Nombre","Medicamento","Organismo","Monto_estimado"]
        ].reset_index(drop=True)
        st.dataframe(top_b, use_container_width=True,
                     column_config={"Monto_estimado": st.column_config.NumberColumn("Monto", format="$ %,.0f")})

    st.divider()

    # ── Por organismo ──────────────────────────────────────────────────────────
    st.markdown("#### Monto por organismo — ¿quién compra más en cada año?")
    org_a = adj_a.groupby("Organismo")["Monto_estimado"].sum().rename(año_a)
    org_b = adj_b.groupby("Organismo")["Monto_estimado"].sum().rename(año_b)
    df_org = pd.concat([org_a, org_b], axis=1).fillna(0)
    df_org["Total"] = df_org[año_a] + df_org[año_b]
    # top 15 por monto total, ascendente para que plotly ponga el mayor arriba
    df_org = df_org.nlargest(15, "Total").sort_values("Total", ascending=True).reset_index()
    df_org_melt = df_org.melt(id_vars="Organismo", value_vars=[año_a, año_b],
                               var_name="Año", value_name="Monto")
    df_org_melt["Monto_MM"] = df_org_melt["Monto"] / 1e6
    df_org_melt["Etiqueta"] = df_org_melt["Monto"].apply(fmt_mm)

    fig_org = px.bar(
        df_org_melt, x="Monto_MM", y="Organismo", color="Año",
        orientation="h", barmode="group", text="Etiqueta",
        labels={"Monto_MM": "Monto (MM CLP)", "Organismo": ""},
        color_discrete_map={año_a: "#0068c9", año_b: "#ff4b4b"},
        height=500,
    )
    fig_org.update_traces(textposition="outside")
    fig_org.update_layout(**PLOTLY_LOCALE)
    st.plotly_chart(fig_org, use_container_width=True)

    st.divider()

    # ── Por tipo de licitación ─────────────────────────────────────────────────
    st.markdown("#### Por tipo de licitación — ¿cambia el tamaño de los procesos?")
    tipo_a = adj_a.groupby("Tipo_desc")["Monto_estimado"].sum().rename(año_a)
    tipo_b = adj_b.groupby("Tipo_desc")["Monto_estimado"].sum().rename(año_b)
    df_tipo = pd.concat([tipo_a, tipo_b], axis=1).fillna(0).reset_index()
    df_tipo_melt = df_tipo.melt(id_vars="Tipo_desc", value_vars=[año_a, año_b],
                                 var_name="Año", value_name="Monto")
    df_tipo_melt["Monto_MM"] = df_tipo_melt["Monto"] / 1e6
    df_tipo_melt["Etiqueta"] = df_tipo_melt["Monto"].apply(fmt_mm)

    fig_tipo = px.bar(
        df_tipo_melt, x="Tipo_desc", y="Monto_MM", color="Año",
        barmode="group", text="Etiqueta",
        labels={"Monto_MM": "Monto (MM CLP)", "Tipo_desc": "Tipo"},
        color_discrete_map={año_a: "#0068c9", año_b: "#ff4b4b"},
    )
    fig_tipo.update_traces(textposition="outside")
    fig_tipo.update_layout(**PLOTLY_LOCALE)
    st.plotly_chart(fig_tipo, use_container_width=True)

    st.divider()

    # ── Por medicamento ────────────────────────────────────────────────────────
    st.markdown("#### Por medicamento — ¿qué droga concentra la diferencia?")
    med_a2 = adj_a[adj_a["Medicamento"] != ""].groupby("Medicamento")["Monto_estimado"].sum().rename(año_a)
    med_b2 = adj_b[adj_b["Medicamento"] != ""].groupby("Medicamento")["Monto_estimado"].sum().rename(año_b)
    df_med2 = pd.concat([med_a2, med_b2], axis=1).fillna(0)
    df_med2["Diferencia"] = df_med2[año_b] - df_med2[año_a]
    df_med2 = df_med2.sort_values("Diferencia", ascending=False).head(15).reset_index()
    df_med2_melt = df_med2.melt(id_vars="Medicamento", value_vars=[año_a, año_b],
                                  var_name="Año", value_name="Monto")
    df_med2_melt["Monto_MM"] = df_med2_melt["Monto"] / 1e6
    df_med2_melt["Etiqueta"] = df_med2_melt["Monto"].apply(fmt_mm)

    fig_med2 = px.bar(
        df_med2_melt, x="Monto_MM", y="Medicamento", color="Año",
        orientation="h", barmode="group", text="Etiqueta",
        labels={"Monto_MM": "Monto (MM CLP)", "Medicamento": ""},
        color_discrete_map={año_a: "#0068c9", año_b: "#ff4b4b"},
        height=500,
    )
    fig_med2.update_traces(textposition="outside")
    fig_med2.update_layout(**PLOTLY_LOCALE)
    st.plotly_chart(fig_med2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MEDICAMENTOS & LABORATORIOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[2]:  # noqa — índice correcto tras agregar tab de análisis

    # Solo ítems cuya licitación existe en la tabla lics (evita conteos inconsistentes)
    _codes_en_lics = set(lics["Codigo"])
    items_med = items_ext[
        (items_ext["Medicamento"].str.strip() != "") &
        (items_ext["Codigo_licitacion"].isin(_codes_en_lics))
    ]
    items_lab = items_ext[
        (items_ext["Proveedor"].str.strip() != "") &
        (items_ext["Codigo_licitacion"].isin(_codes_en_lics))
    ]

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Top 15 medicamentos — monto adjudicado")
        if items_med.empty:
            st.info("Sin datos de medicamentos en ítems.")
        else:
            top_med = (
                items_med.groupby("Medicamento")["Monto_efectivo"]
                .sum().sort_values(ascending=True).tail(15).reset_index()
            )
            top_med["Monto_MM"] = top_med["Monto_efectivo"] / 1e6
            top_med["Etiqueta"] = top_med["Monto_efectivo"].apply(fmt_mm)

            fig_med = px.bar(
                top_med, x="Monto_MM", y="Medicamento",
                orientation="h", text="Etiqueta",
                labels={"Monto_MM": "Monto (MM CLP)", "Medicamento": ""},
                color_discrete_sequence=["#ff4b4b"],
            )
            fig_med.update_traces(textposition="outside")
            fig_med.update_layout(xaxis_tickformat=",.", height=520, **PLOTLY_LOCALE)
            st.plotly_chart(fig_med, use_container_width=True)

    with col_d:
        st.subheader("Top 15 laboratorios — monto adjudicado")
        if items_lab.empty:
            st.info("Sin datos de proveedores en ítems.")
        else:
            top_lab = (
                items_lab.groupby("Proveedor")["Monto_efectivo"]
                .sum().sort_values(ascending=True).tail(15).reset_index()
            )
            top_lab["Monto_MM"] = top_lab["Monto_efectivo"] / 1e6
            top_lab["Etiqueta"] = top_lab["Monto_efectivo"].apply(fmt_mm)

            fig_lab = px.bar(
                top_lab, x="Monto_MM", y="Proveedor",
                orientation="h", text="Etiqueta",
                labels={"Monto_MM": "Monto (MM CLP)", "Proveedor": ""},
                color_discrete_sequence=["#21c354"],
            )
            fig_lab.update_traces(textposition="outside")
            fig_lab.update_layout(xaxis_tickformat=",.", height=520, **PLOTLY_LOCALE)
            st.plotly_chart(fig_lab, use_container_width=True)

    st.divider()

    # ── Tabla laboratorios clickeable ──────────────────────────────────────────
    st.subheader("Detalle por laboratorio / proveedor")
    if items_lab.empty:
        st.info("Sin datos de proveedores.")
    else:
        lab_resumen = (
            items_lab.groupby("Proveedor")
            .agg(
                Licitaciones = ("Codigo_licitacion", "nunique"),
                Medicamentos = ("Medicamento",        "nunique"),
                Monto_total  = ("Monto_efectivo",     "sum"),
            ).sort_values("Monto_total", ascending=False).reset_index()
        )
        lab_resumen["Monto_fmt"] = lab_resumen["Monto_total"].apply(fmt_mm)
        ev_lab = st.dataframe(
            lab_resumen[["Proveedor","Licitaciones","Medicamentos","Monto_fmt"]].rename(
                columns={"Monto_fmt": "Monto total"}),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
        st.caption("💡 Haz clic en una fila para ver las licitaciones del laboratorio.")

        lab_sel = None
        if ev_lab.selection.rows:
            lab_sel = lab_resumen.iloc[ev_lab.selection.rows[0]]["Proveedor"]

        if lab_sel:
            codes_lab = items_ext[items_ext["Proveedor"] == lab_sel]["Codigo_licitacion"].unique()
            lics_lab  = lics[lics["Codigo"].isin(codes_lab)]

            with st.expander(f"🏭 Licitaciones — **{lab_sel}**", expanded=True):
                kl1, kl2, kl3 = st.columns(3)
                kl1.metric("Licitaciones", f"{len(lics_lab):,}".replace(",","."))
                kl2.metric("Adjudicadas",  f"{len(lics_lab[lics_lab['Estado']=='Adjudicada']):,}".replace(",","."))
                kl3.metric("Monto estimado total", fmt_mm(lics_lab["Monto_estimado"].sum()))

                df_lab_show = lics_lab[[
                    "Codigo","Nombre","Medicamento","Estado",
                    "Monto_estimado","Organismo","Fecha_adjudicacion"
                ]].copy()
                st.dataframe(
                    df_lab_show.sort_values("Monto_estimado", ascending=False).reset_index(drop=True),
                    use_container_width=True,
                    column_config={
                        "Monto_estimado":     st.column_config.NumberColumn("Monto estimado", format="$ %,.0f"),
                        "Fecha_adjudicacion": st.column_config.DateColumn("Adjudicación", format="DD/MM/YYYY"),
                    },
                )

    st.divider()

    # ── Análisis de precios ────────────────────────────────────────────────────
    st.subheader("Análisis de precios y volumen por medicamento")

    meds_disponibles = sorted([m for m in items_med["Medicamento"].dropna().unique() if m.strip() != ""])
    med_detalle_sel  = st.selectbox(
        "Seleccionar medicamento para ver detalle",
        ["— ver tabla completa —"] + meds_disponibles,
        key="med_detalle_sel",
    )

    items_precio = items_med[items_med["Monto_unitario"] > 0]
    if med_detalle_sel != "— ver tabla completa —":
        items_precio = items_precio[items_precio["Medicamento"] == med_detalle_sel]

    if items_precio.empty:
        st.info("Sin datos de precio unitario disponibles.")
    else:
        precio_med = (
            items_precio.groupby("Medicamento")
            .agg(
                Licitaciones        = ("Codigo_licitacion",  "nunique"),
                Cant_licitada       = ("Cantidad_licitada",  "sum"),
                Cant_adjudicada     = ("Cantidad_adjudicada","sum"),
                Precio_prom         = ("Monto_unitario",     "mean"),
                Precio_min          = ("Monto_unitario",     "min"),
                Precio_max          = ("Monto_unitario",     "max"),
                Monto_real          = ("Monto_efectivo",     "sum"),
            ).reset_index()
        )
        precio_med["Pct_adj"] = (
            precio_med["Cant_adjudicada"] / precio_med["Cant_licitada"] * 100
        ).round(1).clip(upper=100)
        precio_med = precio_med.sort_values("Monto_real", ascending=False)

        # Precios en formato chileno (texto), monto en texto también para correcta visualización
        precio_med["Precio_prom_fmt"] = precio_med["Precio_prom"].apply(lambda v: fmt_num(v, dec=3))
        precio_med["Precio_min_fmt"]  = precio_med["Precio_min"].apply(lambda v: fmt_num(v, dec=3))
        precio_med["Precio_max_fmt"]  = precio_med["Precio_max"].apply(lambda v: fmt_num(v, dec=3))
        precio_med["Monto_real_fmt"]  = precio_med["Monto_real"].apply(fmt_mm)

        tabla_precio = precio_med[[
            "Medicamento","Licitaciones",
            "Cant_licitada","Cant_adjudicada","Pct_adj",
            "Precio_prom_fmt","Precio_min_fmt","Precio_max_fmt",
            "Monto_real_fmt",
        ]].rename(columns={
            "Cant_licitada":   "Cant. licitada",
            "Cant_adjudicada": "Cant. adjudicada",
            "Pct_adj":         "% Adjudicado",
            "Precio_prom_fmt": "Precio unit. prom.",
            "Precio_min_fmt":  "Precio unit. mín.",
            "Precio_max_fmt":  "Precio unit. máx.",
            "Monto_real_fmt":  "Monto real",
        })

        ev_med = st.dataframe(
            tabla_precio,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "% Adjudicado": st.column_config.ProgressColumn(
                    "% Adjudicado", min_value=0, max_value=100, format="%.1f%%"
                ),
                "Cant. licitada":   st.column_config.NumberColumn("Cant. licitada",   format="%,.0f"),
                "Cant. adjudicada": st.column_config.NumberColumn("Cant. adjudicada", format="%,.0f"),
            },
        )
        st.caption("💡 Haz clic en una fila para ver el resumen del medicamento.")

        if ev_med.selection.rows:
            med_sel = precio_med.iloc[ev_med.selection.rows[0]]["Medicamento"]
            lics_med = lics[lics["Medicamento"] == med_sel]
            its_med  = items_ext[items_ext["Medicamento"] == med_sel]

            with st.expander(f"💊 Resumen: **{med_sel}**", expanded=True):
                km1, km2, km3, km4 = st.columns(4)
                km1.metric("Licitaciones",      f"{len(lics_med):,}".replace(",","."))
                km2.metric("Adjudicadas",       f"{len(lics_med[lics_med['Estado']=='Adjudicada']):,}".replace(",","."))
                km3.metric("Organismos",        f"{lics_med['Organismo'].nunique():,}".replace(",","."))
                km4.metric("Monto total",       fmt_mm(lics_med["Monto_estimado"].sum()))

                ec1, ec2 = st.columns(2)
                with ec1:
                    por_año_m = (lics_med[lics_med["Año_pub"].isin(AÑOS_DASHBOARD)]
                                 .groupby("Año_pub")["Monto_estimado"].sum().reset_index())
                    por_año_m["Año"] = por_año_m["Año_pub"].astype(str)
                    por_año_m["MM"]  = por_año_m["Monto_estimado"] / 1e6
                    por_año_m["Lbl"] = por_año_m["Monto_estimado"].apply(fmt_mm)
                    fig_m_año = px.bar(por_año_m, x="Año", y="MM", text="Lbl",
                                       title="Monto por año", color_discrete_sequence=["#ff4b4b"])
                    fig_m_año.update_traces(textposition="outside")
                    fig_m_año.update_layout(**PLOTLY_LOCALE)
                    st.plotly_chart(fig_m_año, use_container_width=True)

                with ec2:
                    por_org_m = (lics_med.groupby("Organismo")["Monto_estimado"]
                                 .sum().sort_values(ascending=True).tail(8).reset_index())
                    por_org_m["MM"]  = por_org_m["Monto_estimado"] / 1e6
                    por_org_m["Lbl"] = por_org_m["Monto_estimado"].apply(fmt_mm)
                    fig_m_org = px.bar(por_org_m, x="MM", y="Organismo", orientation="h",
                                       text="Lbl", title="Top organismos",
                                       color_discrete_sequence=["#0068c9"])
                    fig_m_org.update_traces(textposition="outside")
                    fig_m_org.update_layout(**PLOTLY_LOCALE)
                    st.plotly_chart(fig_m_org, use_container_width=True)

                st.markdown("**Licitaciones**")
                df_med_show = lics_med[["Codigo","Nombre","Estado","Monto_estimado",
                                         "Organismo","Fecha_adjudicacion"]].copy()
                st.dataframe(df_med_show.reset_index(drop=True), use_container_width=True,
                             column_config={
                                 "Monto_estimado":     st.column_config.NumberColumn("Monto estimado", format="$ %,.0f"),
                                 "Fecha_adjudicacion": st.column_config.DateColumn("Adjudicación", format="DD/MM/YYYY"),
                             })

                # Proveedores / laboratorios para este medicamento
                provs = (
                    its_med[its_med["Proveedor"].str.strip() != ""]
                    .groupby("Proveedor")
                    .agg(Items=("Correlativo","count"), Monto=("Monto_efectivo","sum"))
                    .sort_values("Monto", ascending=False).reset_index()
                )
                if not provs.empty:
                    st.markdown("**Proveedores / Laboratorios**")
                    st.dataframe(provs, use_container_width=True, hide_index=True,
                                 column_config={
                                     "Monto": st.column_config.NumberColumn("Monto total", format="$ %,.0f"),
                                 })

        # Gráfico precio unitario promedio top 15
        st.subheader("Precio unitario promedio — Top 15 medicamentos")
        top_precio = precio_med.nlargest(15, "Precio_prom").sort_values("Precio_prom")
        top_precio["Etiqueta"] = top_precio["Precio_prom"].apply(lambda v: fmt_num(v, dec=3))

        fig_precio = px.bar(
            top_precio, x="Precio_prom", y="Medicamento",
            orientation="h", text="Etiqueta",
            labels={"Precio_prom": "Precio unitario promedio (CLP)", "Medicamento": ""},
            color_discrete_sequence=["#f0a500"],
        )
        fig_precio.update_traces(textposition="outside")
        fig_precio.update_layout(xaxis_tickformat=",.", height=520, **PLOTLY_LOCALE)
        st.plotly_chart(fig_precio, use_container_width=True)
        st.caption("Precio promedio basado en ítems con monto unitario informado en la API.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — PROCESOS ABIERTOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[3]:

    # Solo Publicada y Suspendida = verdaderamente abiertos
    abiertos = lics[lics["Estado"].isin(ESTADOS_ABIERTOS)].copy()

    st.subheader(f"🔓 Procesos abiertos — {len(abiertos):,} licitaciones".replace(",", "."))
    st.caption("Solo incluye licitaciones en estado **Publicada** o **Suspendida**. "
               "Las en estado *Cerrada* están en evaluación y se muestran en 'Todos los procesos'.")

    n_pub = len(abiertos[abiertos["Estado"] == "Publicada"])
    n_sus = len(abiertos[abiertos["Estado"] == "Suspendida"])
    if n_sus > 0:
        a1, a2, a3 = st.columns(3)
        a1.metric("Publicadas",              n_pub)
        a2.metric("Suspendidas",             n_sus)
        a3.metric("Monto estimado abiertos", fmt_mm(abiertos["Monto_estimado"].sum()))
    else:
        a1, a2 = st.columns(2)
        a1.metric("Publicadas",              n_pub)
        a2.metric("Monto estimado abiertos", fmt_mm(abiertos["Monto_estimado"].sum()))

    st.divider()

    # Filtros
    f1, f2, f3 = st.columns(3)
    f4, f5     = st.columns(2)

    estado_ab = f1.selectbox(
        "Estado", ["Todos"] + sorted(abiertos["Estado"].unique().tolist()), key="est_ab"
    )
    med_opciones = ["Todos"] + sorted(
        [m for m in abiertos["Medicamento"].dropna().unique() if m.strip() != ""]
    )
    med_ab = f2.selectbox("Medicamento", med_opciones, key="med_ab")

    reg_opciones = ["Todos"] + sorted(
        [r for r in abiertos["Region"].dropna().unique() if r.strip() != ""]
    )
    region_ab = f3.selectbox("Región", reg_opciones, key="reg_ab")

    org_opciones = ["Todos"] + sorted(
        [o for o in abiertos["Organismo"].dropna().unique() if o.strip() != ""]
    )
    org_ab = f4.selectbox("Organismo", org_opciones, key="org_ab")

    buscar_ab = f5.text_input("Buscar en nombre", key="bus_ab")

    monto_min = int(abiertos["Monto_estimado"].min())
    monto_max = int(abiertos["Monto_estimado"].max())
    if monto_min < monto_max:
        rango_monto = st.slider(
            "Rango monto estimado (CLP)",
            min_value=monto_min, max_value=monto_max,
            value=(monto_min, monto_max),
            key="rango_ab",
            format="%d",
        )
    else:
        rango_monto = (monto_min, monto_max)

    # Aplicar filtros
    df_ab = abiertos.copy()
    if estado_ab  != "Todos": df_ab = df_ab[df_ab["Estado"]     == estado_ab]
    if med_ab     != "Todos": df_ab = df_ab[df_ab["Medicamento"] == med_ab]
    if region_ab  != "Todos": df_ab = df_ab[df_ab["Region"]      == region_ab]
    if org_ab     != "Todos": df_ab = df_ab[df_ab["Organismo"]   == org_ab]
    if buscar_ab:
        df_ab = df_ab[df_ab["Nombre"].str.contains(buscar_ab, case=False, na=False)]
    df_ab = df_ab[
        (df_ab["Monto_estimado"] >= rango_monto[0]) &
        (df_ab["Monto_estimado"] <= rango_monto[1])
    ]

    df_ab_show = df_ab[[
        "Codigo","Nombre","Medicamento","Estado","Monto_estimado",
        "Organismo","Region","Fecha_publicacion","Fecha_adjudicacion"
    ]].copy()

    st.dataframe(
        df_ab_show.reset_index(drop=True),
        use_container_width=True,
        height=500,
        column_config={
            "Monto_estimado":     st.column_config.NumberColumn("Monto estimado (CLP)", format="$ %,.0f"),
            "Fecha_publicacion":  st.column_config.DateColumn("Fecha publicación",  format="DD/MM/YYYY"),
            "Fecha_adjudicacion": st.column_config.DateColumn("Fecha adjudicación", format="DD/MM/YYYY"),
        },
    )
    st.caption(f"{len(df_ab):,} procesos mostrados".replace(",", "."))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — TODOS LOS PROCESOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[4]:

    st.subheader(f"📋 Todos los procesos — {len(lics):,} licitaciones".replace(",", "."))

    f1, f2, f3, f4 = st.columns(4)
    estado_sel = f1.selectbox(
        "Estado",
        ["Todos"] + sorted(lics["Estado"].dropna().unique().tolist()),
        key="est_all"
    )
    años_opc = ["Todos"] + [str(a) for a in sorted(
        [int(a) for a in lics["Año"].dropna().unique()], reverse=True
    )]
    año_sel    = f2.selectbox("Año", años_opc, key="año_all")
    reg_all    = f3.selectbox(
        "Región",
        ["Todos"] + sorted([r for r in lics["Region"].dropna().unique() if r.strip() != ""]),
        key="reg_all"
    )
    org_all    = f4.selectbox(
        "Organismo",
        ["Todos"] + sorted([o for o in lics["Organismo"].dropna().unique() if o.strip() != ""]),
        key="org_all"
    )

    c1, c2 = st.columns(2)
    med_all    = c1.selectbox(
        "Medicamento",
        ["Todos"] + sorted([m for m in lics["Medicamento"].dropna().unique() if m.strip() != ""]),
        key="med_all"
    )
    buscar_all = c2.text_input("Buscar en nombre", key="bus_all")

    df_all = lics.copy()
    if estado_sel != "Todos": df_all = df_all[df_all["Estado"]      == estado_sel]
    if año_sel    != "Todos": df_all = df_all[df_all["Año"]         == int(año_sel)]
    if reg_all    != "Todos": df_all = df_all[df_all["Region"]      == reg_all]
    if org_all    != "Todos": df_all = df_all[df_all["Organismo"]   == org_all]
    if med_all    != "Todos": df_all = df_all[df_all["Medicamento"] == med_all]
    if buscar_all:
        df_all = df_all[df_all["Nombre"].str.contains(buscar_all, case=False, na=False)]

    df_all_show = df_all[[
        "Codigo","Nombre","Medicamento","Estado","Monto_estimado",
        "Organismo","Region","Fecha_publicacion","Fecha_adjudicacion"
    ]].copy()

    ev_all = st.dataframe(
        df_all_show.reset_index(drop=True),
        use_container_width=True,
        height=500,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Monto_estimado":     st.column_config.NumberColumn("Monto estimado (CLP)", format="$ %,.0f"),
            "Fecha_publicacion":  st.column_config.DateColumn("Fecha publicación",  format="DD/MM/YYYY"),
            "Fecha_adjudicacion": st.column_config.DateColumn("Fecha adjudicación", format="DD/MM/YYYY"),
        },
    )
    st.caption(f"{len(df_all):,} de {len(lics):,} procesos  |  💡 Haz clic en una fila para ver el detalle.".replace(",", "."))

    if ev_all.selection.rows:
        idx      = ev_all.selection.rows[0]
        codigo   = df_all.reset_index(drop=True).iloc[idx]["Codigo"]
        row      = lics[lics["Codigo"] == codigo].iloc[0]
        its_lic  = items[items["Codigo_licitacion"] == codigo]

        with st.expander(f"📄 Detalle licitación: **{codigo}**", expanded=True):
            d1, d2, d3 = st.columns(3)
            d1.markdown(f"**Nombre**  \n{row['Nombre']}")
            d2.markdown(f"**Estado**  \n{row['Estado']}")
            d3.markdown(f"**Medicamento**  \n{row['Medicamento'] or '—'}")

            d4, d5, d6 = st.columns(3)
            d4.markdown(f"**Organismo**  \n{row['Organismo']}")
            d5.markdown(f"**Región**  \n{row['Region']}")
            d6.markdown(f"**Unidad de compra**  \n{row['Unidad_compra']}")

            d7, d8, d9 = st.columns(3)
            d7.metric("Monto estimado",   fmt_num(row["Monto_estimado"]))
            d8.metric("N° oferentes",     row.get("N_oferentes") or "—")
            d9.metric("Tipo",             row.get("Tipo_desc") or "—")

            fd1, fd2, fd3 = st.columns(3)
            fd1.markdown(f"**Publicación**  \n{pd.Timestamp(row['Fecha_publicacion']).strftime('%d/%m/%Y') if pd.notna(row['Fecha_publicacion']) else '—'}")
            fd2.markdown(f"**Cierre**  \n{pd.Timestamp(row['Fecha_cierre']).strftime('%d/%m/%Y') if pd.notna(pd.Timestamp(row['Fecha_cierre']) if row.get('Fecha_cierre') else pd.NaT) else '—'}" if row.get('Fecha_cierre') else "**Cierre**  \n—")
            fd3.markdown(f"**Adjudicación**  \n{pd.Timestamp(row['Fecha_adjudicacion']).strftime('%d/%m/%Y') if pd.notna(row['Fecha_adjudicacion']) else '—'}")

            url = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?qs={codigo}"
            st.markdown(f"🔗 [Ver en Mercado Público]({url})")

            if not its_lic.empty:
                st.markdown("**Ítems**")
                its_show = its_lic[[
                    "Correlativo","NombreProducto","Categoria","UnidadMedida",
                    "Cantidad_licitada","Cantidad_adjudicada","Monto_unitario","Monto_total_item","Proveedor"
                ]].copy()
                for col in ["Cantidad_licitada","Cantidad_adjudicada"]:
                    its_show[col] = its_show[col].apply(lambda v: f"{v:,.0f}".replace(",","."))
                its_show["Monto_unitario"]   = its_show["Monto_unitario"].apply(lambda v: fmt_num(v, dec=3))
                its_show["Monto_total_item"] = its_show["Monto_total_item"].apply(fmt_num)
                st.dataframe(its_show.reset_index(drop=True), use_container_width=True)
            else:
                st.info("Sin ítems registrados para esta licitación.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — MODELO DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

with tabs[5]:

    st.subheader("🗄️ Modelo de datos — oncologia.db")

    # ── Diagrama ERD ───────────────────────────────────────────────────────────
    st.markdown("#### Diagrama Entidad-Relación")

    st.components.v1.html("""
<style>
  body { margin:0; background:transparent; font-family: 'Segoe UI', sans-serif; }
  .erd { display:flex; gap:80px; align-items:flex-start; padding:20px; }
  .tbl { border:2px solid #0068c9; border-radius:8px; min-width:260px;
         box-shadow:0 2px 8px rgba(0,0,0,.12); background:#fff; }
  .tbl-header { background:#0068c9; color:#fff; padding:10px 16px;
                font-weight:700; font-size:15px; border-radius:6px 6px 0 0; }
  .tbl-pk  { background:#e8f4ff; }
  .tbl-fk  { background:#fff3cd; }
  .tbl tr td { padding:5px 14px; font-size:13px; border-bottom:1px solid #eee; }
  .tbl tr:last-child td { border-bottom:none; }
  .badge { font-size:10px; font-weight:700; padding:1px 5px; border-radius:3px;
           margin-right:5px; }
  .pk { background:#0068c9; color:#fff; }
  .fk { background:#f0a500; color:#fff; }
  .rel { display:flex; align-items:center; padding-top:52px; }
  .rel-line { display:flex; flex-direction:column; align-items:center; gap:4px;
              font-size:11px; color:#555; }
  .rel-line svg { margin:0 4px; }
</style>
<div class="erd">
  <!-- TABLA LICITACIONES -->
  <div class="tbl">
    <div class="tbl-header">📄 licitaciones &nbsp;<span style="font-size:11px;opacity:.8">(1 fila = 1 proceso)</span></div>
    <table width="100%">
      <tr class="tbl-pk"><td><span class="badge pk">PK</span>Codigo</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Nombre</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Medicamento</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Estado</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Tipo_desc</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Monto_estimado</td><td style="color:#777">REAL</td></tr>
      <tr><td>Moneda</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Fecha_publicacion</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Fecha_cierre</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Fecha_adjudicacion</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Organismo</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Region</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Unidad_compra</td><td style="color:#777">TEXT</td></tr>
      <tr><td>N_oferentes</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Responsable</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Descripcion</td><td style="color:#777">TEXT</td></tr>
      <tr><td>ultima_actualizacion</td><td style="color:#777">TEXT</td></tr>
      <tr style="color:#aaa"><td colspan="2" style="padding:4px 14px;font-size:11px">+ 23 columnas adicionales</td></tr>
    </table>
  </div>

  <!-- LÍNEA DE RELACIÓN -->
  <div class="rel">
    <div class="rel-line">
      <span>1</span>
      <svg width="90" height="16" viewBox="0 0 90 16">
        <line x1="0" y1="8" x2="80" y2="8" stroke="#0068c9" stroke-width="2"/>
        <polygon points="80,4 90,8 80,12" fill="#0068c9"/>
        <line x1="0" y1="4" x2="0" y2="12" stroke="#0068c9" stroke-width="2"/>
      </svg>
      <span>N</span>
    </div>
  </div>

  <!-- TABLA ITEMS -->
  <div class="tbl">
    <div class="tbl-header" style="background:#ff4b4b">📦 items &nbsp;<span style="font-size:11px;opacity:.8">(1 fila = 1 ítem/producto)</span></div>
    <table width="100%">
      <tr class="tbl-fk"><td><span class="badge fk">FK</span>Codigo_licitacion</td><td style="color:#777">TEXT</td></tr>
      <tr class="tbl-pk" style="background:#ffe8e8"><td><span class="badge pk" style="background:#ff4b4b">PK</span>Correlativo</td><td style="color:#777">TEXT</td></tr>
      <tr><td>NombreProducto</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Medicamento</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Categoria</td><td style="color:#777">TEXT</td></tr>
      <tr><td>UnidadMedida</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Cantidad_licitada</td><td style="color:#777">REAL</td></tr>
      <tr><td>Cantidad_adjudicada</td><td style="color:#777">REAL</td></tr>
      <tr><td>Monto_unitario</td><td style="color:#777">REAL</td></tr>
      <tr><td>Monto_total_item</td><td style="color:#777">REAL</td></tr>
      <tr><td>Proveedor</td><td style="color:#777">TEXT</td></tr>
      <tr><td>RUT_proveedor</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Estado_licitacion</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Organismo</td><td style="color:#777">TEXT</td></tr>
      <tr><td>Region</td><td style="color:#777">TEXT</td></tr>
    </table>
  </div>
</div>
<div style="padding:0 20px 12px;font-size:12px;color:#888">
  🔑 PK = clave primaria &nbsp;|&nbsp; 🔑 FK = clave foránea &nbsp;|&nbsp;
  Relación: <b>licitaciones.Codigo → items.Codigo_licitacion</b> (una licitación tiene muchos ítems)
</div>
""", height=520)

    st.divider()

    # ── Tabla licitaciones completa ────────────────────────────────────────────
    st.subheader(f"📄 Tabla licitaciones — {len(lics_raw):,} registros".replace(",","."))

    col_bl1, col_bl2 = st.columns(2)
    buscar_lic_raw = col_bl1.text_input("Buscar en nombre o código", key="bus_lic_raw")
    estado_lic_raw = col_bl2.selectbox(
        "Filtrar por estado",
        ["Todos"] + sorted(lics_raw["Estado"].dropna().unique().tolist()),
        key="est_lic_raw",
    )

    cols_lic = [
        "Codigo","Nombre","Medicamento","Estado","Tipo_desc","Monto_estimado",
        "Organismo","Region","Unidad_compra","N_oferentes",
        "Fecha_publicacion","Fecha_cierre","Fecha_adjudicacion",
        "ultima_actualizacion",
    ]
    df_lic_raw = lics_raw[cols_lic].copy()
    if buscar_lic_raw:
        mask = (df_lic_raw["Nombre"].str.contains(buscar_lic_raw, case=False, na=False) |
                df_lic_raw["Codigo"].str.contains(buscar_lic_raw, case=False, na=False))
        df_lic_raw = df_lic_raw[mask]
    if estado_lic_raw != "Todos":
        df_lic_raw = df_lic_raw[df_lic_raw["Estado"] == estado_lic_raw]

    st.dataframe(
        df_lic_raw.reset_index(drop=True),
        use_container_width=True,
        height=450,
        column_config={
            "Monto_estimado":     st.column_config.NumberColumn("Monto estimado", format="$ %,.0f"),
            "Fecha_publicacion":  st.column_config.DateColumn("F. publicación",  format="DD/MM/YYYY"),
            "Fecha_cierre":       st.column_config.DateColumn("F. cierre",        format="DD/MM/YYYY"),
            "Fecha_adjudicacion": st.column_config.DateColumn("F. adjudicación",  format="DD/MM/YYYY"),
        },
    )
    st.caption(f"{len(df_lic_raw):,} de {len(lics_raw):,} registros mostrados".replace(",","."))

    st.divider()

    # ── Tabla ítems completa ───────────────────────────────────────────────────
    st.subheader(f"📦 Tabla ítems — {len(items_raw):,} registros".replace(",","."))

    col_bi1, col_bi2 = st.columns(2)
    buscar_item_raw = col_bi1.text_input("Buscar en producto o licitación", key="bus_item_raw")
    med_item_raw    = col_bi2.selectbox(
        "Filtrar por medicamento",
        ["Todos"] + sorted([m for m in items_raw["Medicamento"].dropna().unique() if m.strip() != ""]),
        key="med_item_raw",
    )

    cols_items = [
        "Codigo_licitacion","Correlativo","NombreProducto","Medicamento","Categoria",
        "UnidadMedida","Cantidad_licitada","Cantidad_adjudicada",
        "Monto_unitario","Monto_total_item",
        "Proveedor","RUT_proveedor","Organismo","Region","Estado_licitacion",
    ]
    df_items_raw = items_raw[[c for c in cols_items if c in items_raw.columns]].copy()
    if buscar_item_raw:
        mask = (df_items_raw["NombreProducto"].str.contains(buscar_item_raw, case=False, na=False) |
                df_items_raw["Codigo_licitacion"].str.contains(buscar_item_raw, case=False, na=False))
        df_items_raw = df_items_raw[mask]
    if med_item_raw != "Todos":
        df_items_raw = df_items_raw[df_items_raw["Medicamento"] == med_item_raw]

    st.dataframe(
        df_items_raw.reset_index(drop=True),
        use_container_width=True,
        height=450,
        column_config={
            "Cantidad_licitada":   st.column_config.NumberColumn("Cant. licitada",   format="%,.0f"),
            "Cantidad_adjudicada": st.column_config.NumberColumn("Cant. adjudicada", format="%,.0f"),
            "Monto_unitario":      st.column_config.NumberColumn("Monto unitario",   format="$ %,.3f"),
            "Monto_total_item":    st.column_config.NumberColumn("Monto total ítem", format="$ %,.0f"),
        },
    )
    st.caption(f"{len(df_items_raw):,} de {len(items_raw):,} registros mostrados".replace(",","."))
