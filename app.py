import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import sys
from dotenv import load_dotenv
import difflib
from google import genai
import uuid
from pymongo import MongoClient
import urllib.request
import urllib.parse

# Obtener la ruta absoluta donde está bot.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cargar el .env exactamente desde esa ruta
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Configurar Gemini (nuevo SDK)
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

MONGO_URI = os.getenv("MONGO_URI")
mongo_available = False

if MONGO_URI:
    try:
        # Conexión optimizada - timeout reducido para detectar errores rápido
        mongo_client = MongoClient(
            MONGO_URI,
            maxPoolSize=10,
            minPoolSize=1,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=5000,
            retryWrites=True,
            retryReads=True,
            tls=True,
            tlsAllowInvalidCertificates=False
        )
        # Test de conexión
        mongo_client.admin.command('ping')
        db = mongo_client.get_database("macrobot_db")
        col_usuarios = db.usuarios
        col_alimentos = db.alimentos
        mongo_available = True
        print("[OK] MongoDB conectado exitosamente")
    except Exception as e:
        print(f"[ERROR] MongoDB no disponible: {e}")
        print("[INFO] Usando modo en memoria (sin persistencia)")
        mongo_client = None
        col_usuarios = None
        col_alimentos = None
else:
    print("ADVERTENCIA: MONGO_URI no encontrado - modo memoria")
    mongo_client = None
    col_usuarios = None
    col_alimentos = None

def guardar_alimento_global(nombre_key, stats):
    """Guarda un alimento en la colección db.alimentos de MongoDB para enriquecer la base global del bot."""
    if col_alimentos is not None and nombre_key:
        try:
            nombre_clean = str(nombre_key).lower().strip()
            doc = {
                "_id": nombre_clean,
                "kcal": float(stats.get("kcal", 0)),
                "proteinas": float(stats.get("proteinas", 0)),
                "carbos": float(stats.get("carbos", 0)),
                "grasas": float(stats.get("grasas", 0)),
                "fibra": float(stats.get("fibra", 0)),
                "sodio": float(stats.get("sodio", 0))
            }
            if "peso_unidad" in stats:
                doc["peso_unidad"] = float(stats["peso_unidad"])
            col_alimentos.update_one({"_id": nombre_clean}, {"$set": doc}, upsert=True)
        except Exception as e:
            print(f"[WARN] Error guardando alimento global en MongoDB: {e}")

def buscar_alimento_mongo_global(nombre_key):
    """Busca un alimento en la base de datos global db.alimentos de MongoDB."""
    if col_alimentos is not None and nombre_key:
        try:
            nombre_clean = str(nombre_key).lower().strip()
            doc = col_alimentos.find_one({"_id": nombre_clean})
            if doc:
                return doc
        except Exception as e:
            print(f"[WARN] Error consultando alimento global en MongoDB: {e}")
    return None

def buscar_open_food_facts(query):
    """Busca alimentos en la API pública de Open Food Facts por nombre o código de barras."""
    if not query:
        return None
    query_clean = str(query).strip().lower()
    headers = {'User-Agent': 'MacroBotTelegram/2.0 (https://github.com/TomasPrieto360/MacroCalculatorBot_Telegram)'}
    
    try:
        # 1. Si son solo dígitos (8 a 14 números), es un Código de Barras EAN
        if query_clean.isdigit() and len(query_clean) in [8, 12, 13, 14]:
            url = f"https://world.openfoodfacts.org/api/v2/product/{query_clean}.json"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("status") == 1 and "product" in data:
                    p = data["product"]
                    nutriments = p.get("nutriments", {})
                    nombre = p.get("product_name") or p.get("product_name_es") or query_clean
                    sodio_val = nutriments.get("sodium_100g")
                    sodio_mg = float(sodio_val) * 1000 if sodio_val is not None else (float(nutriments.get("salt_100g") or 0) / 2.5 * 1000)
                    return {
                        "alimento": nombre.lower(),
                        "kcal": float(nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal_value") or 0),
                        "proteinas": float(nutriments.get("proteins_100g") or 0),
                        "carbos": float(nutriments.get("carbohydrates_100g") or 0),
                        "grasas": float(nutriments.get("fat_100g") or 0),
                        "fibra": float(nutriments.get("fiber_100g") or 0),
                        "sodio": float(sodio_mg),
                        "fuente": "openfoodfacts"
                    }
        
        # 2. Búsqueda por texto
        encoded_query = urllib.parse.quote(query_clean)
        url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={encoded_query}&search_simple=1&action=process&json=1&page_size=5"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            products = data.get("products", [])
            for p in products:
                nutriments = p.get("nutriments", {})
                kcal = nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal_value")
                if kcal is not None and float(kcal) > 0:
                    nombre = p.get("product_name") or p.get("product_name_es") or query_clean
                    sodio_val = nutriments.get("sodium_100g")
                    sodio_mg = float(sodio_val) * 1000 if sodio_val is not None else (float(nutriments.get("salt_100g") or 0) / 2.5 * 1000)
                    return {
                        "alimento": nombre.lower(),
                        "kcal": float(kcal),
                        "proteinas": float(nutriments.get("proteins_100g") or 0),
                        "carbos": float(nutriments.get("carbohydrates_100g") or 0),
                        "grasas": float(nutriments.get("fat_100g") or 0),
                        "fibra": float(nutriments.get("fiber_100g") or 0),
                        "sodio": float(sodio_mg),
                        "fuente": "openfoodfacts"
                    }
    except Exception as e:
        print(f"[WARN] Open Food Facts Error: {e}")
        
    return None

def calcular_indice_saciedad(prot, fibra, kcal, grasas):
    """Calcula un índice de saciedad del 1.0 al 10.0 basado en proteínas, fibra, calorías y grasas."""
    if kcal <= 0:
        return 5.0, "🍐 Moderado"
        
    proteina_score = (prot / max(1, kcal / 100)) * 2.5
    fibra_score = (fibra / max(1, kcal / 100)) * 3.0
    grasa_deduction = (grasas / max(1, kcal / 100)) * 0.5
    
    score_raw = 4.0 + proteina_score + fibra_score - grasa_deduction
    score = min(max(round(score_raw, 1), 1.0), 10.0)
    
    if score >= 7.5:
        etiqueta = "🍏 ¡Muy Saciante!"
    elif score >= 5.0:
        etiqueta = "🍐 Saciante Moderado"
    else:
        etiqueta = "🍕 Poco Saciante"
        
    return score, etiqueta

def get_user(user_id):
    user_id = str(user_id)
    if col_usuarios is not None:
        try:
            user = col_usuarios.find_one({"_id": user_id})
            if user:
                return user
        except Exception as e:
            print(f"[WARN] Error leyendo usuario: {e}")
    return {
        "kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "fibra": 0, "sodio": 0,
        "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": [], "mis_alimentos": {}
    }

def save_user(user_id, data):
    user_id = str(user_id)
    if col_usuarios is not None:
        try:
            data["_id"] = user_id
            col_usuarios.update_one({"_id": user_id}, {"$set": data}, upsert=True)
        except Exception as e:
            print(f"[WARN] Error guardando usuario: {e}")

# Cache en memoria por peticion para evitar múltiples llamadas a DB en un solo comando
user_cache = {}

class MongoDict(dict):
    def __getitem__(self, key):
        key = str(key)
        if not super().__contains__(key):
            user = get_user(key)
            super().__setitem__(key, user)
        return super().__getitem__(key)
        
    def __contains__(self, key):
        key = str(key)
        if super().__contains__(key):
            return True
        # Si no está en memoria, probamos cargarlo. get_user siempre devuelve un dict (existente o default)
        user = get_user(key)
        super().__setitem__(key, user)
        return True

datos_usuarios = MongoDict()

def guardar_datos():
    for user_id, data in datos_usuarios.items():
        save_user(user_id, data)
    # NO limpiamos el cache - mantenemos datos en memoria entre requests


TOKEN = os.getenv('TELEGRAM_TOKEN', 'TU_TOKEN_ACA')
bot = telebot.TeleBot(TOKEN, threaded=False)

# Configurar comandos de menú oficial de Telegram
try:
    bot.set_my_commands([
        telebot.types.BotCommand("start", "Iniciar bot y menú principal"),
        telebot.types.BotCommand("resumen", "Ver resumen del día y barras de progreso"),
        telebot.types.BotCommand("favoritos", "Ver tus comidas favoritas ('Lo de siempre')"),
        telebot.types.BotCommand("perfil", "Configurar tu perfil y calcular metas TDEE"),
        telebot.types.BotCommand("ia", "Consultar a la IA Nutricional"),
        telebot.types.BotCommand("ayuda", "Guía de uso de comandos y atajos")
    ])
except Exception as e:
    print(f"[WARN] No se pudieron registrar comandos oficiales: {e}")

# ----------------- TECLADOS Y MENÚS -----------------
def menu_principal():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    web_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:10000")
    try:
        markup.add(KeyboardButton("📱 Abrir App Web", web_app=telebot.types.WebAppInfo(url=web_url)))
    except Exception as e:
        print(f"[WARN] WebAppInfo no disponible: {e}")
    markup.add("🍎 Registrar Comida", "📊 Mi Día")
    markup.add("⭐️ Favoritos", "📝 Agregar Macros (IA)")
    markup.add("⚙️ Herramientas")
    return markup

def menu_mi_dia():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 Resumen de Macros", "📝 Ver lo que comí hoy")
    markup.add("🧹 Terminar Día", "🔙 Menú Principal")
    return markup

def menu_favoritos():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("⚡ Cargar Favorito", "➕ Guardar Favorito")
    markup.add("🗑️ Borrar Favorito", "🔙 Menú Principal")
    return markup

def menu_herramientas():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Mi Perfil", "🤖 Preguntarle a la IA")
    markup.add("📦 Cargar Paquete", "🍳 Crear Receta")
    markup.add("🗑️ Borrar Alimento", "🔙 Menú Principal")
    return markup

def boton_volver():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Volver")
    return markup

@bot.message_handler(commands=['start'])
def bienvenida(message):
    bot.reply_to(message, "¡Hola! Soy tu asistente nutricional. ¿Qué querés hacer hoy?", reply_markup=menu_principal())

@bot.message_handler(commands=['ayuda'])
def mostrar_ayuda(message):
    texto = (
        "❓ **Guía de Uso de MacroBot:**\n\n"
        "1. 🍎 **Registrar Comidas**: Escribí `[cantidad] [alimento]` (ej: `150 pollo` o `2 u huevo`).\n"
        "2. 🎤 **Notas de Voz**: ¡Mandale un audio al bot diciendo lo que comiste!\n"
        "3. 📸 **Fotos**: Sacale foto a tu plato de comida o a una etiqueta nutricional.\n"
        "4. ⭐️ **Favoritos**: Guardá tus desayunos o platos en '⭐️ Favoritos' para registrarlos en 1 clic.\n"
        "5. 🤖 **IA Nutricional**: Preguntale qué cocinar con los ingredientes que tengas a mano."
    )
    bot.reply_to(message, texto, reply_markup=menu_principal(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🔙 Menú Principal")
def volver_inicio(message):
    bot.reply_to(message, "Volviendo al inicio...", reply_markup=menu_principal())

@bot.message_handler(func=lambda message: message.text == "📊 Mi Día")
def submenu_mi_dia(message):
    bot.reply_to(message, "¿Qué querés revisar de tu día?", reply_markup=menu_mi_dia())

@bot.message_handler(func=lambda message: message.text == "⚙️ Herramientas")
def submenu_herramientas(message):
    bot.reply_to(message, "Herramientas y opciones extras:", reply_markup=menu_herramientas())

@bot.message_handler(func=lambda message: message.text == "🍎 Registrar Comida")
def instruccion_comida(message):
    bot.reply_to(message, "Para registrar comida simplemente escribime:\n`[cantidad] [alimento]`\n\n*Ejemplos:*\n`150 pollo` (150 gramos)\n`2 u huevo` (2 unidades)\n🎤 O simplemente ¡mandame una **nota de voz** o **foto de tu plato**!", reply_markup=menu_principal(), parse_mode="Markdown")

# ----------------- BASE DE DATOS -----------------
archivo_alimentos = os.path.join(BASE_DIR, "alimentos.json")
if os.path.exists(archivo_alimentos):
    with open(archivo_alimentos, 'r', encoding='utf-8') as f:
        db_alimentos = json.load(f)
        tabla_nutricional = db_alimentos.get("alimentos", {})
        diccionario_alias = db_alimentos.get("alias", {})
else:
    tabla_nutricional = {}
    diccionario_alias = {}


# ----------------- RESET DIARIO -----------------
@bot.message_handler(func=lambda message: message.text == "🧹 Terminar Día")
def terminar_dia(message):
    user_id = str(message.from_user.id)
    if user_id in datos_usuarios:
        datos_usuarios[user_id]["kcal"] = 0
        datos_usuarios[user_id]["proteinas"] = 0
        datos_usuarios[user_id]["carbos"] = 0
        datos_usuarios[user_id]["grasas"] = 0
        datos_usuarios[user_id]["fibra"] = 0
        datos_usuarios[user_id]["sodio"] = 0
        datos_usuarios[user_id]["historial_hoy"] = []
        guardar_datos()
        bot.reply_to(message, "🧹 ¡Día reiniciado! Todos tus macros volvieron a cero. ¡Mañana será otro día!", reply_markup=menu_principal())
    else:
        bot.reply_to(message, "Todavía no cargaste nada.", reply_markup=menu_principal())

# ----------------- RESUMEN Y ESTADO -----------------
def generar_barra_progreso(actual, meta, bloques=10):
    if meta <= 0:
        return "░" * bloques
    porcentaje = min(max(actual / meta, 0.0), 1.0)
    llenos = int(round(porcentaje * bloques))
    vacios = bloques - llenos
    return "▓" * llenos + "░" * vacios

@bot.message_handler(commands=['resumen'])
@bot.message_handler(func=lambda message: message.text == "📊 Resumen de Macros")
def mostrar_resumen(message):
    user_id = str(message.from_user.id)
    if user_id in datos_usuarios:
        datos = datos_usuarios[user_id]
        
        meta_protes = datos.get("meta_proteinas", 160)
        meta_kcal = datos.get("meta_kcal", 2000)
        
        kcal_actual = datos.get("kcal", 0)
        prot_actual = datos.get("proteinas", 0)
        carb_actual = datos.get("carbos", 0)
        gras_actual = datos.get("grasas", 0)
        fibra_actual = datos.get("fibra", 0)
        sodio_actual = datos.get("sodio", 0)
        
        carbos_netos = max(0.0, carb_actual - fibra_actual)
        score_saciedad, etiqueta_saciedad = calcular_indice_saciedad(prot_actual, fibra_actual, kcal_actual, gras_actual)
        
        faltan_protes = meta_protes - prot_actual
        faltan_kcal = meta_kcal - kcal_actual
        
        pct_kcal = (kcal_actual / meta_kcal * 100) if meta_kcal > 0 else 0
        pct_prot = (prot_actual / meta_protes * 100) if meta_protes > 0 else 0
        
        barra_kcal = generar_barra_progreso(kcal_actual, meta_kcal)
        barra_prot = generar_barra_progreso(prot_actual, meta_protes)
        
        texto_protes = f"¡Pasaste la meta por {abs(faltan_protes):.1f}g!" if faltan_protes < 0 else f"Faltan {faltan_protes:.1f}g"
        texto_kcal = f"¡Te pasaste por {abs(faltan_kcal):.0f} kcal!" if faltan_kcal < 0 else f"Faltan {faltan_kcal:.0f} kcal"
        
        alerta_sodio = " ⚠️ (Elevado)" if sodio_actual > 2300 else ""
        
        respuesta = (
            f"📊 **Resumen del Día:**\n\n"
            f"🔥 **Kcal:** [{barra_kcal}] {kcal_actual:.0f} / {meta_kcal:.0f} ({pct_kcal:.0f}%)\n"
            f"👉 _{texto_kcal}_\n\n"
            f"🥩 **Proteínas:** [{barra_prot}] {prot_actual:.1f} / {meta_protes:.1f}g ({pct_prot:.0f}%)\n"
            f"👉 _{texto_protes}_\n\n"
            f"🍞 **Carbos Netos:** {carbos_netos:.1f}g _(Total: {carb_actual:.1f}g \| Fibra: {fibra_actual:.1f}g 🌾)_\n"
            f"🥑 **Grasas:** {gras_actual:.1f}g\n"
            f"🧂 **Sodio:** {sodio_actual:.0f} mg / 2300 mg{alerta_sodio}\n\n"
            f"🍏 **Índice de Saciedad:** {score_saciedad}/10 ({etiqueta_saciedad})"
        )
        bot.reply_to(message, respuesta, reply_markup=menu_mi_dia(), parse_mode="Markdown")
    else:
        bot.reply_to(message, "Che, todavía no cargaste nada de comida hoy.", reply_markup=menu_principal())

@bot.message_handler(func=lambda message: message.text == "📝 Ver lo que comí hoy")
def ver_historial(message):
    user_id = str(message.from_user.id)
    if user_id in datos_usuarios and "historial_hoy" in datos_usuarios[user_id] and len(datos_usuarios[user_id]["historial_hoy"]) > 0:
        historial = datos_usuarios[user_id]["historial_hoy"]
        texto = "🍽️ **Tu registro de hoy:**\n\n"
        markup = InlineKeyboardMarkup()
        
        for idx, item in enumerate(historial):
            emoji = "🍗" if "u " in item["cantidad_str"] else "⚖️"
            texto += f"{idx + 1}. {emoji} {item['cantidad_str']} {item['alimento'].title()} ({item['kcal']:.0f} kcal)\n"
            markup.add(InlineKeyboardButton(f"❌ Borrar {item['alimento'].title()}", callback_data=f"delhist_{item['id']}"))
            
        bot.reply_to(message, texto, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.reply_to(message, "Tu historial de hoy está vacío.", reply_markup=menu_mi_dia())

# ----------------- ONBOARDING (PERFIL) -----------------
registro_temporal = {}

@bot.message_handler(func=lambda message: message.text == "👤 Mi Perfil")
def iniciar_perfil(message):
    user_id = str(message.from_user.id)
    registro_temporal[user_id] = {}
    msg = bot.reply_to(message, "¡Vamos a configurar tu perfil para calcular tus metas!\n\n¿Cuántos años tenés? (Ingresá solo el número, ej: 35)", reply_markup=ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, paso_edad)

def paso_edad(message):
    try:
        edad = int(message.text)
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['edad'] = edad
        msg = bot.reply_to(message, "Perfecto. ¿Cuánto pesás en kg? (Ej: 80.5)")
        bot.register_next_step_handler(msg, paso_peso)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número entero para la edad (ej: 35).")
        bot.register_next_step_handler(msg, paso_edad)

def paso_peso(message):
    try:
        peso = float(message.text.replace(',', '.'))
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['peso'] = peso
        msg = bot.reply_to(message, "Anotado. ¿Cuánto medís en cm? (Ej: 180)")
        bot.register_next_step_handler(msg, paso_altura)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número válido para el peso (ej: 80.5).")
        bot.register_next_step_handler(msg, paso_peso)

def paso_altura(message):
    try:
        altura = int(message.text)
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['altura'] = altura
        
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("Hombre", "Mujer")
        msg = bot.reply_to(message, "Genial. ¿Sos Hombre o Mujer?", reply_markup=markup)
        bot.register_next_step_handler(msg, paso_genero)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número válido para la altura en centímetros (ej: 180).")
        bot.register_next_step_handler(msg, paso_altura)

def paso_genero(message):
    genero = message.text.lower()
    if genero not in ["hombre", "mujer"]:
        msg = bot.reply_to(message, "Por favor, usá los botones para elegir 'Hombre' o 'Mujer'.")
        bot.register_next_step_handler(msg, paso_genero)
        return
        
    user_id = str(message.from_user.id)
    registro_temporal[user_id]['genero'] = genero
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("🛋️ Sedentario", "🚶 Ligero")
    markup.add("🏃 Moderado", "🏋️ Activo")
    markup.add("⛏️ Muy Activo")
    
    texto_act = (
        "¿Cuál es tu nivel de actividad física semanal?\n\n"
        "🛋️ Sedentario (Casi nada de ejercicio, trabajo de oficina)\n"
        "🚶 Ligero (Ejercicio suave 1 a 3 veces por semana)\n"
        "🏃 Moderado (Gym o deporte 3 a 5 veces por semana)\n"
        "🏋️ Activo (Ejercicio intenso 6 a 7 días a la semana)\n"
        "⛏️ Muy Activo (Trabajo físico pesado o doble turno)"
    )
    msg = bot.reply_to(message, texto_act, reply_markup=markup)
    bot.register_next_step_handler(msg, paso_actividad)

def paso_actividad(message):
    texto = message.text
    multiplicadores = {
        "🛋️ Sedentario": 1.2,
        "🚶 Ligero": 1.375,
        "🏃 Moderado": 1.55,
        "🏋️ Activo": 1.725,
        "⛏️ Muy Activo": 1.9
    }
    
    if texto not in multiplicadores:
        texto_error = (
            "Por favor, usá los botones para elegir tu actividad:\n\n"
            "🛋️ Sedentario (Casi nada de ejercicio, trabajo de oficina)\n"
            "🚶 Ligero (Ejercicio suave 1 a 3 veces por semana)\n"
            "🏃 Moderado (Gym o deporte 3 a 5 veces por semana)\n"
            "🏋️ Activo (Ejercicio intenso 6 a 7 días a la semana)\n"
            "⛏️ Muy Activo (Trabajo físico pesado o doble turno)"
        )
        msg = bot.reply_to(message, texto_error)
        bot.register_next_step_handler(msg, paso_actividad)
        return
        
    user_id = str(message.from_user.id)
    registro_temporal[user_id]['actividad'] = multiplicadores[texto]
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Bajar", "Mantener", "Subir")
    msg = bot.reply_to(message, "Última pregunta. ¿Cuál es tu objetivo?", reply_markup=markup)
    bot.register_next_step_handler(msg, paso_objetivo)

def paso_objetivo(message):
    objetivo = message.text.lower()
    if objetivo not in ["bajar", "mantener", "subir"]:
        msg = bot.reply_to(message, "Por favor, elegí Bajar, Mantener o Subir usando los botones.")
        bot.register_next_step_handler(msg, paso_objetivo)
        return
        
    user_id = str(message.from_user.id)
    datos = registro_temporal[user_id]
    
    # Cálculo TMB (Mifflin-St Jeor)
    if datos['genero'] == 'hombre':
        tmb = (10 * datos['peso']) + (6.25 * datos['altura']) - (5 * datos['edad']) + 5
    else:
        tmb = (10 * datos['peso']) + (6.25 * datos['altura']) - (5 * datos['edad']) - 161
        
    tdee = tmb * datos['actividad']
    
    if objetivo == "bajar":
        meta_kcal = tdee - 500
    elif objetivo == "subir":
        meta_kcal = tdee + 500
    else:
        meta_kcal = tdee
        
    meta_proteinas = 2.0 * datos['peso']
    
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0}
        
    datos_usuarios[user_id]["meta_kcal"] = meta_kcal
    datos_usuarios[user_id]["meta_proteinas"] = meta_proteinas
    guardar_datos()
    
    bot.reply_to(message, f"✅ ¡Perfil configurado con éxito!\n\n"
                          f"Tu Gasto Energético (TDEE) es: {tdee:.0f} kcal\n"
                          f"🎯 Para tu objetivo de *{objetivo.upper()}*:\n"
                          f"🔥 Meta diaria de Kcal: {meta_kcal:.0f} kcal\n"
                          f"🥩 Meta de Proteínas: {meta_proteinas:.1f}g\n\n"
                          f"¡Ya podés empezar a cargar comida!", reply_markup=menu_principal(), parse_mode="Markdown")

# ----------------- CARGA DE PAQUETES (FASE 2) -----------------
@bot.message_handler(func=lambda message: message.text == "📦 Cargar Paquete")
def iniciar_paquete(message):
    user_id = str(message.from_user.id)
    if user_id not in registro_temporal:
        registro_temporal[user_id] = {}
        
    msg = bot.reply_to(message, "¡Vamos a guardar un alimento nuevo!\n\n¿Cómo se llama el producto? (Ej: galletitas oreo, barrita cereal)", reply_markup=boton_volver())
    bot.register_next_step_handler(msg, paso_nombre_paquete)

def paso_nombre_paquete(message):
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Cancelado.", reply_markup=menu_herramientas())
        return
        
    nombre = message.text.lower()
    user_id = str(message.from_user.id)
    registro_temporal[user_id]['paquete_nombre'] = nombre
    
    msg = bot.reply_to(message, f"Perfecto. Mirá la etiqueta nutricional de '{nombre}'.\n\n¿De cuántos **gramos** es la porción que figura ahí? (Ej: 22, 50, 100)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, paso_porcion_paquete)

def paso_porcion_paquete(message):
    try:
        porcion = float(message.text.replace(',', '.'))
        if porcion <= 0:
            raise ValueError
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['paquete_porcion'] = porcion
        msg = bot.reply_to(message, f"Anotado (Porción de {porcion}g).\n\n¿Cuántas **Calorías (Kcal)** aporta ESA porción de {porcion}g?", parse_mode="Markdown")
        bot.register_next_step_handler(msg, paso_kcal_paquete)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número mayor a cero (ej: 25). ¿De cuántos gramos es la porción?")
        bot.register_next_step_handler(msg, paso_porcion_paquete)

def paso_kcal_paquete(message):
    try:
        kcal = float(message.text.replace(',', '.'))
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['paquete_kcal'] = kcal
        porcion = registro_temporal[user_id]['paquete_porcion']
        msg = bot.reply_to(message, f"¿Cuántos gramos de **Proteínas** tiene esa porción de {porcion}g?", parse_mode="Markdown")
        bot.register_next_step_handler(msg, paso_prot_paquete)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número válido (ej: 150.5). ¿Kcal de la porción?")
        bot.register_next_step_handler(msg, paso_kcal_paquete)

def paso_prot_paquete(message):
    try:
        prot = float(message.text.replace(',', '.'))
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['paquete_prot'] = prot
        porcion = registro_temporal[user_id]['paquete_porcion']
        msg = bot.reply_to(message, f"¿Cuántos gramos de **Carbohidratos** tiene esa porción de {porcion}g?", parse_mode="Markdown")
        bot.register_next_step_handler(msg, paso_carb_paquete)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número. ¿Proteínas de la porción?")
        bot.register_next_step_handler(msg, paso_prot_paquete)

def paso_carb_paquete(message):
    try:
        carb = float(message.text.replace(',', '.'))
        user_id = str(message.from_user.id)
        registro_temporal[user_id]['paquete_carb'] = carb
        porcion = registro_temporal[user_id]['paquete_porcion']
        msg = bot.reply_to(message, f"Por último, ¿cuántos gramos de **Grasas** tiene esa porción de {porcion}g?", parse_mode="Markdown")
        bot.register_next_step_handler(msg, paso_grasas_paquete)
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número. ¿Carbohidratos de la porción?")
        bot.register_next_step_handler(msg, paso_carb_paquete)

def paso_grasas_paquete(message):
    try:
        gras = float(message.text.replace(',', '.'))
        user_id = str(message.from_user.id)
        
        if user_id not in datos_usuarios:
            datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000}
            
        if "mis_alimentos" not in datos_usuarios[user_id]:
            datos_usuarios[user_id]["mis_alimentos"] = {}
            
        nombre = registro_temporal[user_id]['paquete_nombre']
        porcion = registro_temporal[user_id]['paquete_porcion']
        
        # Convertimos todo a valor por cada 100g para estandarizar la DB
        factor = 100 / porcion
        
        datos_usuarios[user_id]["mis_alimentos"][nombre] = {
            "kcal": registro_temporal[user_id]['paquete_kcal'] * factor,
            "proteinas": registro_temporal[user_id]['paquete_prot'] * factor,
            "carbos": registro_temporal[user_id]['paquete_carb'] * factor,
            "grasas": gras * factor
        }
        
        guardar_datos()
        
        bot.reply_to(message, f"✅ ¡El alimento *{nombre}* se guardó en tu base de datos personal!\n\n"
                              f"La próxima vez que comas esto, solo tenés que escribirme cuántos gramos comiste. Por ejemplo: `50 {nombre}` y yo lo calculo solo.", 
                              reply_markup=menu_principal(), parse_mode="Markdown")
    except:
        msg = bot.reply_to(message, "Por favor, ingresá un número. ¿Grasas de la porción?")
        bot.register_next_step_handler(msg, paso_grasas_paquete)

# ----------------- BORRAR ALIMENTOS -----------------
@bot.message_handler(func=lambda message: message.text == "🗑️ Borrar Alimento")
def iniciar_borrar(message):
    user_id = str(message.from_user.id)
    if user_id in datos_usuarios and "mis_alimentos" in datos_usuarios[user_id] and datos_usuarios[user_id]["mis_alimentos"]:
        alimentos = list(datos_usuarios[user_id]["mis_alimentos"].keys())
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for al in alimentos:
            markup.add(al.title())
        markup.add("❌ Cancelar")
        msg = bot.reply_to(message, "¿Qué alimento o receta querés borrar de tu base personal?", reply_markup=markup)
        bot.register_next_step_handler(msg, paso_borrar)
    else:
        bot.reply_to(message, "No tenés ningún alimento guardado en tu base personal.", reply_markup=menu_principal())

def paso_borrar(message):
    user_id = str(message.from_user.id)
    alimento = message.text.lower()
    if alimento == "❌ cancelar":
        bot.reply_to(message, "Operación cancelada.", reply_markup=menu_principal())
        return
        
    if alimento in datos_usuarios[user_id].get("mis_alimentos", {}):
        del datos_usuarios[user_id]["mis_alimentos"][alimento]
        guardar_datos()
        bot.reply_to(message, f"🗑️ ¡Listo! '{alimento}' fue borrado de tu base personal.", reply_markup=menu_principal())
    else:
        bot.reply_to(message, "Ese alimento no estaba en tu base personal.", reply_markup=menu_principal())

# ----------------- SISTEMA DE RECETAS -----------------
@bot.message_handler(func=lambda message: message.text == "🍳 Crear Receta")
def iniciar_receta(message):
    user_id = str(message.from_user.id)
    if user_id not in registro_temporal:
        registro_temporal[user_id] = {}
        
    msg = bot.reply_to(message, "¡Vamos a armar una receta nueva!\n\n¿Cómo se llama la receta? (Ej: torta de banana, tarta de jamon)", reply_markup=boton_volver())
    bot.register_next_step_handler(msg, paso_nombre_receta)

def paso_nombre_receta(message):
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Cancelado.", reply_markup=menu_herramientas())
        return
        
    nombre = message.text.lower()
    user_id = str(message.from_user.id)
    registro_temporal[user_id]['receta_nombre'] = nombre
    registro_temporal[user_id]['receta_ingredientes'] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "peso_crudo": 0}
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ Listo (Terminar)", "🔙 Volver")
    
    msg = bot.reply_to(message, f"Perfecto. Vamos a agregar ingredientes a '{nombre}'.\n\nEscribime la cantidad y el alimento, igual que cuando comés (Ej: `500 harina 0000`, `200 banana`).\n\nCuando hayas puesto todos los ingredientes, tocá el botón '✅ Listo (Terminar)'.", reply_markup=markup, parse_mode="Markdown")
    bot.register_next_step_handler(msg, paso_ingrediente_receta)

def paso_ingrediente_receta(message):
    user_id = str(message.from_user.id)
    texto = message.text.lower()
    
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Receta cancelada.", reply_markup=menu_herramientas())
        return
        
    if texto == "✅ listo (terminar)":
        datos = registro_temporal[user_id]['receta_ingredientes']
        if datos['peso_crudo'] == 0:
            bot.reply_to(message, "No agregaste ningún ingrediente. Receta cancelada.", reply_markup=menu_principal())
            return
            
        msg = bot.reply_to(message, f"¡Ingredientes anotados!\n\nEn crudo, suman **{datos['peso_crudo']}g**.\n¿Cuánto pesa la receta entera **ya cocinada**? (Si no la cocinaste o no la pesaste, escribí `igual`).", reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
        bot.register_next_step_handler(msg, paso_peso_final_receta)
        return

    # Intentar parsear el ingrediente
    try:
        partes = texto.split()
        cantidad = float(partes[0])
        alimento = " ".join(partes[1:])
        
        # Chequear alias
        alimento = diccionario_alias.get(alimento, alimento)
        
        stats = None
        # Buscar global
        if alimento in tabla_nutricional:
            data = tabla_nutricional[alimento]
            if isinstance(data, dict):
                if "kcal" not in data:
                    registro_temporal[user_id]['cantidad_pendiente'] = cantidad
                    registro_temporal[user_id]['en_receta'] = True
                    
                    markup = InlineKeyboardMarkup()
                    for variante in data.keys():
                        markup.add(InlineKeyboardButton(variante.title(), callback_data=f"cat_{alimento}_{variante}"))
                        
                    bot.reply_to(message, f"¿Qué tipo de {alimento} es para tu receta?", reply_markup=markup)
                    return
                else:
                    stats = data
                    if "peso_unidad" in stats:
                        cantidad = float(partes[0]) * stats["peso_unidad"]
        
        if stats:
            kcal = (stats["kcal"] * cantidad) / 100
            prot = (stats["proteinas"] * cantidad) / 100
            carb = (stats["carbos"] * cantidad) / 100
            gras = (stats["grasas"] * cantidad) / 100
            
            registro_temporal[user_id]['receta_ingredientes']["kcal"] += kcal
            registro_temporal[user_id]['receta_ingredientes']["proteinas"] += prot
            registro_temporal[user_id]['receta_ingredientes']["carbos"] += carb
            registro_temporal[user_id]['receta_ingredientes']["grasas"] += gras
            registro_temporal[user_id]['receta_ingredientes']["peso_crudo"] += cantidad
            
            bot.reply_to(message, f"➕ Agregado: {cantidad}g de {alimento}. (Sumando macros...)\nSeguí agregando o tocá '✅ Listo (Terminar)'.")
        else:
            bot.reply_to(message, f"No encontré '{alimento}' en la base global. Probá con otro ingrediente.")
            
    except:
        bot.reply_to(message, "Formato incorrecto. Acordate de poner: [cantidad] [alimento] (Ej: 100 pollo).")
        
    # Volver a llamar a este mismo paso hasta que toque "Listo"
    bot.register_next_step_handler(message, paso_ingrediente_receta)

def paso_peso_final_receta(message):
    user_id = str(message.from_user.id)
    texto = message.text.lower()
    
    datos = registro_temporal[user_id]['receta_ingredientes']
    peso_crudo = datos['peso_crudo']
    
    if texto == "igual":
        peso_final = peso_crudo
    else:
        try:
            peso_final = float(texto.replace(',', '.'))
            if peso_final <= 0:
                raise ValueError
        except:
            msg = bot.reply_to(message, "Por favor, ingresá un número válido o la palabra 'igual'.")
            bot.register_next_step_handler(msg, paso_peso_final_receta)
            return
            
    # Matemática: llevar los totales a 100g basados en el peso FINAL
    factor = 100 / peso_final
    
    nombre = registro_temporal[user_id]['receta_nombre']
    
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000}
        
    if "mis_alimentos" not in datos_usuarios[user_id]:
        datos_usuarios[user_id]["mis_alimentos"] = {}
        
    datos_usuarios[user_id]["mis_alimentos"][nombre] = {
        "kcal": datos["kcal"] * factor,
        "proteinas": datos["proteinas"] * factor,
        "carbos": datos["carbos"] * factor,
        "grasas": datos["grasas"] * factor
    }
    guardar_datos()
    
    bot.reply_to(message, f"🍳 ¡Receta '{nombre}' guardada con éxito!\n\n"
                          f"Peso final: {peso_final}g.\n"
                          f"Valores cada 100g:\n"
                          f"🔥 Kcal: {datos['kcal'] * factor:.0f}\n"
                          f"🥩 Proteínas: {datos['proteinas'] * factor:.1f}g\n"
                          f"🍞 Carbos: {datos['carbos'] * factor:.1f}g\n"
                          f"🥑 Grasas: {datos['grasas'] * factor:.1f}g\n\n"
                          f"Ya podés usarla como cualquier alimento: `150 {nombre}`.", 
                          reply_markup=menu_principal())
                          
    del registro_temporal[user_id]['receta_nombre']
    del registro_temporal[user_id]['receta_ingredientes']


# ----------------- IA GENERATIVA -----------------
@bot.message_handler(func=lambda message: message.text == "🤖 Preguntarle a la IA")
def iniciar_ia(message):
    msg = bot.reply_to(message, "¡Soy tu asistente inteligente! 🧠\n\nContame, ¿qué querés comer, o qué ingredientes tenés a mano? (Ej: 'Me sobraron huevos y tomate, ¿qué me hago?')", reply_markup=boton_volver())
    bot.register_next_step_handler(msg, procesar_ia)

def procesar_ia(message):
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Volviendo a herramientas.", reply_markup=menu_herramientas())
        return
        
    user_id = str(message.from_user.id)
    
    # Recopilar contexto para la IA
    macros = ""
    if user_id in datos_usuarios:
        d = datos_usuarios[user_id]
        faltan_kcal = max(0, d.get("meta_kcal", 2000) - d.get("kcal", 0))
        faltan_prot = max(0, d.get("meta_proteinas", 160) - d.get("proteinas", 0))
        macros = f"Tener en cuenta: Al usuario le faltan comer hoy {faltan_kcal:.0f} kcal y {faltan_prot:.1f}g de proteínas para su meta."
        
    prompt = f"""Sos un nutricionista directo, preciso y conciso. {macros}
El usuario te pide: '{message.text}'. 

Reglas obligatorias:
- NO saludes ni te despidas.
- NO uses párrafos largos ni des explicaciones innecesarias.
- Usá listas, viñetas y emojis.
- Nada de recetas caras, por ejemplo: 2 huevos y 6 claras de huevo.
- No incluyas proteina en polvo a menos que te lo recomiende el usuario.
- Respetá esta estructura visual de ejemplo:

🥑 [Nombre de la receta]
📜 Ingredientes
- [Ingredientes con viñetas]
👨‍🍳 Preparación
1. [Pasos cortos numerados]
⚡ Cocción (Horno/Microondas)
📊 Macros aproximados (Kcal, Proteína, Carbos, Grasas)
🔥 Cómo hacerla MÁS proteica (Opcional)
💡 Tip importante
"""
    
    try:
        # Verificar que tenga API Key configurada
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "tu_api_key_de_gemini_aqui":
            bot.reply_to(message, "⚠️ La API Key de Gemini no está configurada. Agregá GEMINI_API_KEY en las variables de entorno.", reply_markup=menu_principal())
            return
            
        bot.send_chat_action(message.chat.id, 'typing')
        
        # Usar gemini-2.5-flash que es el modelo estable actual
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        if response.text:
            bot.reply_to(message, response.text, reply_markup=menu_principal())
        else:
            bot.reply_to(message, "La IA no generó respuesta. Probá de nuevo.", reply_markup=menu_principal())
            
    except Exception as e:
        print(f"Error IA: {e}")
        error_msg = str(e)
        if "API_KEY" in error_msg or "invalid" in error_msg.lower():
            bot.reply_to(message, "⚠️ Error de API Key. Verificá que la GEMINI_API_KEY sea válida.", reply_markup=menu_principal())
        else:
            bot.reply_to(message, f"Uy, la IA no respondió. Error: {error_msg[:80]}", reply_markup=menu_principal())


@bot.message_handler(func=lambda message: message.text == "📝 Agregar Macros (IA)")
def iniciar_estimacion_ia(message):
    msg = bot.reply_to(message, "¡Contame qué comiste! Describilo con todos los detalles posibles (ej: '300g de fideos con pesto y crema'). Yo estimo los macros y los cargo.", reply_markup=boton_volver())
    bot.register_next_step_handler(msg, procesar_estimacion_ia)

def procesar_estimacion_ia(message):
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Cancelado.", reply_markup=menu_principal())
        return
        
    user_id = str(message.from_user.id)
    
    prompt = f"""El usuario comió: '{message.text}'.
Sos un nutricionista y extractor de información. Estima los macros (Kcal, proteínas, carbohidratos, grasas) para este plato/comida.
Considerá porciones lógicas estándar si el usuario no especifica cantidades.

Devolvé EXCLUSIVAMENTE un objeto JSON válido, sin markdown, sin texto adicional, con la siguiente estructura:
{{
  "alimento": "Nombre corto del plato (ej: Fideos al pesto con crema)",
  "kcal": 0.0,
  "proteinas": 0.0,
  "carbos": 0.0,
  "grasas": 0.0,
  "explicacion": "Breve explicación de la porción estimada en 1 o 2 frases."
}}
"""
    
    try:
        # Verificar que tenga API Key configurada
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "tu_api_key_de_gemini_aqui":
            bot.reply_to(message, "⚠️ La API Key de Gemini no está configurada. Agregá GEMINI_API_KEY en las variables de entorno.", reply_markup=menu_principal())
            return
            
        bot.send_chat_action(message.chat.id, 'typing')
        
        # Usar gemini-2.5-flash
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio.replace("```json", "").replace("```", "").strip()
            
        datos = json.loads(texto_limpio)
        
        if user_id not in datos_usuarios:
            datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []}
            
        # Guardar en MongoDB para evitar desincronización entre workers
        datos_usuarios[user_id]["estimacion_pendiente"] = {
            "alimento": datos.get("alimento", "Estimación IA"),
            "kcal": float(datos.get("kcal", 0)),
            "proteinas": float(datos.get("proteinas", 0)),
            "carbos": float(datos.get("carbos", 0)),
            "grasas": float(datos.get("grasas", 0))
        }
        guardar_datos()
        
        respuesta = (f"🔍 **Estimación de la IA:**\n"
                     f"🍽️ **Plato:** {datos.get('alimento')}\n\n"
                     f"🔥 **Kcal:** {datos.get('kcal'):.0f}\n"
                     f"🥩 **Proteínas:** {datos.get('proteinas'):.1f}g\n"
                     f"🍞 **Carbos:** {datos.get('carbos'):.1f}g\n"
                     f"🥑 **Grasas:** {datos.get('grasas'):.1f}g\n\n"
                     f"💡 *{datos.get('explicacion')}*\n\n"
                     f"¿Querés registrar esta comida en tu día?")
                     
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Registrar", callback_data="confirmar_ia"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_ia")
        )
        
        bot.reply_to(message, respuesta, reply_markup=markup, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error Estimación IA: {e}")
        bot.reply_to(message, "Uy, no pude estimar la comida. Asegurate de escribir una comida válida y de que la API key funcione.", reply_markup=menu_principal())


# ----------------- AUDIOS DE VOZ -----------------
@bot.message_handler(content_types=['voice'])
def procesar_audio_voz(message):
    user_id = str(message.from_user.id)
    try:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "tu_api_key_de_gemini_aqui":
            bot.reply_to(message, "⚠️ La API Key de Gemini no está configurada. Agregá GEMINI_API_KEY en las variables de entorno.", reply_markup=menu_principal())
            return

        bot.send_chat_action(message.chat.id, 'typing')
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        prompt = """Escuchá atentamente este mensaje de voz donde el usuario indica lo que comió o quiere registrar.
Tu tarea es transcribir y extraer los alimentos y estimar sus macros (Kcal, proteínas, carbohidratos, grasas).
Devolvé EXCLUSIVAMENTE un objeto JSON válido, sin markdown, con esta estructura:
{
  "transcripcion": "Texto transcrito de lo que dijo el usuario",
  "alimento": "Nombre del plato o resumen de la comida",
  "kcal": 0.0,
  "proteinas": 0.0,
  "carbos": 0.0,
  "grasas": 0.0,
  "explicacion": "Explicación breve de las porciones o estimaciones"
}"""

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, {"mime_type": "audio/ogg", "data": downloaded_file}],
            config={'response_mime_type': 'application/json'}
        )
        
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio.replace("```json", "").replace("```", "").strip()
            
        datos = json.loads(texto_limpio)
        
        if user_id not in datos_usuarios:
            datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []}
            
        datos_usuarios[user_id]["estimacion_pendiente"] = {
            "alimento": datos.get("alimento", "Comida registrada por voz"),
            "kcal": float(datos.get("kcal", 0)),
            "proteinas": float(datos.get("proteinas", 0)),
            "carbos": float(datos.get("carbos", 0)),
            "grasas": float(datos.get("grasas", 0))
        }
        guardar_datos()
        
        respuesta = (f"🎤 **Nota de Voz Entendida:**\n"
                     f"💬 *\"{datos.get('transcripcion')}\"*\n\n"
                     f"🍽️ **Plato:** {datos.get('alimento')}\n"
                     f"🔥 **Kcal:** {datos.get('kcal', 0):.0f}\n"
                     f"🥩 **Proteínas:** {datos.get('proteinas', 0):.1f}g\n"
                     f"🍞 **Carbos:** {datos.get('carbos', 0):.1f}g\n"
                     f"🥑 **Grasas:** {datos.get('grasas', 0):.1f}g\n\n"
                     f"💡 *{datos.get('explicacion', '')}*\n\n"
                     f"¿Querés registrar esta comida en tu día?")
                     
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Registrar", callback_data="confirmar_ia"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_ia")
        )
        
        bot.reply_to(message, respuesta, reply_markup=markup, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error Audio Voz: {e}")
        bot.reply_to(message, "Uy, no pude procesar la nota de voz. Intentá hablar más claro o escribir el texto.", reply_markup=menu_principal())


# ----------------- SCANNER VISUAL INTELIGENTE (ETIQUETAS Y PLATOS) -----------------
@bot.message_handler(content_types=['photo'])
def escanear_foto(message):
    user_id = str(message.from_user.id)
    try:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "tu_api_key_de_gemini_aqui":
            bot.reply_to(message, "⚠️ La API Key de Gemini no está configurada.", reply_markup=menu_principal())
            return

        bot.send_chat_action(message.chat.id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        prompt = """Analizá esta imagen. La imagen puede ser:
1. Una ETIQUETA NUTRICIONAL (tabla o texto con calorías/nutrientes por porción).
2. Un PLATO DE COMIDA / ALIMENTO (foto de comida preparada, fruta, carne, etc.).
3. OTRO (no es ni etiqueta ni alimento).

Devolvé EXCLUSIVAMENTE un objeto JSON válido con esta estructura:
{
  "tipo": "etiqueta" | "plato" | "otro",
  "alimento": "Nombre del plato si tipo es 'plato'",
  "porcion_gramos": 0.0,
  "kcal": 0.0,
  "proteinas": 0.0,
  "carbos": 0.0,
  "grasas": 0.0,
  "explicacion": "Explicación breve de la estimación si es plato"
}"""

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, {"mime_type": "image/jpeg", "data": downloaded_file}],
            config={'response_mime_type': 'application/json'}
        )
        
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio.replace("```json", "").replace("```", "").strip()
            
        datos = json.loads(texto_limpio)
        tipo = datos.get("tipo", "otro")
        
        if tipo == "etiqueta":
            if user_id not in registro_temporal:
                registro_temporal[user_id] = {}
            registro_temporal[user_id]['etiqueta_pendiente'] = datos
            
            respuesta = (f"🔍 **¡Etiqueta Leída con Éxito!**\n\n"
                         f"Porción detectada: {datos.get('porcion_gramos', 0)}g\n"
                         f"🔥 Kcal: {datos.get('kcal', 0):.0f}\n"
                         f"🥩 Proteínas: {datos.get('proteinas', 0):.1f}g\n"
                         f"🍞 Carbos: {datos.get('carbos', 0):.1f}g\n"
                         f"🥑 Grasas: {datos.get('grasas', 0):.1f}g\n\n"
                         f"¿Cómo querés llamar a este producto para guardarlo en tu base personal? (Ej: galletitas oreo, pan lactal)")
            msg = bot.reply_to(message, respuesta, parse_mode="Markdown")
            bot.register_next_step_handler(msg, paso_nombre_etiqueta)

        elif tipo == "plato":
            if user_id not in datos_usuarios:
                datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []}
                
            datos_usuarios[user_id]["estimacion_pendiente"] = {
                "alimento": datos.get("alimento", "Plato reconocido por foto"),
                "kcal": float(datos.get("kcal", 0)),
                "proteinas": float(datos.get("proteinas", 0)),
                "carbos": float(datos.get("carbos", 0)),
                "grasas": float(datos.get("grasas", 0))
            }
            guardar_datos()
            
            respuesta = (f"📸 **Plato Reconocido por la IA:**\n"
                         f"🍽️ **Plato:** {datos.get('alimento')}\n\n"
                         f"🔥 **Kcal:** {datos.get('kcal', 0):.0f}\n"
                         f"🥩 **Proteínas:** {datos.get('proteinas', 0):.1f}g\n"
                         f"🍞 **Carbos:** {datos.get('carbos', 0):.1f}g\n"
                         f"🥑 **Grasas:** {datos.get('grasas', 0):.1f}g\n\n"
                         f"💡 *{datos.get('explicacion', '')}*\n\n"
                         f"¿Querés registrar esta comida en tu día?")
                         
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Registrar", callback_data="confirmar_ia"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_ia")
            )
            bot.reply_to(message, respuesta, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.reply_to(message, "Hmm, no detecté ni una etiqueta nutricional clara ni un plato de comida. Sacá una foto más cercana o iluminada.")

    except Exception as e:
        print(f"Error Scanner Visual: {e}")
        bot.reply_to(message, "Falló el análisis de la imagen. Verificá que la foto sea clara y la API Key esté funcionando.")


# ----------------- SISTEMA DE FAVORITOS ("LO DE SIEMPRE") -----------------
@bot.message_handler(func=lambda message: message.text in ["⭐️ Favoritos", "⭐ Favoritos"])
def submenu_favoritos(message):
    bot.reply_to(message, "⭐️ **Comidas Favoritas ('Lo de siempre'):**\n\nGuardá tus desayunos o platos habituales para registrarlos rápidamente.", reply_markup=menu_favoritos(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "⚡ Cargar Favorito")
def listar_favoritos_para_cargar(message):
    user_id = str(message.from_user.id)
    favoritos = datos_usuarios.get(user_id, {}).get("favoritos", {})
    
    if not favoritos:
        bot.reply_to(message, "No tenés ningún favorito guardado aún. Tocá '➕ Guardar Favorito' para agregar uno.", reply_markup=menu_favoritos())
        return
        
    markup = InlineKeyboardMarkup()
    for nombre in favoritos.keys():
        markup.add(InlineKeyboardButton(f"⚡ {nombre.title()}", callback_data=f"favload_{nombre}"))
        
    bot.reply_to(message, "Seleccioná cuál favorito querés registrar hoy:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("favload_"))
def cargar_favorito_callback(call):
    user_id = str(call.from_user.id)
    nombre_fav = call.data.split("_", 1)[1]
    
    favoritos = datos_usuarios.get(user_id, {}).get("favoritos", {})
    if nombre_fav not in favoritos:
        bot.answer_callback_query(call.id, "Ese favorito ya no existe.")
        return
        
    fav = favoritos[nombre_fav]
    kcal = fav.get("kcal", 0)
    prot = fav.get("proteinas", 0)
    carb = fav.get("carbos", 0)
    gras = fav.get("grasas", 0)
    
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []}
    if "historial_hoy" not in datos_usuarios[user_id]:
        datos_usuarios[user_id]["historial_hoy"] = []
        
    datos_usuarios[user_id]["kcal"] += kcal
    datos_usuarios[user_id]["proteinas"] += prot
    datos_usuarios[user_id]["carbos"] += carb
    datos_usuarios[user_id]["grasas"] += gras
    
    nuevo_id = str(uuid.uuid4())[:8]
    datos_usuarios[user_id]["historial_hoy"].append({
        "id": nuevo_id,
        "alimento": f"⭐️ {nombre_fav.title()}",
        "cantidad_str": "1 combo",
        "kcal": kcal, "proteinas": prot, "carbos": carb, "grasas": gras
    })
    guardar_datos()
    
    markup_undo = InlineKeyboardMarkup()
    markup_undo.add(InlineKeyboardButton("↩️ Deshacer esto", callback_data=f"undo_{nuevo_id}"))
    
    respuesta = (f"⚡ Registraste tu favorito **{nombre_fav.title()}**:\n"
                 f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                 f"🍞 Carbos: {carb:.1f}g\n🥑 Grasas: {gras:.1f}g")
                 
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta, reply_markup=markup_undo, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "➕ Guardar Favorito")
def iniciar_guardar_favorito(message):
    msg = bot.reply_to(message, "¡Vamos a guardar un combo favorito!\n\n¿Qué nombre querés ponerle? (Ej: Desayuno Habitual, Merienda Proteica)", reply_markup=boton_volver())
    bot.register_next_step_handler(msg, paso_nombre_favorito)

def paso_nombre_favorito(message):
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Cancelado.", reply_markup=menu_favoritos())
        return
        
    nombre = message.text.lower().strip()
    user_id = str(message.from_user.id)
    if user_id not in registro_temporal:
        registro_temporal[user_id] = {}
    registro_temporal[user_id]['fav_nombre'] = nombre
    
    msg = bot.reply_to(message, f"Perfecto. ¿Qué alimentos incluye **{nombre.title()}**?\nDescribilo o decime las cantidades (Ej: `2 u huevo, 50g avena` o `300g pechuga con arroz`). La IA calculará los macros y guardará el combo.", parse_mode="Markdown")
    bot.register_next_step_handler(msg, paso_contenido_favorito)

def paso_contenido_favorito(message):
    user_id = str(message.from_user.id)
    if message.text == "🔙 Volver":
        bot.reply_to(message, "Cancelado.", reply_markup=menu_favoritos())
        return
        
    nombre_fav = registro_temporal.get(user_id, {}).get('fav_nombre')
    if not nombre_fav:
        bot.reply_to(message, "Ocurrió un error. Volvé a iniciar la carga.", reply_markup=menu_favoritos())
        return

    prompt = f"""El usuario quiere definir un combo o alimento favorito llamado '{nombre_fav}' que contiene: '{message.text}'.
Sos un nutricionista. Estima el total acumulado de macros (Kcal, proteínas, carbohidratos, grasas) para todo el combo completo.
Devolvé EXCLUSIVAMENTE un objeto JSON válido, sin markdown:
{{
  "kcal": 0.0,
  "proteinas": 0.0,
  "carbos": 0.0,
  "grasas": 0.0,
  "explicacion": "Resumen corto de los alimentos sumados"
}}"""

    try:
        bot.send_chat_action(message.chat.id, 'typing')
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio.replace("```json", "").replace("```", "").strip()
            
        datos = json.loads(texto_limpio)
        
        if user_id not in datos_usuarios:
            datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000}
        if "favoritos" not in datos_usuarios[user_id]:
            datos_usuarios[user_id]["favoritos"] = {}
            
        datos_usuarios[user_id]["favoritos"][nombre_fav] = {
            "kcal": float(datos.get("kcal", 0)),
            "proteinas": float(datos.get("proteinas", 0)),
            "carbos": float(datos.get("carbos", 0)),
            "grasas": float(datos.get("grasas", 0))
        }
        guardar_datos()
        
        respuesta = (f"⭐️ **¡Favorito '{nombre_fav.title()}' guardado!**\n\n"
                     f"🔥 Kcal: {datos.get('kcal', 0):.0f}\n"
                     f"🥩 Proteínas: {datos.get('proteinas', 0):.1f}g\n"
                     f"🍞 Carbos: {datos.get('carbos', 0):.1f}g\n"
                     f"🥑 Grasas: {datos.get('grasas', 0):.1f}g\n\n"
                     f"💡 *{datos.get('explicacion', '')}*\n\n"
                     f"La próxima vez podés registrarlo al instante desde **⚡ Cargar Favorito**.")
                     
        bot.reply_to(message, respuesta, reply_markup=menu_favoritos(), parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error Guardar Favorito: {e}")
        bot.reply_to(message, "Uy, hubo un error al calcular los macros de tu favorito. Probá de nuevo escribiendo los alimentos claramente.", reply_markup=menu_favoritos())

@bot.message_handler(func=lambda message: message.text == "🗑️ Borrar Favorito")
def iniciar_borrar_favorito(message):
    user_id = str(message.from_user.id)
    favoritos = datos_usuarios.get(user_id, {}).get("favoritos", {})
    
    if not favoritos:
        bot.reply_to(message, "No tenés ningún favorito guardado.", reply_markup=menu_favoritos())
        return
        
    markup = InlineKeyboardMarkup()
    for nombre in favoritos.keys():
        markup.add(InlineKeyboardButton(f"❌ Borrar {nombre.title()}", callback_data=f"favdel_{nombre}"))
        
    bot.reply_to(message, "Elegí el favorito que querés borrar:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("favdel_"))
def borrar_favorito_callback(call):
    user_id = str(call.from_user.id)
    nombre_fav = call.data.split("_", 1)[1]
    
    if user_id in datos_usuarios and "favoritos" in datos_usuarios[user_id]:
        if nombre_fav in datos_usuarios[user_id]["favoritos"]:
            del datos_usuarios[user_id]["favoritos"][nombre_fav]
            guardar_datos()
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🗑️ Favorito '{nombre_fav.title()}' borrado con éxito.")
            return
            
    bot.answer_callback_query(call.id, "No se encontró el favorito.")


def paso_nombre_etiqueta(message):
    user_id = str(message.from_user.id)
    nombre = message.text.lower()
    
    if nombre == "🔙 menú principal":
        bot.reply_to(message, "Cancelado.", reply_markup=menu_principal())
        return
    
    # 6. Calcular a 100g y guardar
    datos = registro_temporal.get(user_id, {}).get('etiqueta_pendiente')
    if not datos:
        bot.reply_to(message, "Ocurrió un error. Volvé a mandar la foto.", reply_markup=menu_principal())
        return
        
    porcion = datos.get('porcion_gramos', 100)
    if porcion <= 0:
        porcion = 100 # Fallback por si la IA devuelve 0
        
    factor = 100 / porcion
    
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000}
        
    if "mis_alimentos" not in datos_usuarios[user_id]:
        datos_usuarios[user_id]["mis_alimentos"] = {}
        
    datos_usuarios[user_id]["mis_alimentos"][nombre] = {
        "kcal": datos.get("kcal", 0) * factor,
        "proteinas": datos.get("proteinas", 0) * factor,
        "carbos": datos.get("carbos", 0) * factor,
        "grasas": datos.get("grasas", 0) * factor
    }
    
    guardar_datos()
    del registro_temporal[user_id]['etiqueta_pendiente']
    
    bot.reply_to(message, f"✅ ¡Guardado! *{nombre.title()}* ahora está en tu base personal.\n\n"
                          f"Ya podés registrarlo diciendo: `50 {nombre}`.", parse_mode="Markdown", reply_markup=menu_principal())


# ----------------- CALCULADOR (ATRAPA-TODO) -----------------
@bot.message_handler(func=lambda message: True)
def calcular_macros(message):
    try:
        import re
        texto_limpio = message.text.lower().strip()
        match = re.match(r"^([\d\.,]+)\s*(u|g|gr|unidades|unidad)?\s+(.+)$", texto_limpio)
        if not match:
            partes = texto_limpio.split()
            if len(partes) < 2:
                raise ValueError
            cantidad_num = float(partes[0].replace(',', '.'))
            unidad_str = None
            alimento_raw = " ".join(partes[1:])
        else:
            cantidad_num = float(match.group(1).replace(',', '.'))
            unidad_str = match.group(2)
            alimento_raw = match.group(3).strip()
            
        user_id = str(message.from_user.id)
        alimento = diccionario_alias.get(alimento_raw, alimento_raw)
        
        stats = None
        es_categoria = False
        
        # 1. Buscar en la base personal primero
        if user_id in datos_usuarios and "mis_alimentos" in datos_usuarios[user_id]:
            if alimento in datos_usuarios[user_id]["mis_alimentos"]:
                stats = datos_usuarios[user_id]["mis_alimentos"][alimento]
                
        # 2. Buscar en MongoDB Global (db.alimentos)
        if stats is None:
            doc_mongo = buscar_alimento_mongo_global(alimento)
            if doc_mongo:
                stats = doc_mongo
                
        # 3. Buscar en la base local (alimentos.json)
        if stats is None and alimento in tabla_nutricional:
            data = tabla_nutricional[alimento]
            
            if isinstance(data, dict):
                if "kcal" not in data:
                    es_categoria = True
                    if user_id not in registro_temporal:
                        registro_temporal[user_id] = {}
                        
                    registro_temporal[user_id]['cantidad_pendiente_num'] = cantidad_num
                    registro_temporal[user_id]['cantidad_pendiente_unidad'] = unidad_str
                    
                    markup = InlineKeyboardMarkup()
                    for variante in data.keys():
                        markup.add(InlineKeyboardButton(variante.title(), callback_data=f"cat_{alimento}_{variante}"))
                        
                    bot.reply_to(message, f"¿Qué tipo de {alimento} es?", reply_markup=markup)
                    return
                else:
                    stats = data
            else:
                pass

        # 4. Consultar Open Food Facts API (Búsqueda global / Código de Barras)
        if stats is None:
            off_res = buscar_open_food_facts(alimento_raw)
            if off_res:
                stats = off_res
                # Guardar automáticamente en MongoDB Global para futuras consultas de todos los usuarios
                guardar_alimento_global(alimento, stats)

        # 5. Fuzzy Matching
        if stats is None:
            opciones = list(tabla_nutricional.keys())
            if user_id in datos_usuarios and "mis_alimentos" in datos_usuarios[user_id]:
                opciones += list(datos_usuarios[user_id]["mis_alimentos"].keys())
            
            opciones_reales = [op for op in opciones if not op.startswith("_sec_")]
            sugerencias = difflib.get_close_matches(alimento, opciones_reales, n=1, cutoff=0.7)
            
            if sugerencias:
                if user_id not in registro_temporal:
                    registro_temporal[user_id] = {}
                registro_temporal[user_id]['fuzzy_cantidad_num'] = cantidad_num
                registro_temporal[user_id]['fuzzy_unidad_str'] = unidad_str
                
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ Sí, agregar", callback_data=f"fuzzy_{sugerencias[0]}"),
                    InlineKeyboardButton("❌ No, cancelar", callback_data="fuzzy_cancel")
                )
                bot.reply_to(message, f"No encontré '{alimento}'. ¿Quisiste decir **{sugerencias[0].title()}**?", reply_markup=markup, parse_mode="Markdown")
            else:
                bot.reply_to(message, f"No encontré '{alimento}'. Tocá '⚙️ Herramientas' > '📦 Cargar Paquete' para agregarlo o probá enviar una foto/código de barras.", reply_markup=menu_principal())
            return

        # --- LÓGICA DE UNIDADES VS GRAMOS ---
        cantidad_gramos = cantidad_num
        cantidad_str = f"{cantidad_num:g}g"
        
        if "peso_unidad" in stats:
            if unidad_str in ["u", "unidades", "unidad"] or (unidad_str is None and cantidad_num <= 10):
                cantidad_gramos = cantidad_num * stats["peso_unidad"]
                cantidad_str = f"{cantidad_num:g} u"
                
        # Calcular macros y micronutrientes
        kcal = (stats.get("kcal", 0) * cantidad_gramos) / 100
        prot = (stats.get("proteinas", 0) * cantidad_gramos) / 100
        carb = (stats.get("carbos", 0) * cantidad_gramos) / 100
        gras = (stats.get("grasas", 0) * cantidad_gramos) / 100
        fibra = (stats.get("fibra", 0) * cantidad_gramos) / 100
        sodio = (stats.get("sodio", 0) * cantidad_gramos) / 100
        
        if user_id not in datos_usuarios:
            datos_usuarios[user_id] = {
                "kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "fibra": 0, "sodio": 0,
                "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []
            }
            
        if "historial_hoy" not in datos_usuarios[user_id]:
            datos_usuarios[user_id]["historial_hoy"] = []
            
        datos_usuarios[user_id]["kcal"] += kcal
        datos_usuarios[user_id]["proteinas"] += prot
        datos_usuarios[user_id]["carbos"] += carb
        datos_usuarios[user_id]["grasas"] += gras
        datos_usuarios[user_id]["fibra"] = datos_usuarios[user_id].get("fibra", 0) + fibra
        datos_usuarios[user_id]["sodio"] = datos_usuarios[user_id].get("sodio", 0) + sodio
        
        nuevo_id = str(uuid.uuid4())[:8]
        datos_usuarios[user_id]["historial_hoy"].append({
            "id": nuevo_id,
            "alimento": alimento,
            "cantidad_str": cantidad_str,
            "kcal": kcal, "proteinas": prot, "carbos": carb, "grasas": gras,
            "fibra": fibra, "sodio": sodio
        })
        guardar_datos()
        
        markup_undo = InlineKeyboardMarkup()
        markup_undo.add(InlineKeyboardButton("↩️ Deshacer esto", callback_data=f"undo_{nuevo_id}"))
        
        texto_fibra = f" (Fibra: {fibra:.1f}g 🌾)" if fibra > 0 else ""
        
        respuesta = (f"🍗 Agregaste {cantidad_str} de {alimento.title()}:\n"
                     f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                     f"🍞 Carbos: {carb:.1f}g{texto_fibra}\n🥑 Grasas: {gras:.1f}g")
                     
        bot.reply_to(message, respuesta, reply_markup=markup_undo)
    except Exception as e:
        print(f"Error en calcular_macros: {e}")
        bot.reply_to(message, "Formato incorrecto. Usá: [cantidad] [alimento], ej: 100 pollo", reply_markup=menu_principal())

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def manejar_variante(call):
    user_id = str(call.from_user.id)
    
    # call.data es "cat_leche_descremada" -> ["cat", "leche", "descremada"]
    partes = call.data.split("_", 2)
    categoria = partes[1]
    variante = partes[2]
    
    if user_id not in registro_temporal or 'cantidad_pendiente_num' not in registro_temporal[user_id]:
        bot.answer_callback_query(call.id, "Sesión expirada. Volvé a enviar la cantidad.")
        return
        
    cantidad_num = registro_temporal[user_id]['cantidad_pendiente_num']
    unidad_str = registro_temporal[user_id]['cantidad_pendiente_unidad']
    stats = tabla_nutricional[categoria][variante]
    
    cantidad_gramos = cantidad_num
    cantidad_str = f"{cantidad_num:g}g"
    
    if "peso_unidad" in stats:
        if unidad_str in ["u", "unidades", "unidad"] or (unidad_str is None and cantidad_num <= 10):
            cantidad_gramos = cantidad_num * stats["peso_unidad"]
            cantidad_str = f"{cantidad_num:g} u"
    
    kcal = (stats["kcal"] * cantidad_gramos) / 100
    prot = (stats["proteinas"] * cantidad_gramos) / 100
    carb = (stats["carbos"] * cantidad_gramos) / 100
    gras = (stats["grasas"] * cantidad_gramos) / 100
    
    alimento_completo = f"{categoria} {variante}"
    
    # Si estamos en medio de una receta
    if registro_temporal.get(user_id, {}).get('en_receta'):
        registro_temporal[user_id]['receta_ingredientes']["kcal"] += kcal
        registro_temporal[user_id]['receta_ingredientes']["proteinas"] += prot
        registro_temporal[user_id]['receta_ingredientes']["carbos"] += carb
        registro_temporal[user_id]['receta_ingredientes']["grasas"] += gras
        registro_temporal[user_id]['receta_ingredientes']["peso_crudo"] += cantidad_gramos
        
        respuesta = (f"➕ Agregado a la receta: {cantidad_str} de {alimento_completo.title()}.\n"
                     f"Seguí agregando o tocá '✅ Listo (Terminar)'.")
                     
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta)
        
        # Limpiar variables temporales y reactivar el bucle
        del registro_temporal[user_id]['cantidad_pendiente_num']
        del registro_temporal[user_id]['cantidad_pendiente_unidad']
        del registro_temporal[user_id]['en_receta']
        bot.register_next_step_handler(call.message, paso_ingrediente_receta)
        return

    # Si es una comida normal
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []}
    if "historial_hoy" not in datos_usuarios[user_id]:
        datos_usuarios[user_id]["historial_hoy"] = []
    
    datos_usuarios[user_id]["kcal"] += kcal
    datos_usuarios[user_id]["proteinas"] += prot
    datos_usuarios[user_id]["carbos"] += carb
    datos_usuarios[user_id]["grasas"] += gras
    
    nuevo_id = str(uuid.uuid4())[:8]
    datos_usuarios[user_id]["historial_hoy"].append({
        "id": nuevo_id,
        "alimento": alimento_completo,
        "cantidad_str": cantidad_str,
        "kcal": kcal, "proteinas": prot, "carbos": carb, "grasas": gras
    })
    guardar_datos()
    
    markup_undo = InlineKeyboardMarkup()
    markup_undo.add(InlineKeyboardButton("↩️ Deshacer esto", callback_data=f"undo_{nuevo_id}"))
    
    respuesta = (f"🍗 Agregaste {cantidad_str} de {alimento_completo.title()}:\n"
                 f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                 f"🍞 Carbos: {carb:.1f}g\n🥑 Grasas: {gras:.1f}g")
                 
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta, reply_markup=markup_undo)
    del registro_temporal[user_id]['cantidad_pendiente_num']
    del registro_temporal[user_id]['cantidad_pendiente_unidad']

# ----------------- DESHACER Y BORRAR HISTORIAL -----------------
@bot.callback_query_handler(func=lambda call: call.data in ["confirmar_ia", "cancelar_ia"])
def manejar_confirmacion_ia(call):
    user_id = str(call.from_user.id)
    if call.data == "cancelar_ia":
        if user_id in datos_usuarios and "estimacion_pendiente" in datos_usuarios[user_id]:
            del datos_usuarios[user_id]["estimacion_pendiente"]
            guardar_datos()
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Carga cancelada.")
        return
        
    if user_id not in datos_usuarios or "estimacion_pendiente" not in datos_usuarios[user_id]:
        bot.answer_callback_query(call.id, "No hay ninguna estimación pendiente o la sesión expiró.")
        return
        
    est = datos_usuarios[user_id]["estimacion_pendiente"]
    kcal = est.get("kcal", 0)
    prot = est.get("proteinas", 0)
    carb = est.get("carbos", 0)
    gras = est.get("grasas", 0)
    alimento = est.get("alimento", "Estimación IA")
    
    if "historial_hoy" not in datos_usuarios[user_id]:
        datos_usuarios[user_id]["historial_hoy"] = []
        
    datos_usuarios[user_id]["kcal"] += kcal
    datos_usuarios[user_id]["proteinas"] += prot
    datos_usuarios[user_id]["carbos"] += carb
    datos_usuarios[user_id]["grasas"] += gras
    
    nuevo_id = str(uuid.uuid4())[:8]
    datos_usuarios[user_id]["historial_hoy"].append({
        "id": nuevo_id,
        "alimento": alimento,
        "cantidad_str": "1 porción",
        "kcal": kcal, "proteinas": prot, "carbos": carb, "grasas": gras
    })
    
    del datos_usuarios[user_id]["estimacion_pendiente"]
    guardar_datos()
    
    markup_undo = InlineKeyboardMarkup()
    markup_undo.add(InlineKeyboardButton("↩️ Deshacer esto", callback_data=f"undo_{nuevo_id}"))
    
    respuesta = (f"🍗 Agregaste {alimento} (Estimado por IA):\n"
                 f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                 f"🍞 Carbos: {carb:.1f}g\n🥑 Grasas: {gras:.1f}g")
                 
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta, reply_markup=markup_undo)

@bot.callback_query_handler(func=lambda call: call.data.startswith("undo_") or call.data.startswith("delhist_"))
def manejar_borrado_historial(call):
    user_id = str(call.from_user.id)
    accion, item_id = call.data.split("_")
    
    if user_id in datos_usuarios and "historial_hoy" in datos_usuarios[user_id]:
        historial = datos_usuarios[user_id]["historial_hoy"]
        item_a_borrar = next((i for i in historial if i["id"] == item_id), None)
        
        if item_a_borrar:
            datos_usuarios[user_id]["kcal"] = max(0, datos_usuarios[user_id]["kcal"] - item_a_borrar["kcal"])
            datos_usuarios[user_id]["proteinas"] = max(0, datos_usuarios[user_id]["proteinas"] - item_a_borrar["proteinas"])
            datos_usuarios[user_id]["carbos"] = max(0, datos_usuarios[user_id]["carbos"] - item_a_borrar["carbos"])
            datos_usuarios[user_id]["grasas"] = max(0, datos_usuarios[user_id]["grasas"] - item_a_borrar["grasas"])
            
            historial.remove(item_a_borrar)
            guardar_datos()
            
            if accion == "undo":
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🗑️ Deshiciste la carga de {item_a_borrar['cantidad_str']} de {item_a_borrar['alimento'].title()}. Macros restados.")
            else:
                bot.answer_callback_query(call.id, f"Borrado: {item_a_borrar['alimento'].title()}")
                # Recargar la vista del historial
                ver_historial(call.message)
        else:
            bot.answer_callback_query(call.id, "Ese ítem ya no existe en tu historial de hoy.")
    else:
        bot.answer_callback_query(call.id, "No tenés historial para borrar.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("fuzzy_"))
def manejar_fuzzy(call):
    user_id = str(call.from_user.id)
    alimento = call.data.split("_", 1)[1]
    
    if alimento == "cancel":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Carga cancelada.")
        return
        
    if user_id not in registro_temporal or 'fuzzy_cantidad_num' not in registro_temporal[user_id]:
        bot.answer_callback_query(call.id, "Sesión expirada. Volvé a enviar el alimento.")
        return
        
    cantidad_num = registro_temporal[user_id]['fuzzy_cantidad_num']
    unidad_str = registro_temporal[user_id]['fuzzy_unidad_str']
    
    stats = None
    if user_id in datos_usuarios and "mis_alimentos" in datos_usuarios[user_id] and alimento in datos_usuarios[user_id]["mis_alimentos"]:
        stats = datos_usuarios[user_id]["mis_alimentos"][alimento]
    elif alimento in tabla_nutricional:
        data = tabla_nutricional[alimento]
        if isinstance(data, dict):
            if "kcal" not in data:
                # Es categoría, lanzamos los botones de variante
                registro_temporal[user_id]['cantidad_pendiente_num'] = cantidad_num
                registro_temporal[user_id]['cantidad_pendiente_unidad'] = unidad_str
                markup = InlineKeyboardMarkup()
                for variante in data.keys():
                    markup.add(InlineKeyboardButton(variante.title(), callback_data=f"cat_{alimento}_{variante}"))
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"¿Qué tipo de {alimento} es?", reply_markup=markup)
                return
            else:
                stats = data
                
    if stats is None:
        bot.answer_callback_query(call.id, "Error procesando.")
        return
        
    cantidad_gramos = cantidad_num
    cantidad_str = f"{cantidad_num:g}g"
    
    if "peso_unidad" in stats:
        if unidad_str in ["u", "unidades", "unidad"] or (unidad_str is None and cantidad_num <= 10):
            cantidad_gramos = cantidad_num * stats["peso_unidad"]
            cantidad_str = f"{cantidad_num:g} u"
            
    kcal = (stats["kcal"] * cantidad_gramos) / 100
    prot = (stats["proteinas"] * cantidad_gramos) / 100
    carb = (stats["carbos"] * cantidad_gramos) / 100
    gras = (stats["grasas"] * cantidad_gramos) / 100
    
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []}
    if "historial_hoy" not in datos_usuarios[user_id]:
        datos_usuarios[user_id]["historial_hoy"] = []
        
    datos_usuarios[user_id]["kcal"] += kcal
    datos_usuarios[user_id]["proteinas"] += prot
    datos_usuarios[user_id]["carbos"] += carb
    datos_usuarios[user_id]["grasas"] += gras
    
    nuevo_id = str(uuid.uuid4())[:8]
    datos_usuarios[user_id]["historial_hoy"].append({
        "id": nuevo_id,
        "alimento": alimento,
        "cantidad_str": cantidad_str,
        "kcal": kcal, "proteinas": prot, "carbos": carb, "grasas": gras
    })
    guardar_datos()
    
    markup_undo = InlineKeyboardMarkup()
    markup_undo.add(InlineKeyboardButton("↩️ Deshacer esto", callback_data=f"undo_{nuevo_id}"))
    
    respuesta = (f"🍗 Agregaste {cantidad_str} de {alimento.title()}:\n"
                 f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                 f"🍞 Carbos: {carb:.1f}g\n🥑 Grasas: {gras:.1f}g")
                 
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta, reply_markup=markup_undo)
    del registro_temporal[user_id]['fuzzy_cantidad_num']
    if 'fuzzy_unidad_str' in registro_temporal[user_id]:
        del registro_temporal[user_id]['fuzzy_unidad_str']

import time
import base64
from flask import Flask, request, jsonify, render_template

# Configuración del servidor Web para Render/Production/PWA
app = Flask(__name__, template_folder='templates', static_folder='static')

# Ruta base PWA (Servir App Móvil)
@app.route('/')
@app.route('/app')
def index():
    return render_template('index.html')

# Ruta de health check para Render
@app.route('/health')
def health():
    return jsonify({"status": "ok", "mongo": mongo_available}), 200

# Endpoint API: Obtener lista de usuarios para el selector
@app.route('/api/users')
def api_get_users():
    users = []
    if col_usuarios is not None:
        try:
            for doc in col_usuarios.find({}, {"_id": 1, "nombre": 1}):
                users.append({"id": doc["_id"], "name": doc.get("nombre") or f"Usuario {doc['_id']}"})
        except Exception as e:
            print(f"[WARN] Error api_get_users: {e}")
    if not users:
        for uid in datos_usuarios.keys():
            users.append({"id": str(uid), "name": f"Usuario {uid}"})
    if not users:
        users = [{"id": "defecto", "name": "Usuario Principal"}]
    return jsonify(users)

# Endpoint API: Obtener datos completos de un usuario
@app.route('/api/user/<user_id>')
def api_get_user(user_id):
    u_data = datos_usuarios[user_id]
    return jsonify({
        "user_id": str(user_id),
        "kcal": u_data.get("kcal", 0),
        "proteinas": u_data.get("proteinas", 0),
        "carbos": u_data.get("carbos", 0),
        "grasas": u_data.get("grasas", 0),
        "meta_kcal": u_data.get("meta_kcal", 2000),
        "meta_proteinas": u_data.get("meta_proteinas", 160),
        "historial_hoy": u_data.get("historial_hoy", []),
        "mis_alimentos": u_data.get("mis_alimentos", {})
    })

# Endpoint API: Registrar alimento
@app.route('/api/user/<user_id>/log', methods=['POST'])
def api_log_food(user_id):
    req_data = request.get_json() or {}
    alimento = str(req_data.get("alimento", "Comida")).lower().strip()
    cantidad = float(req_data.get("cantidad", 100))
    unidad = str(req_data.get("unidad", "g"))
    stats = req_data.get("stats") or {}
    
    if not stats or "kcal" not in stats:
        found = buscar_alimento_mongo_global(alimento)
        if found:
            stats = found
        elif alimento in tabla_nutricional:
            stats = tabla_nutricional[alimento]
            
    kcal_100 = float(stats.get("kcal", 0))
    prot_100 = float(stats.get("proteinas", 0))
    carb_100 = float(stats.get("carbos", 0))
    gras_100 = float(stats.get("grasas", 0))
    
    cantidad_gramos = cantidad
    cantidad_str = f"{cantidad:g}g"
    if unidad in ["u", "unidades", "unidad"] and "peso_unidad" in stats:
        cantidad_gramos = cantidad * float(stats["peso_unidad"])
        cantidad_str = f"{cantidad:g} u"
        
    kcal = (kcal_100 * cantidad_gramos) / 100
    prot = (prot_100 * cantidad_gramos) / 100
    carb = (carb_100 * cantidad_gramos) / 100
    gras = (gras_100 * cantidad_gramos) / 100
    
    u_data = datos_usuarios[user_id]
    u_data["kcal"] = u_data.get("kcal", 0) + kcal
    u_data["proteinas"] = u_data.get("proteinas", 0) + prot
    u_data["carbos"] = u_data.get("carbos", 0) + carb
    u_data["grasas"] = u_data.get("grasas", 0) + gras
    
    if "historial_hoy" not in u_data:
        u_data["historial_hoy"] = []
        
    item_id = str(uuid.uuid4())[:8]
    item = {
        "id": item_id,
        "alimento": alimento,
        "cantidad_str": cantidad_str,
        "kcal": kcal, "proteinas": prot, "carbos": carb, "grasas": gras
    }
    u_data["historial_hoy"].append(item)
    guardar_datos()
    
    return jsonify({"status": "ok", "item": item})

# Endpoint API: Borrar alimento del historial
@app.route('/api/user/<user_id>/history/<item_id>', methods=['DELETE'])
def api_delete_history(user_id, item_id):
    u_data = datos_usuarios[user_id]
    historial = u_data.get("historial_hoy", [])
    item_to_remove = None
    for item in historial:
        if item.get("id") == item_id:
            item_to_remove = item
            break
            
    if item_to_remove:
        historial.remove(item_to_remove)
        u_data["kcal"] = max(0, u_data.get("kcal", 0) - item_to_remove.get("kcal", 0))
        u_data["proteinas"] = max(0, u_data.get("proteinas", 0) - item_to_remove.get("proteinas", 0))
        u_data["carbos"] = max(0, u_data.get("carbos", 0) - item_to_remove.get("carbos", 0))
        u_data["grasas"] = max(0, u_data.get("grasas", 0) - item_to_remove.get("grasas", 0))
        guardar_datos()
        return jsonify({"status": "ok"})
        
    return jsonify({"status": "error", "message": "Registro no encontrado"}), 404

# Endpoint API: Actualizar configuración de perfil TDEE / Metas
@app.route('/api/user/<user_id>/profile', methods=['POST'])
def api_update_profile(user_id):
    req_data = request.get_json() or {}
    u_data = datos_usuarios[user_id]
    if "meta_kcal" in req_data:
        u_data["meta_kcal"] = float(req_data["meta_kcal"])
    if "meta_proteinas" in req_data:
        u_data["meta_proteinas"] = float(req_data["meta_proteinas"])
    guardar_datos()
    return jsonify({"status": "ok"})

# Endpoint API: Búsqueda unificada de alimentos
@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])
        
    results = []
    seen = set()
    
    # 1. Alimentos en tabla local
    if isinstance(tabla_nutricional, dict):
        for k, v in tabla_nutricional.items():
            if q in k.lower() and isinstance(v, dict) and "kcal" in v:
                results.append({
                    "alimento": k,
                    "kcal": v.get("kcal", 0),
                    "proteinas": v.get("proteinas", 0),
                    "carbos": v.get("carbos", 0),
                    "grasas": v.get("grasas", 0),
                    "fuente": "local"
                })
                seen.add(k.lower())
                if len(results) >= 8:
                    break
                    
    # 2. MongoDB Global
    if col_alimentos is not None and len(results) < 10:
        try:
            for doc in col_alimentos.find({"_id": {"$regex": q, "$options": "i"}}).limit(5):
                if doc["_id"].lower() not in seen:
                    results.append({
                        "alimento": doc["_id"],
                        "kcal": doc.get("kcal", 0),
                        "proteinas": doc.get("proteinas", 0),
                        "carbos": doc.get("carbos", 0),
                        "grasas": doc.get("grasas", 0),
                        "fuente": "mongo"
                    })
                    seen.add(doc["_id"].lower())
        except Exception as e:
            print(f"[WARN] Error search mongo: {e}")
            
    # 3. Open Food Facts
    if len(results) < 3:
        off_item = buscar_open_food_facts(q)
        if off_item and off_item["alimento"] not in seen:
            results.append(off_item)
            
    return jsonify(results)

# Endpoint API: Interpretar comida por texto libre con Gemini IA
@app.route('/api/ai/parse-food', methods=['POST'])
def api_parse_food():
    req_data = request.get_json() or {}
    text = req_data.get("text", "").strip()
    if not text:
        return jsonify({"status": "error", "message": "Texto vacío"}), 400
        
    try:
        prompt = (
            f"Analizá la siguiente descripción de comida: '{text}'.\n"
            "Devuelve ÚNICAMENTE un objeto JSON válido con este formato exacto:\n"
            "{\n"
            '  "alimento": "descripción corta del plato",\n'
            '  "kcal": 000,\n'
            '  "proteinas": 00.0,\n'
            '  "carbos": 00.0,\n'
            '  "grasas": 00.0\n'
            "}\n"
            "No incluyas formato Markdown ni texto extra. Solo el JSON."
        )
        res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        raw_text = res.text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw_text)
        return jsonify({"status": "ok", "parsed": parsed})
    except Exception as e:
        print(f"[ERROR] API Gemini Parse: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint API: Escanear etiqueta con Gemini Vision
@app.route('/api/ai/scan-label', methods=['POST'])
def api_scan_label():
    req_data = request.get_json() or {}
    img_b64 = req_data.get("image_base64", "")
    if not img_b64:
        return jsonify({"status": "error", "message": "Imagen no enviada"}), 400
        
    try:
        img_bytes = base64.b64decode(img_b64)
        prompt = (
            "Analizá la etiqueta nutricional en la imagen. "
            "Extraé los valores POR 100g/100ml.\n"
            "Devuelve ÚNICAMENTE un JSON válido con este formato exacto:\n"
            "{\n"
            '  "alimento": "nombre del producto o marca",\n'
            '  "kcal": 000,\n'
            '  "proteinas": 00.0,\n'
            '  "carbos": 00.0,\n'
            '  "grasas": 00.0\n'
            "}\n"
            "Solo responde con el objeto JSON."
        )
        
        from google.genai import types
        res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt
            ]
        )
        raw_text = res.text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw_text)
        return jsonify({"status": "ok", "parsed": parsed})
    except Exception as e:
        print(f"[ERROR] API Gemini Label Scan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Ruta oculta donde Telegram manda los mensajes
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return 'OK', 200

# ----------------- INICIO EN PRODUCCIÓN -----------------
if __name__ == "__main__":
    # Configurar webhook automáticamente en producción (Render)
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        print(f"[WEBHOOK] Configurando hacia: {render_url}")
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{render_url}/{TOKEN}")
        print(f"[OK] Webhook configurado correctamente")
    else:
        print("[INFO] Entorno de desarrollo local - webhook no configurado")
    
    # Arrancar Flask
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)