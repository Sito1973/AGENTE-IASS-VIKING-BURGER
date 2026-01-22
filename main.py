import json
import openai
import requests
import threading
import random
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
from google import genai
from google.genai import types as genai_types  # <-- Cambiar esta línea
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
                    # Removido warning de reintentos para simplificar logs
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

# Configuración de Seq para logs persistentes
SEQ_SERVER_URL = os.environ.get('SEQ_SERVER_URL')
APP_NAME = os.environ.get('APP_NAME', 'viking-burger')

# Filtro para agregar Application a todos los logs
class AppNameFilter(logging.Filter):
    def filter(self, record):
        record.Application = APP_NAME
        return True

# Crear lista de handlers
log_handlers = [logging.StreamHandler()]  # Salida a la consola

# Agregar handler de Seq si está configurado
if SEQ_SERVER_URL:
    from seqlog import SeqLogHandler
    seq_handler = SeqLogHandler(
        server_url=SEQ_SERVER_URL,
        batch_size=10,
        auto_flush_timeout=10
    )
    seq_handler.setLevel(logging.INFO)
    seq_handler.addFilter(AppNameFilter())
    log_handlers.append(seq_handler)

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=log_handlers
)

logger = logging.getLogger(__name__)

# Variable para debug de Anthropic
ANTHROPIC_DEBUG = os.getenv("ANTHROPIC_DEBUG", "0").strip() in {"1", "true", "True", "yes", "YES"}

if SEQ_SERVER_URL:
    logger.info("✅ Seq logging habilitado: %s (App: %s)", SEQ_SERVER_URL, APP_NAME)

# URL del webhook de n8n (ajusta esto según tu configuración)
N8N_WEBHOOK_URL = os.environ.get(
    'N8N_WEBHOOK_URL',
    'https://n8niass.cocinandosonrisas.co/webhook/eleccionFormaPagoTheVikingBurgerApi')

# Mapa para asociar valores de 'assistant' con nombres de archivos
ASSISTANT_FILES = {
    0: "PROMPTS/URBAN/ASISTENTE_INICIAL.txt",
    1: 'PROMPTS/URBAN/ASISTENTE_DOMICILIO.txt',
    2: 'PROMPTS/URBAN/ASISTENTE_RECOGER.txt',
    3: 'PROMPTS/URBAN/ASISTENTE_FORMA_PAGO.txt',
    4: 'PROMPTS/URBAN/ASISTENTE_POSTVENTA.txt',
    5: 'PROMPTS/URBAN/ASISTENTE_INICIAL_FUERA_DE_HORARIO.txt' 
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
        self.crear_reserva_webhook_url = os.environ.get(
            "N8N_RESERVA_WEBHOOK_URL",
            "https://n8niass.cocinandosonrisas.co/webhook/herramientaEnviarFormularioReservaBandidosApi"
        )
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

    def reserva_mesa(self, payload):
        """Envía los datos para reserva de mesa al webhook de n8n"""
        logger.debug("Enviando datos de reserva mesa a n8n con payload: %s",
                     payload)
        response = requests.post(self.crear_reserva_webhook_url, json=payload)
        logger.info("Respuesta de n8n al enviar datos de reserva_mesa: %s %s",
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
            try:
                # Intentar parsear JSON solo si hay contenido
                if response.text and 'application/json' in response.headers.get('Content-Type', ''):
                    response_content = response.json()
                else:
                    response_content = {"message": response.text if response.text else 'MENU Operación exitosa.'}
            except ValueError:
                # Si falla el parseo JSON, usar el texto directo
                response_content = {"message": response.text if response.text else 'MENU Operación exitosa.'}

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
            try:
                # Intentar parsear JSON solo si hay contenido
                if response.text and 'application/json' in response.headers.get('Content-Type', ''):
                    response_content = response.json()
                else:
                    response_content = {"message": response.text if response.text else 'Operación exitosa.'}
            except ValueError:
                # Si falla el parseo JSON, usar el texto directo
                response_content = {"message": response.text if response.text else 'Operación exitosa.'}

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'Operación exitosa.')

        logger.info("crear_direccion result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en crear_direccion: %s", e)
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

def reserva_mesa(tool_input, subscriber_id):
    """
    Función para enviar los datos del pedido al webhook de n8n y devolver su respuesta al modelo
    """
    logger.info("Iniciando reserva_mesa con datos: %s", tool_input)
    logger.debug("subscriber_id en reserva_mesa: %s", subscriber_id)

    try:
        n8n_api = N8nAPI()

        # Construir el payload con la información del tool_input y las variables adicionales
        payload = {
            "response": {
                "tool_code": "reservar_mesa",
                "subscriber_id": subscriber_id,
                "sede": tool_input  # Datos provenientes del LLM
            }
        }

        logger.debug("Payload para enviar al webhook de n8n: %s", payload)

        # Enviar el payload al webhook de n8n
        response = n8n_api.reserva_mesa(payload)

        # Verificar si la respuesta es exitosa
        if response.status_code not in [200, 201]:
            logger.error("Error al enviar datos al webhook de n8n: %s",
                         response.text)
            # Retornar la respuesta de n8n al modelo para que lo informe al usuario
            result = {"error": response.text}
        else:
            # Si todo va bien, extraemos directamente el mensaje sin envolverlo en otro objeto
            response_content = response.json(
            ) if 'application/json' in response.headers.get(
                'Content-Type', '') else {
                    "message": response.text
                }

            # Extraer directamente el mensaje sin envolverlo en "result"
            result = response_content.get('message', 'formulario enviado exitosamente.')

        logger.info("reserva_mesa result: %s", result)
        return result  # Retornamos el resultado como diccionario con 'result' o 'error'

    except Exception as e:
        logger.exception("Error en reserva_mesa: %s", e)
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

        if "role" not in message or message["role"] not in [
                "user", "assistant"
        ]:
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


thread_locks = {}


def generate_response(api_key,
                      message,
                      assistant_content_text,
                      thread_id,
                      event,
                      subscriber_id,
                      use_cache_control,
                      llmID=None,
                      cost_base_input=1.0,
                      cost_cache_write_5m=1.25,
                      cost_cache_read=0.10,
                      cost_output=5.0):
    if not llmID:
        llmID = "claude-haiku-4-5-20251001"  # Modelo por defecto

    logger.info("Intentando adquirir lock para thread_id: %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error("No se encontró lock para thread_id: %s", thread_id)
        thread_locks[thread_id] = threading.Lock()
        lock = thread_locks[thread_id]

    if lock and lock.locked():
        if ANTHROPIC_DEBUG:
            logger.info("🔒 Lock ocupado para thread_id: %s", thread_id)

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
            
            # ========================================
            # SISTEMA AUTOMÁTICO DE CACHE MANAGEMENT 
            # ========================================
            # Gestión inteligente de máximo 4 bloques cache por conversación
            # Reseteo automático cada 5 minutos, priorización estratégica
            
            cache_blocks_used = 0
            max_cache_blocks = 4
            current_time = time.time()
            
            # Verificar si necesitamos resetear cache (4 min 50 seg de INACTIVIDAD = 290 segundos)
            # Margen de seguridad de 10 segundos antes de que Anthropic expire el cache a los 5 min
            last_activity_time = conversations[thread_id].get("last_activity", 0)
            cache_expired_by_inactivity = (current_time - last_activity_time) > 290
            is_new_conversation = last_activity_time == 0 or len(conversation_history) == 0
            
            if is_new_conversation:
                conversations[thread_id]["cache_reset"] = True
                conversations[thread_id]["last_activity"] = current_time
                logger.info("🔄 Cache inicial para nueva conversación thread_id: %s", thread_id)
            elif cache_expired_by_inactivity:
                conversations[thread_id]["cache_reset"] = True
                conversations[thread_id]["last_activity"] = current_time
                logger.info("🔄 Cache reseteado por inactividad para thread_id: %s (4 min 50 seg sin mensajes)", thread_id)
            else:
                conversations[thread_id]["cache_reset"] = False
                conversations[thread_id]["last_activity"] = current_time  # Actualizar actividad
                time_remaining = 290 - (current_time - last_activity_time)
                logger.info("🔄 Cache activo para thread_id: %s (TTL restante: %.0f segundos)", thread_id, time_remaining)
            
            # Análisis de conversación para cache inteligente
            messages_count = len(conversation_history)
            current_stage = conversations[thread_id].get("assistant", 0)
            is_conversation_established = messages_count >= 3
            
            # Determinar tokens estimados para modelos (mínimos requeridos)
            model_cache_minimum = 2048 if "haiku" in llmID.lower() else 1024
            
            # Función helper para estimar tokens (aproximadamente 4 caracteres = 1 token)
            def estimate_tokens(text):
                return len(text) // 4
            
            # ========================================
            # FUNCIONES DE CACHE MANAGEMENT
            # ========================================
            def clean_existing_cache_controls(conversation_history):
                """Limpia cache_control existentes para implementar cache incremental"""
                for message in conversation_history:
                    if "content" in message and isinstance(message["content"], list):
                        for content_item in message["content"]:
                            if isinstance(content_item, dict) and "cache_control" in content_item:
                                del content_item["cache_control"]
                return conversation_history
            
            def count_existing_cache_blocks(conversation_history):
                """Cuenta cuántos bloques de cache están actualmente en uso"""
                cache_count = 0
                for message in conversation_history:
                    if "content" in message and isinstance(message["content"], list):
                        for content_item in message["content"]:
                            if isinstance(content_item, dict) and "cache_control" in content_item:
                                cache_count += 1
                return cache_count
            
            # Limpiar cache_control existentes SOLO cuando hay reset (nueva conversación o TTL expirado)
            if conversations[thread_id].get("cache_reset", False):
                conversation_history = clean_existing_cache_controls(conversation_history)
                cache_blocks_used = 0  # Reiniciar conteo después de limpiar
                logger.info("🧹 Cache controls existentes limpiados para thread_id: %s", thread_id)
            else:
                # Mantener cache existente, solo contar bloques usados
                cache_blocks_used = count_existing_cache_blocks(conversation_history)
                logger.info("🔄 Cache existente mantenido para thread_id: %s (%d bloques usados)", thread_id, cache_blocks_used)
            
            # ============================================
            # BLOQUE 1: USER MESSAGE CACHE (Prioridad 4)
            # ============================================
            user_message_content = {"type": "text", "text": message}
            
            # Cachear mensaje del usuario SOLO cuando hay reset (nueva conversación o TTL expirado)
            should_cache_user_message = False  # Por defecto NO cachear user messages
            
            if should_cache_user_message:
                user_message_content["cache_control"] = {"type": "ephemeral"}
                cache_blocks_used += 1
                logger.info("💬 User message cached (bloque %d/4) para thread_id: %s (maximizando uso de cache)", 
                           cache_blocks_used, thread_id)
            else:
                reason = "cache reset por TTL/stage" if conversations[thread_id].get("cache_reset", False) else f"límite bloques alcanzado ({cache_blocks_used}/4)"
                logger.info("💬 User message sin cache para thread_id: %s (%s)", thread_id, reason)
            
            conversation_history.append({
                "role": "user",
                "content": [user_message_content]
            })
            
            # ============================================
            # BLOQUE EXTRA: CACHE INCREMENTAL DEL HISTORIAL
            # ============================================
            # Si tenemos espacio y hay varios mensajes, cachear el último mensaje del historial
            if cache_blocks_used < max_cache_blocks and len(conversation_history) > 1:
                # Cachear el penúltimo mensaje (no el que acabamos de agregar)
                previous_message = conversation_history[-2]
                if "content" in previous_message and isinstance(previous_message["content"], list):
                    for content_item in previous_message["content"]:
                        if isinstance(content_item, dict) and "cache_control" not in content_item:
                            content_item["cache_control"] = {"type": "ephemeral"}
                            cache_blocks_used += 1
                            logger.info("📜 Historial cached (bloque %d/4) para thread_id: %s (cache incremental)", 
                                       cache_blocks_used, thread_id)
                            break  # Solo uno por mensaje

            # Cargar herramientas
            assistant_value = conversations[thread_id].get("assistant")
            assistant_str = str(assistant_value)
            if assistant_str in ["0", "5"]:
                tools_file_name = "tools_stage0.json"
            elif assistant_str in ["1", "2"]:
                tools_file_name = "tools_stage1.json"
            elif assistant_str in ["3"]:
                tools_file_name = "tools_stage2.json"
            elif assistant_str in ["4"]:
                tools_file_name = "tools_stage3.json"
            elif assistant_str in ["20"]:
                tools_file_name = "tools_stage20.json"
            else:
                tools_file_name = "default_tools.json"

            tools_file_path = os.path.join(os.path.dirname(__file__),
                                           tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools = json.load(tools_file)
            logger.info("HERRAMIENTAS CARGADAS DESDE (ANTHROPIC) %s",
                        tools_file_name)

            # ========================================
            # PREPARAR TOOLS PARA COMBINAR CON SYSTEM
            # ========================================
            tools_text = ""
            tools_tokens = 0
            if tools:
                tools_text = f"\n\n<tools>\n{json.dumps(tools, ensure_ascii=False, indent=2)}\n</tools>\n\n"
                tools_tokens = estimate_tokens(tools_text)
                logger.info("🔧 Tools preparadas para combinar con system (%d tokens) para thread_id: %s", 
                           tools_tokens, thread_id)

            # ========================================
            # BLOQUE ÚNICO: TOOLS + SYSTEM CACHE (Prioridad 1)
            # ========================================
            # SOLO aplicar cache_control cuando hay reset (nueva conversación o TTL expirado)
            should_apply_system_cache = conversations[thread_id].get("cache_reset", False)
            
            if should_apply_system_cache and cache_blocks_used < max_cache_blocks:
                # Combinar tools con system prompt para máxima eficiencia
                combined_content = tools_text + assistant_content_text
                
                # Separación inteligente estático/dinámico para maximizar cache hits
                separators = ["Información del Cliente:", "<customer_info>", "Nombre del Cliente:"]
                static_part = combined_content
                dynamic_part = ""
                separator_found = None
                
                for separator in separators:
                    if separator in combined_content:
                        static_part = combined_content.split(separator)[0]
                        dynamic_part = combined_content[len(static_part):]
                        separator_found = separator
                        break
                
                # Verificar si la parte estática tiene suficientes tokens para cachear
                static_tokens = estimate_tokens(static_part.strip())
                total_tokens = estimate_tokens(combined_content)
                combined_tokens = tools_tokens + estimate_tokens(assistant_content_text)
                
                # Aplicar cache estratégico según contenido y tokens mínimos
                if dynamic_part.strip() and cache_blocks_used < max_cache_blocks and static_tokens >= model_cache_minimum:
                    # Contenido mixto: cachear solo parte estática SI supera el mínimo
                    assistant_content = [
                        {
                            "type": "text",
                            "text": static_part.strip(),
                            "cache_control": {"type": "ephemeral"}
                        },
                        {
                            "type": "text", 
                            "text": dynamic_part.strip()  # Variables no se cachean
                        }
                    ]
                    cache_blocks_used += 1
                    logger.info("🔧📝 Tools+System cached (bloque %d/4) - separación estático/dinámico en '%s' (%d+%d=%d tokens) para thread_id: %s", 
                               cache_blocks_used, separator_found, tools_tokens, static_tokens-tools_tokens, static_tokens, thread_id)
                elif not dynamic_part.strip() and cache_blocks_used < max_cache_blocks and total_tokens >= model_cache_minimum:
                    # Contenido completamente estático
                    assistant_content = [{
                        "type": "text",
                        "text": combined_content,
                        "cache_control": {"type": "ephemeral"}
                    }]
                    cache_blocks_used += 1
                    logger.info("🔧📝 Tools+System cached completo (bloque %d/4) - sin variables (%d+%d=%d tokens) para thread_id: %s", 
                               cache_blocks_used, tools_tokens, total_tokens-tools_tokens, total_tokens, thread_id)
                elif dynamic_part.strip() and static_tokens < model_cache_minimum and total_tokens >= model_cache_minimum:
                    # Parte estática muy pequeña: cachear todo junto
                    assistant_content = [{
                        "type": "text",
                        "text": combined_content,
                        "cache_control": {"type": "ephemeral"}
                    }]
                    cache_blocks_used += 1
                    logger.info("🔧📝 Tools+System cached completo (bloque %d/4) - estático insuficiente, cacheando todo (%d+%d=%d tokens) para thread_id: %s", 
                               cache_blocks_used, tools_tokens, total_tokens-tools_tokens, total_tokens, thread_id)
                else:
                    # Sin cache: no hay espacio o no alcanza tokens mínimos
                    assistant_content = [{
                        "type": "text",
                        "text": assistant_content_text
                    }]
                    reason = "límite bloques" if cache_blocks_used >= max_cache_blocks else f"tokens insuficientes ({total_tokens}<{model_cache_minimum})"
                    logger.info("📝 System prompt sin cache para thread_id: %s (%s)", thread_id, reason)
            else:
                # Mantener cache existente del sistema si no hay reset
                if not conversations[thread_id].get("cache_reset", False):
                    # Reusar cache del sistema existente
                    combined_content = tools_text + assistant_content_text
                    assistant_content = [{
                        "type": "text",
                        "text": combined_content,
                        "cache_control": {"type": "ephemeral"}
                    }]
                    cache_blocks_used += 1
                    logger.info("📝 System cache reutilizado para thread_id: %s (bloque %d/4)", 
                               thread_id, cache_blocks_used)
                else:
                    assistant_content = [{
                        "type": "text",
                        "text": assistant_content_text
                    }]
                    logger.info("📝 System prompt sin cache para thread_id: %s (límite bloques alcanzado: %d/4)", 
                               thread_id, cache_blocks_used)

            # ========================================  
            # RESUMEN CACHE MANAGEMENT AUTOMÁTICO
            # ========================================
            # Determinar estado de cache para tools y system
            tools_cache_applied = any("cache_control" in tool for tool in tools) if tools else False
            system_cache_applied = any("cache_control" in item for item in assistant_content)
            
            # Calcular TTL restante basado en inactividad (4 min 50 seg = 290 segundos)
            cache_ttl_seconds = 290
            time_elapsed = current_time - conversations[thread_id].get("last_activity", current_time)
            ttl_remaining = max(0, cache_ttl_seconds - int(time_elapsed))
            
            cache_summary = {
                "bloques_usados": cache_blocks_used,
                "maximo_permitido": max_cache_blocks,
                "modelo": llmID,
                "tokens_minimos_requeridos": model_cache_minimum,
                "stage_actual": current_stage,
                "mensajes_count": messages_count,
                "cache_reset": conversations[thread_id].get("cache_reset", False),
                "tools_cache": "applied" if tools_cache_applied else "no_applied",
                "system_cache": "applied" if system_cache_applied else "no_applied",
                "tools_tokens": tools_tokens if 'tools_tokens' in locals() else 0,
                "system_tokens": (static_tokens - tools_tokens) if 'static_tokens' in locals() and 'tools_tokens' in locals() else (total_tokens - tools_tokens) if 'total_tokens' in locals() and 'tools_tokens' in locals() else 0,
                "cache_ttl_remaining_seconds": ttl_remaining
            }
            
            logger.info("🎯 CACHE SUMMARY para thread_id %s: %s", thread_id, cache_summary)
            
            # Actualizar estadísticas del hilo
            conversations[thread_id]["cache_stats"] = cache_summary

            # Mapear herramientas a funciones
            tool_functions = {
                "crear_pedido": crear_pedido,
                "crear_link_pago": crear_link_pago,
                "enviar_menu": enviar_menu,
                "crear_direccion": crear_direccion,
                "eleccion_forma_pago": eleccion_forma_pago,
                "facturacion_electronica": facturacion_electronica,
                "pqrs": pqrs,
                #"reserva_mesa":reserva_mesa
                
            }

            # Iniciar interacción con el modelo
            while True:
                # Validar estructura de mensajes antes de enviar
                if not validate_conversation_history(conversation_history):
                    logger.error("Estructura de mensajes inválida: %s",
                                 conversation_history)
                    raise ValueError("Estructura de conversación inválida")

                try:
                    if ANTHROPIC_DEBUG:
                        logger.info("⤴️ PAYLOAD ANTHROPIC: %s", conversation_history)
                    # Llamar a la API con reintentos
                    logger.info("Llamando a Anthropic API para thread_id: %s",
                                thread_id)
                    api_call_started = time.time()
                    if ANTHROPIC_DEBUG:
                        logger.info(
                            "⏱️ Inicio llamada Anthropic | thread_id=%s | modelo=%s | mensajes=%d",
                            thread_id, llmID, len(conversation_history))
                    # Preparar headers para cache TTL extendido si es necesario
                    extra_headers = {}
                    if use_cache_control and any(
                        tool.get("cache_control", {}).get("ttl") == "1h" 
                        for tool in tools if isinstance(tool, dict)
                    ):
                        extra_headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11"
                        logger.info("Header beta agregado para cache TTL extendido en thread_id: %s", thread_id)
                    response = call_anthropic_api(
                        client=client,
                        model=llmID,
                        max_tokens=2000,
                        #temperature=0.8,
                        thinking={
                        "type": "enabled",
                        "budget_tokens": 1200
                        },
                        system=assistant_content,
                        tools=tools,  # Mantenemos tools por separado para funcionalidad
                        tool_choice={
                            "type": "auto",
                            "disable_parallel_tool_use": True
                        },
                        messages=conversation_history,
                        **extra_headers)
                    api_call_elapsed = time.time() - api_call_started
                    usage_obj = get_field(response, "usage")
                    tier = get_field(usage_obj, "service_tier") or "unknown"
                    in_tok = get_field(usage_obj, "input_tokens")
                    out_tok = get_field(usage_obj, "output_tokens")
                    cache_read_tok = get_field(usage_obj, "cache_read_input_tokens")
                    cache_create_tok = get_field(usage_obj, "cache_creation_input_tokens")
                    if ANTHROPIC_DEBUG:
                        logger.info(
                            "✅ Fin llamada Anthropic (%.2fs) | tier=%s | in=%s | out=%s | cache_read=%s | cache_create=%s",
                            api_call_elapsed, tier, in_tok, out_tok, cache_read_tok, cache_create_tok)
                        logger.info("📣 RESPUESTA RAW ANTHROPIC: %s", response)
                    
                     # Procesar respuesta - Filtrar bloques de texto vacíos para evitar error de API
                    filtered_content = [
                        block for block in response.content
                        if not (get_field(block, "type") == "text" and not get_field(block, "text"))
                    ]
                    
                    # Procesar respuesta
                    conversation_history.append({
                        "role": "assistant",
                        "content": filtered_content if filtered_content else response.content
                    })

                    # Almacenar tokens del turno actual
                    current_usage = {
                        "input_tokens":
                        response.usage.input_tokens,
                        "output_tokens":
                        response.usage.output_tokens,
                        "cache_creation_input_tokens":
                        response.usage.cache_creation_input_tokens,
                        "cache_read_input_tokens":
                        response.usage.cache_read_input_tokens,
                    }
                    
                    # Actualizar contadores acumulativos del thread
                    if "total_usage" not in conversations[thread_id]:
                        conversations[thread_id]["total_usage"] = {
                            "total_input_tokens": 0,
                            "total_output_tokens": 0,
                            "total_cache_creation_tokens": 0,
                            "total_cache_read_tokens": 0
                        }
                    
                    # Acumular tokens
                    conversations[thread_id]["total_usage"]["total_input_tokens"] += current_usage["input_tokens"]
                    conversations[thread_id]["total_usage"]["total_output_tokens"] += current_usage["output_tokens"] 
                    conversations[thread_id]["total_usage"]["total_cache_creation_tokens"] += current_usage["cache_creation_input_tokens"]
                    conversations[thread_id]["total_usage"]["total_cache_read_tokens"] += current_usage["cache_read_input_tokens"]
                    
                    # Calcular costos del turno actual (en USD)
                    def calculate_costs(tokens, cost_per_mtok):
                        return (tokens / 1_000_000) * cost_per_mtok
                    
                    current_cost_input = calculate_costs(current_usage["input_tokens"], cost_base_input)
                    current_cost_output = calculate_costs(current_usage["output_tokens"], cost_output)
                    current_cost_cache_creation = calculate_costs(current_usage["cache_creation_input_tokens"], cost_cache_write_5m)
                    current_cost_cache_read = calculate_costs(current_usage["cache_read_input_tokens"], cost_cache_read)
                    current_total_cost = current_cost_input + current_cost_output + current_cost_cache_creation + current_cost_cache_read
                    
                    # Inicializar costos acumulativos si no existen
                    if "total_costs" not in conversations[thread_id]:
                        conversations[thread_id]["total_costs"] = {
                            "total_cost_input": 0.0,
                            "total_cost_output": 0.0,
                            "total_cost_cache_creation": 0.0,
                            "total_cost_cache_read": 0.0,
                            "total_cost_all": 0.0
                        }
                    
                    # Acumular costos
                    conversations[thread_id]["total_costs"]["total_cost_input"] += current_cost_input
                    conversations[thread_id]["total_costs"]["total_cost_output"] += current_cost_output
                    conversations[thread_id]["total_costs"]["total_cost_cache_creation"] += current_cost_cache_creation
                    conversations[thread_id]["total_costs"]["total_cost_cache_read"] += current_cost_cache_read
                    conversations[thread_id]["total_costs"]["total_cost_all"] += current_total_cost
                    
                    usage = current_usage
                    conversations[thread_id]["usage"] = usage

                    logger.info("Tokens utilizados - Input: %d, Output: %d",
                                usage["input_tokens"], usage["output_tokens"])
                    logger.info("Cache Creation Input Tokens: %d",
                                usage["cache_creation_input_tokens"])
                    logger.info("Cache Read Input Tokens: %d",
                                usage["cache_read_input_tokens"])

                    # Procesar herramientas
                    if response.stop_reason == "tool_use":
                        tool_use_blocks = [
                            block for block in response.content
                            if get_field(block, "type") == "tool_use"
                        ]
                        logger.info(
                            "🧰 Respuesta con tool_calls detectada (ANTHROPIC): %s",
                            tool_use_blocks)
                        if not tool_use_blocks:
                            # Si no hay herramientas, procesamos la respuesta final
                            assistant_response_text = ""
                            for content_block in response.content:
                                if get_field(content_block, "type") == "text":
                                    assistant_response_text += (get_field(
                                        content_block, "text") or "")
                            conversations[thread_id][
                                "response"] = assistant_response_text
                            conversations[thread_id]["status"] = "completed"
                            break

                        # Procesar herramienta
                        tool_use = tool_use_blocks[0]
                        tool_name = get_field(tool_use, "name")
                        tool_input = get_field(tool_use, "input")

                        if tool_name in tool_functions:
                            try:
                                result = tool_functions[tool_name](tool_input,
                                                                   subscriber_id)
                                result_json = json.dumps(result)

                                # Agregar resultado exitoso
                                conversation_history.append({
                                    "role": "user",
                                    "content": [{
                                        "type": "tool_result",
                                        "tool_use_id": get_field(tool_use, "id"),
                                        "content": result_json,
                                    }],
                                })
                            except Exception as tool_error:
                                logger.exception("Error ejecutando herramienta %s: %s", tool_name, tool_error)
                                
                                # Agregar tool_result de error cuando la función falla
                                conversation_history.append({
                                    "role": "user",
                                    "content": [{
                                        "type": "tool_result",
                                        "tool_use_id": get_field(tool_use, "id"),
                                        "content": f"Error ejecutando '{tool_name}': {str(tool_error)}",
                                        "is_error": True
                                    }],
                                })
                                logger.info("Tool_result de error agregado para función fallida: %s", tool_name)
                        else:
                            logger.warning("Herramienta desconocida: %s", tool_name)
                            
                            # Agregar tool_result de error para mantener balance tool_use/tool_result
                            conversation_history.append({
                                "role": "user",
                                "content": [{
                                    "type": "tool_result",
                                    "tool_use_id": get_field(tool_use, "id"),
                                    "content": f"Error: Tool '{tool_name}' is not available or unknown in this context",
                                    "is_error": True
                                }],
                            })
                            logger.info("Tool_result de error agregado para tool_use_id: %s", get_field(tool_use, "id"))
                            # Continuar el bucle en lugar de break para permitir que Claude maneje el error
                    else:
                        # Respuesta final
                        assistant_response_text = ""
                        for content_block in response.content:
                            if get_field(content_block, "type") == "text":
                                assistant_response_text += (get_field(
                                    content_block, "text") or "")
                        conversations[thread_id][
                            "response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        break

                except Exception as api_error:
                    if ANTHROPIC_DEBUG:
                        try:
                            elapsed_api = time.time() - api_call_started
                            logger.warning(
                                "❌ Error Anthropic tras %.2fs | thread_id=%s | %s",
                                elapsed_api, thread_id, api_error)
                        except Exception:
                            logger.warning(
                                "❌ Error Anthropic | thread_id=%s | %s",
                                thread_id, api_error)
                    logger.exception(
                        "Error en llamada a API para thread_id %s: %s",
                        thread_id, api_error)
                    # Enviar el error con prefijo identificador seguido del error de la API
                    conversations[thread_id]["response"] = f"error API anthropic: {str(api_error)}"
                    conversations[thread_id]["status"] = "error"
                    break

        except Exception as e:
            logger.exception(
                "Error en generate_response para thread_id %s: %s", thread_id,
                e)
            # Enviar el error con prefijo identificador seguido del error
            conversations[thread_id]["response"] = f"error API anthropic: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            elapsed_time = time.time() - start_time
            logger.info(
                "Generación completada en %.2f segundos para thread_id: %s",
                elapsed_time, thread_id)
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
        llmID = "gpt-4.1"

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
        start_time = time.time()

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
            elif assistant_str in ["4"]:
                tools_file_name = "tools_stage3.json"
            elif assistant_str in ["5"]:
                tools_file_name = "tools_stage0.json"
            else:
                tools_file_name = "default_tools.json"

            # Cargar el archivo de herramientas correspondiente
            tools_file_path = os.path.join(os.path.dirname(__file__), tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools_anthropic_format = json.load(tools_file)
            logger.info("Herramientas cargadas desde (OPENAI) %s", tools_file_name)

            # Convertir herramientas al formato de OpenAI Function Calling
            tools_openai_format = []
            for tool in tools_anthropic_format:
                # Obtener parámetros del formato Anthropic o input_schema
                parameters = tool.get("parameters", tool.get("input_schema", {}))

                # Si se usa strict mode, asegurar que additionalProperties esté en false
                if tool.get("strict", True):
                    if "additionalProperties" not in parameters:
                        parameters["additionalProperties"] = False

                openai_tool = {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": parameters,
                    "strict": tool.get("strict", True)
                }
                tools_openai_format.append(openai_tool)
            tools = tools_openai_format

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

            # Debug: Log del historial antes de procesarlo
            logger.debug(f"Procesando {len(conversation_history)} mensajes del historial")
            for i, msg in enumerate(conversation_history):
                if isinstance(msg, dict):
                    keys = list(msg.keys())
                    logger.debug(f"Mensaje {i} - Claves: {keys}")
                else:
                    logger.debug(f"Mensaje {i} - Tipo: {type(msg)} - Valor: {msg}")

            # Preparar los mensajes para la nueva API
            input_messages = []

            # Agregar mensajes de la conversación
            for i, msg in enumerate(conversation_history):
                # Validar que msg sea un diccionario
                if not isinstance(msg, dict):
                    logger.warning(f"Mensaje {i} no es un diccionario, ignorando: {type(msg)}")
                    continue

                # Verificar si el mensaje tiene 'role' (mensajes normales)
                if "role" in msg:
                    if msg["role"] == "user":
                        input_messages.append({
                            "role": "user",
                            "content": [{"type": "input_text", "text": msg["content"]}]
                        })
                    elif msg["role"] == "assistant":
                        assistant_input = {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": msg["content"]}]
                        }
                        # Solo agregar IDs válidos que empiecen con 'msg_'
                        if "id" in msg and msg["id"] and msg["id"].startswith("msg_"):
                            assistant_input["id"] = msg["id"]

                        input_messages.append(assistant_input)

                # Verificar si el mensaje tiene 'type' (function calls y outputs)
                elif "type" in msg:
                    if msg["type"] == "function_call":
                        # Agregar function calls directamente
                        input_messages.append(msg)
                    elif msg["type"] == "function_call_output":
                        # Agregar function call outputs directamente
                        input_messages.append(msg)

                # Si no tiene ni 'role' ni 'type', ignorar el mensaje y log warning
                else:
                    logger.warning(f"Mensaje {i} sin 'role' ni 'type' ignorado: {msg}")
                    continue

            # Variable para seguir track de llamadas a herramientas
            call_counter = 0
            max_iterations = 5  # Límite de iteraciones para evitar bucles infinitos

            while call_counter < max_iterations:
                try:
                    # Llamar a la API en el nuevo formato
                    logger.info("🚨PAYLOAD OPENAI: %s", conversation_history)

                    response = client.responses.create(
                        model=llmID,
                        instructions=assistant_content_text,
                        input=input_messages,
                        tools=tools,
                        temperature=0.7,
                        max_output_tokens=2000,
                        top_p=1,
                       
                        store=True
                    )
                    logger.info("✅RESPUESTA OPENAI: %s", response.output)
                    # Imprimir la estructura completa para debug
                    #print("✅RESPUESTA RAW OPENAI: %s", response.output)
                    print("💰💰 TOKENIZACION: %s", response.usage)  # Deshabilitado

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
                    message_id = None
                    function_called = False

                    # Procesar la respuesta
                    if hasattr(response, 'output') and response.output:
                        # Caso 1: La respuesta es un texto normal
                        for output_item in response.output:
                            if hasattr(output_item, 'type'):
                                # Es un objeto (no un diccionario)
                                if output_item.type == 'message' and hasattr(output_item, 'content'):
                                    # Extraer ID del mensaje
                                    message_id = getattr(output_item, 'id', None)
                                    logger.info("ID del mensaje extraído: %s", message_id)

                                    for content_item in output_item.content:
                                        if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                            assistant_response_text = content_item.text
                                            #logger.info("Respuesta de texto encontrada: %s", assistant_response_text)
                                            break

                                # Caso 2: La respuesta es una llamada a función
                                elif output_item.type == 'function_call':
                                    function_called = True
                                    tool_name = output_item.name
                                    tool_arguments_str = output_item.arguments
                                    call_id = output_item.call_id if hasattr(output_item, 'call_id') else f"call_{call_counter}"
                                    function_call_id = getattr(output_item, 'id', None)

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

                                        # Agregar function call y output al historial en formato correcto
                                        function_call_entry = {
                                            "type": "function_call",
                                            "call_id": call_id,
                                            "name": tool_name,
                                            "arguments": tool_arguments_str
                                        }
                                        # Agregar ID si existe
                                        if function_call_id:
                                            function_call_entry["id"] = function_call_id

                                        function_output_entry = {
                                            "type": "function_call_output",
                                            "call_id": call_id,
                                            "output": result_str
                                        }

                                        conversation_history.append(function_call_entry)
                                        conversation_history.append(function_output_entry)

                                        # Preparar entrada para la siguiente iteración
                                        input_messages.append(function_call_entry)
                                        input_messages.append(function_output_entry)

                                        # Solicitar continuación de la conversación después de la llamada a la función
                                        continue_response = client.responses.create(
                                            model=llmID,
                                            instructions=assistant_content_text,
                                            input=input_messages,
                                            tools=tools,
                                            temperature=0.7,
                                            max_output_tokens=2000,
                                            top_p=1,
                                            store=True
                                        )

                                        logger.info("✅✅Respuesta después de la llamada a la función: %s", continue_response.output)

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
                                        continue_message_id = None
                                        if hasattr(continue_response, 'output') and continue_response.output:
                                            for continue_item in continue_response.output:
                                                if hasattr(continue_item, 'type') and continue_item.type == 'message':
                                                    # Extraer ID de continuación
                                                    continue_message_id = getattr(continue_item, 'id', None)
                                                    logger.info("ID del mensaje de continuación: %s", continue_message_id)

                                                    if hasattr(continue_item, 'content'):
                                                        for content_item in continue_item.content:
                                                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                                                assistant_response_text = content_item.text
                                                                logger.info("Respuesta de texto después de la función: %s", assistant_response_text)
                                                                break

                                        # Si obtuvimos una respuesta de texto, guardémosla CON ID
                                        if assistant_response_text:
                                            conversations[thread_id]["response"] = assistant_response_text
                                            conversations[thread_id]["status"] = "completed"
                                            # Crear mensaje con ID de continuación
                                            final_message = {
                                                "role": "assistant",
                                                "content": assistant_response_text
                                            }
                                            if continue_message_id:
                                                final_message["id"] = continue_message_id

                                            conversation_history.append(final_message)

                                            # IMPORTANTE: Salir del bucle while aquí
                                            logger.info("Respuesta final obtenida después de llamada a función, saliendo del bucle")
                                            break  # Salir del bucle for
                                        else:
                                            # Si no obtuvimos respuesta, usemos un mensaje genérico
                                            assistant_response_text = f"He procesado tu solicitud correctamente. ¿En qué más puedo ayudarte?"
                                            conversations[thread_id]["response"] = assistant_response_text
                                            conversations[thread_id]["status"] = "completed"
                                            conversation_history.append({
                                                "role": "assistant",
                                                "content": assistant_response_text
                                            })

                                            # IMPORTANTE: Salir del bucle while aquí también
                                            logger.info("Respuesta genérica después de llamada a función, saliendo del bucle")
                                            break  # Salir del bucle for

                                    else:
                                        logger.warning("Herramienta desconocida: %s", tool_name)
                                        break

                    # IMPORTANTE: Si procesamos una función y obtuvimos respuesta, salir del bucle while
                    if function_called and assistant_response_text:
                        logger.info("Función procesada y respuesta obtenida, saliendo del bucle while")
                        break

                    # Si encontramos un texto de respuesta y no hubo llamada a función, estamos listos
                    if assistant_response_text and not function_called:
                        # Crear mensaje con ID
                        assistant_message = {
                            "role": "assistant",
                            "content": assistant_response_text
                        }
                        if message_id:
                            assistant_message["id"] = message_id

                        conversations[thread_id]["response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        conversation_history.append(assistant_message)
                        break

                    # Si no encontramos ni texto ni llamada a función, algo salió mal
                    if not assistant_response_text and not function_called:
                        # Intentar una última extracción con un método diferente
                        if hasattr(response, 'output') and isinstance(response.output, list) and len(response.output) > 0:
                            first_output = response.output[0]
                            if hasattr(first_output, 'type') and first_output.type == 'function_call':
                                function_called = True
                                tool_name = first_output.name
                                tool_arguments_str = first_output.arguments
                                call_id = first_output.call_id if hasattr(first_output, 'call_id') else f"call_{call_counter}"
                                alt_function_call_id = getattr(first_output, 'id', None)

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
                                    assistant_response_text = f"He procesado tu solicitud correctamente. ¿En qué más puedo ayudarte?"
                                    conversations[thread_id]["response"] = assistant_response_text
                                    conversations[thread_id]["status"] = "completed"

                                    # Agregar function call y output al historial
                                    function_call_entry = {
                                        "type": "function_call",
                                        "call_id": call_id,
                                        "name": tool_name,
                                        "arguments": tool_arguments_str
                                    }
                                    if alt_function_call_id:
                                        function_call_entry["id"] = alt_function_call_id

                                    function_output_entry = {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": result_str
                                    }

                                    final_message = {
                                        "role": "assistant",
                                        "content": assistant_response_text
                                    }

                                    conversation_history.append(function_call_entry)
                                    conversation_history.append(function_output_entry)
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
            elapsed_time = time.time() - start_time
            print(f"⏰ Respuesta generada en {elapsed_time:.1f}s")  # Info importante como print
            logger.debug("Evento establecido para thread_id (OpenAI): %s", thread_id)
            #logger.info("Liberando lock para thread_id (OpenAI): %s", thread_id)

def generate_response_gemini(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    llmID=None):
    if not llmID:
        llmID = "gemini-3-flash-preview"  # Modelo más reciente de Gemini
        
    logger.info("Intentando adquirir lock para thread_id (Gemini): %s",
                thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error(
            "No se encontró lock para thread_id (Gemini): %s. Esto no debería ocurrir.",
            thread_id)
        return

    with lock:
        logger.info("Lock adquirido para thread_id (Gemini): %s", thread_id)
        logger.info("Generando respuesta para thread_id (Gemini): %s",
                    thread_id)
        logger.debug("subscriber_id en generate_response_gemini: %s",
                     subscriber_id)

        try:

            api_key = os.environ["GEMINI_API_KEY"]
            # Initialize Gemini client - CORRECTED LINE HERE
            client = genai.Client(
                api_key=api_key)

            conversation_history = conversations[thread_id]["messages"]

            # Add user message to conversation history usando tipos nativos de Gemini
            user_message = genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=message)]
            )
            conversation_history.append(user_message)
            #logger.info("HISTORIAL CONVERSACION GEMINI: %s",
                        #conversation_history)

            
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
            tools_file_path = os.path.join(os.path.dirname(__file__),
                                           tools_file_name)
            with open(tools_file_path, "r", encoding="utf-8") as tools_file:
                tools_anthropic_format = json.load(tools_file)

            logger.info("Herramientas cargadas desde %s (Gemini)",
                        tools_file_name)

            # Según la documentación oficial de Gemini, las function declarations
            # se pueden pasar como diccionarios JSON directamente
            # Normalizar formato: si usa "input_schema" cambiarlo a "parameters"
            function_declarations = []
            for tool in tools_anthropic_format:
                tool_declaration = {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters") or tool.get("input_schema") or {}
                }
                function_declarations.append(tool_declaration)

            # Crear Tool con las function declarations como diccionarios JSON
            tools = [genai_types.Tool(function_declarations=function_declarations)] if function_declarations else []
            if function_declarations:
                logger.info("Funciones habilitadas (Gemini): %s", [fd["name"] for fd in function_declarations])

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

            # Prepare historial normalizado para Gemini
            def build_gemini_messages(history):
                normalized_messages = []
                for entry in history:
                    # Si ya es un objeto Content de Gemini, agregarlo directamente
                    if isinstance(entry, genai_types.Content):
                        normalized_messages.append(entry)
                        continue

                    if isinstance(entry, dict):
                        role = entry.get("role", "user")
                        # Mapear roles de Anthropic a Gemini
                        if role == "assistant":
                            role = "model"

                        parts = entry.get("parts")
                        if parts:
                            normalized_parts = []
                            for part in parts:
                                # Si es un objeto Part de Gemini, agregarlo directamente
                                if isinstance(part, genai_types.Part):
                                    normalized_parts.append(part)
                                elif isinstance(part, dict):
                                    # Manejar diferentes tipos de parts
                                    if part.get("text"):
                                        normalized_parts.append(genai_types.Part.from_text(text=part.get("text")))
                                    elif part.get("function_call"):
                                        # Reconstruir function_call Part
                                        fc = part.get("function_call")
                                        normalized_parts.append(genai_types.Part.from_function_call(
                                            name=fc.get("name"),
                                            args=fc.get("args", {})
                                        ))
                                    elif part.get("function_response"):
                                        # Reconstruir function_response Part
                                        fr = part.get("function_response")
                                        normalized_parts.append(genai_types.Part.from_function_response(
                                            name=fr.get("name"),
                                            response=fr.get("response", {})
                                        ))
                            if normalized_parts:
                                normalized_messages.append(genai_types.Content(role=role, parts=normalized_parts))
                                continue

                        # Manejar formato Anthropic con "content"
                        content_items = entry.get("content")
                        if content_items:
                            normalized_parts = []
                            if isinstance(content_items, str):
                                # Content es un string simple
                                normalized_parts.append(genai_types.Part.from_text(text=content_items))
                            elif isinstance(content_items, list):
                                for item in content_items:
                                    text_value = None
                                    if isinstance(item, dict):
                                        text_value = item.get("text")
                                    elif isinstance(item, str):
                                        text_value = item
                                    if text_value:
                                        normalized_parts.append(genai_types.Part.from_text(text=text_value))
                            if normalized_parts:
                                normalized_messages.append(genai_types.Content(role=role, parts=normalized_parts))
                return normalized_messages

            messages_for_gemini = build_gemini_messages(conversation_history)

            # Start interaction con Gemini
            while True:
                logger.info("⤴️ PAYLOAD GEMINI: %s", messages_for_gemini)

                # Generate content with tools - CON REINTENTOS PARA ERRORES 500
                max_retries = 3
                retry_delay = 2  # segundos iniciales
                response_gemini = None

                for attempt in range(max_retries):
                    try:
                        response_gemini = client.models.generate_content(
                            contents=messages_for_gemini,
                            model=llmID,
                            config=genai_types.GenerateContentConfig(
                                tools=tools,
                                system_instruction=[
                                    genai_types.Part.from_text(text=assistant_content_text),
                                ],
                                thinking_config=genai_types.ThinkingConfig(
                                    thinking_level="HIGH",
                                ),
                                temperature=1.0,
                                max_output_tokens=3000,
                                safety_settings=[
                                    genai_types.SafetySetting(
                                        category="HARM_CATEGORY_HATE_SPEECH",
                                        threshold="OFF"
                                    ),
                                    genai_types.SafetySetting(
                                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                                        threshold="OFF"
                                    ),
                                    genai_types.SafetySetting(
                                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                                        threshold="OFF"
                                    ),
                                    genai_types.SafetySetting(
                                        category="HARM_CATEGORY_HARASSMENT",
                                        threshold="OFF"
                                    )
                                ]
                            ),
                        )
                        # Si llegamos aquí, la llamada fue exitosa
                        break
                    except Exception as api_error:
                        error_str = str(api_error)
                        # Verificar si es un error 500 (interno) o 503 (servicio no disponible)
                        if "500" in error_str or "503" in error_str or "INTERNAL" in error_str:
                            if attempt < max_retries - 1:
                                logger.warning(
                                    "⚠️ Error temporal de Gemini (intento %d/%d): %s. Reintentando en %d segundos...",
                                    attempt + 1, max_retries, error_str, retry_delay
                                )
                                time.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                            else:
                                logger.error("❌ Error de Gemini después de %d intentos: %s", max_retries, error_str)
                                raise  # Re-lanzar la excepción después de agotar reintentos
                        else:
                            # Para otros errores, no reintentar
                            raise

                if response_gemini is None:
                    raise Exception("No se pudo obtener respuesta de Gemini después de reintentos")

                logger.info("📢RESPUESTA RAW GEMINI: %s", response_gemini)

                # Capturar información de tokens
                if response_gemini.usage_metadata:
                    # Capturar información de tokens según el mapeo solicitado
                    usage = {
                        "input_tokens":
                        response_gemini.usage_metadata.total_token_count,
                        "output_tokens":
                        response_gemini.usage_metadata.candidates_token_count,
                        "cache_creation_input_tokens":
                        response_gemini.usage_metadata.prompt_token_count,
                        "cache_read_input_tokens":
                        response_gemini.usage_metadata.cached_content_token_count,
                    }

                    # Almacenar en la conversación
                    conversations[thread_id]["usage"] = usage

                    # --- MODIFICACIÓN AQUÍ ---
                    # Asegurar que los valores de tokens sean numéricos para el logging
                    input_tokens_log = usage.get("input_tokens", 0) if usage.get("input_tokens") is not None else 0
                    output_tokens_log = usage.get("output_tokens", 0) if usage.get("output_tokens") is not None else 0
                    cache_creation_tokens_log = usage.get("cache_creation_input_tokens", 0) if usage.get("cache_creation_input_tokens") is not None else 0
                    cache_read_tokens_log = usage.get("cache_read_input_tokens", 0) if usage.get("cache_read_input_tokens") is not None else 0
                    # --- FIN DE MODIFICACIÓN ---

                    # Registrar en logs
                    logger.info("Tokens utilizados - Input: %d, Output: %d",
                                input_tokens_log, output_tokens_log)
                    logger.info("Cache Creation Input Tokens: %d",
                                cache_creation_tokens_log)
                    logger.info("Cache Read Input Tokens: %d",
                                cache_read_tokens_log)

                # Capturar finish_reason SIEMPRE que haya candidates (incluso si content está vacío)
                if response_gemini.candidates:
                    finish_reason_raw = response_gemini.candidates[0].finish_reason
                    conversations[thread_id]["finish_reason"] = str(finish_reason_raw) if finish_reason_raw else None
                    logger.info("📢 FINISH_REASON GEMINI: %s", conversations[thread_id]["finish_reason"])

                if response_gemini.candidates and response_gemini.candidates[
                        0].content.parts:
                    response_content = response_gemini.candidates[0].content

                    # Check for function calls in the response
                    function_call_part = None
                    for part in response_content.parts:
                        if part.function_call:
                            function_call_part = part.function_call
                            break

                    if function_call_part:
                        logger.info(
                            "Respuesta con function_call detectada (Gemini): %s",
                            function_call_part)

                        tool_name = function_call_part.name
                        tool_arguments = function_call_part.args

                        logger.info("Llamando a la herramienta (Gemini): %s",
                                    tool_name)
                        logger.info(
                            "Argumentos de la herramienta (Gemini): %s",
                            tool_arguments)

                        if tool_name in tool_functions:
                            result = tool_functions[tool_name](
                                tool_arguments,
                                subscriber_id)  # Call tool function
                            logger.debug(
                                "Resultado de la herramienta %s (Gemini): %s",
                                tool_name, result)
                            logger.info(
                                "Resultado de la herramienta %s (Gemini): %s",
                                tool_name, result)

                            # Add function response to history según documentación oficial de Gemini
                            # Paso 1: Agregar la respuesta del modelo (con function call)
                            conversation_history.append(response_content)

                            # Paso 2: Crear y agregar function response con role="user"
                            function_response_part = genai_types.Part.from_function_response(
                                name=tool_name,
                                response={
                                    "output": result
                                }
                            )
                            # Según la documentación: role="user" para function responses
                            function_response_content = genai_types.Content(
                                role="user", parts=[function_response_part])
                            conversation_history.append(function_response_content)

                            messages_for_gemini = build_gemini_messages(conversation_history)  # Update messages for next turn

                            logger.info(
                                "Mensaje function_response enviado a Gemini (Gemini): %s",
                                function_response_content)

                        else:
                            logger.warning(
                                "Herramienta desconocida (Gemini): %s",
                                tool_name)
                            break  # Exit loop if unknown tool

                    else:
                        # No function call, process text response
                        assistant_response_text = ""
                        for part in response_content.parts:
                            if part.text:
                                assistant_response_text += part.text
                        conversations[thread_id][
                            "response"] = assistant_response_text
                        conversations[thread_id]["status"] = "completed"
                        logger.info(
                            "Respuesta generada para thread_id (Gemini): %s",
                            thread_id)

                        # Agregar respuesta del modelo al historial (response_content ya es Content de Gemini)
                        conversation_history.append(response_content)
                        break  # Exit loop for final text response
                else:
                    conversations[thread_id]["response"] = ""
                    conversations[thread_id]["status"] = "completed"
                    logger.warning(
                        "Respuesta vacía del modelo Gemini para thread_id: %s",
                        thread_id)
                    break

        except Exception as e:
            logger.exception(
                "Error en generate_response_gemini para thread_id %s: %s",
                thread_id, e)
            conversations[thread_id]["response"] = f"Error Gemini: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            logger.debug("Evento establecido para thread_id (Gemini): %s",
                         thread_id)
            logger.info("Liberando lock para thread_id (Gemini): %s",
                        thread_id)
            # Lock is automatically released when exiting 'with' block
   
@app.route('/sendmensaje', methods=['POST'])
def send_message():
    logger.info("Endpoint /sendmensaje llamado")
    data = request.json

    # Extraer parámetros principales
    message = data.get('message')
    assistant_value = data.get('assistant')
    thread_id = data.get('thread_id')
    subscriber_id = data.get('subscriber_id')
    thinking = data.get('thinking', 0)
    modelID = data.get('modelID', '').lower()
    telefono = data.get('telefono')
    direccionCliente = data.get('direccionCliente')
    # Cache control siempre habilitado internamente - no depende del request
    use_cache_control = False
    llmID = data.get('llmID')

    # Parámetros de costo (precios por millón de tokens - MTok)
    cost_base_input = data.get('cost_base_input', 1.0)  # Claude Sonnet 4: $3/MTok
    cost_cache_write_5m = data.get('cost_cache_write_5m', 1.25)  # $3.75/MTok (TTL por defecto)
    cost_cache_read = data.get('cost_cache_read', 0.10)  # $0.30/MTok
    cost_output = data.get('cost_output', 5.0)  # $15/MTok

    logger.info("MENSAJE CLIENTE: %s", message)
    # Extraer variables adicionales para sustitución
    variables = data.copy()
    keys_to_remove = [
        'message', 'assistant', 'thread_id', 'subscriber_id',
        'thinking', 'modelID', 'direccionCliente', 'use_cache_control', 'llmID',
        'cost_base_input', 'cost_cache_write_5m', 'cost_cache_read', 'cost_output'
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
        if modelID == 'llmO3':
            thread = Thread(target=generate_response_openai_o3,
                           args=(message, assistant_content,
                                thread_id, event, subscriber_id, llmID))
            logger.info("Ejecutando LLM2 para thread_id: %s", thread_id)

        elif modelID == 'gemini':
            thread = Thread(target=generate_response_gemini,
                            args=(message, assistant_content,
                                  thread_id, event, subscriber_id, llmID))
            logger.info("Ejecutando Gemini para thread_id: %s", thread_id)

        elif modelID == 'llm':
            thread = Thread(target=generate_response_openai,
                            args=(message, assistant_content,
                                  thread_id, event, subscriber_id, llmID))
            logger.info("Ejecutando LLM para thread_id: %s", thread_id)

        else:  # Default to Anthropic
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_api_key:
                logger.error("API key de Anthropic no configurada en .env")
                return jsonify({"error": "Configuración del servidor incompleta - ANTHROPIC_API_KEY"}), 500
            thread = Thread(target=generate_response,
                            args=(anthropic_api_key, message, assistant_content,
                                  thread_id, event, subscriber_id,
                                  use_cache_control, llmID,
                                  cost_base_input, cost_cache_write_5m,
                                  cost_cache_read, cost_output))
            logger.info("Ejecutando Anthropic para thread_id: %s", thread_id)

        thread.start()
        event.wait(timeout=60)

        # Preparar respuesta final
        response_data = {
            "thread_id": thread_id,
            "usage": conversations[thread_id].get("usage"),
            "finish_reason": conversations[thread_id].get("finish_reason")
        }

        # Agregar estadísticas de cache al usage si existen
        if "cache_stats" in conversations[thread_id]:
            cache_stats = conversations[thread_id]["cache_stats"]
            if "usage" in response_data and response_data["usage"]:
                response_data["usage"].update({
                    "cache_blocks_used": cache_stats.get("bloques_usados", 0),
                    "cache_blocks_max": cache_stats.get("maximo_permitido", 4),
                    "tools_cache_status": cache_stats.get("tools_cache", "no_applied"),
                    "system_cache_status": cache_stats.get("system_cache", "no_applied"),
                    "tools_cache_tokens": cache_stats.get("tools_tokens", 0),
                    "system_cache_tokens": cache_stats.get("system_tokens", 0),
                    "combined_cache_tokens": cache_stats.get("tools_tokens", 0) + cache_stats.get("system_tokens", 0),
                    "cache_reset": cache_stats.get("cache_reset", False),
                    "cache_ttl_remaining_seconds": cache_stats.get("cache_ttl_remaining_seconds", 0)
                })

        # Agregar totales acumulativos del thread si existen
        if "total_usage" in conversations[thread_id]:
            total_usage = conversations[thread_id]["total_usage"]
            if "usage" in response_data and response_data["usage"]:
                response_data["usage"].update({
                    "thread_total_input_tokens": total_usage.get("total_input_tokens", 0),
                    "thread_total_output_tokens": total_usage.get("total_output_tokens", 0),
                    "thread_total_cache_creation_tokens": total_usage.get("total_cache_creation_tokens", 0),
                    "thread_total_cache_read_tokens": total_usage.get("total_cache_read_tokens", 0),
                    "thread_total_all_tokens": (
                        total_usage.get("total_input_tokens", 0) +
                        total_usage.get("total_output_tokens", 0) +
                        total_usage.get("total_cache_creation_tokens", 0) +
                        total_usage.get("total_cache_read_tokens", 0)
                    )
                })

        # Agregar costos del turno actual y totales acumulativos si existen
        if "total_costs" in conversations[thread_id]:
            total_costs = conversations[thread_id]["total_costs"]
            if "usage" in response_data and response_data["usage"]:
                # Calcular costos del turno actual
                current_usage = response_data["usage"]
                current_cost_input = (current_usage.get("input_tokens", 0) / 1_000_000) * cost_base_input
                current_cost_output = (current_usage.get("output_tokens", 0) / 1_000_000) * cost_output
                current_cost_cache_creation = (current_usage.get("cache_creation_input_tokens", 0) / 1_000_000) * cost_cache_write_5m
                current_cost_cache_read = (current_usage.get("cache_read_input_tokens", 0) / 1_000_000) * cost_cache_read
                current_total_cost = current_cost_input + current_cost_output + current_cost_cache_creation + current_cost_cache_read

                response_data["usage"].update({
                    # Costos del turno actual (USD)
                    "current_cost_input_usd": round(current_cost_input, 6),
                    "current_cost_output_usd": round(current_cost_output, 6),
                    "current_cost_cache_creation_usd": round(current_cost_cache_creation, 6),
                    "current_cost_cache_read_usd": round(current_cost_cache_read, 6),
                    "current_total_cost_usd": round(current_total_cost, 6),

                    # Costos acumulativos del thread (USD)
                    "thread_total_cost_input_usd": round(total_costs.get("total_cost_input", 0), 6),
                    "thread_total_cost_output_usd": round(total_costs.get("total_cost_output", 0), 6),
                    "thread_total_cost_cache_creation_usd": round(total_costs.get("total_cost_cache_creation", 0), 6),
                    "thread_total_cost_cache_read_usd": round(total_costs.get("total_cost_cache_read", 0), 6),
                    "thread_total_cost_all_usd": round(total_costs.get("total_cost_all", 0), 6)
                })

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
        # Realizar la solicitud POST al webhook de n8n original
        response = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        response.raise_for_status()

        logger.info(
            f"Webhook de n8n respondió con status {response.status_code}: {response.text}"
        )

        # NUEVO: Envío al webhook adicional
        # Obtener la URL del nuevo webhook desde variables de entorno
        new_webhook_url = os.environ.get('WEBHOOK_URL_NUEVO_LINK')

        if new_webhook_url:
            # Preparar datos específicos para el nuevo webhook
            new_data = {
                "pedido_id": pedido_id,
                "telefono": telefono,
                "formato": forma,
                "link": link
            }

            logger.info(f"Enviando datos al nuevo webhook de n8n: {new_data}")

            # Realizar la solicitud POST al nuevo webhook
            new_response = requests.post(new_webhook_url, json=new_data, timeout=10)
            new_response.raise_for_status()

            logger.info(
                f"Nuevo webhook de n8n respondió con status {new_response.status_code}: {new_response.text}"
            )
        else:
            logger.warning("N8N_NUEVO_WEBHOOK_URL no está definido en el archivo .env")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error al enviar datos a webhook de n8n: {e}")
        return jsonify({
            "error":
            "No se pudo procesar el pago. Inténtalo de nuevo más tarde."
        }), 500

    # Construir la URL de redirección a Bold
    bold_url = f"https://checkout.bold.co/payment/{link}"
    logger.info(f"Redireccionando al usuario a: {bold_url}")

    # Redireccionar al usuario a la URL de Bold
    return redirect(bold_url, code=302)

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
