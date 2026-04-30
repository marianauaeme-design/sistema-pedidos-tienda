# 🛒 Sistema de Pedidos por Llamada

Sistema automático que recibe llamadas de Twilio, transcribe el audio, extrae producto y cantidad con Gemini AI y guarda los pedidos en Firebase.

## Arquitectura

```
Llamada Twilio → FastAPI (Railway) → Gemini AI → Firebase → Dashboard Streamlit
```

## Archivos

- `main.py` — Servidor FastAPI que recibe webhooks de Twilio
- `dashboard.py` — Dashboard Streamlit para ver y gestionar pedidos
- `requirements.txt` — Dependencias Python
- `Procfile` — Configuración para Railway

## Variables de entorno necesarias

En Railway configura estas variables:

```
GEMINI_API_KEY=tu_api_key_de_gemini
FIREBASE_KEY={"type":"service_account",...}  # contenido del JSON de Firebase
```

## Configuración en Twilio

En tu número de Twilio, configura el webhook de grabación apuntando a:
```
https://tu-app.railway.app/twilio/recording
```

## Dashboard local

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## Deploy en Railway

1. Sube el código a GitHub
2. Conecta Railway con tu repositorio
3. Configura las variables de entorno
4. Railway desplegará automáticamente
