from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import os
import json
import traceback
from google import genai
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

SHEET_ID = "1pyc0n_FIk6o9519kvSsQVUcZGYvu8qN45FZ5M12W0io"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Usamos GOOGLE_KEY para las credenciales de Google
google_key = json.loads(os.environ.get("FIREBASE_KEY", "{}"))
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_sheets():
    creds = Credentials.from_service_account_info(google_key, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_config():
    try:
        sh = get_sheets()
        hoja = sh.worksheet("Configuracion")
        registros = hoja.get_all_records()
        config = {}
        for row in registros:
            config[row.get("Campo", "")] = row.get("Valor", "")
        return config
    except Exception as e:
        print(f"Error config: {e}")
        return {}

def buscar_en_inventario(producto_nombre):
    try:
        sh = get_sheets()
        hoja = sh.worksheet("Inventario")
        registros = hoja.get_all_records()
        palabras = producto_nombre.lower().split()
        for row in registros:
            nombre = str(row.get("Producto", "")).lower()
            disponible = str(row.get("Disponible", "")).lower()
            stock = int(row.get("Stock", 0) or 0)
            if any(word in nombre for word in palabras):
                return {
                    "disponible": disponible in ["si", "sí", "yes", "true", "1"],
                    "nombre": row.get("Producto", ""),
                    "precio": float(row.get("Precio", 0) or 0),
                    "stock": stock
                }
        return {"disponible": False}
    except Exception as e:
        traceback.print_exc()
        return {"disponible": False, "error": str(e)}

def guardar_pedido(pedido):
    try:
        sh = get_sheets()
        hoja = sh.worksheet("Pedidos")
        row = [
            pedido.get("fecha", ""),
            pedido.get("telefono", ""),
            pedido.get("producto", ""),
            pedido.get("cantidad", 0),
            pedido.get("precio_unit", 0),
            pedido.get("total", 0),
            pedido.get("estado", "")
        ]
        hoja.append_row(row)
        print(f"Pedido guardado: {row}")
    except Exception as e:
        traceback.print_exc()
        print(f"Error guardando pedido: {str(e)}")

@app.get("/")
def root():
    return {"status": "Sistema de Pedidos activo ✅"}

@app.get("/test-sheets")
async def test_sheets():
    try:
        sh = get_sheets()
        hojas = [ws.title for ws in sh.worksheets()]
        return JSONResponse({"ok": True, "hojas": hojas})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)})

@app.get("/precio")
async def consultar_precio_get(producto: str = ""):
    if not producto:
        return JSONResponse({"error": "Producto no especificado"})
    inventario = buscar_en_inventario(producto)
    if inventario.get("disponible"):
        precio = inventario.get("precio", 0)
        stock = inventario.get("stock", 0)
        nombre = inventario.get("nombre", producto)
        return JSONResponse({
            "disponible": True,
            "nombre": nombre,
            "precio": precio,
            "stock": stock,
            "mensaje": f"El precio de {nombre} es ${precio} pesos. Tenemos {stock} unidades disponibles."
        })
    else:
        return JSONResponse({
            "disponible": False,
            "mensaje": f"Lo sentimos, no encontramos {producto} en nuestro inventario."
        })

@app.post("/precio")
async def consultar_precio_post(request: Request):
    try:
        body = await request.json()
        producto = ""
        if "producto" in body:
            producto = body["producto"]
        elif "message" in body:
            tool_calls = body["message"].get("toolCalls", [])
            if tool_calls:
                args = tool_calls[0].get("function", {}).get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                producto = args.get("producto", "")
    except:
        producto = ""

    if not producto:
        return JSONResponse({"result": "No se especificó el producto"})

    inventario = buscar_en_inventario(producto)
    if inventario.get("disponible"):
        precio = inventario.get("precio", 0)
        stock = inventario.get("stock", 0)
        nombre = inventario.get("nombre", producto)
        return JSONResponse({
            "result": f"El precio de {nombre} es ${precio} pesos. Tenemos {stock} unidades disponibles."
        })
    else:
        return JSONResponse({
            "result": f"Lo sentimos, no encontramos {producto} en nuestro inventario."
        })

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

    print(f"TRANSCRIPT: {transcript[:200]}")
    if not transcript:
        return JSONResponse({"status": "ok"})

    prompt = f"""Analiza esta conversación de una tienda en México y extrae:
1. El pedido FINAL confirmado por el cliente
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
        resp = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
        print(f"GEMINI RAW: {raw}")
        datos = json.loads(raw)
    except Exception as gemini_error:
        traceback.print_exc()
        print(f"GEMINI ERROR: {gemini_error}")
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

    inventario = buscar_en_inventario(producto_principal)
    estado = "Pendiente"
    precio_unit = 0

    if inventario.get("disponible"):
        stock = inventario.get("stock", 0)
        precio_unit = inventario.get("precio", 0)
        if stock >= cantidad:
            estado = "Confirmado"
        else:
            estado = "Sin stock"

    total = precio_unit * cantidad

    pedido = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "telefono": telefono,
        "producto": producto,
        "cantidad": cantidad,
        "precio_unit": precio_unit,
        "total": total,
        "forma_pago": forma_pago,
        "estado": estado
    }

    guardar_pedido(pedido)
    return JSONResponse({"status": "ok"})
