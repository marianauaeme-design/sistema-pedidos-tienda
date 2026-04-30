import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import pandas as pd
import os
import json

st.set_page_config(page_title="Sistema de Pedidos", page_icon="🛒", layout="wide")

# Firebase init (solo una vez)
if not firebase_admin._apps:
    # En Railway usamos variable de entorno, en local usamos archivo
    if os.path.exists("firebase_key.json"):
        cred = credentials.Certificate("firebase_key.json")
    else:
        firebase_key = json.loads(os.environ["FIREBASE_KEY"])
        cred = credentials.Certificate(firebase_key)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Cargar pedidos
def cargar_pedidos():
    docs = db.collection("pedidos").order_by("creado_en", direction=firestore.Query.DESCENDING).stream()
    pedidos = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        pedidos.append(d)
    return pedidos

# Actualizar estado
def actualizar_estado(doc_id, nuevo_estado):
    db.collection("pedidos").document(doc_id).update({"estado": nuevo_estado})

# Header
st.title("🛒 Sistema de Pedidos por Llamada")
st.markdown("---")

# Cargar datos
pedidos = cargar_pedidos()

if not pedidos:
    st.info("No hay pedidos aún.")
else:
    df = pd.DataFrame(pedidos)

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Pedidos", len(df))
    with col2:
        pendientes = len(df[df["estado"] == "Pendiente"])
        st.metric("Pendientes", pendientes)
    with col3:
        completados = len(df[df["estado"] == "Completado"])
        st.metric("Completados", completados)
    with col4:
        total_productos = df["cantidad"].sum()
        st.metric("Total Productos", int(total_productos))

    st.markdown("---")

    # Estadísticas
    st.subheader("📊 Estadísticas")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Productos más pedidos**")
        if "producto" in df.columns:
            top_productos = df.groupby("producto")["cantidad"].sum().sort_values(ascending=False).head(5)
            st.bar_chart(top_productos)

    with col2:
        st.markdown("**Pedidos por estado**")
        estado_counts = df["estado"].value_counts()
        st.bar_chart(estado_counts)

    st.markdown("---")

    # Tabla de pedidos
    st.subheader("📋 Pedidos Recientes")

    for pedido in pedidos[:20]:
        with st.expander(f"📞 {pedido.get('telefono')} — {pedido.get('producto')} x{pedido.get('cantidad')} — {pedido.get('estado')}"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Fecha:** {pedido.get('fecha', 'N/A')}")
                st.write(f"**Teléfono:** {pedido.get('telefono', 'N/A')}")
                st.write(f"**Producto:** {pedido.get('producto', 'N/A')}")
                st.write(f"**Cantidad:** {pedido.get('cantidad', 0)}")
            with col2:
                st.write(f"**Estado:** {pedido.get('estado', 'N/A')}")
                if pedido.get("transcripcion"):
                    st.write(f"**Transcripción:** {pedido.get('transcripcion')}")

                nuevo_estado = st.selectbox(
                    "Cambiar estado",
                    ["Pendiente", "En proceso", "Completado", "Cancelado"],
                    key=pedido["id"]
                )
                if st.button("Actualizar", key=f"btn_{pedido['id']}"):
                    actualizar_estado(pedido["id"], nuevo_estado)
                    st.success("Estado actualizado ✅")
                    st.rerun()

# Botón refrescar
if st.button("🔄 Refrescar pedidos"):
    st.rerun()
