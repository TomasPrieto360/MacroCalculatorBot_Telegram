# 📱 Macro Calculator App - Aplicación Móvil Nutricional

Macro Calculator App es una Web App Móvil PWA para seguimiento nutricional. Permite registrar comidas, consultar bases de datos nutricionales y de supermercado (Open Food Facts), escanear códigos de barras, armar recetas y consultar una IA nutricional impulsada por Google Gemini.

## ✨ Características

- 📊 **Cálculo de Macros y Calorías** - Registrá tus comidas del día con sus macronutrientes.
- 👤 **Perfil Personal** - Ajustá tus datos personales (peso, altura, nivel de actividad, metas) y calculá tu TDEE.
- 🔍 **Buscador Nutricional** - Buscá alimentos en la base local o a través de Open Food Facts.
- 📷 **Scanner de Código de Barras** - Escaneá directamente con la cámara del celular.
- 🍳 **Sistema de Recetas** - Creá tus propias recetas compuestas y calculá sus valores por porción/100g.
- 🧠 **IA Nutricional (Gemini)** - Consultale a Gemini ideas de comidas según tus macros o pedile que analice la información de un plato.
- ☁️ **MongoDB / Almacenamiento Local** - Persistencia en la nube con MongoDB Atlas o fallback local en memoria/JSON.

## 🐛 Desarrollo Local

### Prerrequisitos

- Python 3.10+
- (Opcional) API Key de Google Gemini en `.env`
- (Opcional) MongoDB URI en `.env`

### Pasos para ejecutar

```bash
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/MacroCalculatorBot_Telegram.git
cd MacroCalculatorBot_Telegram

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno (opcional)
copy .env.example .env

# 4. Iniciar servidor Flask
python app.py
```

Abrí tu navegador e ingresá a `http://localhost:5000` (o `http://127.0.0.1:5000`).

## 🚀 Deploy a Render (Producción)

1. En Render, creá un **Web Service**.
2. Conectá el repositorio.
3. Configurá:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT app:app`
4. Agregá las variables de entorno (`GEMINI_API_KEY`, `MONGO_URI`) en la pestaña **Environment**.

## 📁 Estructura del Proyecto

```
MacroCalculatorBot_Telegram/
├── app.py              # Backend Flask (REST API)
├── templates/
│   └── index.html      # UI Móvil Single Page Application (PWA)
├── static/
│   ├── js/
│   │   └── app.js      # Lógica de la aplicación frontend
│   └── css/
│       └── style.css   # Estilos de la aplicación móvil
├── alimentos.json      # Base de datos nutricional local
├── requirements.txt   # Dependencias de Python
└── .env.example       # Plantilla de configuración
```

---

*Hecho con ❤️ para facilitar el tracking nutricional*