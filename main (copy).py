import json
import requests
import random
import google.genai as genai
from google.genai import types
import base64
import os
import time
import re
from flask import Flask, request, jsonify
import anthropic
from threading import Thread, Event
import uuid
import logging
from datetime import datetime
import pytz
from datetime import timedelta
import xmlrpc.client
from bs4 import BeautifulSoup  # Importar BeautifulSoup para convertir HTML a texto

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

# Mapa para asociar valores de 'assistant' con nombres de archivos
ASSISTANT_FILES = {
    1: '1 Asistente Cliente Nuevo.txt',
    2: '2. Asistente Cliente Existente.txt',
    3: '3. Asistente Despues del pago.txt'
}

conversations = {}


class ManyChatAPI:

    def __init__(self):
        self.base_url = 'https://api.manychat.com/fb'
        self.api_key = os.environ.get(
            'MANYCHAT_API_KEY', '2009465:bbd96efc570bd145faa7171b593278e7')

        self.headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        logger.info("Inicializado ManyChatAPI con API key: %s", self.api_key)

    def set_custom_fields(self, subscriber_id, contact_data):
        """Guarda los campos personalizados en ManyChat para crear contacto"""
        logger.debug("Enviando set_custom_fields para subscriber_id: %s",
                     subscriber_id)
        url = f'{self.base_url}/subscriber/setCustomFields'
        payload = {
            "subscriber_id":
            subscriber_id,
            "fields": [{
                "field_name": "Nombre Cliente FG",
                "field_value": contact_data["nombre"]
            }, {
                "field_name": "Apellido Cliente FG",
                "field_value": contact_data["apellido"]
            }, {
                "field_name": "Ciudad Cliente FG",
                "field_value": contact_data["ciudad"]
            }, {
                "field_name": "Cedula",
                "field_value": contact_data["cedula"]
            }, {
                "field_name": "Contactar",
                "field_value": contact_data["contactar"]
            }, {
                "field_name": "ToolCrearContacto",
                "field_value": 1
            }, {
                "field_name": "Solicitud FG",
                "field_value": contact_data["solicitud"]
            }]
        }
        logger.debug("Enviando set_custom_fields con payload: %s", payload)
        response = requests.post(url, headers=self.headers, json=payload)
        logger.info("Respuesta set_custom_fields: %s %s", response.status_code,
                    response.text)
        return response

    def set_custom_fields_agendar_llamada(self, subscriber_id, contact_data):
        """Guarda los campos personalizados en ManyChat para agendar llamada"""
        logger.debug("Enviando set_custom_fields_agendar_llamada para subscriber_id: %s", subscriber_id)
        url = f'{self.base_url}/subscriber/setCustomFields'
        payload = {
            "subscriber_id": subscriber_id,
            "fields": [
               
                {
                    "field_name": "fecha_llamada",
                    "field_value": contact_data["fecha_llamada"]
                },
                {
                    "field_name": "hora_llamada",
                    "field_value": contact_data["hora_llamada"]
                }
            ]
        }
        logger.debug("Enviando set_custom_fields_agendar_llamada con payload: %s", payload)
        response = requests.post(url, headers=self.headers, json=payload)
        logger.info("Respuesta set_custom_fields_agendar_llamada: %s %s", response.status_code, response.text)
        return response

    def send_flow(self, subscriber_id, flow_ns="content20241029204321_898129"):
        """Envía un flujo específico al suscriptor para crear contacto"""
        url = f'{self.base_url}/sending/sendFlow'
        payload = {"subscriber_id": subscriber_id, "flow_ns": flow_ns}
        logger.info("Enviando send_flow con payload: %s", payload)
        response = requests.post(url, headers=self.headers, json=payload)
        logger.info("Respuesta send_flow: %s %s", response.status_code,
                    response.text)
        return response

    # Nuevos métodos para actualizar contacto
    def set_custom_fields_update(self, subscriber_id, contact_data):
        """Actualiza campos personalizados en ManyChat para actualizar contacto"""
        logger.debug(
            "Enviando set_custom_fields_update para subscriber_id: %s",
            subscriber_id)
        url = f'{self.base_url}/subscriber/setCustomFields'
        payload = {
            "subscriber_id":
            subscriber_id,
            "fields": [{
                "field_name": "Solicitud FG",
                "field_value": contact_data["solicitud"]
            }]
        }
        logger.debug("Enviando set_custom_fields_update con payload: %s",
                     payload)
        response = requests.post(url, headers=self.headers, json=payload)
        logger.info("Respuesta set_custom_fields_update: %s %s",
                    response.status_code, response.text)
        return response

    def send_flow_update(self,
                         subscriber_id,
                         flow_ns="content20241120044926_071414"):
        """Envía un flujo específico al suscriptor para actualizar contacto"""
        url = f'{self.base_url}/sending/sendFlow'
        payload = {"subscriber_id": subscriber_id, "flow_ns": flow_ns}
        logger.info("Enviando send_flow_update con payload: %s", payload)
        response = requests.post(url, headers=self.headers, json=payload)
        logger.info("Respuesta send_flow_update: %s %s", response.status_code,
                    response.text)
        return response

import re

def remove_thinking_block(text):
    """
    Elimina todos los bloques <thinking>...</thinking> del texto.

    Args:
        text (str): El texto del cual se eliminarán los bloques <thinking>.

    Returns:
        str: El texto limpio sin los bloques <thinking>.
    """
    pattern = re.compile(r'<thinking>.*?</thinking>', re.DOTALL | re.IGNORECASE)
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


def save_contact(contact_data, subscriber_id):
    """
    Función principal para guardar contacto y enviar flow
    """
    logger.info("Iniciando save_contact con datos: %s", contact_data)
    logger.debug("subscriber_id en save_contact: %s", subscriber_id)
    try:
        manychat = ManyChatAPI()
        subscriber_id = subscriber_id  # Ajustar según necesidad
        logger.debug("Subscriber ID: %s", subscriber_id)

        # Paso 1: Guardar campos
        fields_response = manychat.set_custom_fields(subscriber_id,
                                                     contact_data)
        if fields_response.status_code not in [200, 201]:
            logger.error("Error al guardar campos: %s", fields_response.text)
            return {
                "status": "error",
                "message": f"Error al guardar campos: {fields_response.text}",
                "status_code": fields_response.status_code
            }

        # Paso 2: Enviar flow
        flow_response = manychat.send_flow(subscriber_id)

        # Construir respuesta final
        result = {
            "status":
            "success"
            if flow_response.status_code in [200, 201] else "partial_success",
            "message":
            "Proceso completado exitosamente" if flow_response.status_code
            in [200, 201] else "Campos guardados pero error al enviar flow",
            "fields_response":
            fields_response.json(),
            "flow_response":
            flow_response.json()
            if flow_response.status_code in [200, 201] else None,
            "data":
            contact_data
        }

        logger.info("save_contact result: %s", result)
        return result

    except Exception as e:
        logger.exception("Error en save_contact: %s", e)
        return {
            "status": "error",
            "message": f"Error al procesar la solicitud: {str(e)}"
        }


def agendar_llamada(tool_input, subscriber_id):
    """
    Función para agendar una llamada y enviar un flujo específico en ManyChat
    """
    logger.info("Iniciando agendar_llamada con datos: %s", tool_input)
    logger.debug("subscriber_id en agendar_llamada: %s", subscriber_id)
    try:
        manychat = ManyChatAPI()
        # **AQUI CAMBIAS EL FLOW_NS AL QUE DESEAS**
        flow_ns = "content20241105191240_679356"  # **Este es el flujo para agendar llamada**

        # Extraer los datos del input
        nombre_contacto = tool_input.get("nombre_del_contacto")
        #telefono_contacto = tool_input.get("telefono_contacto")
        fecha_llamada = tool_input.get("fecha_llamada")
        hora_llamada = tool_input.get("hora_llamada")

        # Validar que los datos obligatorios estén presentes
        if not all([nombre_contacto, fecha_llamada, hora_llamada]):
            return {
                "status": "error",
                "message": "Faltan datos obligatorios para agendar la llamada."
            }

        # Crear un diccionario con los datos para ManyChat
        contact_data = {
            #"telefono_contacto": telefono_contacto,
            "fecha_llamada": fecha_llamada,
            "hora_llamada": hora_llamada
        }

        # Paso 1: Guardar campos personalizados en ManyChat usando la función específica
        fields_response = manychat.set_custom_fields_agendar_llamada(subscriber_id, contact_data)
        if fields_response.status_code not in [200, 201]:
            logger.error("Error al guardar campos en ManyChat: %s", fields_response.text)
            return {
                "status": "error",
                "message": f"Error al guardar campos en ManyChat: {fields_response.text}",
                "status_code": fields_response.status_code
            }

        # Paso 2: Enviar el flujo en ManyChat
        flow_response = manychat.send_flow(subscriber_id, flow_ns)
        if flow_response.status_code not in [200, 201]:
            logger.error("Error al enviar el flujo en ManyChat: %s", flow_response.text)
            return {
                "status": "partial_success",
                "message": f"Campos guardados pero error al enviar flujo en ManyChat: {flow_response.text}",
                "fields_response": fields_response.json(),
                "flow_response": flow_response.text,
                "data": contact_data
            }

        # Construir respuesta final
        result = {
            "status": "success",
            "message": "Llamada agendada exitosamente",
            "fields_response": fields_response.json(),
            "flow_response": flow_response.json(),
            "data": contact_data
        }

        logger.info("agendar_llamada result: %s", result)
        return result

    except Exception as e:
        logger.exception("Error en agendar_llamada: %s", e)
        return {
            "status": "error",
            "message": f"Error al procesar la solicitud: {str(e)}"
        }

def update_contact(contact_data, subscriber_id):
    """
    Función para actualizar la descripción de una oportunidad/lead en Odoo CRM,
    actualizar campos personalizados en ManyChat y enviar un flujo.
    """
    logger.info("Iniciando update_contact con datos: %s", contact_data)
    logger.debug("subscriber_id en update_contact: %s", subscriber_id)
    try:
        manychat = ManyChatAPI()
        logger.debug("Subscriber ID: %s", subscriber_id)

        # Paso 1: Actualizar campos personalizados específicos para actualizar contacto
        fields_response = manychat.set_custom_fields_update(
            subscriber_id, contact_data)
        if fields_response.status_code not in [200, 201]:
            logger.error("Error al actualizar campos: %s",
                         fields_response.text)
            return {
                "status": "error",
                "message":
                f"Error al actualizar campos: {fields_response.text}",
                "status_code": fields_response.status_code
            }

        # Paso 2: Enviar flujo específico para actualizar contacto
        flow_response = manychat.send_flow_update(subscriber_id)
        if flow_response.status_code not in [200, 201]:
            logger.error("Error al enviar flujo: %s", flow_response.text)
            return {
                "status": "partial_success",
                "message":
                f"Campos actualizados pero error al enviar flujo: {flow_response.text}",
                "fields_response": fields_response.json(),
                "flow_response": flow_response.text,
                "data": contact_data
            }

        # Construir respuesta final
        result = {
            "status": "success",
            "message": "Proceso de actualización completado exitosamente",
            "fields_response": fields_response.json(),
            "flow_response": flow_response.json(),
            "data": contact_data
        }

        logger.info("update_contact result: %s", result)
        return result

    except Exception as e:
        logger.exception("Error en update_contact: %s", e)
        return {
            "status": "error",
            "message": f"Error al procesar la solicitud: {str(e)}"
        }



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

        # Mapear nombres de herramientas a funciones
        tool_functions = {
            "crear_contacto": save_contact,
            "agendar_llamada": agendar_llamada,
            "crear_actividad": update_contact
        }

        # Ajustar assistant_content para incluir cache_control si está habilitado
        assistant_content = [{"type": "text", "text": assistant_content_text}]

        #logger.info(assistant_content)

        if use_cache_control:
            assistant_content[0]["cache_control"] = {"type": "ephemeral"}

        # Iniciar la interacción con el modelo de Anthropic utilizando beta.prompt_caching
        while True:
            # logger.info("IGRESE TY3TRTR2YTR432RYT4R23TR4Y23YT4RY2RYT4RYRY3RY32RY32RY")

            response = client.beta.prompt_caching.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.8,
                system=assistant_content,
                messages=conversation_history,
                tools=tools)
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
                logger.info("Respuesta ssssssssssssssssssssssssssssssssssssss %s",  response)
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



def generate_response_gemini(api_key, message, assistant_content_text, thread_id,
                             event, subscriber_id, use_cache_control):
    logger.info("Generando respuesta con Gemini para thread_id: %s", thread_id)
    logger.debug("subscriber_id en generate_response_gemini: %s", subscriber_id)

    try:
        # Configurar las credenciales de autenticación
        if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"

        # Leer proyecto y ubicación desde variables de entorno o usar valores por defecto
        project = os.environ.get('GCP_PROJECT', 'gemini-cocoson')  # Reemplaza con tu ID de proyecto
        location = os.environ.get('GCP_LOCATION', 'us-central1')

        client = genai.Client(
            vertexai=True,
            project=project,
            location=location
        )

        model = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-exp')

        conversation_history = conversations[thread_id]["messages"]

        # Agregar el mensaje del usuario al historial de conversación
        user_message_content = {"type": "text", "text": message}
        if use_cache_control:
            user_message_content["cache_control"] = {"type": "ephemeral"}

        conversation_history.append({
            "role": "user",
            "content": [user_message_content]
        })
        logger.debug("Historial de conversación actualizado: %s", conversation_history)

        # Construir la lista de contenidos para la API de Gemini
        contents = []
        for msg in conversation_history:
            role = msg['role']
            content_blocks = msg['content']
            message_text = ''
            for block in content_blocks:
                if block['type'] == 'text':
                    message_text += block['text']

            # Mapear roles a los esperados por Gemini
            if role == 'assistant':
                gemini_role = 'model'
            elif role == 'user':
                gemini_role = 'user'
            else:
                gemini_role = role  # En caso de otros roles

            contents.append(types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(message_text)]
            ))

        # Construir la instrucción del sistema
        system_instruction = [types.Part.from_text(assistant_content_text)]

        # Configurar los parámetros de generación
        generate_content_config = types.GenerateContentConfig(
            temperature=0.8,
            top_p=0.95,
            max_output_tokens=1000,
            response_modalities=["TEXT"],
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="OFF"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="OFF"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="OFF"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="OFF"
                )
            ],
            system_instruction=system_instruction,
        )

        # Generar la respuesta
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

        # Extraer el texto generado por el modelo
        generated_text = response.candidates[0].content.parts[0].text

        # Agregar la respuesta del asistente al historial de conversación
        assistant_message_content = {"type": "text", "text": generated_text}
        if use_cache_control:
            assistant_message_content["cache_control"] = {"type": "ephemeral"}

        conversation_history.append({
            "role": "assistant",
            "content": [assistant_message_content]
        })
        logger.debug("Respuesta del asistente añadida al historial")

        # Actualizar el estado de la conversación
        conversations[thread_id]["response"] = generated_text
        conversations[thread_id]["status"] = "completed"
        logger.info("Respuesta generada para thread_id: %s", thread_id)

    except Exception as e:
        logger.exception("Error en generate_response_gemini para thread_id %s: %s", thread_id, e)
        conversations[thread_id]["response"] = f"Error: {str(e)}"
        conversations[thread_id]["status"] = "error"
    finally:
        event.set()
        logger.debug("Evento establecido para thread_id: %s", thread_id)

@app.route('/sendmensaje', methods=['POST'])
def send_message():
    logger.info("Endpoint /sendmensaje llamado")
    data = request.json
    api_key = data.get('api_key')
    message = data.get('message')
    assistant_value = data.get('assistant')
    thread_id = data.get('thread_id')
    subscriber_id = data.get('subscriber_id')  # Nuevo parámetro
    thinking = data.get('thinking', 1)  # Nuevo parámetro con valor por defecto 1
    modelID = data.get('modelID', 'anthropic')  # Nuevo parámetro con valor por defecto 'anthropic'
    logger.info("subscriber_id recibido: %s", subscriber_id)
    logger.info("thinking recibido: %s", thinking)
    logger.info("ModelID recibido: %s", modelID)
    use_cache_control = data.get('use_cache_control', False)
    logger.info("Cache control es %s", use_cache_control)
    logger.info("Mensaje recibido: %s", message)

    # Extraer las variables adicionales
    variables = data.copy()
    variables.pop('api_key', None)
    variables.pop('message', None)
    variables.pop('assistant', None)
    variables.pop('thread_id', None)
    variables.pop('subscriber_id', None)
    variables.pop('thinking', None)
    variables.pop('modelID', None)  # Remover 'modelID' de las variables adicionales

    if not subscriber_id:
        logger.warning("Falta el 'subscriber_id' en la solicitud")
        return jsonify({"error": "Falta el 'subscriber_id'"}), 400

    # Intentar convertir subscriber_id a entero si es necesario
    try:
        subscriber_id = int(subscriber_id)
    except (TypeError, ValueError):
        logger.warning("El 'subscriber_id' proporcionado no es válido: %s",
                       subscriber_id)
        return jsonify(
            {"error": "El 'subscriber_id' proporcionado no es válido"}), 400

    if not api_key:
        logger.warning("Falta la clave API en la solicitud")
        return jsonify({"error": "Falta la clave API"}), 400

    if not thread_id or not thread_id.startswith('thread_'):
        thread_id = f"thread_{uuid.uuid4()}"
        logger.info("Generado nuevo thread_id: %s", thread_id)

    if assistant_value not in ASSISTANT_FILES:
        logger.warning("Valor de 'assistant' inválido: %s", assistant_value)
        return jsonify({"error": "Valor de 'assistant' inválido"}), 400

    assistant_file = ASSISTANT_FILES[assistant_value]
    assistant_path = os.path.join(os.path.dirname(__file__), assistant_file)

    try:
        with open(assistant_path, 'r', encoding='utf-8') as file:
            assistant_content = file.read()
            logger.info("Archivo de asistente cargado: %s", assistant_file)
    except FileNotFoundError:
        logger.error("Archivo %s no encontrado.", assistant_file)
        return jsonify({"error":
                        f"Archivo {assistant_file} no encontrado."}), 500
    except Exception as e:
        logger.exception("Error al leer el archivo %s: %s", assistant_file, e)
        return jsonify({"error": f"Error al leer el archivo: {str(e)}"}), 500

    try:
        pattern = re.compile(r'\{\{(\w+)\}\}')

        def replace_placeholder(match):
            key = match.group(1)
            return str(variables.get(key, match.group(0)))

        assistant_content = pattern.sub(replace_placeholder, assistant_content)
        logger.debug("Contenido del asistente procesado con variables: %s",
                     assistant_content)
    except Exception as e:
        logger.exception("Error al procesar el contenido del asistente: %s", e)
        return jsonify({"error":
                        f"Error al procesar el contenido: {str(e)}"}), 500

    if thread_id not in conversations:
        conversations[thread_id] = {
            "status": "processing",
            "response": None,
            "messages": [],
            "assistant": assistant_value,
            "thinking": thinking  # Almacenar el valor de 'thinking'
        }
        logger.info("Creada nueva conversación para thread_id: %s", thread_id)
    else:
        if assistant_value is not None:
            conversations[thread_id]["assistant"] = assistant_value
            conversations[thread_id]["thinking"] = thinking  # Actualizar el valor de 'thinking'
            logger.debug("Actualizado valor de assistant y thinking para thread_id: %s",
                         thread_id)
        else:
            assistant_value = conversations[thread_id]["assistant"]
            thinking = conversations[thread_id].get("thinking", 0)  # Obtener el valor actual de 'thinking'

    conversations[thread_id]["status"] = "processing"
    event = Event()

    # Decidir qué función de generación de respuesta usar según modelID
    if modelID.lower() == 'gemini':
        thread = Thread(target=generate_response_gemini,
                        args=(api_key, message, assistant_content, thread_id,
                              event, subscriber_id, use_cache_control))
        logger.info("Usando generate_response_gemini para thread_id: %s", thread_id)
    else:
        thread = Thread(target=generate_response,
                        args=(api_key, message, assistant_content, thread_id,
                              event, subscriber_id, use_cache_control))
        logger.info("Usando generate_response (Anthropic) para thread_id: %s", thread_id)

    logger.info("Iniciando hilo con subscriber_id: %s", subscriber_id)
    thread.start()
    logger.info("Thread iniciado para generar respuesta en thread_id: %s",
                thread_id)

    event.wait(timeout=8)
    logger.debug("Esperada respuesta para thread_id: %s", thread_id)
    # Logs adicionales para seguimiento
    logger.debug("Estado de la conversación para thread_id %s: %s", thread_id,
                 conversations[thread_id]["status"])
    logger.debug("Respuesta del asistente para thread_id %s: %s", thread_id,
                 conversations[thread_id]["response"])

    if conversations[thread_id]["status"] == "completed":
        logger.info("Proceso completado para thread_id: %s", thread_id)
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

        response_data = {
            "response": cleaned_response,
            "thread_id": thread_id,
            "usage": conversations[thread_id].get("usage")
        }
        logger.info("Datos de respuesta enviados al cliente: %s", response_data)
        return jsonify(response_data)
    else:
        logger.info("Run_id en espera para thread_id: %s", thread_id)
        return jsonify({
            "response": "run_id en espera",
            "thread_id": thread_id
        })


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
            original_error = conversations[thread_id].get('response', 'Error desconocido')
            # Obtener el valor de 'thinking'
            current_thinking = conversations[thread_id].get("thinking", 0)
            if current_thinking == 1:
                # Limpiar el mensaje de error eliminando el bloque <thinking>
                cleaned_error = remove_thinking_block(original_error)
            else:
                # No limpiar el mensaje de error
                cleaned_error = original_error

            return jsonify(
                {"response": f"Error: {cleaned_error}"})
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
            return jsonify({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}), 400

        # Extraer credenciales y parámetros del evento
        url = datos.get('url')
        db = datos.get('db')
        username = datos.get('username')
        password = datos.get('password')

        # Datos del evento
        name = datos.get('name') # Nombre del evento
        start = datos.get('start') # Fecha y hora de inicio
        stop = datos.get('stop') # Fecha y hora de fin
        duration = datos.get('duration')
        description = datos.get('description')
        user_id = datos.get('user_id')

        # Campos opcionales
        allday = datos.get('allday', False) # Evento de todo el día (opcional)
        partner_ids = datos.get('partner_ids', []) # Lista de IDs de partners (opcional)
        location = datos.get('location', '')

        # Verificar que todos los campos obligatorios están presentes
        campos_obligatorios = [url, db, username, password, name, start, duration]
        if not all(campos_obligatorios):
            return jsonify({'error': 'Faltan campos obligatorios en la solicitud.'}), 400

        # Autenticación con Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return jsonify({'error': 'Autenticación fallida. Verifica tus credenciales.'}), 401

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
             datos_evento['stop'] =  (datetime.fromisoformat(start) + timedelta(hours=float(duration))).isoformat()

        # Crear el evento en el calendario
        evento_id = models.execute_kw(db, uid, password, 'calendar.event', 'create', [datos_evento])

        return jsonify({'mensaje': f'Evento creado con ID: {evento_id}', 'id': evento_id}), 200

    except xmlrpc.client.Fault as fault:
        return jsonify({'error': f"Error al comunicarse con Odoo: {fault}"}), 500
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


if __name__ == '__main__':
    logger.info("Iniciando la aplicación Flask")
    app.run(host='0.0.0.0', port=8080)
