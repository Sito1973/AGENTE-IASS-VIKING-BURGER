import json
import requests
from urllib.parse import urlparse
import os
import tempfile
import re
from flask import Flask, request, jsonify
import anthropic
from threading import Thread, Event
import uuid
import os  # Importar módulo para manejar rutas de archivos

app = Flask(__name__)

# Mapa para asociar valores de 'assistant' con nombres de archivos
ASSISTANT_FILES = {
    1: 'ASISTENTE_PRINCIPAL.TXT',
    2: 'ASISTENTE_CLIENTES_EXISTENTES.TXT',
    3: 'ASISTENTE_EXTRACTOR_DATOS_NUEVO.TXT',
    4: 'ASISTENTE_EXTRACTOR_DATOS_EXISTENTE.TXT' # Asegúrate de que este archivo exista
}

conversations = {}

def generate_response(api_key, message, assistant_content, thread_id, event):
    try:
        client = anthropic.Anthropic(api_key=api_key)
        conversation_history = conversations[thread_id]["messages"]
        conversation_history.append({
            "role": "user",
            "content": [{"type": "text", "text": message}]
        })

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0.8,
            system=assistant_content,
            messages=conversation_history
        )

        conversation_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": response.content[0].text}]
        })

        conversations[thread_id]["response"] = response.content[0].text
        conversations[thread_id]["status"] = "completed"
    except Exception as e:
        conversations[thread_id]["response"] = str(e)
        conversations[thread_id]["status"] = "error"
    finally:
        event.set()

@app.route('/sendmensaje', methods=['POST'])
def send_message():
    data = request.json
    api_key = data.get('api_key')
    message = data.get('message')
    assistant_value = data.get('assistant')
    thread_id = data.get('thread_id')

    # Extraer las variables adicionales
    variables = data.copy()
    variables.pop('api_key', None)
    variables.pop('message', None)
    variables.pop('assistant', None)
    variables.pop('thread_id', None)

    if not api_key:
        return jsonify({"error": "Falta la clave API"}), 400

    if not thread_id or not thread_id.startswith('thread_'):
        thread_id = f"thread_{uuid.uuid4()}"

    # Verificar si el valor de 'assistant' es válido
    if assistant_value not in ASSISTANT_FILES:
        return jsonify({"error": "Valor de 'assistant' inválido. Debe ser 1, 2 o 3."}), 400

    # Obtener el nombre del archivo correspondiente
    assistant_file = ASSISTANT_FILES[assistant_value]
    # Definir la ruta completa del archivo
    assistant_path = os.path.join(os.path.dirname(__file__), assistant_file)

    # Leer el contenido del archivo TXT
    try:
        with open(assistant_path, 'r', encoding='utf-8') as file:
            assistant_content = file.read()
    except FileNotFoundError:
        return jsonify({"error": f"Archivo {assistant_file} no encontrado."}), 500
    except Exception as e:
        return jsonify({"error": f"Error al leer el archivo: {str(e)}"}), 500

    # Reemplazar los marcadores de posición con los valores proporcionados
    try:
        # Patrón para encontrar {{variable}}
        pattern = re.compile(r'\{\{(\w+)\}\}')

        # Función para reemplazar cada coincidencia
        def replace_placeholder(match):
            key = match.group(1)
            return str(variables.get(key, match.group(0)))

        assistant_content = pattern.sub(replace_placeholder, assistant_content)
    except Exception as e:
        return jsonify({"error": f"Error al procesar el contenido: {str(e)}"}), 500

    if thread_id not in conversations:
        conversations[thread_id] = {
            "status": "processing",
            "response": None,
            "messages": [],
            "assistant": assistant_value
        }
    else:
        if assistant_value is not None:
            conversations[thread_id]["assistant"] = assistant_value
        else:
            assistant_value = conversations[thread_id]["assistant"]

    conversations[thread_id]["status"] = "processing"
    event = Event()
    thread = Thread(target=generate_response, args=(
        api_key, message, assistant_content, thread_id, event))
    thread.start()

    event.wait(timeout=8)

    if conversations[thread_id]["status"] == "completed":
        return jsonify({"response": conversations[thread_id]["response"], "thread_id": thread_id})
    else:
        return jsonify({"response": "run_id en espera", "thread_id": thread_id})


@app.route('/extract', methods=['POST'])
def extract():
    try:
        # Verificar si el body contiene un JSON bien formateado
        if not request.is_json:
            error_result = {
                "status": "error",
                "message": "El body de la solicitud no está en formato JSON válido"
            }
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

        return jsonify(result)

    except Exception as e:
        # Manejar cualquier error que pueda ocurrir
        error_result = {
            "status": "error",
            "message": str(e)
        }
        return jsonify(error_result), 400

@app.route('/time', methods=['POST'])
def convert_time():
    data = request.json
    input_time = data.get('datetime')

    if not input_time:
        return jsonify({"error": "Falta el parámetro 'datetime'"}), 400

    try:
        local_time = datetime.fromisoformat(input_time)
        utc_time = local_time.astimezone(pytz.utc)
        new_time = utc_time + timedelta(hours=1)
        new_time_str = new_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        return jsonify({"original": input_time, "converted": new_time_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Agrega el nuevo endpoint /upload
@app.route('/upload', methods=['POST'])
def upload_file():
    data = request.json
    url = data.get('url')
    is_shared = data.get('is_shared', True)  # Por defecto, true si no se proporciona
    targetable_id = data.get('targetable_id')
    targetable_type = data.get('targetable_type')
    name = data.get('name', 'file')  # Nombre por defecto si no se proporciona

    # Verificar que los parámetros necesarios estén presentes
    if not url or not targetable_id or not targetable_type:
        return jsonify({"error": "Faltan parámetros requeridos (url, targetable_id, targetable_type)"}), 400

    # Descargar el archivo desde la URL
    response = requests.get(url)
    if response.status_code == 200:
        file_content = response.content
    else:
        return jsonify({"error": "No se pudo descargar el archivo desde la URL", "status_code": response.status_code}), 400

    # Obtener la clave API y la URL base de Freshsales desde variables de entorno
    FRESHSALES_API_KEY = os.environ.get('FRESHSALES_API_KEY', "nZKxdpwoRkt6BUnVks2d9Q")
    FRESHSALES_BASE_URL = os.environ.get('FRESHSALES_BASE_URL', 'https://cocinandosonrisas.myfreshworks.com')

    if not FRESHSALES_API_KEY:
        return jsonify({"error": "Falta la clave API de Freshsales"}), 500

    headers = {
        'Authorization': f'Token token={FRESHSALES_API_KEY}'
    }

    # Asegurar que is_shared sea una cadena 'true' o 'false'
    is_shared_str = 'true' if is_shared else 'false'

    data = {
        'file_name': name,
        'is_shared': is_shared_str,
        'targetable_id': str(targetable_id),
        'targetable_type': targetable_type
    }

    # Obtener el tipo de contenido del archivo
    content_type = response.headers.get('Content-Type', 'application/octet-stream')

    files = {
        'file': (name, file_content, content_type)
    }

    upload_url = FRESHSALES_BASE_URL + '/crm/sales/documents'

    upload_response = requests.post(upload_url, headers=headers, data=data, files=files)

    try:
        response_json = upload_response.json()
    except ValueError:
        response_json = None

    if upload_response.status_code in (200, 201):
        # Subida exitosa
        return jsonify({"message": "Archivo subido exitosamente", "response": response_json}), upload_response.status_code
    else:
        # Error en la subida
        return jsonify({"error": "No se pudo subir el archivo", "details": response_json or upload_response.text}), upload_response.status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)