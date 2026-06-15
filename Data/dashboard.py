import streamlit as st
import pandas as pd
import sqlite3

st.title("Dashboard Oncológico — Mercado Público")

conn = sqlite3.connect("oncologia.db")
df = pd.read_sql("SELECT * FROM licitaciones", conn)
conn.close()

st.dataframe(df)