import json
import openai
import requests
import threading
import random
import google.genai as genai
from google.genai import types
import base64
import os
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
# Sistema de reintentos para llamadas a API
# Sistema de reintentos para API de Anthropic
import time
from functools import wraps

def retry_on_exception(max_retries=3, initial_wait=1):
    """Reintenta llamadas a la API con backoff exponencial."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    wait_time = initial_wait * (2 ** retries)
                    if retries >= max_retries:
                        logger.error(f"Error definitivo tras {max_retries} intentos: {e}")
                        raise
                    logger.warning(f"Error en llamada a API (intento {retries}). Reintentando en {wait_time}s: {e}")
                    time.sleep(wait_time)
        return wrapper
    return decorator

@retry_on_exception(max_retries=3, initial_wait=1)
def call_anthropic_api(client, **kwargs):
    """Llama a la API de Anthropic con reintentos automáticos."""
    return client.messages.create(**kwargs)
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
    'https://n8niass.cocinandosonrisas.co/webhook/eleccionFormaPagoDarkBurgerApi')

# Mapa para asociar valores de 'assistant' con nombres de archivos
ASSISTANT_FILES = {
    0: "PROMPTS/DARK BURGER/2_ASISTENTE_INICIAL_DB.txt",
    1: 'PROMPTS/DARK BURGER/2_ASISTENTE_DOMICILIO_DB.txt',
    2: 'PROMPTS/DARK BURGER/2_ASISTENTE_RECOGER_DB.txt',
    3: 'PROMPTS/DARK BURGER/2_ASISTENTE_FORMA_PAGO_DB.txt',
    4: 'PROMPTS/DARK BURGER/2_ASISTENTE_POSTVENTA_DOMICILIO_DB.txt',
    5: "PROMPTS/DARK BURGER/2_ASISTENTE_POSTVENTA_RECOGER_DB.txt"
}

conversations = {}


class N8nAPI:

    def __init__(self):
        self.crear_pedido_webhook_url = os.environ.get("N8N_CREAR_PEDIDO_WEBHOOK_URL")
        self.link_pago_webhook_url = os.environ.get("N8N_LINK_PAGO_WEBHOOK_URL")
        self.enviar_menu_webhook_url = os.environ.get("N8N_ENVIAR_MENU_WEBHOOK_URL")
        self.crear_direccion_webhook_url =os.environ.get("N8N_CREAR_DIRECCION_WEBHOOK_URL")
        self.eleccion_forma_pago_url =os.environ.get("N8N_ELECCION_FORMA_PAGO_WEBHOOK_URL")
        self.facturacion_electronica_url =os.environ.get("N8N_FACTURACION_ELECTRONICA_WEBHOOK_URL")
        self.pqrs_url =os.environ.get("N8N_PQRS_WEBHOOK_URL")
        # Puedes añadir más URLs de webhook si lo necesitas
        logger.info("Inicializado N8nAPI con las URLs")

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
        logger.debug("Enviando datos de enviar menu a n8n con payload: %s",
                     payload)
        response = requests.post(self.enviar_menu_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos de enviar_menu: %s %s",
                    response.status_code, response.text)
        return response

    def crear_direccion(self, payload):
        """Envía los datos para generar el link de pago al webhook de n8n"""
        logger.debug("Enviando datos para crear direccion a n8n con payload: %s",
                     payload)
        response = requests.post(self.crear_direccion_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos crear direccion: %s %s",
                    response.status_code, response.text)
        return response

    def eleccion_forma_pago(self, payload):
        """Envía los datos para registrar la forma de pago al webhook de n8n"""
        logger.debug("Enviando datos para eleccion forma de pago a n8n con payload: %s",
                     payload)
        response = requests.post( self.eleccion_forma_pago_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos eleccion_forma_pago: %s %s",
                    response.status_code, response.text)
        return response

    def facturacion_electronica(self, payload):
        """Envía los datos para registrar facturacion electronica al webhook de n8n"""
        logger.debug("Enviando datos para facturacion electronica a n8n con payload: %s",
                     payload)
        response = requests.post( self.facturacion_electronica_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos facturacion_electronica: %s %s",
                    response.status_code, response.text)
        return response

    def pqrs(self, payload):
        """Envía los datos para registrar pqrs al webhook de n8n"""
        logger.debug("Enviando datos para pqrs a n8n con payload: %s",
                     payload)
        response = requests.post( self.pqrs_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos pqrs: %s %s",
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
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'Operación exitosa.')
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
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'LInk de pago generado exitosamente')

        logger.info("crear_link_pago result: %s", result)
        return result  # Retornamos el resultado al modelo

    except Exception as e:
        logger.exception("Error en crear_link_pago: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}


def enviar_menu(tool_input, subscriber_id):
    """
    Función para enviar los datos del pedido al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando enviar_menu con datos: %s", tool_input)
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
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'MENU Operación exitosa.')

        logger.info("enviar_menu result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en enviar_menu: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}

def crear_direccion(tool_input, subscriber_id ):
    """
    Función para enviar los datos del pedido al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando crear_direccion con datos: %s", tool_input)
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
        response = n8n_api.crear_direccion(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'Operación exitosa.')

        logger.info("enviar_menu result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en enviar_menu: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}

def eleccion_forma_pago(tool_input, subscriber_id ):
    """
    Función para enviar los datos de la froma de pago al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando eleccion_forma_pago con datos: %s", tool_input)
    logger.debug("subscriber_id en eleccion_forma_pago: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {
            
                "tool_code": "eleccion_forma_pago",
                "id": subscriber_id,
                "forma": tool_input  # Datos provenientes del LLM
            
        }


        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.eleccion_forma_pago(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'Eleccion FPG Operación exitosa.')

        logger.info("eleccion_forma_pagoresult: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en enviar_menu: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}

def facturacion_electronica(tool_input, subscriber_id ):
    """
    Función para enviar los datos de la facturacion electronica al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando facturacion_electronica con datos: %s", tool_input)
    logger.debug("subscriber_id en facturacion_electronica: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {

                "tool_code": "facturacion_electronica",
                "id": subscriber_id,
                "datos": tool_input  # Datos provenientes del LLM

        }


        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.facturacion_electronica(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'Fact Elect Operación exitosa.')

        logger.info("facturacion_electronica result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en facturacion electronica: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}

def pqrs(tool_input, subscriber_id ):
    """
    Función para enviar los datos de la pqrs al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando pqrs con datos: %s", tool_input)
    logger.debug("subscriber_id en pqrs: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {

                "tool_code": "pqrs",
                "id": subscriber_id,
                "datos": tool_input  # Datos provenientes del LLM

        }


        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.pqrs(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s", response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json() if 'application/json' in response.headers.get('Content-Type', '') else {"message": response.text}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'Operación exitosa.')

        logger.info("pqrs result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en pqrs: %s", e)
        return {"error": f"Error al procesar la solicitud: {str(e)}"}
        
def validate_conversation_history(history):
    """Valida que la estructura del historial sea correcta para Anthropic."""
    if not isinstance(history, list):
        logger.error("El historial no es una lista")
        return False

    for message in history:
        # Validar estructura básica del mensaje
        if not isinstance(message, dict):
            logger.error("Mensaje no es un diccionario: %s", message)
            return False

        if "role" not in message or message["role"] not in ["user", "assistant"]:
            logger.error("Rol inválido en mensaje: %s", message)
            return False

        if "content" not in message:
            logger.error("Falta contenido en mensaje: %s", message)
            return False

    return True

# Versión mejorada de get_field
def get_field(item, key):
    """Obtiene un campo de un objeto o diccionario de forma segura."""
    if item is None:
        return None

    if isinstance(item, dict):
        return item.get(key)

    try:
        return getattr(item, key, None)
    except Exception as e:
        logger.warning("Error al acceder a atributo %s: %s", key, e)
        return None

# Función auxiliar para acceder a un campo, ya sea en un diccionario o en un objeto
#def get_field(item, key):
    #if isinstance(item, dict):
        #return item.get(key)
    #return getattr(item, key, None)


thread_locks = {}


def generate_response(
    api_key,
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    use_cache_control,
    llmID=None
    ):
    if not llmID:
        llmID = "claude-3-5-haiku-latest"

    logger.info("Intentando adquirir lock para thread_id: %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error("No se encontró lock para thread_id: %s", thread_id)
        thread_locks[thread_id] = threading.Lock()
        lock = thread_locks[thread_id]

    with lock:
        logger.info("Lock adquirido para thread_id: %s", thread_id)
        start_time = time.time()

        try:
            # Registrar la hora de última actividad para limpieza
            conversations[thread_id]["last_activity"] = time.time()

            client = anthropic.Anthropic(api_key=api_key)
            conversation_history = conversations[thread_id]["messages"]

            # Agregar el mensaje del usuario al historial
            user_message_content = {"type": "text", "text": message}
            if use_cache_control:
                user_message_content["cache_control"] = {"type": "ephemeral"}
            conversation_history.append({
                "role": "user",
                "content": [user_message_content]
            })

            # Cargar herramientas
            assistant_value = conversations[thread_id].get("assistant")
            assistant_str = str(assistant_value)
            if assistant_str in ["0"]:
                tools_file_name = "tools_stage0.json"
            elif assistant_str in ["1", "2"]:
                tools_file_name = "tools_stage1.json"
            elif assistant_str in ["3"]:
                tools_file_name = "tools_stage2.json"
            elif assistant_str in ["4", "5"]:
                tools_file_name = "tools_stage3.json"
            else:
                tools_file_name = "default_tools.json"

            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools = json.load(tools_file)

            # Configurar sistema
            assistant_content = [{"type": "text", "text": assistant_content_text}]

            # Mapear herramientas a funciones
            tool_functions = {
                "crear_pedido": crear_pedido,
                "crear_link_pago": crear_link_pago,
                "enviar_menu": enviar_menu,
                "crear_direccion": crear_direccion,
                "eleccion_forma_pago": eleccion_forma_pago,
                "facturacion_electronica": facturacion_electronica,
                "pqrs": pqrs,
            }

            # Iniciar interacción con el modelo
            while True:
                # Validar estructura de mensajes antes de enviar
                if not validate_conversation_history(conversation_history):
                    logger.error("Estructura de mensajes inválida: %s", conversation_history)
                    raise ValueError("Estructura de conversación inválida")

                try:
                    logger.info("PAYLOAD ANTHROPIC: %s", conversation_history)
                    # Llamar a la API con reintentos
                    logger.info("Llamando a Anthropic API para thread_id: %s", thread_id)
                    response = call_anthropic_api(
                        client=client,
                        model=llmID,
                        max_tokens=1000,
                        temperature=0.8,
                        system=assistant_content,
                        tools=tools,
                        messages=conversation_history
                    )
                    logger.info("RESPUESTA RAW ANTHROPIC: %s", response)
                    # Procesar respuesta
                    conversation_history.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    # Almacenar tokens
                    usage = {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
                        "cache_read_input_tokens": response.usage.cache_read_input_tokens,
                    }
                    conversations[thread_id]["usage"] = usage

                    logger.info(
                        "Tokens utilizados - Input: %d, Output: %d",
                        usage["input_tokens"],
                        usage["output_tokens"]
                    )
                    logger.info("Cache Creation Input Tokens: %d", 
                                usage["cache_creation_input_tokens"])
                    logger.info("Cache Read Input Tokens: %d", 
                                usage["cache_read_input_tokens"])

                    # Procesar herramientas
                    if response.stop_reason == "tool_use":
                        tool_use_blocks = [block for block in response.content if get_field(block, "type") == "tool_use"]

                        if not tool_use_blocks:
                            # Si no hay herramientas, procesamos la respuesta final
                            assistant_response_text = ""
                            for content_block in response.content:
                                if get_field(content_block, "type") == "text":
                                    assistant_response_text += (get_field(content_block, "text") or "")
                            conversations[thread_id]["response"] = assistant_response_text
                            conversations[thread_id]["status"] = "completed"
                            break

                        # Procesar herramienta
                        tool_use = tool_use_blocks[0]
                        tool_name = get_field(tool_use, "name")
                        tool_input = get_field(tool_use, "input")

                        if tool_name in tool_functions:
                            result = tool_functions[tool_name](tool_input, subscriber_id)
                            result_json = json.dumps(result)

                            # Agregar resultado
                            conversation_history.append({
                                "role": "user",
                                "content": [{
                                    "type": "tool_result",
                                    "tool_use_id": get_field(tool_use, "id"),
                                    "content": result_json,
                                }],
                            })
                        else:
                            logger.warning("Herramienta desconocida: %s", tool_name)
                            break
                    else:
                        # Respuesta final
                        assistant_response_text = ""
                        for content_block in response.content:
                            if get_field(content_block, "type") == "text":
                                assistant_response_text += (get_field(content_block, "text") or "")
                        conversations[thread_id]["response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        break

                except Exception as api_error:
                    logger.exception("Error en llamada a API para thread_id %s: %s", thread_id, api_error)
                    conversations[thread_id]["response"] = f"Error de comunicación: {str(api_error)}"
                    conversations[thread_id]["status"] = "error"
                    break

        except Exception as e:
            logger.exception("Error en generate_response para thread_id %s: %s", thread_id, e)
            conversations[thread_id]["response"] = f"Error: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            elapsed_time = time.time() - start_time
            logger.info("Generación completada en %.2f segundos para thread_id: %s", elapsed_time, thread_id)
            # El lock se libera automáticamente al salir del bloque 'with'


def generate_response_openai(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    llmID=None
):
    if not llmID:
        llmID = "gpt-4o-mini"

    logger.info("Intentando adquirir lock para thread_id (OpenAI): %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error(
            "No se encontró lock para thread_id (OpenAI): %s. Esto no debería ocurrir.",
            thread_id)
        return

    with lock:
        logger.info("Lock adquirido para thread_id (OpenAI): %s", thread_id)
        logger.info("Generando respuesta para thread_id (OpenAI): %s", thread_id)
        logger.debug("subscriber_id en generate_response_openai: %s", subscriber_id)

        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.error("API key de OpenAI no configurada en Replit Secrets")
                raise Exception("API key de OpenAI no configurada")

            # Inicializar cliente con la nueva importación
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            conversation_history = conversations[thread_id]["messages"]

            # Agregar el mensaje del usuario al historial de conversación
            user_message = {"role": "user", "content": message}
            conversation_history.append(user_message)
            logger.debug("Historial de conversación actualizado (OpenAI): %s", conversation_history)

            # Cargar herramientas
            assistant_value = conversations[thread_id].get("assistant")
            assistant_str = str(assistant_value)
            if assistant_str in ["0"]:
                tools_file_name = "tools_stage0.json"
            elif assistant_str in ["1", "2"]:
                tools_file_name = "tools_stage1.json"
            elif assistant_str in ["3"]:
                tools_file_name = "tools_stage2.json"
            elif assistant_str in ["4", "5"]:
                tools_file_name = "tools_stage3.json"
            else:
                tools_file_name = "default_tools.json"

            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools = json.load(tools_file)

            # Cargar el archivo de herramientas correspondiente
            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools_anthropic_format = json.load(tools_file)
            logger.info("Herramientas cargadas desde %s", tools_file_name)

            # Convertir herramientas al formato de OpenAI Function Calling
            tools_openai_format = []
            for tool in tools_anthropic_format:
                openai_tool = {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
                tools_openai_format.append(openai_tool)
            tools = tools_openai_format

            # Mapear nombres de herramientas a funciones
            tool_functions = {
                "crear_pedido": crear_pedido,
                "crear_link_pago": crear_link_pago,
                "enviar_menu": enviar_menu,
                "crear_direccion": crear_direccion,
                "eleccion_forma_pago": eleccion_forma_pago,
                "facturacion_electronica": facturacion_electronica,
                "pqrs": pqrs,
            }

            # Preparar los mensajes para la nueva API
            input_messages = []

            # Agregar mensaje del sistema
            #input_messages.append({
             #   "role": "system",
             #   "content": [{"type": "input_text", "text": assistant_content_text}]
           # })

            # Agregar mensajes de la conversación
            for msg in conversation_history:
                if msg["role"] == "user":
                    input_messages.append({
                        "role": "user",
                        "content": [{"type": "input_text", "text": msg["content"]}]
                    })
                elif msg["role"] == "assistant":
                    input_messages.append({
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": msg["content"]}]
                    })
                # Ignorar mensajes tool por ahora

            # Variable para seguir track de llamadas a herramientas
            call_counter = 0
            max_iterations = 5  # Límite de iteraciones para evitar bucles infinitos

            while call_counter < max_iterations:
                try:
                    # Llamar a la API en el nuevo formato

                    logger.info("PAYLOAD OPENAI: %s", input_messages)

                    response = client.responses.create(
                        model="gpt-4o",
                        instructions=assistant_content_text,
                        input=input_messages,
                        tools=tools,
                        temperature=0.9,
                        max_output_tokens=1000,
                        top_p=1,
                        store=True
                    )

                    # Imprimir la estructura completa para debug
                    logger.info("RESPUESTA RAW OPENAI: %s", response)

                    # Extraer y almacenar información de tokens
                    if hasattr(response, 'usage'):
                        usage = {
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "cache_creation_input_tokens": 0,  # Valor predeterminado
                            "cache_read_input_tokens": response.usage.total_tokens,  # Según lo solicitado
                        }

                        # Si hay detalles adicionales de tokens, actualizar cache_creation_input_tokens
                        if (hasattr(response.usage, 'input_tokens_details') and 
                            hasattr(response.usage.input_tokens_details, 'cached_tokens')):
                            usage["cache_creation_input_tokens"] = response.usage.input_tokens_details.cached_tokens

                        conversations[thread_id]["usage"] = usage

                        logger.info(
                            "Tokens utilizados - Input: %d, Output: %d",
                            usage["input_tokens"],
                            usage["output_tokens"]
                        )
                        logger.info("Cache Creation Input Tokens: %d", 
                                    usage["cache_creation_input_tokens"])
                        logger.info("Cache Read Input Tokens: %d", 
                                    usage["cache_read_input_tokens"])

                    # Variables para rastrear el tipo de respuesta
                    assistant_response_text = None
                    function_called = False

                    # Procesar la respuesta
                    if hasattr(response, 'output') and response.output:
                        # Caso 1: La respuesta es un texto normal (ejemplo del primer log)
                        for output_item in response.output:
                            if hasattr(output_item, 'type'):
                                # Es un objeto (no un diccionario)
                                if output_item.type == 'message' and hasattr(output_item, 'content'):
                                    for content_item in output_item.content:
                                        if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                            assistant_response_text = content_item.text
                                            logger.info("Respuesta de texto encontrada: %s", assistant_response_text)
                                            break

                                # Caso 2: La respuesta es una llamada a función (ejemplo del último log)
                                elif output_item.type == 'function_call':
                                    function_called = True
                                    tool_name = output_item.name
                                    tool_arguments_str = output_item.arguments
                                    call_id = output_item.call_id if hasattr(output_item, 'call_id') else f"call_{call_counter}"

                                    logger.info("Llamada a función detectada: %s con ID %s", tool_name, call_id)
                                    logger.info("Argumentos: %s", tool_arguments_str)

                                    try:
                                        tool_arguments = json.loads(tool_arguments_str)
                                    except json.JSONDecodeError:
                                        tool_arguments = {}

                                    if tool_name in tool_functions:
                                        # Ejecutar la función
                                        result = tool_functions[tool_name](tool_arguments, subscriber_id)
                                        result_str = str(result)
                                        logger.info("Resultado de la llamada a función: %s", result_str)

                                        # Agregar la llamada a la función y el resultado al historial
                                        assistant_message = {
                                            "role": "assistant",
                                            "content": f"Función llamada: {tool_name}"
                                        }
                                        tool_message = {
                                            "role": "tool",
                                            "tool_call_id": call_id,
                                            "name": tool_name,
                                            "content": result_str
                                        }
                                        conversation_history.append(assistant_message)
                                        conversation_history.append(tool_message)

                                        # Preparar entrada para la siguiente iteración incluyendo el resultado
                                        input_messages.append({
                                            "type": "function_call",
                                            "call_id": call_id,
                                            "name": tool_name,
                                            "arguments": tool_arguments_str
                                        })

                                        input_messages.append({
                                            "type": "function_call_output",
                                            "call_id": call_id,
                                            "output": result_str
                                        })
                                        logger.info("PAYLOAD OPENAI USO HERRAMIENTA: %s", input_messages)
                                        # Solicitar continuación de la conversación después de la llamada a la función
                                        continue_response = client.responses.create(
                                            model="gpt-4o",
                                            instructions=assistant_content_text,
                                            input=input_messages,
                                            tools=tools,
                                            temperature=0.7,
                                            max_output_tokens=1000,
                                            top_p=1,
                                            store=True
                                        )

                                        logger.info("RESPUESTA RAW OPENAI DESPUES DE HERRAMIENTA: %s", continue_response)

                                        # Actualizar información de tokens con la respuesta continua
                                        if hasattr(continue_response, 'usage'):
                                            if not conversations[thread_id].get("usage"):
                                                conversations[thread_id]["usage"] = {
                                                    "input_tokens": 0,
                                                    "output_tokens": 0,
                                                    "cache_creation_input_tokens": 0,
                                                    "cache_read_input_tokens": 0
                                                }

                                            # Actualizar los tokens acumulativos
                                            current_usage = conversations[thread_id]["usage"]
                                            current_usage["input_tokens"] += continue_response.usage.input_tokens
                                            current_usage["output_tokens"] += continue_response.usage.output_tokens

                                            # Actualizar cache_read_input_tokens con total_tokens
                                            current_usage["cache_read_input_tokens"] += continue_response.usage.total_tokens

                                            # Actualizar cache_creation_input_tokens si está disponible
                                            if (hasattr(continue_response.usage, 'input_tokens_details') and 
                                                hasattr(continue_response.usage.input_tokens_details, 'cached_tokens')):
                                                current_usage["cache_creation_input_tokens"] += continue_response.usage.input_tokens_details.cached_tokens

                                            logger.info(
                                                "Tokens acumulados - Input: %d, Output: %d",
                                                current_usage["input_tokens"],
                                                current_usage["output_tokens"]
                                            )
                                            logger.info("Cache Creation Input Tokens acumulados: %d", 
                                                        current_usage["cache_creation_input_tokens"])
                                            logger.info("Cache Read Input Tokens acumulados: %d", 
                                                        current_usage["cache_read_input_tokens"])

                                        # Procesar la respuesta de continuación
                                        if hasattr(continue_response, 'output') and continue_response.output:
                                            for continue_item in continue_response.output:
                                                if hasattr(continue_item, 'type') and continue_item.type == 'message':
                                                    if hasattr(continue_item, 'content'):
                                                        for content_item in continue_item.content:
                                                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                                                assistant_response_text = content_item.text
                                                                logger.info("Respuesta de texto después de la función: %s", assistant_response_text)
                                                                break

                                        # Si obtuvimos una respuesta de texto, guardémosla
                                        if assistant_response_text:
                                            conversations[thread_id]["response"] = assistant_response_text
                                            conversations[thread_id]["status"] = "completed"
                                            conversation_history.append({
                                                "role": "assistant",
                                                "content": assistant_response_text
                                            })
                                        else:
                                            # Si no obtuvimos respuesta, usemos un mensaje genérico
                                            assistant_response_text = f"He enviado el menú para la sede La Virginia. ¿En qué más puedo ayudarte?"
                                            conversations[thread_id]["response"] = assistant_response_text
                                            conversations[thread_id]["status"] = "completed"
                                            conversation_history.append({
                                                "role": "assistant",
                                                "content": assistant_response_text
                                            })

                                        # Incrementar contador y salir
                                        call_counter += 1
                                        break
                                    else:
                                        logger.warning("Herramienta desconocida: %s", tool_name)
                                        break

                    # Si encontramos un texto de respuesta y no hubo llamada a función, estamos listos
                    if assistant_response_text and not function_called:
                        conversations[thread_id]["response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        conversation_history.append({
                            "role": "assistant",
                            "content": assistant_response_text
                        })
                        break

                    # Si no encontramos ni texto ni llamada a función, algo salió mal
                    if not assistant_response_text and not function_called:
                        # Intentar una última extracción con un método diferente
                        # A veces, la función está directamente en response.output (no dentro de un loop)
                        if hasattr(response, 'output') and isinstance(response.output, list) and len(response.output) > 0:
                            first_output = response.output[0]
                            if hasattr(first_output, 'type') and first_output.type == 'function_call':
                                function_called = True
                                tool_name = first_output.name
                                tool_arguments_str = first_output.arguments
                                call_id = first_output.call_id if hasattr(first_output, 'call_id') else f"call_{call_counter}"

                                logger.info("Llamada a función detectada (método alternativo): %s", tool_name)

                                try:
                                    tool_arguments = json.loads(tool_arguments_str)
                                except json.JSONDecodeError:
                                    tool_arguments = {}

                                if tool_name in tool_functions:
                                    # Ejecutar la función
                                    result = tool_functions[tool_name](tool_arguments, subscriber_id)
                                    result_str = str(result)
                                    logger.info("Resultado de la llamada a función: %s", result_str)

                                    # Mensaje genérico después de ejecutar la función
                                    assistant_response_text = f"He enviado el menú para la sede La Virginia. ¿En qué más puedo ayudarte?"
                                    conversations[thread_id]["response"] = assistant_response_text
                                    conversations[thread_id]["status"] = "completed"

                                    # Agregar mensajes al historial
                                    assistant_message = {
                                        "role": "assistant",
                                        "content": f"Función llamada: {tool_name}"
                                    }
                                    tool_message = {
                                        "role": "tool",
                                        "tool_call_id": call_id,
                                        "name": tool_name,
                                        "content": result_str
                                    }
                                    final_message = {
                                        "role": "assistant",
                                        "content": assistant_response_text
                                    }

                                    conversation_history.append(assistant_message)
                                    conversation_history.append(tool_message)
                                    conversation_history.append(final_message)

                                    break

                        # Si aún no hemos encontrado respuesta, reportar error
                        if not assistant_response_text and not function_called:
                            logger.warning("No se encontró respuesta ni llamada a función en la respuesta de la API")
                            conversations[thread_id]["response"] = "Lo siento, no pude procesar tu solicitud en este momento."
                            conversations[thread_id]["status"] = "error"
                            break

                except Exception as api_error:
                    logger.exception("Error en la llamada a la API: %s", api_error)
                    conversations[thread_id]["response"] = f"Error en la API de OpenAI: {str(api_error)}"
                    conversations[thread_id]["status"] = "error"
                    break

        except Exception as e:
            logger.exception("Error en generate_response_openai para thread_id %s: %s", thread_id, e)
            conversations[thread_id]["response"] = f"Error OpenAI: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            logger.debug("Evento establecido para thread_id (OpenAI): %s", thread_id)
            logger.info("Liberando lock para thread_id (OpenAI): %s", thread_id)

def generate_response_openai_o3(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    llmID=None
):
    if not llmID:
        llmID = "low"

    logger.info("Intentando adquirir lock para thread_id (OpenAI): %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error(
            "No se encontró lock para thread_id (OpenAI): %s. Esto no debería ocurrir.",
            thread_id)
        return

    with lock:
        logger.info("Lock adquirido para thread_id (OpenAI): %s", thread_id)
        logger.info("Generando respuesta para thread_id (OpenAI): %s", thread_id)
        logger.debug("subscriber_id en generate_response_openai: %s", subscriber_id)

        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.error("API key de OpenAI no configurada en Replit Secrets")
                raise Exception("API key de OpenAI no configurada")

            # Inicializar cliente con la nueva importación
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            conversation_history = conversations[thread_id]["messages"]

            # Agregar el mensaje del usuario al historial de conversación
            user_message = {"role": "user", "content": message}
            conversation_history.append(user_message)
            logger.debug("Historial de conversación actualizado (OpenAI): %s", conversation_history)

            # Cargar herramientas
            assistant_value = conversations[thread_id].get("assistant")
            assistant_str = str(assistant_value)
            if assistant_str in ["0"]:
                tools_file_name = "tools_stage0.json"
            elif assistant_str in ["1", "2"]:
                tools_file_name = "tools_stage1.json"
            elif assistant_str in ["3"]:
                tools_file_name = "tools_stage2.json"
            elif assistant_str in ["4", "5"]:
                tools_file_name = "tools_stage3.json"
            else:
                tools_file_name = "default_tools.json"

            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools = json.load(tools_file)

            # Cargar el archivo de herramientas correspondiente
            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools_anthropic_format = json.load(tools_file)
            logger.info("Herramientas cargadas desde %s", tools_file_name)

            # Convertir herramientas al formato de OpenAI Function Calling
            tools_openai_format = []
            for tool in tools_anthropic_format:
                openai_tool = {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
                tools_openai_format.append(openai_tool)
            tools = tools_openai_format

            # Mapear nombres de herramientas a funciones
            tool_functions = {
                "crear_pedido": crear_pedido,
                "crear_link_pago": crear_link_pago,
                "enviar_menu": enviar_menu,
                "crear_direccion": crear_direccion,
                "eleccion_forma_pago": eleccion_forma_pago,
                "facturacion_electronica": facturacion_electronica,
                "pqrs": pqrs,
            }

            # Preparar los mensajes para la nueva API
            input_messages = []

            # Agregar mensaje del sistema
            #input_messages.append({
               # "role": "system",
               # "content": [{"type": "input_text", "text": assistant_content_text}]
            #})

            # Agregar mensajes de la conversación
            for msg in conversation_history:
                if msg["role"] == "user":
                    input_messages.append({
                        "role": "user",
                        "content": [{"type": "input_text", "text": msg["content"]}]
                    })
                elif msg["role"] == "assistant":
                    input_messages.append({
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": msg["content"]}]
                    })
                # Ignorar mensajes tool por ahora

            # Variable para seguir track de llamadas a herramientas
            call_counter = 0
            max_iterations = 5  # Límite de iteraciones para evitar bucles infinitos

            while call_counter < max_iterations:
                try:
                    # Llamar a la API en el nuevo formato

                    logger.info("PAYLOAD OPENAI: %s", input_messages)

                    response = client.responses.create(
                        model="o3-mini",
                        instructions=assistant_content_text,
                        input=input_messages,
                        tools=tools,
                         reasoning={
                            "effort": llmID},
                        top_p=1,
                        store=True
                    )

                    # Imprimir la estructura completa para debug
                    logger.info("RESPUESTA RAW OPENAI: %s", response)

                    # Extraer y almacenar información de tokens
                    if hasattr(response, 'usage'):
                        usage = {
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "cache_creation_input_tokens": 0,  # Valor predeterminado
                            "cache_read_input_tokens": response.usage.total_tokens,  # Según lo solicitado
                        }

                        # Si hay detalles adicionales de tokens, actualizar cache_creation_input_tokens
                        if (hasattr(response.usage, 'input_tokens_details') and 
                            hasattr(response.usage.input_tokens_details, 'cached_tokens')):
                            usage["cache_creation_input_tokens"] = response.usage.input_tokens_details.cached_tokens

                        conversations[thread_id]["usage"] = usage

                        logger.info(
                            "Tokens utilizados - Input: %d, Output: %d",
                            usage["input_tokens"],
                            usage["output_tokens"]
                        )
                        logger.info("Cache Creation Input Tokens: %d", 
                                    usage["cache_creation_input_tokens"])
                        logger.info("Cache Read Input Tokens: %d", 
                                    usage["cache_read_input_tokens"])

                    # Variables para rastrear el tipo de respuesta
                    assistant_response_text = None
                    function_called = False

                    # Procesar la respuesta
                    if hasattr(response, 'output') and response.output:
                        # Caso 1: La respuesta es un texto normal (ejemplo del primer log)
                        for output_item in response.output:
                            if hasattr(output_item, 'type'):
                                # Es un objeto (no un diccionario)
                                if output_item.type == 'message' and hasattr(output_item, 'content'):
                                    for content_item in output_item.content:
                                        if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                            assistant_response_text = content_item.text
                                            logger.info("Respuesta de texto encontrada: %s", assistant_response_text)
                                            break

                                # Caso 2: La respuesta es una llamada a función (ejemplo del último log)
                                elif output_item.type == 'function_call':
                                    function_called = True
                                    tool_name = output_item.name
                                    tool_arguments_str = output_item.arguments
                                    call_id = output_item.call_id if hasattr(output_item, 'call_id') else f"call_{call_counter}"

                                    logger.info("Llamada a función detectada: %s con ID %s", tool_name, call_id)
                                    logger.info("Argumentos: %s", tool_arguments_str)

                                    try:
                                        tool_arguments = json.loads(tool_arguments_str)
                                    except json.JSONDecodeError:
                                        tool_arguments = {}

                                    if tool_name in tool_functions:
                                        # Ejecutar la función
                                        result = tool_functions[tool_name](tool_arguments, subscriber_id)
                                        result_str = str(result)
                                        logger.info("Resultado de la llamada a función: %s", result_str)

                                        # Agregar la llamada a la función y el resultado al historial
                                        assistant_message = {
                                            "role": "assistant",
                                            "content": f"Función llamada: {tool_name}"
                                        }
                                        tool_message = {
                                            "role": "tool",
                                            "tool_call_id": call_id,
                                            "name": tool_name,
                                            "content": result_str
                                        }
                                        conversation_history.append(assistant_message)
                                        conversation_history.append(tool_message)

                                        # Preparar entrada para la siguiente iteración incluyendo el resultado
                                        input_messages.append({
                                            "type": "function_call",
                                            "call_id": call_id,
                                            "name": tool_name,
                                            "arguments": tool_arguments_str
                                        })

                                        input_messages.append({
                                            "type": "function_call_output",
                                            "call_id": call_id,
                                            "output": result_str
                                        })

                                        # Solicitar continuación de la conversación después de la llamada a la función
                                        continue_response = client.responses.create(
                                            model="o3-mini",
                                            instructions=assistant_content_text,
                                            input=input_messages,
                                            tools=tools,
                                            reasoning={
                                                "effort": llmID},
                                            top_p=1,
                                            store=True
                                        )

                                        logger.info("Respuesta después de la llamada a la función: %s", vars(continue_response))

                                        # Actualizar información de tokens con la respuesta continua
                                        if hasattr(continue_response, 'usage'):
                                            if not conversations[thread_id].get("usage"):
                                                conversations[thread_id]["usage"] = {
                                                    "input_tokens": 0,
                                                    "output_tokens": 0,
                                                    "cache_creation_input_tokens": 0,
                                                    "cache_read_input_tokens": 0
                                                }

                                            # Actualizar los tokens acumulativos
                                            current_usage = conversations[thread_id]["usage"]
                                            current_usage["input_tokens"] += continue_response.usage.input_tokens
                                            current_usage["output_tokens"] += continue_response.usage.output_tokens

                                            # Actualizar cache_read_input_tokens con total_tokens
                                            current_usage["cache_read_input_tokens"] += continue_response.usage.total_tokens

                                            # Actualizar cache_creation_input_tokens si está disponible
                                            if (hasattr(continue_response.usage, 'input_tokens_details') and 
                                                hasattr(continue_response.usage.input_tokens_details, 'cached_tokens')):
                                                current_usage["cache_creation_input_tokens"] += continue_response.usage.input_tokens_details.cached_tokens

                                            logger.info(
                                                "Tokens acumulados - Input: %d, Output: %d",
                                                current_usage["input_tokens"],
                                                current_usage["output_tokens"]
                                            )
                                            logger.info("Cache Creation Input Tokens acumulados: %d", 
                                                        current_usage["cache_creation_input_tokens"])
                                            logger.info("Cache Read Input Tokens acumulados: %d", 
                                                        current_usage["cache_read_input_tokens"])

                                        # Procesar la respuesta de continuación
                                        if hasattr(continue_response, 'output') and continue_response.output:
                                            for continue_item in continue_response.output:
                                                if hasattr(continue_item, 'type') and continue_item.type == 'message':
                                                    if hasattr(continue_item, 'content'):
                                                        for content_item in continue_item.content:
                                                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                                                assistant_response_text = content_item.text
                                                                logger.info("Respuesta de texto después de la función: %s", assistant_response_text)
                                                                break

                                        # Si obtuvimos una respuesta de texto, guardémosla
                                        if assistant_response_text:
                                            conversations[thread_id]["response"] = assistant_response_text
                                            conversations[thread_id]["status"] = "completed"
                                            conversation_history.append({
                                                "role": "assistant",
                                                "content": assistant_response_text
                                            })
                                        else:
                                            # Si no obtuvimos respuesta, usemos un mensaje genérico
                                            assistant_response_text = f"He enviado el menú para la sede La Virginia. ¿En qué más puedo ayudarte?"
                                            conversations[thread_id]["response"] = assistant_response_text
                                            conversations[thread_id]["status"] = "completed"
                                            conversation_history.append({
                                                "role": "assistant",
                                                "content": assistant_response_text
                                            })

                                        # Incrementar contador y salir
                                        call_counter += 1
                                        break
                                    else:
                                        logger.warning("Herramienta desconocida: %s", tool_name)
                                        break

                    # Si encontramos un texto de respuesta y no hubo llamada a función, estamos listos
                    if assistant_response_text and not function_called:
                        conversations[thread_id]["response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        conversation_history.append({
                            "role": "assistant",
                            "content": assistant_response_text
                        })
                        break

                    # Si no encontramos ni texto ni llamada a función, algo salió mal
                    if not assistant_response_text and not function_called:
                        # Intentar una última extracción con un método diferente
                        # A veces, la función está directamente en response.output (no dentro de un loop)
                        if hasattr(response, 'output') and isinstance(response.output, list) and len(response.output) > 0:
                            first_output = response.output[0]
                            if hasattr(first_output, 'type') and first_output.type == 'function_call':
                                function_called = True
                                tool_name = first_output.name
                                tool_arguments_str = first_output.arguments
                                call_id = first_output.call_id if hasattr(first_output, 'call_id') else f"call_{call_counter}"

                                logger.info("Llamada a función detectada (método alternativo): %s", tool_name)

                                try:
                                    tool_arguments = json.loads(tool_arguments_str)
                                except json.JSONDecodeError:
                                    tool_arguments = {}

                                if tool_name in tool_functions:
                                    # Ejecutar la función
                                    result = tool_functions[tool_name](tool_arguments, subscriber_id)
                                    result_str = str(result)
                                    logger.info("Resultado de la llamada a función: %s", result_str)

                                    # Mensaje genérico después de ejecutar la función
                                    assistant_response_text = f"He enviado el menú para la sede La Virginia. ¿En qué más puedo ayudarte?"
                                    conversations[thread_id]["response"] = assistant_response_text
                                    conversations[thread_id]["status"] = "completed"

                                    # Agregar mensajes al historial
                                    assistant_message = {
                                        "role": "assistant",
                                        "content": f"Función llamada: {tool_name}"
                                    }
                                    tool_message = {
                                        "role": "tool",
                                        "tool_call_id": call_id,
                                        "name": tool_name,
                                        "content": result_str
                                    }
                                    final_message = {
                                        "role": "assistant",
                                        "content": assistant_response_text
                                    }

                                    conversation_history.append(assistant_message)
                                    conversation_history.append(tool_message)
                                    conversation_history.append(final_message)

                                    break

                        # Si aún no hemos encontrado respuesta, reportar error
                        if not assistant_response_text and not function_called:
                            logger.warning("No se encontró respuesta ni llamada a función en la respuesta de la API")
                            conversations[thread_id]["response"] = "Lo siento, no pude procesar tu solicitud en este momento."
                            conversations[thread_id]["status"] = "error"
                            break

                except Exception as api_error:
                    logger.exception("Error en la llamada a la API: %s", api_error)
                    conversations[thread_id]["response"] = f"Error en la API de OpenAI: {str(api_error)}"
                    conversations[thread_id]["status"] = "error"
                    break

        except Exception as e:
            logger.exception("Error en generate_response_openai para thread_id %s: %s", thread_id, e)
            conversations[thread_id]["response"] = f"Error OpenAI: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            logger.debug("Evento establecido para thread_id (OpenAI): %s", thread_id)
            logger.info("Liberando lock para thread_id (OpenAI): %s", thread_id)


def generate_response_gemini(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
):
    logger.info("Intentando adquirir lock para thread_id (Gemini): %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error(
            "No se encontró lock para thread_id (Gemini): %s. Esto no debería ocurrir.",
            thread_id)
        return

    with lock:
        logger.info("Lock adquirido para thread_id (Gemini): %s", thread_id)
        logger.info("Generando respuesta para thread_id (Gemini): %s", thread_id)
        logger.debug("subscriber_id en generate_response_gemini: %s", subscriber_id)

        try:

            api_key = os.environ["GEMINI_API_KEY"]
            # Initialize Gemini client - CORRECTED LINE HERE
            client = genai.Client(api_key=api_key,
                                 http_options=types.HttpOptions(api_version='v1alpha'))

            conversation_history = conversations[thread_id]["messages"]

            # Add user message to conversation history
            user_message = {"role": "user", "parts": [types.Part.from_text(text=message)]}
            conversation_history.append(user_message)
            logger.info("HIATORIQL CONVERSACION GEMINI: %s", conversation_history)

            assistant_value = conversations[thread_id].get("assistant")
            assistant_str = str(assistant_value)
            if assistant_str in ["0"]:
                tools_file_name = "tools_stage0_gemini.json"
            elif assistant_str in ["1", "2"]:
                tools_file_name = "tools_stage1_gemini.json"
            elif assistant_str == "3":
                tools_file_name = "tools_stage2_gemini.json"
            elif assistant_str in ["4", "5"]:
                tools_file_name = "tools_stage3_gemini.json"
            else:
                tools_file_name = "default_tools.json"

            # Cargar el archivo de herramientas correspondiente
            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools_anthropic_format = json.load(tools_file)

            logger.info("Herramientas cargadas desde %s (Gemini)", tools_file_name)

            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools_anthropic_format = json.load(tools_file)
            logger.info("Herramientas cargadas desde %s", tools_file_name)

            # Si tu JSON de tool pone "input_schema" en vez de "parameters", ajusta aquí
            #schema = t.get("parameters") or t.get("input_schema")
            # Convert tools to Gemini format
            tools_gemini_format = []
            for tool in tools_anthropic_format:
                gemini_tool = types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=tool["name"],
                            description=tool["description"],
                            parameters=types.Schema(
                                type=tool["parameters"]["type"], # Use type from schema (OBJECT, STRING)
                                properties=tool["parameters"]["properties"],
                                required=tool["parameters"]["required"] if "required" in tool["parameters"] else []
                            )
                        )
                    ]
                )
                tools_gemini_format.append(gemini_tool)
            tools = tools_gemini_format

            # Tool functions mapping (reusing same functions)
            tool_functions = {
                "crear_pedido": crear_pedido,
                "crear_link_pago": crear_link_pago,
                "enviar_menu": enviar_menu,
                "crear_direccion": crear_direccion,
                "eleccion_forma_pago": eleccion_forma_pago,
                "facturacion_electronica": facturacion_electronica,
                "pqrs": pqrs,
            }

            # System instruction for Gemini
            system_instruction = types.GenerateContentConfig(system_instruction=assistant_content_text)


            # Start interaction with Gemini
            messages_for_gemini = conversation_history # Gemini handles conversation history internally in chat object, but we are managing history ourselves.
            while True:
                logger.info("PAYLOAD GEMINI: %s", messages_for_gemini)

                # Generate content with tools
                response_gemini = client.models.generate_content( 
                    contents=messages_for_gemini,
                    model="gemini-2.5-pro-exp-03-25",
                    config=types.GenerateContentConfig(
                        tools=tools,
                        system_instruction=assistant_content_text,
                        temperature=0.9,
                        max_output_tokens=1000,
                    ),
                )
                logger.info("RESPUESTA RAW GEMINI: %s", response_gemini)

                # Capturar información de tokens
                if response_gemini.usage_metadata:
                    # Capturar información de tokens según el mapeo solicitado
                    usage = {
                        "input_tokens": response_gemini.usage_metadata.total_token_count,
                        "output_tokens": response_gemini.usage_metadata.candidates_token_count,
                        "cache_creation_input_tokens": response_gemini.usage_metadata.prompt_token_count,
                        "cache_read_input_tokens": 0,  # Establecido a 0 como solicitado
                    }

                    # Almacenar en la conversación
                    conversations[thread_id]["usage"] = usage

                    # Registrar en logs
                    logger.info(
                        "Tokens utilizados - Input: %d, Output: %d",
                        usage["input_tokens"],
                        usage["output_tokens"]
                    )
                    logger.info("Cache Creation Input Tokens: %d", 
                                usage["cache_creation_input_tokens"])
                    logger.info("Cache Read Input Tokens: %d", 
                                usage["cache_read_input_tokens"])

                if response_gemini.candidates and response_gemini.candidates[0].content.parts:
                    response_content = response_gemini.candidates[0].content

                    # Check for function calls in the response
                    function_call_part = None
                    for part in response_content.parts:
                        if part.function_call:
                            function_call_part = part.function_call
                            break

                    if function_call_part:
                        logger.info("Respuesta con function_call detectada (Gemini): %s", function_call_part)

                        tool_name = function_call_part.name
                        tool_arguments = function_call_part.args


                        logger.info("Llamando a la herramienta (Gemini): %s", tool_name)
                        logger.info("Argumentos de la herramienta (Gemini): %s", tool_arguments)

                        if tool_name in tool_functions:
                            result = tool_functions[tool_name](tool_arguments, subscriber_id) # Call tool function
                            logger.debug("Resultado de la herramienta %s (Gemini): %s", tool_name, result)
                            result_json = json.dumps(result)
                            logger.info("Resultado de la herramienta %s (Gemini): %s", tool_name, result_json)

                            # Add function response to history
                            function_response_part = types.Part.from_function_response(
                                name=tool_name,
                                response={"result": result_json} # Gemini expects result to be in a dict
                            )
                            function_response_content = types.Content(role="tool", parts=[function_response_part])

                            conversation_history.append({"role": "model", "parts": response_content.parts}) # Append assistant message with function call
                            conversation_history.append(function_response_content) # Append tool response

                            messages_for_gemini = conversation_history # Update messages for next turn

                            logger.info("Mensaje function_response enviado a Gemini (Gemini): %s", function_response_content)


                        else:
                            logger.warning("Herramienta desconocida (Gemini): %s", tool_name)
                            break # Exit loop if unknown tool

                    else:
                        # No function call, process text response
                        assistant_response_text = ""
                        for part in response_content.parts:
                            if part.text:
                                assistant_response_text += part.text
                        conversations[thread_id]["response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        logger.info("Respuesta generada para thread_id (Gemini): %s", thread_id)

                        conversation_history.append({"role": "model", "parts": response_content.parts}) # Append assistant message to history
                        break # Exit loop for final text response
                else:
                    conversations[thread_id]["response"] = "Respuesta vacía del modelo Gemini"
                    conversations[thread_id]["status"] = "error"
                    logger.warning("Respuesta vacía del modelo Gemini para thread_id: %s", thread_id)
                    break


        except Exception as e:
            logger.exception("Error en generate_response_gemini para thread_id %s: %s", thread_id, e)
            conversations[thread_id]["response"] = f"Error Gemini: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            logger.debug("Evento establecido para thread_id (Gemini): %s", thread_id)
            logger.info("Liberando lock para thread_id (Gemini): %s", thread_id)
            # Lock is automatically released when exiting 'with' block

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
    llmID = data.get('llmID')

    logger.info("MENSAJE CLIENTE: %s", message)
    # Extraer variables adicionales para sustitución
    variables = data.copy()
    keys_to_remove = [
        'api_key', 'message', 'assistant', 'thread_id', 'subscriber_id',
        'thinking', 'modelID', 'direccionCliente', 'use_cache_control'
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
    if modelID == 'deepseek':
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
                        return str(variables.get(key, "[UNDEFINED]"))

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
            "usage": None,
            "last_activity": time.time()  # Timestamp para limpieza
        }
        logger.info("Nueva conversación creada: %s", thread_id)
    else:
        conversations[thread_id].update({
            "assistant": assistant_value or conversations[thread_id]["assistant"],
            "thinking": thinking,
            "telefono": telefono,
            "direccionCliente": direccionCliente,
            "last_activity": time.time()  # Actualizar timestamp
        })

    # --- Asegurar que haya un lock para este thread_id ---
    if thread_id not in thread_locks:
        thread_locks[thread_id] = threading.Lock()
        logger.info("Lock creado para thread_id: %s", thread_id)

    # Crear y ejecutar hilo según el modelo
    event = Event()

    try:
        if modelID == 'llm2':
            thread = Thread(target=generate_response_openai_o3,
                           args=(message, assistant_content,
                                thread_id, event, subscriber_id, llmID))
            logger.info("Ejecutando LLM2 para thread_id: %s", thread_id)

        elif modelID == 'gemini':
            thread = Thread(target=generate_response_gemini,
                            args=(message, assistant_content,
                                  thread_id, event, subscriber_id))
            logger.info("Ejecutando Gemini para thread_id: %s", thread_id)

        elif modelID == 'llm':
            thread = Thread(target=generate_response_openai,
                            args=(message, assistant_content,
                                  thread_id, event, subscriber_id, llmID))
            logger.info("Ejecutando LLM para thread_id: %s", thread_id)

        else:  # Default to Anthropic
            thread = Thread(target=generate_response,
                            args=(api_key, message, assistant_content,
                                  thread_id, event, subscriber_id,
                                  use_cache_control, llmID))
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
            response_data["razonamiento"] = conversations[thread_id].get(
                "razonamiento", "")

        else:
            response_data["response"] = "Procesando..."

        return jsonify(response_data)

    except Exception as e:
        logger.exception("Error crítico en el endpoint: %s", str(e))
        return jsonify({
            "error": "Error interno del servidor",
            "details": str(e)
        }), 500



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
        "forma": {
            "forma": forma
        }
    }

    logger.info(f"Enviando datos al webhook de n8n: {data}")

    try:
        # Realizar la solicitud POST al webhook de n8n
        response = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        response.raise_for_status()  # Lanza una excepción si la respuesta fue un error HTTP

        logger.info(
            f"Webhook de n8n respondió con status {response.status_code}: {response.text}"
        )

        # NUEVO: Envío al webhook adicional
        # Obtener la URL del nuevo webhook desde variables de entorno
        nuevo_webhook_url = os.environ.get('WEBHOOK_URL_NUEVO_LINK')

        if nuevo_webhook_url:
            # Preparar datos específicos para el nuevo webhook
            nuevo_data = {
                "pedido_id": pedido_id,
                "telefono": telefono,
                "formato": forma,
                "link": link
            }

            logger.info(f"Enviando datos al nuevo webhook de n8n: {nuevo_data}")

            # Realizar la solicitud POST al nuevo webhook
            try:
                nuevo_response = requests.post(nuevo_webhook_url, json=nuevo_data, timeout=10)
                nuevo_response.raise_for_status()

                logger.info(
                    f"Nuevo webhook respondió con status {nuevo_response.status_code}: {nuevo_response.text}"
                )
            except requests.exceptions.RequestException as e_nuevo:
                logger.error(f"Error al enviar datos al nuevo webhook: {e_nuevo}")
                # Continuamos con el flujo normal aunque falle esta solicitud
        else:
            logger.warning("WEBHOOK_URL_NUEVO_LINK no está definido en el archivo .env")

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

def cleanup_inactive_conversations():
    """Limpia conversaciones inactivas después de 3 horas."""
    current_time = time.time()
    expiration_time = 10800  # 3 horas en segundos

    thread_ids = list(conversations.keys())
    cleaned = 0

    for thread_id in thread_ids:
        if "last_activity" in conversations[thread_id]:
            if current_time - conversations[thread_id]["last_activity"] > expiration_time:
                logger.info(f"Limpiando conversación inactiva (>3h): {thread_id}")
                try:
                    del conversations[thread_id]
                    if thread_id in thread_locks:
                        del thread_locks[thread_id]
                    cleaned += 1
                except Exception as e:
                    logger.error(f"Error al limpiar thread_id {thread_id}: {e}")

    if cleaned > 0:
        logger.info(f"Limpieza completada: {cleaned} conversaciones eliminadas")

# Iniciar un hilo para ejecutar la limpieza periódica
def start_cleanup_thread():
    """Inicia un hilo que ejecuta la limpieza cada hora."""
    import threading

    def cleanup_worker():
        while True:
            try:
                time.sleep(3600)  # Ejecutar cada hora
                logger.info("Ejecutando limpieza programada")
                cleanup_inactive_conversations()
            except Exception as e:
                logger.error(f"Error en hilo de limpieza: {e}")

    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info("Hilo de limpieza iniciado")

# Agregar esta línea justo antes de 'if __name__ == '__main__'
start_cleanup_thread()

if __name__ == '__main__':
    logger.info("Iniciando la aplicación Flask")
    app.run(host='0.0.0.0', port=8080)
