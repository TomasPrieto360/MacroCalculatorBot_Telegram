import json
import os
from pymongo import MongoClient
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("Error: No se encontró MONGO_URI en .env")
    exit(1)

client = MongoClient(MONGO_URI)
db = client.get_database("macrobot_db")

# Migrar alimentos
archivo_alimentos = os.path.join(BASE_DIR, "alimentos.json")
if os.path.exists(archivo_alimentos):
    with open(archivo_alimentos, 'r', encoding='utf-8') as f:
        alimentos_data = json.load(f)
    
    alimentos_docs = []
    for nombre, datos in alimentos_data.items():
        doc = {"_id": nombre}
        doc.update(datos)
        alimentos_docs.append(doc)
    
    if alimentos_docs:
        col_alimentos = db.alimentos
        for doc in alimentos_docs:
            col_alimentos.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        print(f"Migrados {len(alimentos_docs)} alimentos a MongoDB.")

# Migrar usuarios
archivo_usuarios = os.path.join(BASE_DIR, "usuarios.json")
if os.path.exists(archivo_usuarios):
    with open(archivo_usuarios, 'r', encoding='utf-8') as f:
        usuarios_data = json.load(f)
        
    usuarios_docs = []
    for user_id, datos in usuarios_data.items():
        doc = {"_id": str(user_id)}
        doc.update(datos)
        usuarios_docs.append(doc)
        
    if usuarios_docs:
        col_usuarios = db.usuarios
        for doc in usuarios_docs:
            col_usuarios.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        print(f"Migrados {len(usuarios_docs)} usuarios a MongoDB.")

print("Migración completada con éxito.")
