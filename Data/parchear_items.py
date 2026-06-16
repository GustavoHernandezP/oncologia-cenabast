"""
parchear_items.py
─────────────────────────────────────────────────────────────────────────────
Corrige los ítems de oncologia.db donde la API no devolvió CantidadAdjudicada
(queda en 0) pero sí hay precio unitario (MontoUnitario > 0).

Criterio aplicado:
  · Si Cantidad_adjudicada = 0  Y  Monto_unitario > 0  Y  Cantidad_licitada > 0
    → Cantidad_adjudicada = Cantidad_licitada  (mejor estimación disponible)
    → Monto_total_item    = Monto_unitario × Cantidad_adjudicada

Esto es una estimación; no indica que SE adjudicó exactamente esa cantidad,
sino que es la que la licitación estipulaba comprar.

Uso:
    cd ".../Laboratorios/Data"
    python3 parchear_items.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "oncologia.db"

def main():
    conn = sqlite3.connect(DB_PATH)

    # ── Diagnóstico previo ────────────────────────────────────────────────────
    total, cero_adj, cero_monto = conn.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN Cantidad_adjudicada = 0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN Monto_total_item    = 0 THEN 1 ELSE 0 END)
        FROM items
    """).fetchone()

    print(f"Total ítems          : {total:>6,}")
    print(f"Cant. adjudicada = 0 : {cero_adj:>6,}  ({round(cero_adj/total*100,1)}%)")
    print(f"Monto total = 0      : {cero_monto:>6,}  ({round(cero_monto/total*100,1)}%)")

    # ── Parche ────────────────────────────────────────────────────────────────
    conn.execute("""
        UPDATE items
        SET
            Cantidad_adjudicada = Cantidad_licitada,
            Monto_total_item    = ROUND(Monto_unitario * Cantidad_licitada, 2)
        WHERE
            Cantidad_adjudicada = 0
            AND Monto_unitario  > 0
            AND Cantidad_licitada > 0
    """)
    actualizados = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()

    # ── Diagnóstico posterior ─────────────────────────────────────────────────
    _, cero_adj2, cero_monto2 = conn.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN Cantidad_adjudicada = 0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN Monto_total_item    = 0 THEN 1 ELSE 0 END)
        FROM items
    """).fetchone()

    monto_nuevo = conn.execute(
        "SELECT SUM(Monto_total_item) FROM items"
    ).fetchone()[0] or 0

    conn.close()

    print(f"\nRegistros actualizados : {actualizados:,}")
    print(f"Cant. adjudicada = 0   : {cero_adj2:>6,}  (los restantes no tienen precio unitario)")
    print(f"Monto total = 0        : {cero_monto2:>6,}")
    print(f"Monto total ítems ahora: $ {monto_nuevo:>18,.0f}")
    print("\n✅ Parche aplicado correctamente.")
    print("   Recuerda reiniciar Streamlit (Ctrl+C y python3 -m streamlit run dashboard.py)")
    print("   para que el caché se limpie y cargue los datos actualizados.")

if __name__ == "__main__":
    main()
