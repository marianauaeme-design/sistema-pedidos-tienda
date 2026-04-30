from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
import json
import httpx
import base64
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

@app.post("/twilio/recording", response_class=PlainTextResponse)
async def recibir_grabacion(
    RecordingUrl: str = Form(None),
    From: str = Form(None),
    Timestamp: str = Form(None),
    TranscriptionText: str = Form(None),
):
    texto = None

    if RecordingUrl:
        try:
            # Usar .wav en lugar de .mp3
            url = RecordingUrl + ".wav"
            async with httpx.AsyncClient() as http:
                audio_resp = await http.get(url, timeout=30)
            audio_b64 = base64.b64encode(audio_resp.content).decode("utf-8")

            trans_resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "audio/wav",
                                    "data": audio_b64
                                }
                            },
                            {
                                "text": "Transcribe en español exactamente lo que dice esta grabación. Solo escribe lo que se dice, sin explicaciones."
                            }
                        ]
                    }
                ]
            )
            texto = trans_resp.text.strip()
        except Exception as e:
            texto = TranscriptionText or f"Error: {str(e)}"

    if not texto:
        texto = TranscriptionText or "No se pudo obtener el texto"

    # Extraer producto y cantidad
    prompt = f"""Eres un extractor de datos para una tienda en Mexico.
Extrae el producto y la cantidad del siguiente texto en español.
Responde SOLO con JSON puro sin backticks ni markdown.
Formato: {{"producto": "nombre del producto", "cantidad": numero}}

Texto: {texto}"""

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
