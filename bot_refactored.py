import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import sys
from dotenv import load_dotenv

import difflib
from google import genai
import uuid # Para generar IDs unicos para historial

# Obtener la ruta absoluta donde está bot.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cargar el .env exactamente desde esa ruta
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Configurar Gemini (nuevo SDK)
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

from pymongo import MongoClient
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

MONGO_URI = os.getenv("MONGO_URI")
if MONGO_URI:
    try:
        # Parsear y escapar el password si tiene caracteres especiales
        if "://" in MONGO_URI:
            # Extraer usuario:password@host
            from urllib.parse import urlparse
            parsed = urlparse(MONGO_URI)
            if parsed.password:
                # Reconstruir con password escapado
                user = parsed.username
                password = quote_plus(parsed.password)
                host = parsed.netloc.split('@')[1] if '@' in parsed.netloc else parsed.netloc
                db_name = parsed.path.replace('/', '') if parsed.path else 'macrobot_db'
                
                new_uri = f"{parsed.scheme}://{user}:{password}@{host}/{db_name}{'?' + parsed.query if parsed.query else ''}"
                MONGO_URI = new_uri
                print(f"🔧 URI de MongoDB re-construida con password escapado")
        
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client.get_database("macrobot_db")
        col_usuarios = db.usuarios
        col_alimentos = db.alimentos
        print("✅ MongoDB conectado exitosamente")
    except Exception as e:
        print(f"❌ Error conectando a MongoDB: {e}")
        col_usuarios = None
        col_alimentos = None
else:
    print("ADVERTENCIA: MONGO_URI no encontrado.")
    col_usuarios = None
    col_alimentos = None

def get_user(user_id):
    user_id = str(user_id)
    if col_usuarios:
        user = col_usuarios.find_one({"_id": user_id})
        if user:
            return user
    return {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": [], "mis_alimentos": {}}

def save_user(user_id, data):
    user_id = str(user_id)
    if col_usuarios:
        data["_id"] = user_id
        col_usuarios.update_one({"_id": user_id}, {"$set": data}, upsert=True)

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
    datos_usuarios.clear() # Clear cache so next request fetches fresh data


TOKEN = os.getenv('TELEGRAM_TOKEN', 'TU_TOKEN_ACA')
bot = telebot.TeleBot(TOKEN, threaded=False)

# ----------------- TECLADOS Y MENÚS -----------------
def menu_principal():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🍎 Registrar Comida", "📊 Mi Día")
    markup.add("⚙️ Herramientas")
    return markup

def menu_mi_dia():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 Resumen de Macros", "📝 Ver lo que comí hoy")
    markup.add("🧹 Terminar Día", "🔙 Menú Principal")
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
    bot.reply_to(message, "Para registrar comida simplemente escribime:\n`[cantidad] [alimento]`\n\n*Ejemplos:*\n`150 pollo` (150 gramos)\n`2 u huevo` (2 unidades)", reply_markup=menu_principal(), parse_mode="Markdown")

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
        datos_usuarios[user_id]["historial_hoy"] = []
        guardar_datos()
        bot.reply_to(message, "🧹 ¡Día reiniciado! Todos tus macros volvieron a cero. ¡Mañana será otro día!", reply_markup=menu_principal())
    else:
        bot.reply_to(message, "Todavía no cargaste nada.", reply_markup=menu_principal())

# ----------------- RESUMEN Y ESTADO -----------------
@bot.message_handler(commands=['resumen'])
@bot.message_handler(func=lambda message: message.text == "📊 Resumen de Macros")
def mostrar_resumen(message):
    user_id = str(message.from_user.id)
    if user_id in datos_usuarios:
        datos = datos_usuarios[user_id]
        
        meta_protes = datos.get("meta_proteinas", 160)
        meta_kcal = datos.get("meta_kcal", 2000)
        
        faltan_protes = meta_protes - datos["proteinas"]
        faltan_kcal = meta_kcal - datos["kcal"]
        
        texto_protes = f"¡Pasaste la meta por {abs(faltan_protes):.1f}g!" if faltan_protes < 0 else f"Faltan {faltan_protes:.1f}g"
        texto_kcal = f"¡Te pasaste por {abs(faltan_kcal):.0f} kcal!" if faltan_kcal < 0 else f"Faltan {faltan_kcal:.0f} kcal"
        
        bot.reply_to(message, f"📊 Resumen del día:\n\n"
                              f"🔥 Kcal: {datos['kcal']:.0f} / {meta_kcal:.0f} ({texto_kcal})\n"
                              f"🥩 Proteínas: {datos['proteinas']:.1f}g / {meta_protes:.1f}g ({texto_protes})\n"
                              f"🍞 Carbos: {datos['carbos']:.1f}g\n"
                              f"🥑 Grasas: {datos['grasas']:.1f}g", reply_markup=menu_mi_dia())
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
        
        # Usar gemini-1.5-flash que es más estable y disponible
        response = gemini_client.models.generate_content(
            model='gemini-1.5-flash',
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


# ----------------- SCANNER VISUAL (ETIQUETAS) -----------------
@bot.message_handler(content_types=['photo'])
def leer_etiqueta(message):
    user_id = str(message.from_user.id)
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        # 1. Bajar la imagen
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # 2. Armar el prompt para JSON
        prompt = """Sos un extractor de información nutricional. El usuario te pasa la foto de una etiqueta nutricional.
Tu única tarea es extraer la información y devolverla EXCLUSIVAMENTE como un objeto JSON válido, sin markdown, sin texto adicional.
El JSON debe tener exactamente esta estructura:
{
  "es_etiqueta": true,
  "porcion_gramos": 0.0,
  "kcal": 0.0,
  "proteinas": 0.0,
  "carbos": 0.0,
  "grasas": 0.0
}
Si la imagen no parece ser una etiqueta nutricional, poné "es_etiqueta": false y el resto en 0."""

        # 3. Llamar a Gemini (SDK v2)
        response = gemini_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[prompt, {"mime_type": "image/jpeg", "data": downloaded_file}],
            config={'response_mime_type': 'application/json'}
        )
        
        # 4. Parsear respuesta
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio.replace("```json", "").replace("```", "").strip()
            
        datos = json.loads(texto_limpio)
        
        if not datos.get("es_etiqueta"):
            bot.reply_to(message, "Hmm, no parece una etiqueta nutricional clara. Intentá sacar una foto más de cerca a la tablita.")
            return
            
        # 5. Guardar en memoria y pedir nombre
        if user_id not in registro_temporal:
            registro_temporal[user_id] = {}
            
        registro_temporal[user_id]['etiqueta_pendiente'] = datos
        
        respuesta = (f"🔍 **¡Etiqueta Leída con Éxito!**\n\n"
                     f"Porción detectada: {datos.get('porcion_gramos', 0)}g\n"
                     f"🔥 Kcal: {datos.get('kcal', 0)}\n"
                     f"🥩 Proteínas: {datos.get('proteinas', 0)}g\n"
                     f"🍞 Carbos: {datos.get('carbos', 0)}g\n"
                     f"🥑 Grasas: {datos.get('grasas', 0)}g\n\n"
                     f"¿Cómo querés llamar a este producto para guardarlo? (Ej: galletitas oreo, pan lactal)")
                     
        msg = bot.reply_to(message, respuesta, parse_mode="Markdown")
        bot.register_next_step_handler(msg, paso_nombre_etiqueta)
        
    except Exception as e:
        print(f"Error OCR Etiqueta: {e}")
        bot.reply_to(message, "Falló la lectura de la imagen. Asegurate de que la foto se vea clara y la API Key esté funcionando.")

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
                
        # 2. Si no lo encuentra, buscar en la global (json)
        if stats is None and alimento in tabla_nutricional:
            data = tabla_nutricional[alimento]
            
            # Chequear si es un diccionario válido (para ignorar los textos separadores _sec_)
            if isinstance(data, dict):
                # Detectar si es categoría (es dict pero no tiene 'kcal')
                if "kcal" not in data:
                    es_categoria = True
                    
                    # Lanzar botones inline
                    if user_id not in registro_temporal:
                        registro_temporal[user_id] = {}
                        
                    registro_temporal[user_id]['cantidad_pendiente_num'] = cantidad_num
                    registro_temporal[user_id]['cantidad_pendiente_unidad'] = unidad_str
                    
                    markup = InlineKeyboardMarkup()
                    for variante in data.keys():
                        # Usamos cat_categoria_variante para identificar en el callback
                        markup.add(InlineKeyboardButton(variante.title(), callback_data=f"cat_{alimento}_{variante}"))
                        
                    bot.reply_to(message, f"¿Qué tipo de {alimento} es?", reply_markup=markup)
                    return
                else:
                    stats = data
            else:
                pass # Es un separador como _sec_parrilla, se ignora y caerá en el 'else' final

        # 3. Fuzzy Matching
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
                bot.reply_to(message, f"No encontré '{alimento}'. Tocá '⚙️ Herramientas' > '📦 Cargar Paquete' para agregarlo.", reply_markup=menu_principal())
            return

        # --- LOGICA DE UNIDADES VS GRAMOS ---
        cantidad_gramos = cantidad_num
        cantidad_str = f"{cantidad_num:g}g"
        
        if "peso_unidad" in stats:
            if unidad_str in ["u", "unidades", "unidad"] or (unidad_str is None and cantidad_num <= 10):
                cantidad_gramos = cantidad_num * stats["peso_unidad"]
                cantidad_str = f"{cantidad_num:g} u"
                
        # Calcular macros
        kcal = (stats["kcal"] * cantidad_gramos) / 100
        prot = (stats["proteinas"] * cantidad_gramos) / 100
        carb = (stats["carbos"] * cantidad_gramos) / 100
        gras = (stats["grasas"] * cantidad_gramos) / 100
        
        if user_id not in datos_usuarios:
            datos_usuarios[user_id] = {
                "kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, 
                "meta_proteinas": 160, "meta_kcal": 2000, "historial_hoy": []
            }
            
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
                     
        bot.reply_to(message, respuesta, reply_markup=markup_undo)
    except:
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
from flask import Flask, request

# Configuración del servidor Web para Render/Production
app = Flask(__name__)

# Ruta base para chequear que la app está viva
@app.route('/')
def index():
    return "MacroBot funcionando 24/7 con MongoDB", 200

# Ruta de health check para Render
@app.route('/health')
def health():
    return {"status": "ok"}, 200

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
        print(f"🔗 Configurando webhook hacia: {render_url}")
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{render_url}/{TOKEN}")
        print(f"✅ Webhook configurado correctamente")
    else:
        print("ℹ️ Entorno de desarrollo local - webhook no configurado")
    
    # Arrancar Flask
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)