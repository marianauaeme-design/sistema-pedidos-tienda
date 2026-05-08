from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
from datetime import datetime
import os
import json
import traceback
import gspread
from google.oauth2.service_account import Credentials
from groq import Groq

app = FastAPI()

SHEET_ID = "1pyc0n_FIk6o9519kvSsQVUcZGYvu8qN45FZ5M12W0io"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

google_key = json.loads(os.environ.get("FIREBASE_KEY", "{}"))
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

def get_sheets():
    creds = Credentials.from_service_account_info(google_key, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

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
        return {"disponible": False}

def buscar_precios_productos(productos_str):
    """Busca precios de múltiples productos y retorna desglose"""
    productos = [p.strip() for p in productos_str.split(",")]
    desglose = []
    total = 0
    
    for prod in productos:
        inv = buscar_en_inventario(prod)
        if inv.get("disponible"):
            precio = inv.get("precio", 0)
            nombre = inv.get("nombre", prod)
            desglose.append(f"{nombre}: ${precio:.0f}")
            total += precio
        else:
            desglose.append(f"{prod}: $0")
    
    return ", ".join(desglose), total

def guardar_pedido(pedido):
    try:
        sh = get_sheets()
        hoja = sh.worksheet("Pedidos")
        row = [
            pedido.get("nombre_cliente", ""),
            pedido.get("fecha", ""),
            pedido.get("telefono", ""),
            pedido.get("producto", ""),
            pedido.get("cantidad", 0),
            pedido.get("precio_unit", ""),
            pedido.get("total", 0),
            pedido.get("forma_pago", ""),
            pedido.get("estado", "")
        ]
        hoja.append_row(row)
        print(f"Pedido guardado: {row}")
    except Exception as e:
        traceback.print_exc()
        print(f"Error guardando pedido: {str(e)}")

def extraer_datos_con_groq(transcript):
    prompt = f"""Analiza esta conversación de una tienda en México y extrae:
1. El nombre del cliente
2. El pedido FINAL confirmado con cantidad de cada producto
3. La forma de pago mencionada (efectivo o tarjeta)

Responde SOLO con JSON puro sin backticks ni markdown.
Formato exacto:
{{
  "nombre_cliente": "nombre del cliente o No especificado",
  "productos": "(2) Papas, (1) Chocolate, (3) Coca Cola",
  "cantidad_total": numero total de todos los items sumados,
  "forma_pago": "Efectivo" o "Tarjeta" o "No especificado",
  "producto_principal": "nombre del primer producto"
}}

Ejemplo: si pidieron 2 papas y 1 chocolate, productos seria: "(2) Papas, (1) Chocolate"

Conversación:
{transcript}"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    print(f"GROQ RAW: {raw}")
    return json.loads(raw)

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

@app.get("/pedidos")
async def get_pedidos():
    try:
        sh = get_sheets()
        hoja = sh.worksheet("Pedidos")
        registros = hoja.get_all_records()
        return JSONResponse({"pedidos": registros, "total": len(registros)})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"pedidos": [], "error": str(e)})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html = Path("dashboard.html").read_text()
    return HTMLResponse(content=html)

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

    if not transcript:
        return JSONResponse({"status": "ok"})

    print(f"TRANSCRIPT: {transcript[:200]}")

    try:
        datos = extraer_datos_con_groq(transcript)
    except Exception as e:
        traceback.print_exc()
        print(f"GROQ ERROR: {e}")
        datos = {
            "productos": "No identificado",
            "cantidad_total": 0,
            "forma_pago": "No especificado",
            "producto_principal": "No identificado"
        }

    nombre_cliente = datos.get("nombre_cliente", "No especificado")
    producto = datos.get("productos", "No identificado")
    cantidad = datos.get("cantidad_total", 0)
    forma_pago = datos.get("forma_pago", "No especificado")
    producto_principal = datos.get("producto_principal", producto)

    # Buscar precios de todos los productos
    precio_desglose, total_calculado = buscar_precios_productos(producto)

    # Verificar inventario del producto principal
    inventario = buscar_en_inventario(producto_principal)
    estado = "Pendiente"

    if inventario.get("disponible"):
        stock = inventario.get("stock", 0)
        if stock >= cantidad:
            estado = "Confirmado"
        else:
            estado = "Sin stock"

    pedido = {
        "nombre_cliente": nombre_cliente,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "telefono": telefono,
        "producto": producto,
        "cantidad": cantidad,
        "precio_unit": precio_desglose,
        "total": total_calculado,
        "forma_pago": forma_pago,
        "estado": estado
    }

    guardar_pedido(pedido)
    return JSONResponse({"status": "ok"})
