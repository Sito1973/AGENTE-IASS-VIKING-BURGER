import os
import json
from google import genai
from google.genai.types import Tool, GenerateContentConfig

# Definición del schema de la herramienta
enviar_menu_schema = {
    "name": "enviar_menu",
    "description": "Envía el menú o la carta al cliente. Esta herramienta debe usarse cuando el cliente pide ver el menú o la carta. Es obligatorio preguntar y especificar la sede (Dosquebradas, La Virginia, Pereira, Cerritos).",
    "input_schema": {
        "type": "object",
        "properties": {
            "sede": {
                "type": "string",
                "enum": [
                    "La Virginia",
                    "Pereira",
                    "Dosquebradas",
                    "Cerritos"
                ],
                "description": "Sede para la cual se debe enviar el menú o carta (obligatorio: La Virginia, Pereira, Dosquebradas, Cerritos)"
            }
        },
        "required": [
            "sede"
        ]
    }
}

# Definir la función enviar_menu
def enviar_menu(sede):
    menus = {
        "La Virginia": "Menú La Virginia:\n1. Bandeja Paisa\n2. Arepas\n3. Ajiaco",
        "Pereira": "Menú Pereira:\n1. Sancocho\n2. Empanadas\n3. Chorizo",
        "Dosquebradas": "Menú Dosquebradas:\n1. Tamales\n2. Changua\n3. Buñuelos",
        "Cerritos": "Menú Cerritos:\n1. Arroz con Pollo\n2. Patacones\n3. Lulada"
    }

    menu = menus.get(sede)
    if menu:
        print(f"Enviando el menú para {sede}:\n{menu}")
    else:
        print(f"Sede '{sede}' no reconocida.")

#
client = genai.Client(api_key="AIzaSyAAvCm7AZVqmdZVk3eQGha0ddlVkFKVkZg")

# Definir el modelo
model_id = "gemini-2.0-flash-exp"

# Prompt de ejemplo
prompt = "Quisiera ver el menú, por favor."

# Configurar las herramientas
tools = [
    {"function_declarations": [enviar_menu_schema]}
]

# Generar contenido con las herramientas configuradas
response = client.models.generate_content(
    model=model_id,
    contents=prompt,
    config=GenerateContentConfig(
        tools=tools,
        response_modalities=["TEXT"],
    )
)

# Procesar la respuesta
print("Respuesta de Gemini 2.0 Flash (experimental):")
print(response.text)

# Manejar posibles llamadas a funciones
try:
    response_json = json.loads(response.text)
    if "function_call" in response_json:
        function_name = response_json["function_call"]["name"]
        arguments = response_json["function_call"].get("arguments", {})

        if function_name == "enviar_menu":
            sede = arguments.get("sede")
            if sede:
                enviar_menu(sede)
            else:
                print("No se proporcionó la sede.")
        else:
            print(f"Función desconocida: {function_name}")
    else:
        print("No se solicitaron llamadas a funciones.")
except json.JSONDecodeError:
    print("La respuesta no está en formato JSON.")
except Exception as e:
    print(f"Ocurrió un error al procesar la respuesta: {e}")
