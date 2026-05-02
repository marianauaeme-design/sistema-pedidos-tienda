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
    """Busca un producto en el inventario de Firebase"""
    try:
        docs = db.collection("inventario").stream()
        for doc in docs:
            d = doc.to_dict()
            nombre = d.get("nombre", "").lower()
            # Buscar coincidencia parcial
            if any(word in nombre for word in producto_nombre.lower().split()):
                return {"id": doc.id, "disponible": True, **d}
        return {"disponible": False}
    except Exception as e:
        return {"disponible": False, "error": str(e)}

def actualizar_inventario(doc_id, cantidad_pedida, cantidad_actual):
    """Reduce el inventario después de un pedido"""
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

    # Extraer solo lo que dijo el usuario
    user_text = ""
    for line in transcript.split("\n"):
        if line.strip().startswith("User:"):
            user_text += line.replace("User:", "").strip() + " "
    
    if not user_text:
        user_text = transcript

    # Extraer producto y cantidad con Gemini
    prompt = f"""Eres un extractor de datos para una tienda en Mexico.
Extrae el producto principal y la cantidad del siguiente pedido en español.
Responde SOLO con JSON puro sin backticks ni markdown.
Formato: {{"producto": "nombre del producto", "cantidad": numero}}

Pedido: {user_text}"""

    try:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
        datos = json.loads(raw)
    except Exception:
        datos = {"producto": "No identificado", "cantidad": 0}

    producto = datos.get("producto", "No identificado")
    cantidad = datos.get("cantidad", 0)

    # Verificar inventario
    inventario = buscar_en_inventario(producto)
    estado = "Pendiente"
    
    if inventario.get("disponible"):
        cantidad_disponible = inventario.get("cantidad", 0)
        precio_unit = inventario.get("precio", 0)
        
        if cantidad_disponible >= cantidad:
            estado = "Confirmado"
            # Actualizar inventario
            actualizar_inventario(inventario["id"], cantidad, cantidad_disponible)
        else:
            estado = "Sin stock"
    else:
        precio_unit = 0

    total = precio_unit * cantidad

    pedido = {
        "fecha": datetime.now().isoformat(),
        "telefono": telefono,
        "producto": producto,
        "cantidad": cantidad,
        "precio_unit": precio_unit,
        "total": total,
        "estado": estado,
        "transcripcion": transcript,
        "creado_en": datetime.now().isoformat()
    }

    db.collection("pedidos").add(pedido)
    return JSONResponse({"status": "ok"})
