# 🤖 MacroBot - Asistente Nutricional Avanzado para Telegram

MacroBot es un bot de Telegram diseñado para llevar un registro preciso y rápido de tu alimentación diaria. Pensado para nutrición deportiva, permite cargar alimentos sueltos, armar paquetes personalizados y crear recetas completas con cálculos matemáticos exactos (pérdida/ganancia de agua).

## ✨ Características Principales

- **Cálculo de TDEE:** Configuración inicial (edad, peso, altura, actividad) que calcula calorías y macros diarios según la fórmula Mifflin-St Jeor.
- **Base de Datos Dinámica JSON:** Datos nutricionales organizados por categorías y alias sin depender de motores SQL pesados.
- **Registro Interactivo:** Comandos ultra-rápidos (ej: `150 pollo`). El bot suma calorías, proteínas, carbohidratos y grasas automáticamente.
- **Sistema de Recetas:** Sumá ingredientes en crudo y pasale el peso final cocinado. El bot recalcula los valores a 100g y los guarda en tu perfil.
- **Alimentos Personalizados:** Creá "paquetes" leyendo etiquetas de productos comerciales.

## 🚀 Instalación y Uso Local

1. **Cloná el repositorio:**
   ```bash
   git clone https://github.com/TU_USUARIO/MacroBot.git
   cd MacroBot
   ```

2. **Instalá las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurá tu Token de Telegram:**
   - Copiá el archivo `.env.example` y renombralo a `.env`.
   - Reemplazá el contenido con el token que te dio [@BotFather](https://t.me/BotFather):
     ```env
     TELEGRAM_TOKEN=tu_token_secreto_aqui
     ```

4. **Iniciá el bot:**
   ```bash
   python bot.py
   ```

## 📝 Estructura de Datos

- **`alimentos.json`**: Base de datos global de alimentos. Se pueden usar separadores `_sec_...` para organizar visualmente el JSON.
- **`usuarios.json`**: Base de datos dinámica local ignorada por Git. Almacena el estado diario y las recetas personalizadas de cada usuario usando su ID de Telegram.

## 🛠️ Tecnologías
- Python 3
- pyTelegramBotAPI (telebot)
- dotenv para variables de entorno

---
*Bot construido para seguimiento macro-nutricional sin fricción.*
