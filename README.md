# 🤖 MacroBot - Asistente Nutricional para Telegram

MacroBot es un bot de Telegram para seguimiento nutricional. Permite registrar comidas, crear recetas, escanear etiquetas y consultar una IA nutricional.

## ✨ Características

- 📊 **Cálculo de Macros** - Registrá `150 pollo` y el bot calcula kcal, proteínas, carbs y grasas
- 👤 **Perfil Personal** - Calcula tu TDEE con fórmula Mifflin-St Jeor
- 📦 **Paquetes Personalizados** - Cargá productos del supermercado escaneando sus etiquetas
- 🍳 **Sistema de Recetas** - Armá recetas y el bot recalcula valores a 100g
- 🧠 **IA Nutricional** - Consultale a Gemini qué podés preparar con lo que tengas
- 📷 **Scanner de Etiquetas** - Enviá foto de una etiqueta y el bot la lee automáticamente
- ☁️ **MongoDB** - Base de datos en la nube (no más JSONs locales)

## 🚀 Deploy a Render (Producción)

### Prerrequisitos

1. Cuenta en [Render.com](https://render.com)
2. MongoDB Atlas (cluster gratuito) con connection string
3. Token de tu bot de Telegram (@BotFather)
4. API Key de Google Gemini (https://aistudio.google.com/app/apikey)

### Pasos

#### 1. Prepará tu entorno local

```bash
# Cloná el repo
git clone https://github.com/TU_USUARIO/MacroBot.git
cd MacroBot

# Copiá y configurá el .env
copy .env.example .env
# Editá .env con tus datos reales
```

#### 2. Subí el código a GitHub

```bash
git add .
git commit -m "Ready for Render deploy"
git push origin main
```

#### 3. Creá el servicio en Render

1. Ir a [Dashboard de Render](https://dashboard.render.com)
2. Click en **"New +"** → **"Web Service"**
3. Conectá tu repositorio de GitHub
4. Configurá:
   - **Name**: macrobot
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT bot_refactored:app`

#### 4. Configurá las Variables de Entorno

En Render, agregá estas variables (en "Environment"):

| Variable | Valor |
|----------|-------|
| `TELEGRAM_TOKEN` | Tu token de @BotFather |
| `GEMINI_API_KEY` | Tu API key de Gemini |
| `MONGO_URI` | Connection string de MongoDB Atlas |

#### 5. Desplegá

Click en **"Create Web Service"** y esperá a que termine el build.

#### 6. Configurá el Webhook

Una vez deployado, vas a ver la URL de tu servicio (ej: `https://macrobot.onrender.com`).

**Opción A - Automático**: El bot ya se configura solo al iniciar (líneas finales de `bot_refactored.py`)

**Opción B - Manual** (si no funcionó):
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://tu-servicio.onrender.com/<TOKEN>"
```

#### 7. Migrá los datos (una sola vez)

Si tenés datos en los JSONs old, ejecutá el script de migración:

```bash
python migrate_db.py
```

## 🔄 Cambiar de PythonAnywhere a Render

Cuando tu bot esté funcionando en Render:

1. En tu terminal, cambiá el webhook de Telegram a la nueva URL de Render:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://tu-servicio.onrender.com/<TOKEN>"
   ```

2. Desactivá el bot en PythonAnywhere (o dejalo andando como backup)

3. ¡Listo! Ya no necesitás la PC prendida 🇦🇷

## 🐛 Desarrollo Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar (usa polling, no webhooks)
python bot_refactored.py
```

## 📁 Estructura

```
MacroBot/
├── bot_refactored.py   # Bot principal con MongoDB
├── migrate_db.py       # Script de migración JSON → MongoDB
├── alimentos.json      # Base de datos de alimentos
├── requirements.txt   # Dependencias Python
├── Dockerfile         # Para containerización
├── Procfile           # Para Render
└── .env.example       # Plantilla de configuración
```

## 📝 Notas

- El archivo `usuarios.json` ya no se usa — todo está en MongoDB
- Si hay errores, revisá los logs en el dashboard de Render
- El bot usa **webhooks** (no polling) en producción

---

*Hecho con ❤️ para facilitar el tracking nutricional*