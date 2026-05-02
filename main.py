from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
import json
from google import genai

app = FastAPI()

firebase_key = json.loads(os.environ["FIREBASE_KEY"])
cred = credentials.Certificate(firebase_key)
firebase_admin.initialize_app(cred)
db = firestore.client()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def buscar_en_inventario(producto_nombre):
    try:
        docs = db.collection("inventario").stream()
        palabras = producto_nombre.lower().split()
        for doc in docs:
            d = doc.to_dict()
            nombre = d.get("nombre", "").lower()
            if any(word in nombre for word in palabras):
                return {"id": doc.id, "disponible": True, **d}
        return {"disponible": False}
    except:
        return {"disponible": False}

def actualizar_inventario(doc_id, cantidad_pedida, cantidad_actual):
    nueva_cantidad = max(0, cantidad_actual - cantidad_pedida)
    db.collection("inventario").document(doc_id).update({"cantidad": nueva_cantidad})

@app.get("/")
def root():
    return {"status": "Sistema de Pedidos activo ✅"}

@app.post("/vapi")
async def recibir_vapi(request: Request):
    try:
        body = await request.json()
    except:
        return JSONResponse({"status": "ok"})

    message = body.get("message", {})
    msg_type = message.get("type", "")

    if msg_type != "end-of-call-report":
        return JSONResponse({"status": "ok"})

    transcript = message.get("transcript", "")
    call = message.get("call", {})
    customer = call.get("customer", {})
    telefono = customer.get("number", "Desconocido")

    if not transcript:
        return JSONResponse({"status": "ok"})

    # Usar Gemini para analizar toda la conversación
    prompt = f"""Analiza esta conversación de una tienda en México y extrae:
1. El pedido FINAL confirmado por el cliente (ignorando correcciones anteriores)
2. La forma de pago mencionada (efectivo o tarjeta)

Responde SOLO con JSON puro sin backticks ni markdown.
Formato exacto:
{{
  "productos": "lista de productos separados por coma",
  "cantidad_total": numero total de items,
  "forma_pago": "Efectivo" o "Tarjeta" o "No especificado",
  "producto_principal": "nombre del primer producto"
}}

Conversación:
{transcript}"""

    try:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
        datos = json.loads(raw)
    except Exception as e:
        datos = {
            "productos": "No identificado",
            "cantidad_total": 0,
            "forma_pago": "No especificado",
            "producto_principal": "No identificado"
        }

    producto = datos.get("productos", "No identificado")
    cantidad = datos.get("cantidad_total", 0)
    forma_pago = datos.get("forma_pago", "No especificado")
    producto_principal = datos.get("producto_principal", producto)

    # Verificar inventario del producto principal
    inventario = buscar_en_inventario(producto_principal)
    estado = "Pendiente"
    precio_unit = 0

    if inventario.get("disponible"):
        cantidad_disponible = inventario.get("cantidad", 0)
        precio_unit = inventario.get("precio", 0)
        if cantidad_disponible >= cantidad:
            estado = "Confirmado"
            actualizar_inventario(inventario["id"], cantidad, cantidad_disponible)
        else:
            estado = "Sin stock"

    total = precio_unit * cantidad

    pedido = {
        "fecha": datetime.now().isoformat(),
        "telefono": telefono,
        "producto": producto,
        "cantidad": cantidad,
        "precio_unit": precio_unit,
        "total": total,
        "forma_pago": forma_pago,
        "estado": estado,
        "transcripcion": transcript,
        "creado_en": datetime.now().isoformat()
    }

    db.collection("pedidos").add(pedido)
    return JSONResponse({"status": "ok"})
