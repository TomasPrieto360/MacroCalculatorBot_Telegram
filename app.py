import json
import os
import sys
import base64
from datetime import datetime
import time
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
    headers = {'User-Agent': 'MacroCalculatorApp/2.0'}
    
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
        "meta_proteinas": 160, "meta_kcal": 2000, "meta_carbos": 250, "meta_grasas": 65,
        "racha_dias": 0, "historial_hoy": [], "historial_dias": [], "mis_alimentos": {}, "favoritos": {}, "perfil_fisico": {}
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

# ----------------- BASE DE DATOS LOCAL DE ALIMENTOS -----------------
archivo_alimentos = os.path.join(BASE_DIR, "alimentos.json")
if os.path.exists(archivo_alimentos):
    with open(archivo_alimentos, 'r', encoding='utf-8') as f:
        db_alimentos = json.load(f)
        tabla_nutricional = db_alimentos.get("alimentos", {})
        diccionario_alias = db_alimentos.get("alias", {})
else:
    tabla_nutricional = {}
    diccionario_alias = {}

import time
import base64
from flask import Flask, request, jsonify, render_template

# Configuración del servidor Web para Render/Production/PWA
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

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
        "nombre": u_data.get("nombre") or f"Usuario {user_id}",
        "kcal": round(u_data.get("kcal", 0), 1),
        "proteinas": round(u_data.get("proteinas", 0), 1),
        "carbos": round(u_data.get("carbos", 0), 1),
        "grasas": round(u_data.get("grasas", 0), 1),
        "meta_kcal": u_data.get("meta_kcal", 2000),
        "meta_proteinas": u_data.get("meta_proteinas", 160),
        "meta_carbos": u_data.get("meta_carbos", 250),
        "meta_grasas": u_data.get("meta_grasas", 65),
        "racha_dias": u_data.get("racha_dias", 0),
        "historial_hoy": u_data.get("historial_hoy", []),
        "historial_dias": u_data.get("historial_dias", []),
        "favoritos": u_data.get("favoritos", {}),
        "perfil_fisico": u_data.get("perfil_fisico", {}),
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
        
    kcal = round((kcal_100 * cantidad_gramos) / 100, 1)
    prot = round((prot_100 * cantidad_gramos) / 100, 1)
    carb = round((carb_100 * cantidad_gramos) / 100, 1)
    gras = round((gras_100 * cantidad_gramos) / 100, 1)
    
    u_data = datos_usuarios[user_id]
    u_data["kcal"] = round(u_data.get("kcal", 0) + kcal, 1)
    u_data["proteinas"] = round(u_data.get("proteinas", 0) + prot, 1)
    u_data["carbos"] = round(u_data.get("carbos", 0) + carb, 1)
    u_data["grasas"] = round(u_data.get("grasas", 0) + gras, 1)
    
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

# Endpoint API: Borrar alimento del historial de hoy
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
        u_data["kcal"] = max(0, round(u_data.get("kcal", 0) - item_to_remove.get("kcal", 0), 1))
        u_data["proteinas"] = max(0, round(u_data.get("proteinas", 0) - item_to_remove.get("proteinas", 0), 1))
        u_data["carbos"] = max(0, round(u_data.get("carbos", 0) - item_to_remove.get("carbos", 0), 1))
        u_data["grasas"] = max(0, round(u_data.get("grasas", 0) - item_to_remove.get("grasas", 0), 1))
        guardar_datos()
        return jsonify({"status": "ok"})
        
    return jsonify({"status": "error", "message": "Registro no encontrado"}), 404

# Endpoint API: Actualizar configuración de perfil TDEE / Metas
@app.route('/api/user/<user_id>/profile', methods=['POST'])
def api_update_profile(user_id):
    req_data = request.get_json() or {}
    u_data = datos_usuarios[user_id]
    if "nombre" in req_data:
        u_data["nombre"] = str(req_data["nombre"]).strip()
    if "meta_kcal" in req_data:
        u_data["meta_kcal"] = float(req_data["meta_kcal"])
    if "meta_proteinas" in req_data:
        u_data["meta_proteinas"] = float(req_data["meta_proteinas"])
    if "meta_carbos" in req_data:
        u_data["meta_carbos"] = float(req_data["meta_carbos"])
    if "meta_grasas" in req_data:
        u_data["meta_grasas"] = float(req_data["meta_grasas"])
    guardar_datos()
    return jsonify({"status": "ok"})

# Endpoint API: Calcular TDEE e instalar metas personales
@app.route('/api/user/<user_id>/calculate-tdee', methods=['POST'])
def api_calculate_tdee(user_id):
    req_data = request.get_json() or {}
    try:
        peso = float(req_data.get("peso", 70))
        altura = float(req_data.get("altura", 170))
        edad = float(req_data.get("edad", 25))
        sexo = str(req_data.get("sexo", "m")).strip().lower()
        actividad = str(req_data.get("actividad", "moderado")).strip().lower()
        objetivo = str(req_data.get("objetivo", "mantener")).strip().lower()

        # Mifflin-St Jeor
        bmr = (10 * peso) + (6.25 * altura) - (5 * edad) + (5 if sexo == 'm' else -161)
        mult_dict = {
            "sedentario": 1.2,
            "ligero": 1.375,
            "moderado": 1.55,
            "intenso": 1.725,
            "extremo": 1.9
        }
        mult = mult_dict.get(actividad, 1.55)
        tdee = bmr * mult

        if objetivo == "perder":
            meta_kcal = round(tdee - 400)
        elif objetivo == "ganar":
            meta_kcal = round(tdee + 300)
        else:
            meta_kcal = round(tdee)

        # Reparto de macros
        prot_g = round(peso * (2.0 if actividad in ["moderado", "intenso", "extremo"] else 1.8))
        fat_g = round((meta_kcal * 0.25) / 9)
        carb_g = max(50, round((meta_kcal - (prot_g * 4 + fat_g * 9)) / 4))

        u_data = datos_usuarios[user_id]
        u_data["meta_kcal"] = meta_kcal
        u_data["meta_proteinas"] = prot_g
        u_data["meta_carbos"] = carb_g
        u_data["meta_grasas"] = fat_g
        u_data["perfil_fisico"] = {
            "peso": peso, "altura": altura, "edad": edad,
            "sexo": sexo, "actividad": actividad, "objetivo": objetivo, "tdee": round(tdee)
        }
        guardar_datos()
        return jsonify({
            "status": "ok",
            "meta_kcal": meta_kcal,
            "meta_proteinas": prot_g,
            "meta_carbos": carb_g,
            "meta_grasas": fat_g,
            "tdee": round(tdee)
        })
    except Exception as e:
        print(f"[ERROR] API TDEE: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

def calcular_racha_usuario(historial_dias):
    """Calcula dinámicamente la racha de días consecutivos cumplidos desde el historial."""
    if not historial_dias:
        return 0
        
    dias_ordenados = sorted(historial_dias, key=lambda x: x.get("fecha", ""), reverse=True)
    racha = 0
    from datetime import datetime
    
    fecha_prev = None
    for dia in dias_ordenados:
        if not dia.get("cumplido"):
            break
        
        fecha_str = dia.get("fecha")
        if not fecha_str:
            break
            
        try:
            fecha_curr = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            break
            
        if fecha_prev is None:
            racha += 1
            fecha_prev = fecha_curr
        else:
            diff = (fecha_prev - fecha_curr).days
            if diff == 1:
                racha += 1
                fecha_prev = fecha_curr
            elif diff == 0:
                continue
            else:
                break
                
    return racha

# Endpoint API: Terminar Día (Cerrar día, guardar historial con fecha elegida y resetear)
@app.route('/api/user/<user_id>/close-day', methods=['POST'])
def api_close_day(user_id):
    try:
        from datetime import datetime
        req_data = request.get_json() or {}
        fecha_cierre = str(req_data.get("fecha", "")).strip()
        
        if not fecha_cierre:
            fecha_cierre = datetime.now().strftime("%Y-%m-%d")

        u_data = datos_usuarios[user_id]
        
        consumed_kcal = round(u_data.get("kcal", 0), 1)
        consumed_prot = round(u_data.get("proteinas", 0), 1)
        consumed_carb = round(u_data.get("carbos", 0), 1)
        consumed_gras = round(u_data.get("grasas", 0), 1)
        meta_k = u_data.get("meta_kcal", 2000)
        
        # Evaluar si cumplió la meta (dentro de +-15% de margen)
        cumplido = abs(consumed_kcal - meta_k) <= (meta_k * 0.15) or (consumed_kcal >= meta_k * 0.85 and consumed_kcal <= meta_k * 1.15)
        
        registro_dia = {
            "fecha": fecha_cierre,
            "kcal": consumed_kcal,
            "proteinas": consumed_prot,
            "carbos": consumed_carb,
            "grasas": consumed_gras,
            "meta_kcal": meta_k,
            "comidas_count": len(u_data.get("historial_hoy", [])),
            "cumplido": cumplido
        }
        
        if "historial_dias" not in u_data:
            u_data["historial_dias"] = []
            
        # Si ya existía un registro para esa fecha, actualizarlo
        existente_idx = -1
        for idx, item in enumerate(u_data["historial_dias"]):
            if item.get("fecha") == fecha_cierre:
                existente_idx = idx
                break
                
        if existente_idx >= 0:
            u_data["historial_dias"][existente_idx] = registro_dia
        else:
            u_data["historial_dias"].append(registro_dia)
            
        # Re-ordenar por fecha descendente y limitar a 90 días
        u_data["historial_dias"] = sorted(u_data["historial_dias"], key=lambda x: x.get("fecha", ""), reverse=True)[:90]

        # Calcular racha dinámica
        racha = calcular_racha_usuario(u_data["historial_dias"])
        u_data["racha_dias"] = racha

        # Resetear día actual
        u_data["kcal"] = 0
        u_data["proteinas"] = 0
        u_data["carbos"] = 0
        u_data["grasas"] = 0
        u_data["historial_hoy"] = []
        
        guardar_datos()
        return jsonify({
            "status": "ok",
            "resumen": registro_dia,
            "racha_dias": racha
        })
    except Exception as e:
        print(f"[ERROR] API close-day: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint API: Eliminar un día del historial pasado
@app.route('/api/user/<user_id>/history-day/<fecha>', methods=['DELETE'])
def api_delete_history_day(user_id, fecha):
    try:
        u_data = datos_usuarios[user_id]
        hist = u_data.get("historial_dias", [])
        
        u_data["historial_dias"] = [d for d in hist if d.get("fecha") != fecha]
        racha = calcular_racha_usuario(u_data["historial_dias"])
        u_data["racha_dias"] = racha
        
        guardar_datos()
        return jsonify({
            "status": "ok",
            "racha_dias": racha,
            "historial_dias": u_data["historial_dias"]
        })
    except Exception as e:
        print(f"[ERROR] API delete-history-day: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint API: Favoritos del usuario
@app.route('/api/user/<user_id>/favorites', methods=['GET', 'POST', 'DELETE'])
def api_favorites(user_id):
    u_data = datos_usuarios[user_id]
    if "favoritos" not in u_data:
        u_data["favoritos"] = {}
        
    if request.method == 'GET':
        return jsonify(u_data["favoritos"])
        
    elif request.method == 'POST':
        req_data = request.get_json() or {}
        nombre = str(req_data.get("nombre", "")).strip()
        if not nombre:
            return jsonify({"status": "error", "message": "Nombre requerido"}), 400
        u_data["favoritos"][nombre.lower()] = {
            "nombre": nombre,
            "kcal": float(req_data.get("kcal", 0)),
            "proteinas": float(req_data.get("proteinas", 0)),
            "carbos": float(req_data.get("carbos", 0)),
            "grasas": float(req_data.get("grasas", 0))
        }
        guardar_datos()
        return jsonify({"status": "ok", "favoritos": u_data["favoritos"]})
        
    elif request.method == 'DELETE':
        nombre = request.args.get("nombre", "").strip().lower()
        if nombre in u_data["favoritos"]:
            del u_data["favoritos"][nombre]
            guardar_datos()
        return jsonify({"status": "ok", "favoritos": u_data["favoritos"]})

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

def clean_json_from_llm(raw_text):
    """Limpia y extrae de forma segura objetos/arrays JSON generados por el modelo IA."""
    if not raw_text:
        return {}
    clean = raw_text.strip()
    if "```" in clean:
        lines = clean.splitlines()
        filtered = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            filtered.append(line)
        clean = "\n".join(filtered).strip()
    try:
        return json.loads(clean)
    except Exception:
        import re
        match = re.search(r'(\{.*\}|\[.*\])', clean, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise

# Endpoint API: Buscar producto por Código de Barras directo
@app.route('/api/barcode/<code_str>')
def api_barcode(code_str):
    code_clean = str(code_str).strip()
    if not code_clean:
        return jsonify({"status": "error", "message": "Código de barras no provisto"}), 400
        
    try:
        # 1. Buscar en Open Food Facts por EAN
        off = buscar_open_food_facts(code_clean)
        if off and off.get("kcal", 0) > 0:
            return jsonify({"status": "ok", "alimento": off})
            
        # 2. Buscar en MongoDB global
        doc = buscar_alimento_mongo_global(code_clean)
        if doc:
            return jsonify({
                "status": "ok",
                "alimento": {
                    "alimento": doc["_id"],
                    "kcal": doc.get("kcal", 0),
                    "proteinas": doc.get("proteinas", 0),
                    "carbos": doc.get("carbos", 0),
                    "grasas": doc.get("grasas", 0),
                    "fuente": "mongo"
                }
            })
            
        return jsonify({"status": "error", "message": f"No se encontró información para el código {code_clean}"}), 404
    except Exception as e:
        print(f"[ERROR] API Barcode: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint API: Analizar Foto de Comida con IA Vision + Texto de ayuda opcional
@app.route('/api/ai/scan-meal-photo', methods=['POST'])
def api_scan_meal_photo():
    req_data = request.get_json() or {}
    img_b64 = req_data.get("image_base64", "")
    text_hint = req_data.get("text_hint", "").strip()
    
    if not img_b64:
        return jsonify({"status": "error", "message": "Imagen no enviada"}), 400
        
    try:
        mime_type = "image/jpeg"
        if "," in img_b64:
            header, img_b64 = img_b64.split(",", 1)
            if "image/png" in header:
                mime_type = "image/png"
            elif "image/webp" in header:
                mime_type = "image/webp"
            
        img_bytes = base64.b64decode(img_b64)
        
        prompt = (
            "Analizá cuidadosamente la foto de este plato de comida.\n"
            + (f"DETALLES ADICIONALES DADOS POR EL USUARIO PARA AYUDAR AL ANÁLISIS: '{text_hint}'.\n" if text_hint else "") +
            "Identificá el alimento o preparación, estimá el tamaño de porción realista en gramos y calculá las calorías y macronutrientes totales.\n"
            "Devuelve ÚNICAMENTE un objeto JSON válido con este formato exacto:\n"
            "{\n"
            '  "alimento": "Nombre del plato (ej: Milanesa de pollo con puré)",\n'
            '  "cantidad_estimada_g": 250,\n'
            '  "kcal": 450,\n'
            '  "proteinas": 35.0,\n'
            '  "carbos": 40.0,\n'
            '  "grasas": 15.0,\n'
            '  "confianza": "Alta"\n'
            "}\n"
            "Solo responde con el objeto JSON. Sin código markdown adicional."
        )
        
        from google.genai import types
        res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
                prompt
            ]
        )
        parsed = clean_json_from_llm(res.text)
        return jsonify({"status": "ok", "parsed": parsed})
    except Exception as e:
        print(f"[ERROR] API Scan Meal Photo: {e}")
        return jsonify({"status": "error", "message": f"Error procesando imagen: {str(e)}"}), 500

# Endpoint API: Escanear etiqueta con Gemini Vision + Texto opcional
@app.route('/api/ai/scan-label', methods=['POST'])
def api_scan_label():
    req_data = request.get_json() or {}
    img_b64 = req_data.get("image_base64", "")
    text_hint = req_data.get("text_hint", "").strip()
    
    if not img_b64:
        return jsonify({"status": "error", "message": "Imagen no enviada"}), 400
        
    try:
        mime_type = "image/jpeg"
        if "," in img_b64:
            header, img_b64 = img_b64.split(",", 1)
            if "image/png" in header:
                mime_type = "image/png"
            elif "image/webp" in header:
                mime_type = "image/webp"
            
        img_bytes = base64.b64decode(img_b64)
        prompt = (
            "Analizá cuidadosamente la información nutreicional o etiqueta en esta imagen.\n"
            "Extraé o calcula los valores exactos POR 100g O 100ml de producto.\n"
            + (f"PISTA ADICIONAL O NOMBRE DEL PRODUCTO: '{text_hint}'.\n" if text_hint else "") +
            "Devuelve ÚNICAMENTE un JSON válido con este formato exacto:\n"
            "{\n"
            '  "alimento": "Nombre del producto o marca detectada",\n'
            '  "kcal": 000,\n'
            '  "proteinas": 00.0,\n'
            '  "carbos": 00.0,\n'
            '  "grasas": 00.0,\n'
            '  "peso_porcion": 100\n'
            "}\n"
            "Nota: 'peso_porcion' es la porción sugerida por el fabricante si aparece en la etiqueta (ej: 30g para 3 galletitas). Si no aparece, pon 100.\n"
            "Solo responde con el objeto JSON sin texto extra."
        )
        
        from google.genai import types
        res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
                prompt
            ]
        )
        parsed = clean_json_from_llm(res.text)
        return jsonify({"status": "ok", "parsed": parsed})
    except Exception as e:
        print(f"[ERROR] API Gemini Label Scan: {e}")
        return jsonify({"status": "error", "message": f"Error procesando etiqueta: {str(e)}"}), 500

# Endpoint API: Recetas de Heladera con IA
@app.route('/api/ai/fridge-recipes', methods=['POST'])
def api_fridge_recipes():
    req_data = request.get_json() or {}
    ingredientes = req_data.get("ingredientes", [])
    kcal_rem = req_data.get("kcal_rem", 600)
    prot_rem = req_data.get("prot_rem", 40)
    
    if not ingredientes:
        return jsonify({"status": "error", "message": "Ingredientes requeridos"}), 400
        
    try:
        prompt = (
            f"Tengo los siguientes ingredientes disponibles: {', '.join(ingredientes)}.\n"
            f"Objetivo nutricional: alrededor de {kcal_rem} kcal y {prot_rem}g de proteínas.\n"
            "Sugerí 3 opciones de recetas prácticas e indica ingredientes, instrucciones cortas y macros aproximados por porción.\n"
            "Devuelve ÚNICAMENTE un array JSON válido con objetos del siguiente formato:\n"
            "[\n"
            "  {\n"
            '    "titulo": "Nombre de la receta",\n'
            '    "ingredientes": ["ingrediente 1", "ingrediente 2"],\n'
            '    "instrucciones": "Paso 1... Paso 2...",\n'
            '    "kcal": 400,\n'
            '    "proteinas": 30,\n'
            '    "carbos": 35,\n'
            '    "grasas": 12\n'
            "  }\n"
            "]\n"
            "Solo responde con el array JSON."
        )
        res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        raw_text = res.text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw_text)
        return jsonify({"status": "ok", "recetas": parsed})
    except Exception as e:
        print(f"[ERROR] API Fridge Recipes: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------- INICIO EN PRODUCCIÓN -----------------
if __name__ == "__main__":
    # Arrancar servidor Flask Móvil
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)