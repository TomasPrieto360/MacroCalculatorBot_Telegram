import os
import re

with open("bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace the JSON loading at the top
json_load_pattern = r'''archivo_datos = os\.path\.join\(BASE_DIR, "usuarios\.json"\)
if os\.path\.exists\(archivo_datos\):
    with open\(archivo_datos, 'r'\) as f:
        datos_usuarios = json\.load\(f\)
else:
    datos_usuarios = \{\}

def guardar_datos\(\):
    with open\(archivo_datos, 'w'\) as f:
        json\.dump\(datos_usuarios, f, indent=4\)'''

mongo_init = '''from pymongo import MongoClient
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

MONGO_URI = os.getenv("MONGO_URI")
if MONGO_URI:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client.get_database("macrobot_db")
    col_usuarios = db.usuarios
    col_alimentos = db.alimentos
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
user_cache = {}'''

content = re.sub(json_load_pattern, mongo_init, content)

# 2. Refactor 'user_id in datos_usuarios' -> not needed if get_user handles defaults, but to be safe:
# We will use a regex to replace the global access.
# Since there are many accesses, we will just redefine `datos_usuarios` as a property or use the cache.
# Actually, the safest and easiest way is to inject a middleware at the start of EVERY handler that loads the user into `datos_usuarios`, and then at the end of the handler it saves it!
# But we can't easily hook into every handler. 

# Let's write a custom dictionary class for `datos_usuarios`!
dict_class = '''class MongoDict(dict):
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
'''

# We will just append the dict_class after mongo_init
content = content.replace(mongo_init, mongo_init + "\n\n" + dict_class)

# 3. Replace cargar_alimentos and guardar_alimentos
alimentos_pattern = r'''def cargar_alimentos\(\):
    try:
        ruta = os\.path\.join\(BASE_DIR, "alimentos\.json"\)
        with open\(ruta, "r", encoding="utf-8"\) as file:
            return json\.load\(file\)
    except Exception as e:
        print\(f"Error cargando alimentos: \{e\}"\)
        return \{\}

def guardar_alimentos\(alimentos_dict\):
    try:
        ruta = os\.path\.join\(BASE_DIR, "alimentos\.json"\)
        with open\(ruta, "w", encoding="utf-8"\) as file:
            json\.dump\(alimentos_dict, file, ensure_ascii=False, indent=4\)
        print\("✅ Base de datos guardada correctamente\."\)
    except Exception as e:
        print\(f"Error al guardar alimentos\.json: \{e\}"\)'''

mongo_alimentos = '''def cargar_alimentos():
    if col_alimentos:
        alimentos = list(col_alimentos.find())
        return {doc["_id"]: doc for doc in alimentos if "_id" in doc}
    return {}

def guardar_alimentos(alimentos_dict):
    if col_alimentos:
        for nombre, datos in alimentos_dict.items():
            doc = {"_id": nombre}
            doc.update(datos)
            col_alimentos.update_one({"_id": nombre}, {"$set": doc}, upsert=True)
'''
content = re.sub(alimentos_pattern, mongo_alimentos, content)

with open("bot_refactored.py", "w", encoding="utf-8") as f:
    f.write(content)
print("bot_refactored.py created!")
