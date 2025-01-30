import json
import requests
import random
import google.genai as genai
from google.genai import types
import base64
import os
import time
import re
from flask import Flask, request, jsonify, redirect
import anthropic
from threading import Thread, Event
import uuid
import logging
from datetime import datetime
import pytz
from datetime import timedelta
import xmlrpc.client
from bs4 import BeautifulSoup  # Importar BeautifulSoup para convertir HTML a texto
from openai import OpenAI
from dotenv import load_dotenv

# Cargar variables de entorno (al principio del archivo)
load_dotenv()

#https://github.com/googleapis/python-genai

app = Flask(__name__)

# Configuración del logging
logging.basicConfig(
    level=logging.
    INFO,  # Nivel de logging: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # Salida a la consola
    ])

logger = logging.getLogger(__name__)

# URL del webhook de n8n (ajusta esto según tu configuración)
N8N_WEBHOOK_URL = os.environ.get(
    'N8N_WEBHOOK_URL',
    'https://n8n.cocinandosonrisas.co/webhook/eleccionFormaPagoSPApi')

# Mapa para asociar valores de 'assistant' con nombres de archivos
ASSISTANT_FILES = {
    0: "0 prompt inicial.txt",
    1: 'ASISTENTE_PDC_DOMICILIO.txt',
    2: 'ASISTENTE_PDC_DOMICILIO_PROMO.txt',
    3: 'ASISTENTE_PDC_RECOGER.txt',
    4: 'ASISTENTE_PDC_RECOGER_PROMO.txt',
    5: "ASISTENTE_LV_DOMICILIO.txt",
    6: "ASISTENTE_LV_DOMICILIO_PROMO.txt",
    7: "ASISTENTE_LV_RECOGER.txt",
    8: "ASISTENTE_LV_RECOGER_PROMO.txt",
    9: "ASISTENTE_POSTVENTA_DOMICILIO.txt",
    10: "ASISTENTE_POSTVENTA_RECOGER.txt"
}

conversations = {}


class N8nAPI:

    def __init__(self):
        self.crear_pedido_webhook_url = os.environ.get(
            'N8N_CREAR_PEDIDO_WEBHOOK_URL')
        self.link_pago_webhook_url = os.environ.get(
            'N8N_LINK_PAGO_WEBHOOK_URL')
        self.enviar_menu_webhook_url = os.environ.get(
            'N8N_ENVIAR_MENU_WEBHOOK_URL')
        self.crear_direccion_webhook_url = os.environ.get(
            'N8N_CREAR_DIRECCION_WEBHOOK_URL')
        # Puedes añadir más URLs de webhook si lo necesitas
        logger.info("Inicializado N8nAPI con las URLs: %s, %s",
                    self.crear_pedido_webhook_url, self.link_pago_webhook_url)

    def crear_pedido(self, payload):
        """Envía el pedido al webhook de n8n"""
        logger.debug("Enviando pedido a n8n con payload: %s", payload)
        response = requests.post(self.crear_pedido_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar pedido: %s %s",
                    response.status_code, response.text)
        return response

    def enviar_link_pago(self, payload):
        """Envía los datos para generar el link de pago al webhook de n8n"""
        logger.debug("Enviando datos de link de pago a n8n con payload: %s",
                     payload)
        response = requests.post(self.link_pago_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos de link de pago: %s %s",
                    response.status_code, response.text)
        return response

    def enviar_menu(self, payload):
        """Envía los datos para generar el link de pago al webhook de n8n"""
        logger.debug("Enviando datos de link de pago a n8n con payload: %s",
                     payload)
        response = requests.post(self.enviar_menu_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos de link de pago: %s %s",
                    response.status_code, response.text)
        return response

    def crear_direccion(self, payload):
        """Envía los datos para generar el link de pago al webhook de n8n"""
        logger.debug("Enviando datos de link de pago a n8n con payload: %s",
                     payload)
        response = requests.post(self.crear_direccion_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos de link de pago: %s %s",
                    response.status_code, response.text)
        return response

    # Añade más métodos si necesitas interactuar con otros webhooks de n8n


def remove_thinking_block(text):
    """
    Elimina todos los bloques <thinking>...</thinking> del texto.

    Args:
        text (str): El texto del cual se eliminarán los bloques <thinking>.

    Returns:
        str: El texto limpio sin los bloques <thinking>.
    """
    pattern = re.compile(r'<thinking>.*?</thinking>',
                         re.DOTALL | re.IGNORECASE)
    cleaned_text = pattern.sub('', text).strip()
    return cleaned_text


# Función para generar un color HSL aleatorio
def get_random_hsl():
    h = random.randint(0, 360)  # Matiz entre 0 y 360
    s = random.randint(0, 100)  # Saturación entre 0 y 100
    l = random.randint(0, 100)  # Luminosidad entre 0 y 100
    return f'hsl({h}, {s}%, {l}%)'


# Función para crear SVG correctamente y convertirlo a Base64 sin prefijo
def create_svg_base64(letter, width, height):
    background_color = get_random_hsl()
    # Generar el SVG en una sola línea preservando espacios necesarios
    svg_string = f"<svg height='{height}' width='{width}' xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'><rect fill='{background_color}' height='{height}' width='{width}'/><text fill='#ffffff' font-size='{height * 0.53}' text-anchor='middle' x='{width / 2}' y='{height * 0.7}' font-family='sans-serif'>{letter}</text></svg>"

    # Codificar el SVG en Base64
    base64_bytes = base64.b64encode(svg_string.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')

    return base64_string, svg_string


def crear_pedido(tool_input, subscriber_id):
    """
    Función para enviar los datos del pedido al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando crear_pedido con datos: %s", tool_input)
    logger.debug("subscriber_id en crear_pedido: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {
            "response": {
                "tool_code": "crear_pedido",
                "subscriber_id": subscriber_id,
                "datos": tool_input  # Datos provenientes del LLM
            }
        }

        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.crear_pedido(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s",
                         response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, retornamos el contenido de la respuesta de n8n
            response_content = response.json(
            ) if 'application/json' in response.headers.get(
                'Content-Type', '') else {
                    "message": response.text
                }
            result = {
                "result": response_content.get('message', 'Operación exitosa.')
            }

        logger.info("crear_pedido result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en crear_pedido: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}


def crear_link_pago(tool_input, subscriber_id):
    """
    Función para enviar los datos para crear un link de pago al webhook de n8n y devolver su respuesta al modelo.
    """
    logger.info("Iniciando crear_link_pago con datos: %s", tool_input)
    logger.debug("subscriber_id en crear_link_pago: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input
        payload = {
            "response": {
                "tool_code": "crear_link_pago",
                "subscriber_id": subscriber_id,
                "datos": tool_input  # Datos provenientes del LLM
            }
        }

        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n para crear el link de pago
        response = n8n_api.enviar_link_pago(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error(
                "Error al enviar datos al webhook de n8n para link de pago: %s",
                response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, retornamos el contenido de la respuesta de n8n
            response_content = response.json(
            ) if 'application/json' in response.headers.get(
                'Content-Type', '') else {
                    "message": response.text
                }
            result = {
                "result":
                response_content.get('message',
                                     'Link de pago generado exitosamente.')
            }

        logger.info("crear_link_pago result: %s", result)
        return result  # Retornamos el resultado al modelo

    except Exception as e:
        logger.exception("Error en crear_link_pago: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}


def enviar_menu(tool_input, subscriber_id):
    """
    Función para enviar los datos del pedido al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando crear_pedido con datos: %s", tool_input)
    logger.debug("subscriber_id en crear_pedido: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {
            "response": {
                "tool_code": "enviar_menu",
                "subscriber_id": subscriber_id,
                "sede": tool_input  # Datos provenientes del LLM
            }
        }


        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.enviar_menu(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s",
                         response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, retornamos el contenido de la respuesta de n8n
            response_content = response.json(
            ) if 'application/json' in response.headers.get(
                'Content-Type', '') else {
                    "message": response.text
                }
            result = {
                "result": response_content.get('message', 'Operación exitosa.')
            }

        logger.info("enviar_menu result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en enviar_menu: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}

def crear_direccion(tool_input, subscriber_id ):
    """
    Función para enviar los datos del pedido al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando crear_pedido con datos: %s", tool_input)
    logger.debug("subscriber_id en crear_pedido: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {
            "response": {
                "tool_code": "crear_direccion",
                "subscriber_id": subscriber_id,
                "sede": tool_input  # Datos provenientes del LLM
            }
        }


        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.enviar_menu(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s",
                         response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, retornamos el contenido de la respuesta de n8n
            response_content = response.json(
            ) if 'application/json' in response.headers.get(
                'Content-Type', '') else {
                    "message": response.text
                }
            result = {
                "result": response_content.get('message', 'Operación exitosa.')
            }

        logger.info("enviar_menu result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en enviar_menu: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}



def generate_response(api_key, message, assistant_content_text, thread_id,
                      event, subscriber_id, use_cache_control):
    logger.info("Generando respuesta para thread_id: %s", thread_id)

    logger.debug("subscriber_id en generate_response: %s", subscriber_id)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        conversation_history = conversations[thread_id]["messages"]

        # Agregar el mensaje del usuario al historial de conversación
        user_message_content = {"type": "text", "text": message}
        if use_cache_control:
            user_message_content["cache_control"] = {"type": "ephemeral"}

        conversation_history.append({
            "role": "user",
            "content": [user_message_content]
        })
        logger.debug("Historial de conversación actualizado: %s",
                     conversation_history)

        # Leer las herramientas desde el archivo JSON
        tools_file_path = os.path.join(os.path.dirname(__file__), 'tools.json')
        with open(tools_file_path, 'r', encoding='utf-8') as tools_file:
            tools = json.load(tools_file)
        logger.info("Herramientas cargadas desde tools.json")

        # Obtener 'telefono' y 'direccionCliente' desde conversations
        telefono = conversations.get(thread_id, {}).get('telefono')
        direccionCliente = conversations.get(thread_id,
                                             {}).get('direccionCliente')

        # Mapear nombres de herramientas a funciones
        tool_functions = {
            "crear_pedido":
            lambda tool_input, subscriber_id: crear_pedido(
                tool_input, subscriber_id, telefono, direccionCliente),
            "crear_link_pago":
            crear_link_pago
        }

        # Ajustar assistant_content para incluir cache_control si está habilitado
        assistant_content = [{"type": "text", "text": assistant_content_text}]

        if use_cache_control:
            assistant_content[0]["cache_control"] = {"type": "ephemeral"}

        # Iniciar la interacción con el modelo de Anthropic utilizando beta.prompt_caching
        while True:
            response = client.messages.create(
                #model="claude-3-5-haiku-latest",
                model="claude-3-5-haiku-latest",
                max_tokens=1000,
                temperature=0.8,
                system=assistant_content,
                messages=conversation_history,
                #tools=tools
            )
            #logger.info("Respuesta de Anthropic: %s", response)

            # Agregar la respuesta de Claude al historial de conversación
            conversation_history.append({
                "role": "assistant",
                "content": response.content
            })
            logger.info("Historial de conversación actualizado: %s",
                        conversation_history)

            # Extraer los tokens utilizados y otros valores de uso
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_input_tokens":
                response.usage.cache_creation_input_tokens,
                "cache_read_input_tokens":
                response.usage.cache_read_input_tokens
            }

            # Almacenar los valores de uso en el diccionario conversations
            conversations[thread_id]["usage"] = usage

            logger.info("Tokens utilizados - Input: %d, Output: %d",
                        usage["input_tokens"], usage["output_tokens"])
            logger.info("Cache Creation Input Tokens: %d",
                        usage["cache_creation_input_tokens"])
            logger.info("Cache Read Input Tokens: %d",
                        usage["cache_read_input_tokens"])

            # Verificar el motivo de parada
            if response.stop_reason == "tool_use":
                logger.info(
                    "Respuesta ssssssssssssssssssssssssssssssssssssss %s",
                    response)
                # Procesar el uso de la herramienta
                tool_use_blocks = [
                    block for block in response.content
                    if block.type == "tool_use"
                ]

                if not tool_use_blocks:

                    # Procesar la respuesta final sin herramientas
                    assistant_response_text = ''
                    for content_block in response.content:
                        if content_block.type == 'text':
                            assistant_response_text += content_block.text

                    # Guardar la respuesta generada y marcar la conversación como completada
                    conversations[thread_id][
                        "response"] = assistant_response_text
                    conversations[thread_id]["status"] = "completed"
                    logger.info("Respuesta generada para thread_id: %s",
                                thread_id)
                    break  # Salir del bucle

                tool_use = tool_use_blocks[0]
                tool_name = tool_use.name
                tool_input = tool_use.input

                logger.info("Uso de herramienta detectado: %s", tool_name)
                logger.info("Bloque tool_use completo: %s", tool_use)
                logger.info("Entrada de la herramienta: %s", tool_input)
                logger.info(
                    "Contenido completo de la respuesta del asistente: %s",
                    response.content)

                # Ejecutar la herramienta correspondiente
                if tool_name in tool_functions:

                    # Llamar a la función correspondiente
                    result = tool_functions[tool_name](tool_input,
                                                       subscriber_id)
                    logger.debug("Resultado de la herramienta %s: %s",
                                 tool_name, result)
                    logger.info(
                        f"Resultado de la herramienta {tool_name} ANTES de json.dumps(): {result}"
                    )  # Nuevo log
                    result_json = json.dumps(result)
                    logger.info(
                        f"Resultado de la herramienta {tool_name} DESPUÉS de json.dumps(): {result_json}"
                    )  # Nuevo log
                    logger.debug("Resultado de la herramienta %s: %s",
                                 tool_name, result)

                    # Agregar el resultado de la herramienta al historial de conversación
                    conversation_history.append({
                        "role":
                        "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps(result)
                        }]
                    })
                    logger.info(
                        f"Contenido del mensaje enviado a Anthropic: {conversation_history[-1]}"
                    )  # Nuevo log
                    logger.debug(
                        "Resultado de la herramienta %s añadido al historial",
                        tool_name)
                else:
                    logger.warning("Herramienta desconocida: %s", tool_name)
                    break  # Salir del bucle si la herramienta no es reconocida
            else:
                # No hay más herramientas por usar; obtener la respuesta final
                assistant_response_text = ''
                for content_block in response.content:
                    if content_block.type == 'text':
                        assistant_response_text += content_block.text

                # Actualizar el estado de la conversación
                conversations[thread_id]["response"] = assistant_response_text
                conversations[thread_id]["status"] = "completed"
                logger.info("Respuesta generada para thread_id: %s", thread_id)
                break  # Salir del bucle al completar la interacción

    except Exception as e:
        logger.exception("Error en generate_response para thread_id %s: %s",
                         thread_id, e)
        conversations[thread_id]["response"] = f"Error: {str(e)}"
        conversations[thread_id]["status"] = "error"
    finally:
        event.set()
        logger.debug("Evento establecido para thread_id: %s", thread_id)


def generate_response_gemini(
    api_key,
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    use_cache_control,
):
    logger.info("Generando respuesta con Gemini para thread_id: %s", thread_id)
    logger.debug("subscriber_id en generate_response_gemini: %s", subscriber_id)

    try:
        # 1) Configurar credenciales y cliente
        if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"

        project = os.environ.get("GCP_PROJECT", "gemini-cocoson")
        location = os.environ.get("GCP_LOCATION", "us-central1")
        api_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})

       

        # 2) Usar el modelo "thinking-exp" para obtener los "thoughts"
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")

        # Recuperar historial
        conversation_history = conversations[thread_id].get("messages", [])

        # Agregar mensaje del usuario
        user_message_content = {"type": "text", "text": message}
        if use_cache_control:
            user_message_content["cache_control"] = {"type": "ephemeral"}

        conversation_history.append({"role": "user", "content": [user_message_content]})

        # Cargar herramientas (opcional, si tu JSON las incluye)
        tools_file_path = os.path.join(os.path.dirname(__file__), "gemini.json")
        with open(tools_file_path, "r", encoding="utf-8") as tools_file:
            tools_json = json.load(tools_file)
        logger.info("Herramientas cargadas desde gemini.json")

        # (Opcional) Mapeo de herramientas -> function_definitions (si lo requieres)
        tools = []
        function_definitions = []
        for tool in tools_json:
            function = {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            }
            function_definitions.append(function)
            tools.append(types.Tool(function_declarations=[function]))

        # Convertir historial a la estructura de "contents"
        contents = []
        for msg in conversation_history:
            role = msg["role"]
            content_blocks = msg["content"]
            message_text = ""

            for block in content_blocks:
                if block["type"] == "text":
                    message_text += block["text"]

            if role == "assistant":
                gemini_role = "model"
            elif role == "user":
                gemini_role = "user"
            else:
                gemini_role = role

            contents.append(
                types.Content(
                    role=gemini_role, parts=[types.Part.from_text(message_text)]
                )
            )

        # Instrucción del sistema
        system_instruction = [types.Part.from_text(assistant_content_text)]

        # 3) Configuración para obtener "thoughts"
        generate_content_config = types.GenerateContentConfig(
            temperature=1.6,
            top_p=0.95,
            max_output_tokens=1000,
            response_modalities=["TEXT"],
            system_instruction=system_instruction,
            tools=tools, # <- Agregar si lo usas
            #thinking_config={"include_thoughts": False},  # <- Importante
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"
                ),
            ],
            
        )

        # 4) Llamada inicial al modelo
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        logger.info("Respuesta de GEMINI: %s", response)
        # Variables para almacenar datos
        chain_of_thought = ""
        assistant_response = ""
        function_calls = []

        # Ajuste para manejar el caso de candidate vacío:
        parts = []
        if response.candidates:
            candidate = response.candidates[0]
            # Verificamos si candidate.content no es None y tiene .parts
            if candidate.content and candidate.content.parts:
                parts = candidate.content.parts
            else:
                # Si está vacío o None, asignamos un "fallback"
                parts = [types.Part.from_text(".")]
        else:
            # Si no hay candidates, también asignamos el "fallback"
            parts = [types.Part.from_text(".")]

        for part in parts:
            # Si es "thought", lo guardamos en chain_of_thought
            if getattr(part, "thought", False):
                chain_of_thought += part.text or ""
            # Si hay una llamada a herramienta (function_call)
            elif part.function_call:
                function_calls.append(part.function_call)
                # Añade el "part" al historial si necesitas
                contents.append(types.Content(role="model", parts=[part]))
            else:
                # Resto: asumimos que es la respuesta final al usuario
                if part.text:
                    assistant_response += part.text

        # Guardar el razonamiento en la conversación
        conversations[thread_id]["razonamiento"] = chain_of_thought

        # 6) Manejar function calls si aparecen
        if function_calls:
            # Mapea nombres de funciones a tus funciones reales
            telefono = conversations.get(thread_id, {}).get("telefono")
            direccionCliente = conversations.get(thread_id, {}).get("direccionCliente")
            tool_functions = {
                "crear_pedido": crear_pedido,
                "crear_link_pago": crear_link_pago,
                "enviar_menu": enviar_menu,
                "crear_direccion": crear_direccion,
            }

            # Ejecutar cada call
            function_responses = []
            for func_call in function_calls:
                function_name = func_call.name
                function_args = func_call.args

                logger.info("Uso de herramienta: %s", function_name)
                logger.debug("Argumentos: %s", function_args)

                if function_name in tool_functions:
                    result = tool_functions[function_name](function_args, subscriber_id)
                    function_response_part = types.Part.from_function_response(
                        name=function_name, response=result
                    )
                    function_responses.append(
                        types.Content(role="function", parts=[function_response_part])
                    )
                else:
                    logger.warning("Herramienta desconocida: %s", function_name)

            # Agregar las respuestas de las funciones al historial y regenerar
            contents.extend(function_responses)
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=generate_content_config,
            )

            # Procesar la respuesta final
            assistant_response = ""
            for part in response.candidates[0].content.parts:
                if getattr(part, "thought", False):
                    # Agregar esos "thoughts" adicionales si siguió pensando
                    chain_of_thought += part.text or ""
                elif part.text:
                    assistant_response += part.text

            # Actualizar "razonamiento" con posibles pensamientos adicionales
            conversations[thread_id]["razonamiento"] = chain_of_thought

        # Agregar la respuesta final del asistente al historial
        assistant_message_content = {"type": "text", "text": assistant_response}
        if use_cache_control:
            assistant_message_content["cache_control"] = {"type": "ephemeral"}

        conversation_history.append(
            {"role": "assistant", "content": [assistant_message_content]}
        )

        # Actualizar la conversación
        conversations[thread_id]["messages"] = conversation_history
        conversations[thread_id]["response"] = assistant_response
        conversations[thread_id]["status"] = "completed"

        logger.info("Respuesta generada para thread_id: %s", thread_id)

    except Exception as e:
        logger.exception(
            "Error en generate_response_gemini para thread_id %s: %s", thread_id, e
        )
        conversations[thread_id]["response"] = f"Error:g {str(e)}"
        conversations[thread_id]["status"] = "error"
    finally:
        event.set()
        logger.debug("Evento establecido para thread_id: %s", thread_id)

def generate_response_deepseek(api_key, message, assistant_content_text,
                               thread_id, event, subscriber_id,
                               use_cache_control, modelId):
    logger.info("Generando respuesta (Deepseek) para thread_id: %s", thread_id)

    try:
        # Configuración de API Key
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("API key para DeepSeek no configurada")

        # Inicializar cliente
        client = OpenAI(
            api_key="sk-1ffe629918a242f9be0b281e506d2c03",
            base_url="https://api.deepseek.com",
        )

        # Obtener historial de conversación
        conversation_history = conversations[thread_id]["messages"]

        # Agregar system message si es necesario
        if not any(msg["role"] == "system"
                   for msg in conversation_history) and assistant_content_text:
            conversation_history.append({
                "role": "system",
                "content": assistant_content_text
            })

        # Agregar user message
        conversation_history.append({"role": "user", "content": message})

        # Cargar herramientas específicas para DeepSeek
        tools_file_path = os.path.join(os.path.dirname(__file__),
                                       'tools_deepseek.json')
        with open(tools_file_path, 'r', encoding='utf-8') as tools_file:
            tools = json.load(tools_file)
            logger.info(
                "Herramientas DeepSeek cargadas desde tools_deepseek.json")

        # Validar estructura de herramientas
        required_fields = ['type', 'function']
        for tool in tools:
            if not all(field in tool for field in required_fields):
                raise ValueError(
                    "Formato de herramienta inválido en tools_deepseek.json")
            if tool['type'] != 'function':
                raise ValueError("Tipo de herramienta no soportado")

        # Mapeo de funciones
        tool_functions = {
            "crear_pedido": crear_pedido,
            "crear_link_pago": crear_link_pago
        }

        max_loops = 3
        loop_counter = 0
        final_response = None

        while loop_counter < max_loops:
            loop_counter += 1

            # Configurar parámetros
            request_params = {
                #"model": "deepseek-reasoner",
                "model": "deepseek-chat",
                "messages": conversation_history,
                # "tools": tools,
                #"tool_choice": "auto",
                "max_tokens": 1024,
                "temperature": 0.7,
                "stream": False
            }

            try:
                response = client.chat.completions.create(**request_params)
                message_response = response.choices[0].message
                #logger.info("Respuesta inicial del modelo: %s", response)
                # Intentar obtener el reasoning_content
                reasoning_content = getattr(message_response, 'reasoning_content', '')
                conversations[thread_id]["razonamiento"] = reasoning_content

            except Exception as e:
                logger.error("Error en API Deepseek: %s", str(e))
                break

            # Manejar tool calls
            if message_response.tool_calls:
                conversation_history.append({
                    "role":
                    "assistant",
                    "content":
                    message_response.content,
                    "tool_calls":
                    message_response.tool_calls
                })

                for tool_call in message_response.tool_calls:
                    function_name = tool_call.function.name
                    try:
                        function_args = json.loads(
                            tool_call.function.arguments)
                    except json.JSONDecodeError:
                        function_args = {}
                        logger.error("Error decodificando argumentos JSON")

                    logger.info("Ejecutando herramienta: %s", function_name)

                    if function_name in tool_functions:
                        try:
                            tool_response = tool_functions[function_name](
                                function_args, subscriber_id)
                            content = str(
                                tool_response.get('result', tool_response))
                        except Exception as e:
                            content = f"Error: {str(e)}"
                            logger.exception("Error en herramienta")
                    else:
                        content = f"Error: Herramienta {function_name} no existe"
                        logger.warning(content)

                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": content
                    })
            else:
                final_response = message_response.content
                conversation_history.append({
                    "role": "assistant",
                    "content": final_response
                })
                break

        # Actualizar estado
        if final_response:
            conversations[thread_id].update({
                "response": final_response,
                "status": "completed",
                "messages": conversation_history
            })
        else:
            conversations[thread_id].update({
                "response": "Error: No se pudo generar respuesta válida",
                "status": "error"
            })

    except Exception as e:
        logger.exception("Error crítico en Deepseek: %s", str(e))
        conversations[thread_id].update({
            "response": f"Error: {str(e)}",
            "status": "error"
        })
    finally:
        event.set()


@app.route('/sendmensaje', methods=['POST'])
def send_message():
    logger.info("Endpoint /sendmensaje llamado")
    data = request.json

    # Extraer parámetros principales
    api_key = data.get('api_key')
    message = data.get('message')
    assistant_value = data.get('assistant')
    thread_id = data.get('thread_id')
    subscriber_id = data.get('subscriber_id')
    thinking = data.get('thinking', 0)
    modelID = data.get('modelID', '').lower()
    telefono = data.get('telefono')
    direccionCliente = data.get('direccionCliente')
    use_cache_control = data.get('use_cache_control', False)

    # Extraer variables adicionales para sustitución
    variables = data.copy()
    keys_to_remove = [
        'api_key', 'message', 'assistant', 'thread_id', 'subscriber_id',
        'thinking', 'modelID',  'direccionCliente',
        'use_cache_control'
    ]
    for key in keys_to_remove:
        variables.pop(key, None)

    # Validaciones obligatorias
    if not message:
        logger.warning("Mensaje vacío recibido")
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    if not subscriber_id:
        logger.warning("Falta subscriber_id")
        return jsonify({"error": "Falta el subscriber_id"}), 400

    # Configuración especial para Deepseek
    if modelID == 'deepsee':
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            logger.error("API key de DeepSeek no configurada")
            return jsonify({"error":
                            "Configuración del servidor incompleta"}), 500

    # Generar o validar thread_id
    if not thread_id or not thread_id.startswith('thread_'):
        thread_id = f"thread_{uuid.uuid4()}"
        logger.info("Nuevo thread_id generado: %s", thread_id)

    # Cargar contenido del asistente
    assistant_content = ""
    if assistant_value is not None:
        assistant_file = ASSISTANT_FILES.get(assistant_value)
        if assistant_file:
            try:
                assistant_path = os.path.join(os.path.dirname(__file__),
                                              assistant_file)
                with open(assistant_path, 'r', encoding='utf-8') as file:
                    assistant_content = file.read()

                    # Sustitución de variables
                    pattern = re.compile(r'\{\{(\w+)\}\}')

                    def replace_placeholder(match):
                        key = match.group(1)
                        return str(variables.get(key,  "[UNDEFINED]"))

                    assistant_content = pattern.sub(replace_placeholder,
                                                    assistant_content)

                logger.info("Archivo de asistente cargado: %s", assistant_file)
            except Exception as e:
                logger.error("Error cargando archivo de asistente: %s", str(e))
                return jsonify(
                    {"error": f"Error al cargar el asistente: {str(e)}"}), 500

    # Inicializar/Mantener conversación
    if thread_id not in conversations:
        conversations[thread_id] = {
            "status": "processing",
            "response": None,
            "messages": [],
            "assistant": assistant_value,
            "thinking": thinking,
            "telefono": telefono,
            "direccionCliente": direccionCliente,
            "usage": None
        }
        logger.info("Nueva conversación creada para thread_id: %s", thread_id)
    else:
        conversations[thread_id].update({
            "assistant":
            assistant_value or conversations[thread_id]["assistant"],
            "thinking":
            thinking,
            "telefono":
            telefono,
            "direccionCliente":
            direccionCliente
        })

    # Crear y ejecutar hilo según el modelo
    event = Event()

    try:
        if modelID == 'deepseek':
            thread = Thread(target=generate_response_deepseek,
                            args=(api_key, message, assistant_content,
                                  thread_id, event, subscriber_id,
                                  use_cache_control,
                                  data.get('modelId', 'deepseek-chat')))
            logger.info("Ejecutando Deepseek para thread_id: %s", thread_id)

        elif modelID == 'gemini':
            thread = Thread(target=generate_response_gemini,
                            args=(api_key, message, assistant_content,
                                  thread_id, event, subscriber_id,
                                  use_cache_control))
            logger.info("Ejecutando Gemini para thread_id: %s", thread_id)

        else:  # Default to Anthropic
            thread = Thread(target=generate_response,
                            args=(api_key, message, assistant_content,
                                  thread_id, event, subscriber_id,
                                  use_cache_control))
            logger.info("Ejecutando Anthropic para thread_id: %s", thread_id)

        thread.start()
        event.wait(timeout=30)

        # Preparar respuesta final
        response_data = {
            "thread_id": thread_id,
            "usage": conversations[thread_id].get("usage")
        }

        if conversations[thread_id]["status"] == "completed":
            original_response = conversations[thread_id]["response"]

            # Manejar bloque thinking si está activado
            if conversations[thread_id]["thinking"] == 1:
                response_data["response"] = remove_thinking_block(
                    original_response)
            else:
                response_data["response"] = original_response

            # <-- Aquí agregamos la razón (si existe)
            response_data["razonamiento"] = conversations[thread_id].get("razonamiento", "")


        else:
            response_data["response"] = "Procesando..."

        return jsonify(response_data)

    except Exception as e:
        logger.exception("Error crítico en el endpoint: %s", str(e))
        return jsonify({
            "error": "Error interno del servidor",
            "details": str(e)
        }), 500


@app.route('/status', methods=['POST'])
def check_status():
    logger.info("Endpoint /status llamado")
    data = request.json
    thread_id = data.get('thread_id')

    if thread_id not in conversations:
        logger.warning("Thread_id no encontrado: %s", thread_id)
        return jsonify({"response": "Thread no encontrado"}), 404

    start_time = time.time()
    while time.time() - start_time < 8:
        status = conversations[thread_id]["status"]
        if status == "completed":
            logger.info("Estado completed para thread_id: %s", thread_id)
            # Obtener la respuesta original
            original_response = conversations[thread_id].get("response", "")
            # Obtener el valor de 'thinking'
            current_thinking = conversations[thread_id].get("thinking", 0)
            if current_thinking == 1:
                # Limpiar la respuesta eliminando el bloque <thinking>
                cleaned_response = remove_thinking_block(original_response)
            else:
                # No limpiar la respuesta
                cleaned_response = original_response

            return jsonify({
                "response": cleaned_response,
                "usage": conversations[thread_id].get("usage")
            })
        elif status == "error":
            logger.error("Estado error para thread_id: %s, mensaje: %s",
                         thread_id, conversations[thread_id]['response'])
            # Obtener el mensaje de error original
            original_error = conversations[thread_id].get(
                'response', 'Error desconocido')
            # Obtener el valor de 'thinking'
            current_thinking = conversations[thread_id].get("thinking", 0)
            if current_thinking == 1:
                # Limpiar el mensaje de error eliminando el bloque <thinking>
                cleaned_error = remove_thinking_block(original_error)
            else:
                # No limpiar el mensaje de error
                cleaned_error = original_error

            return jsonify({"response": f"Error: {cleaned_error}"})
        time.sleep(0.5)

    logger.info("Run_id en espera tras timeout para thread_id: %s", thread_id)
    return jsonify({"response": "run_id en espera"})


@app.route('/extract', methods=['POST'])
def extract():
    logger.info("Endpoint /extract llamado")
    try:
        # Verificar si el body contiene un JSON bien formateado
        if not request.is_json:
            error_result = {
                "status": "error",
                "message":
                "El body de la solicitud no está en formato JSON válido"
            }
            logger.warning("Solicitud no es JSON válida")
            return jsonify(error_result), 400

        # Obtener los datos JSON de la solicitud
        data = request.get_json()

        # Extraer los campos específicos directamente del body
        nombre = data.get('nombre', '')
        apellido = data.get('apellido', '')
        cedula = data.get('cedula', '')
        ciudad = data.get('ciudad', '')
        solicitud = data.get('solicitud', '')
        contactar = data.get('contactar', '')

        # Crear el resultado en el formato deseado
        result = {
            "nombre": nombre,
            "apellido": apellido,
            "cedula": cedula,
            "ciudad": ciudad,
            "solicitud": solicitud,
            "contactar": contactar,
            "status": "success"
        }

        logger.info("Datos extraídos correctamente: %s", result)
        return jsonify(result)

    except Exception as e:
        # Manejar cualquier error que pueda ocurrir
        error_result = {"status": "error", "message": str(e)}
        logger.exception("Error en /extract: %s", e)
        return jsonify(error_result), 400


@app.route('/letranombre', methods=['POST'])
def letra_nombre():
    # Obtener los datos JSON de la solicitud
    data = request.json
    name = data.get('text', '').strip()  # Eliminar espacios en blanco

    if not name:
        return jsonify({'error': 'No se proporcionó texto'}), 400

    # Extraer la primera letra y convertirla a mayúscula
    first_letter = name[0].upper()

    # Definir resoluciones
    resoluciones = [1920, 1024, 512, 256, 128]
    imagenes = {}

    # Generar SVG para cada resolución
    for resolucion in resoluciones:
        base64_img, svg_code = create_svg_base64(first_letter, resolucion,
                                                 resolucion)
        imagenes[f'avatar_{resolucion}'] = {
            'base64': base64_img,
            'svg': svg_code
        }

    # Devolver las imágenes en formato JSON
    return jsonify(imagenes)


@app.route('/time', methods=['POST'])
def convert_time():
    logger.info("Endpoint /time llamado")
    data = request.json
    input_time = data.get('datetime')

    if not input_time:
        logger.warning("Falta el parámetro 'datetime'")
        return jsonify({"error": "Falta el parámetro 'datetime'"}), 400

    try:
        local_time = datetime.fromisoformat(input_time)
        utc_time = local_time.astimezone(pytz.utc)
        new_time = utc_time + timedelta(hours=1)
        new_time_str = new_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        result = {"original": input_time, "converted": new_time_str}
        logger.info("Tiempo convertido: %s", result)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error al convertir el tiempo: %s", e)
        return jsonify({"error": str(e)}), 400


# Agrega el nuevo endpoint /upload
@app.route('/upload', methods=['POST'])
def upload_file():
    logger.info("Endpoint /upload llamado")
    data = request.json
    url = data.get('url')
    is_shared = data.get('is_shared',
                         True)  # Por defecto, true si no se proporciona
    targetable_id = data.get('targetable_id')
    targetable_type = data.get('targetable_type')
    name = data.get('name', 'file')  # Nombre por defecto si no se proporciona

    # Verificar que los parámetros necesarios estén presentes
    if not url or not targetable_id or not targetable_type:
        logger.warning("Faltan parámetros requeridos en /upload")
        return jsonify({
            "error":
            "Faltan parámetros requeridos (url, targetable_id, targetable_type)"
        }), 400

    # Descargar el archivo desde la URL
    logger.info("Descargando archivo desde URL: %s", url)
    response = requests.get(url)
    if response.status_code == 200:
        file_content = response.content
        logger.info("Archivo descargado exitosamente")
    else:
        logger.error(
            "No se pudo descargar el archivo desde la URL, status_code: %s",
            response.status_code)
        return jsonify({
            "error": "No se pudo descargar el archivo desde la URL",
            "status_code": response.status_code
        }), 400

    # Obtener la clave API y la URL base de Freshsales desde variables de entorno
    FRESHSALES_API_KEY = os.environ.get('FRESHSALES_API_KEY',
                                        "TU_FRESHSALES_API_KEY_AQUI")
    FRESHSALES_BASE_URL = os.environ.get(
        'FRESHSALES_BASE_URL', 'https://tu_dominio.myfreshworks.com')

    if not FRESHSALES_API_KEY:
        logger.error("Falta la clave API de Freshsales")
        return jsonify({"error": "Falta la clave API de Freshsales"}), 500

    headers = {'Authorization': f'Token token={FRESHSALES_API_KEY}'}

    # Asegurar que is_shared sea una cadena 'true' o 'false'
    is_shared_str = 'true' if is_shared else 'false'

    data_payload = {
        'file_name': name,
        'is_shared': is_shared_str,
        'targetable_id': str(targetable_id),
        'targetable_type': targetable_type
    }
    logger.debug("Payload para upload: %s", data_payload)

    # Obtener el tipo de contenido del archivo
    content_type = response.headers.get('Content-Type',
                                        'application/octet-stream')

    files = {'file': (name, file_content, content_type)}

    upload_url = FRESHSALES_BASE_URL + '/crm/sales/documents'
    logger.info("Subiendo archivo a Freshsales en URL: %s", upload_url)

    upload_response = requests.post(upload_url,
                                    headers=headers,
                                    data=data_payload,
                                    files=files)
    logger.info("Respuesta de subida: %s %s", upload_response.status_code,
                upload_response.text)

    try:
        response_json = upload_response.json()
        logger.debug("Respuesta JSON de subida: %s", response_json)
    except ValueError:
        response_json = None
        logger.warning("No se pudo parsear la respuesta de subida como JSON")

    if upload_response.status_code in (200, 201):
        # Subida exitosa
        logger.info("Archivo subido exitosamente a Freshsales")
        return jsonify({
            "message": "Archivo subido exitosamente",
            "response": response_json
        }), upload_response.status_code
    else:
        # Error en la subida
        logger.error("Error al subir el archivo a Freshsales: %s",
                     response_json or upload_response.text)
        return jsonify({
            "error": "No se pudo subir el archivo",
            "details": response_json or upload_response.text
        }), upload_response.status_code


@app.route('/crearactividad', methods=['POST'])
def crear_actividad():
    try:
        # Obtener los datos del cuerpo de la solicitud
        datos = request.get_json()
        if not datos:
            return jsonify(
                {'error':
                 'El cuerpo de la solicitud debe ser JSON válido.'}), 400

        # Extraer credenciales y parámetros de actividad
        url = datos.get('url')  # URL de la instancia de Odoo
        db = datos.get('db')  # Nombre de la base de datos
        username = datos.get('username')
        password = datos.get('password')

        # Datos de la actividad
        res_model = datos.get('res_model', 'crm.lead')
        res_id = datos.get('res_id')
        activity_type_id = datos.get('activity_type_id')
        summary = datos.get('summary')
        note = datos.get('note')
        date_deadline = datos.get('date_deadline')
        user_id = datos.get('user_id')

        # Verificar que todos los campos obligatorios están presentes
        campos_obligatorios = [
            url, db, username, password, res_id, activity_type_id, summary,
            date_deadline
        ]
        if not all(campos_obligatorios):
            return jsonify(
                {'error': 'Faltan campos obligatorios en la solicitud.'}), 400

        # Autenticación con Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return jsonify(
                {'error':
                 'Autenticación fallida. Verifica tus credenciales.'}), 401

        # Conexión con el modelo
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

        # Obtener res_model_id si es necesario
        res_model_id = datos.get('res_model_id')
        if not res_model_id:
            res_model_data = models.execute_kw(db, uid, password, 'ir.model',
                                               'search_read',
                                               [[['model', '=', res_model]]],
                                               {'fields': ['id']})
            if res_model_data:
                res_model_id = res_model_data[0]['id']
            else:
                return jsonify({
                    'error':
                    f"No se encontró el modelo '{res_model}' en Odoo."
                }), 400

        # Preparar datos de la actividad
        datos_actividad = {
            'res_model_id': res_model_id,
            'res_id': res_id,
            'activity_type_id': activity_type_id,
            'summary': summary,
            'note': note or '',
            'date_deadline': date_deadline,
            'user_id': user_id or uid,
        }

        # Crear la actividad
        actividad_id = models.execute_kw(db, uid, password, 'mail.activity',
                                         'create', [datos_actividad])

        return jsonify({'mensaje':
                        f'Actividad creada con ID: {actividad_id}'}), 200

    except xmlrpc.client.Fault as fault:
        return jsonify({'error':
                        f"Error al comunicarse con Odoo: {fault}"}), 500
    except Exception as e:
        return jsonify({'error': f"Ocurrió un error: {e}"}), 500


@app.route('/crearevento', methods=['POST'])
def crear_evento():
    try:
        # Obtener los datos del cuerpo de la solicitud
        datos = request.get_json()
        if not datos:
            return jsonify(
                {'error':
                 'El cuerpo de la solicitud debe ser JSON válido.'}), 400

        # Extraer credenciales y parámetros del evento
        url = datos.get('url')
        db = datos.get('db')
        username = datos.get('username')
        password = datos.get('password')

        # Datos del evento
        name = datos.get('name')  # Nombre del evento
        start = datos.get('start')  # Fecha y hora de inicio
        stop = datos.get('stop')  # Fecha y hora de fin
        duration = datos.get('duration')
        description = datos.get('description')
        user_id = datos.get('user_id')

        # Campos opcionales
        allday = datos.get('allday', False)  # Evento de todo el día (opcional)
        partner_ids = datos.get('partner_ids',
                                [])  # Lista de IDs de partners (opcional)
        location = datos.get('location', '')

        # Verificar que todos los campos obligatorios están presentes
        campos_obligatorios = [
            url, db, username, password, name, start, duration
        ]
        if not all(campos_obligatorios):
            return jsonify(
                {'error': 'Faltan campos obligatorios en la solicitud.'}), 400

        # Autenticación con Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return jsonify(
                {'error':
                 'Autenticación fallida. Verifica tus credenciales.'}), 401

        # Conexión con el modelo
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

        # Preparar datos del evento
        datos_evento = {
            'name': name,
            'start': start,
            'duration': duration,
            'description': description or '',
            'user_id': user_id or uid,
            'allday': allday,
            'partner_ids': [(6, 0, partner_ids)],
            'location': location
        }

        if stop:
            datos_evento['stop'] = stop
        else:
            datos_evento['stop'] = (
                datetime.fromisoformat(start) +
                timedelta(hours=float(duration))).isoformat()

        # Crear el evento en el calendario
        evento_id = models.execute_kw(db, uid, password, 'calendar.event',
                                      'create', [datos_evento])

        return jsonify({
            'mensaje': f'Evento creado con ID: {evento_id}',
            'id': evento_id
        }), 200

    except xmlrpc.client.Fault as fault:
        return jsonify({'error':
                        f"Error al comunicarse con Odoo: {fault}"}), 500
    except Exception as e:
        return jsonify({'error': f"Ocurrió un error: {e}"}), 500


@app.route('/leeractividades', methods=['POST'])
def leer_actividades():
    try:
        # Obtener los datos del cuerpo de la solicitud
        datos = request.get_json()
        if not datos:
            return jsonify(
                {'error':
                 'El cuerpo de la solicitud debe ser JSON válido.'}), 400

        # Extraer credenciales y parámetros necesarios
        url = datos.get('url')  # URL de la instancia de Odoo
        db = datos.get('db')  # Nombre de la base de datos
        username = datos.get('username')
        password = datos.get('password')
        res_id = datos.get('res_id')  # ID de la oportunidad (lead) a consultar

        # Verificar que todos los campos obligatorios están presentes
        campos_obligatorios = [url, db, username, password, res_id]
        if not all(campos_obligatorios):
            return jsonify(
                {'error': 'Faltan campos obligatorios en la solicitud.'}), 400

        # Autenticación con Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return jsonify(
                {'error':
                 'Autenticación fallida. Verifica tus credenciales.'}), 401

        # Conexión con los modelos de Odoo
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

        # Verificar que el lead existe
        lead_exists = models.execute_kw(db, uid, password, 'crm.lead',
                                        'search', [[['id', '=', res_id]]])
        if not lead_exists:
            return jsonify(
                {'error': f"No se encontró el lead con ID {res_id}."}), 404

        # Obtener información del lead
        opportunity_data = models.execute_kw(db, uid, password, 'crm.lead',
                                             'read', [res_id])

        if opportunity_data and isinstance(opportunity_data, list):
            opportunity_data = opportunity_data[0]

        # Obtener los IDs de las actividades asociadas
        activity_ids = opportunity_data.get('activity_ids', [])

        # Inicializar variables para la descripción, el asesor y la etapa
        descripcion_oportunidad = ""
        asesor = "N/A"
        etapa = "N/A"

        # Obtener y procesar la descripción de la oportunidad
        description_html = opportunity_data.get('description', '')
        if description_html:
            # Convertir HTML a texto plano usando BeautifulSoup
            soup = BeautifulSoup(description_html, 'html.parser')
            descripcion_oportunidad = soup.get_text(separator='\n').strip()

        # Obtener el nombre del asesor desde 'create_uid'
        create_uid = opportunity_data.get('create_uid', [0, 'N/A'])
        if isinstance(create_uid, list) and len(create_uid) >= 2:
            asesor = create_uid[1]
        else:
            asesor = "N/A"

        # Obtener la etapa desde 'stage_id'
        stage_id = opportunity_data.get('stage_id', [0, 'N/A'])
        if isinstance(stage_id, list) and len(stage_id) >= 2:
            etapa = stage_id[1]
        else:
            etapa = "N/A"

        # Verificar si hay actividades asociadas
        if activity_ids:
            # Especificar los campos que deseas obtener de cada actividad
            campos_actividades = [
                'create_date', 'summary', 'note', 'date_deadline'
            ]

            # Obtener información de las actividades con campos específicos
            activities_data = models.execute_kw(db, uid, password,
                                                'mail.activity', 'read',
                                                [activity_ids],
                                                {'fields': campos_actividades})

            # Procesar las actividades para consolidarlas en una sola cadena de texto
            actividades_texto = ""
            for actividad in activities_data:
                fecha_creada = actividad.get('create_date', 'N/A')
                descripcion = actividad.get('summary', 'N/A')
                nota = actividad.get('note', 'N/A')
                fecha_vencimiento = actividad.get('date_deadline', 'N/A')

                # Formatear la información de cada actividad
                actividad_formateada = (
                    f"Fecha Creada: {fecha_creada}\n"
                    f"Descripción: {descripcion}\n"
                    f"Nota: {nota}\n"
                    f"Fecha Vencimiento Actividad: {fecha_vencimiento}\n"
                    f"{'-'*40}\n")
                actividades_texto += actividad_formateada

            # Crear el diccionario final con todas las actividades, descripción, asesor y etapa
            resultado_final = {
                "actividades":
                actividades_texto.strip(),  # Eliminar el último salto de línea
                "descrpcion_oportunidad": descripcion_oportunidad,
                "asesor": asesor,
                "etapa": etapa
            }

            return jsonify(resultado_final), 200
        else:
            # No hay actividades asociadas
            resultado_final = {
                "actividades": "",
                "descrpcion_oportunidad": descripcion_oportunidad,
                "asesor": asesor,
                "etapa": etapa
            }
            return jsonify(resultado_final), 200

    except xmlrpc.client.Fault as fault:
        return jsonify({'error':
                        f"Error al comunicarse con Odoo: {fault}"}), 500
    except Exception as e:
        return jsonify({'error': f"Ocurrió un error: {e}"}), 500


@app.route('/linkpago', methods=['GET'])
def linkpago():
    logger.info("Endpoint /linkpago llamado")

    # Extraer los parámetros de la query
    pedido_id = request.args.get('id')
    telefono = request.args.get('telefono')
    link = request.args.get('link')
    forma = request.args.get('forma')

    logger.info(
        f"Parámetros recibidos - ID: {pedido_id}, Telefono: {telefono}, Link: {link}, Forma: {forma}"
    )

    # Validar que todos los parámetros estén presentes
    if not all([pedido_id, telefono, link, forma]):
        logger.warning("Faltan uno o más parámetros requeridos en /linkpago")
        return jsonify({
            "error":
            "Faltan uno o más parámetros requeridos: id, telefono, link, forma"
        }), 400

    # Preparar los datos para enviar al webhook de n8n
    data = {
        "id": pedido_id,
        "telefono": telefono,
        "link": link,
        "forma": forma
    }

    logger.info(f"Enviando datos al webhook de n8n: {data}")

    try:
        # Realizar la solicitud POST al webhook de n8n
        response = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        response.raise_for_status(
        )  # Lanza una excepción si la respuesta fue un error HTTP

        logger.info(
            f"Webhook de n8n respondió con status {response.status_code}: {response.text}"
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Error al enviar datos al webhook de n8n: {e}")
        return jsonify({
            "error":
            "No se pudo procesar el pago. Inténtalo de nuevo más tarde."
        }), 500

    # Construir la URL de redirección a Wompi
    wompi_url = f"https://checkout.wompi.co/l/{link}"
    logger.info(f"Redireccionando al usuario a: {wompi_url}")

    # Redireccionar al usuario a la URL de Wompi
    return redirect(wompi_url, code=302)


if __name__ == '__main__':
    logger.info("Iniciando la aplicación Flask")
    app.run(host='0.0.0.0', port=8080)
