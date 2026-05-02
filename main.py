from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
import json
import re
from google import genai

app = FastAPI()

firebase_key = json.loads(os.environ["FIREBASE_KEY"])
cred = credentials.Certificate(firebase_key)
firebase_admin.initialize_app(cred)
db = firestore.client()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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

    # Extraer solo lo que dijo el usuario (quitar "AI:" y "User:")
    user_text = ""
    for line in transcript.split("\n"):
        if line.strip().startswith("User:"):
            user_text += line.replace("User:", "").strip() + " "
    
    if not user_text:
        user_text = transcript

    # Extraer producto y cantidad con Gemini
    prompt = f"""Eres un extractor de datos para una tienda en Mexico.
Extrae TODOS los productos y cantidades del siguiente pedido en español.
Si hay varios productos, pon el primero como "producto" y la cantidad total como "cantidad".
Responde SOLO con JSON puro sin backticks ni markdown.
Formato: {{"producto": "nombre del producto principal", "cantidad": numero}}

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

    pedido = {
        "fecha": datetime.now().isoformat(),
        "telefono": telefono,
        "producto": datos.get("producto", "No identificado"),
        "cantidad": datos.get("cantidad", 0),
        "precio_unit": 0,
        "total": 0,
        "estado": "Pendiente",
        "transcripcion": transcript,
        "creado_en": datetime.now().isoformat()
    }

    db.collection("pedidos").add(pedido)
    return JSONResponse({"status": "ok"})
