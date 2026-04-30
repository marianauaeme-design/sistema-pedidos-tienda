from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
import json
import httpx

app = FastAPI()

# Firebase init
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Gemini init
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

@app.get("/")
def root():
    return {"status": "Sistema de Pedidos activo ✅"}

@app.post("/twilio/recording", response_class=PlainTextResponse)
async def recibir_grabacion(
    RecordingUrl: str = Form(None),
    From: str = Form(None),
    Timestamp: str = Form(None),
    TranscriptionText: str = Form(None),
):
    texto = TranscriptionText

    # Si no hay transcripción, descargar y transcribir con Gemini
    if not texto and RecordingUrl:
        try:
            async with httpx.AsyncClient() as client:
                audio_resp = await client.get(RecordingUrl + ".mp3")
            audio_bytes = audio_resp.content

            # Usar Gemini para transcribir
            audio_part = {"mime_type": "audio/mp3", "data": audio_bytes}
            trans_resp = model.generate_content([
                "Transcribe exactamente lo que dice esta grabación de voz en español.",
                audio_part
            ])
            texto = trans_resp.text
        except Exception as e:
            texto = f"Error transcribiendo: {str(e)}"

    if not texto:
        return "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"

    # Extraer producto y cantidad con Gemini
    prompt = f"""Eres un extractor de datos para una tienda. 
Extrae el producto y la cantidad del siguiente texto de una llamada.
Responde SOLO con JSON puro sin backticks ni markdown.
Formato exacto: {{"producto": "nombre del producto", "cantidad": numero}}

Texto: {texto}"""

    try:
        resp = model.generate_content(prompt)
        raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
        datos = json.loads(raw)
    except Exception as e:
        datos = {"producto": "No identificado", "cantidad": 0}

    # Guardar en Firebase
    pedido = {
        "fecha": Timestamp or datetime.now().isoformat(),
        "telefono": From or "Desconocido",
        "producto": datos.get("producto", "No identificado"),
        "cantidad": datos.get("cantidad", 0),
        "precio_unit": 0,
        "total": 0,
        "estado": "Pendiente",
        "transcripcion": texto,
        "creado_en": datetime.now().isoformat()
    }

    db.collection("pedidos").add(pedido)

    return "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"
