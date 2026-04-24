import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
from dotenv import load_dotenv

load_dotenv() # Carga las variables del archivo .env

archivo_datos = "usuarios.json"
if os.path.exists(archivo_datos):
    with open(archivo_datos, 'r') as f:
        datos_usuarios = json.load(f)
else:
    datos_usuarios = {}

def guardar_datos():
    with open(archivo_datos, 'w') as f:
        json.dump(datos_usuarios, f, indent=4)

TOKEN = os.getenv('TELEGRAM_TOKEN', 'TU_TOKEN_ACA')
bot = telebot.TeleBot(TOKEN)

# ----------------- TECLADO PRINCIPAL -----------------
def menu_principal():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Mi Perfil", "📊 Resumen")
    markup.add("📦 Cargar Paquete", "🧹 Terminar Día")
    markup.add("🍳 Crear Receta", "🗑️ Borrar Alimento")
    return markup

@bot.message_handler(commands=['start'])
def bienvenida(message):
    bot.reply_to(message, "¡Hola! Soy tu asistente nutricional. ¿Qué querés hacer hoy?", reply_markup=menu_principal())

# ----------------- BASE DE DATOS -----------------
archivo_alimentos = "alimentos.json"
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
        guardar_datos()
        bot.reply_to(message, "🧹 ¡Día reiniciado! Todos tus macros volvieron a cero. ¡Mañana será otro día!", reply_markup=menu_principal())
    else:
        bot.reply_to(message, "Todavía no cargaste nada.", reply_markup=menu_principal())

# ----------------- RESUMEN -----------------
@bot.message_handler(commands=['resumen'])
@bot.message_handler(func=lambda message: message.text == "📊 Resumen")
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
                              f"🥑 Grasas: {datos['grasas']:.1f}g", reply_markup=menu_principal())
    else:
        bot.reply_to(message, "Che, todavía no cargaste nada de comida hoy.", reply_markup=menu_principal())

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
        
    msg = bot.reply_to(message, "¡Vamos a guardar un alimento nuevo!\n\n¿Cómo se llama el producto? (Ej: galletitas oreo, barrita cereal)", reply_markup=ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, paso_nombre_paquete)

def paso_nombre_paquete(message):
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
        
    msg = bot.reply_to(message, "¡Vamos a armar una receta nueva!\n\n¿Cómo se llama la receta? (Ej: torta de banana, tarta de jamon)", reply_markup=ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, paso_nombre_receta)

def paso_nombre_receta(message):
    nombre = message.text.lower()
    user_id = str(message.from_user.id)
    registro_temporal[user_id]['receta_nombre'] = nombre
    registro_temporal[user_id]['receta_ingredientes'] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "peso_crudo": 0}
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ Listo (Terminar)")
    
    msg = bot.reply_to(message, f"Perfecto. Vamos a agregar ingredientes a '{nombre}'.\n\nEscribime la cantidad y el alimento, igual que cuando comés (Ej: `500 harina 0000`, `200 banana`).\n\nCuando hayas puesto todos los ingredientes, tocá el botón '✅ Listo (Terminar)'.", reply_markup=markup, parse_mode="Markdown")
    bot.register_next_step_handler(msg, paso_ingrediente_receta)

def paso_ingrediente_receta(message):
    user_id = str(message.from_user.id)
    texto = message.text.lower()
    
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


# ----------------- CALCULADOR (ATRAPA-TODO) -----------------
@bot.message_handler(func=lambda message: True)
def calcular_macros(message):
    try:
        partes = message.text.lower().split()
        cantidad = float(partes[0])
        alimento = " ".join(partes[1:])
        user_id = str(message.from_user.id)
        
        # 0. Chequear alias
        alimento = diccionario_alias.get(alimento, alimento)
        
        stats = None
        es_categoria = False
        
        # 1. Buscar en base personal primero
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
                    registro_temporal[user_id]['cantidad_pendiente'] = cantidad
                    
                    markup = InlineKeyboardMarkup()
                    for variante in data.keys():
                        # Usamos cat_categoria_variante para identificar en el callback
                        markup.add(InlineKeyboardButton(variante.title(), callback_data=f"cat_{alimento}_{variante}"))
                        
                    bot.reply_to(message, f"¿Qué tipo de {alimento} es?", reply_markup=markup)
                    return
                else:
                    stats = data
                    # Mutar cantidad si el alimento tiene 'peso_unidad'
                    if "peso_unidad" in stats:
                        cantidad = float(partes[0]) * stats["peso_unidad"]
            else:
                pass # Es un separador como _sec_parrilla, se ignora y caerá en el 'else' final

        if stats:
            kcal = (stats["kcal"] * cantidad) / 100
            prot = (stats["proteinas"] * cantidad) / 100
            carb = (stats["carbos"] * cantidad) / 100
            gras = (stats["grasas"] * cantidad) / 100
            
            if user_id not in datos_usuarios:
                datos_usuarios[user_id] = {
                    "kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, 
                    "meta_proteinas": 160, "meta_kcal": 2000
                }
            
            datos_usuarios[user_id]["kcal"] += kcal
            datos_usuarios[user_id]["proteinas"] += prot
            datos_usuarios[user_id]["carbos"] += carb
            datos_usuarios[user_id]["grasas"] += gras
            guardar_datos()
            
            respuesta = (f"🍗 Agregaste {cantidad}g de {alimento}:\n"
                         f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                         f"🍞 Carbos: {carb:.1f}g\n🥑 Grasas: {gras:.1f}g\n\n"
                         f"✅ ¡Guardado! Tocá '📊 Resumen' para ver tu total.")
            bot.reply_to(message, respuesta, reply_markup=menu_principal())
        else:
            bot.reply_to(message, "No tengo ese alimento registrado aún. Podés tocar '📦 Cargar Paquete' para agregarlo a tu base personal.", reply_markup=menu_principal())
    except:
        bot.reply_to(message, "Formato incorrecto. Usá: [cantidad] [alimento], ej: 100 pollo", reply_markup=menu_principal())

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def manejar_variante(call):
    user_id = str(call.from_user.id)
    
    # call.data es "cat_leche_descremada" -> ["cat", "leche", "descremada"]
    partes = call.data.split("_", 2)
    categoria = partes[1]
    variante = partes[2]
    
    if user_id not in registro_temporal or 'cantidad_pendiente' not in registro_temporal[user_id]:
        bot.answer_callback_query(call.id, "Sesión expirada. Volvé a enviar la cantidad.")
        return
        
    cantidad = registro_temporal[user_id]['cantidad_pendiente']
    stats = tabla_nutricional[categoria][variante]
    
    # Mutar cantidad si la variante tiene 'peso_unidad' (poco común, pero por las dudas)
    if "peso_unidad" in stats:
        cantidad = cantidad * stats["peso_unidad"]
    
    kcal = (stats["kcal"] * cantidad) / 100
    prot = (stats["proteinas"] * cantidad) / 100
    carb = (stats["carbos"] * cantidad) / 100
    gras = (stats["grasas"] * cantidad) / 100
    
    # Si estamos en medio de una receta
    if registro_temporal.get(user_id, {}).get('en_receta'):
        registro_temporal[user_id]['receta_ingredientes']["kcal"] += kcal
        registro_temporal[user_id]['receta_ingredientes']["proteinas"] += prot
        registro_temporal[user_id]['receta_ingredientes']["carbos"] += carb
        registro_temporal[user_id]['receta_ingredientes']["grasas"] += gras
        registro_temporal[user_id]['receta_ingredientes']["peso_crudo"] += cantidad
        
        respuesta = (f"➕ Agregado a la receta: {cantidad}g de {categoria.title()} {variante.title()}.\n"
                     f"Seguí agregando o tocá '✅ Listo (Terminar)'.")
                     
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta)
        
        # Limpiar variables temporales y reactivar el bucle
        del registro_temporal[user_id]['cantidad_pendiente']
        del registro_temporal[user_id]['en_receta']
        bot.register_next_step_handler(call.message, paso_ingrediente_receta)
        return

    # Si es una comida normal
    if user_id not in datos_usuarios:
        datos_usuarios[user_id] = {"kcal": 0, "proteinas": 0, "carbos": 0, "grasas": 0, "meta_proteinas": 160, "meta_kcal": 2000}
    
    datos_usuarios[user_id]["kcal"] += kcal
    datos_usuarios[user_id]["proteinas"] += prot
    datos_usuarios[user_id]["carbos"] += carb
    datos_usuarios[user_id]["grasas"] += gras
    guardar_datos()
    
    respuesta = (f"🍗 Agregaste {cantidad}g de {categoria.title()} {variante.title()}:\n"
                 f"🔥 Kcal: {kcal:.0f}\n🥩 Proteínas: {prot:.1f}g\n"
                 f"🍞 Carbos: {carb:.1f}g\n🥑 Grasas: {gras:.1f}g\n\n"
                 f"✅ ¡Guardado!")
                 
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=respuesta)
    del registro_temporal[user_id]['cantidad_pendiente']

# Mantiene al bot escuchando mensajes
bot.polling()