"""
GENERATE RESPONSE - ANTHROPIC API
=================================
Función lista para copiar y pegar en otros proyectos.
Incluye: Cache Management, Thinking, Tool Use, Costos

REQUISITOS:
- pip install anthropic
- Variable de entorno: ANTHROPIC_API_KEY

DEPENDENCIAS QUE DEBES TENER EN TU MAIN:
- conversations = {}  (diccionario global)
- thread_locks = {}   (diccionario global)
- ANTHROPIC_DEBUG = os.getenv("ANTHROPIC_DEBUG", "0").strip() in {"1", "true", "True", "yes", "YES"}
- Funciones de tools (crear_pedido, enviar_menu, etc.)
- Función validate_conversation_history()
- Función get_field()
- Función call_anthropic_api()
"""

import os
import json
import time
import logging
import threading
import anthropic
from functools import wraps

# ============================================
# CONFIGURACIÓN
# ============================================
logger = logging.getLogger(__name__)

# Variable para debug (activar con ANTHROPIC_DEBUG=1 en .env)
ANTHROPIC_DEBUG = os.getenv("ANTHROPIC_DEBUG", "0").strip() in {"1", "true", "True", "yes", "YES"}

# Diccionarios globales (deben existir en tu main)
conversations = {}
thread_locks = {}


# ============================================
# FUNCIONES AUXILIARES NECESARIAS
# ============================================
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
                    time.sleep(wait_time)
        return wrapper
    return decorator


@retry_on_exception(max_retries=3, initial_wait=1)
def call_anthropic_api(client, **kwargs):
    """Llama a la API de Anthropic con reintentos automáticos."""
    return client.messages.create(**kwargs)


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


def validate_conversation_history(history):
    """Valida que la estructura del historial sea correcta para Anthropic."""
    if not isinstance(history, list):
        logger.error("El historial no es una lista")
        return False

    for message in history:
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


# ============================================
# FUNCIÓN PRINCIPAL - GENERATE RESPONSE
# ============================================
def generate_response(api_key,
                      message,
                      assistant_content_text,
                      thread_id,
                      event,
                      subscriber_id,
                      use_cache_control,
                      llmID=None,
                      cost_base_input=3.0,
                      cost_cache_write_5m=3.75,
                      cost_cache_read=0.30,
                      cost_output=15.0,
                      tools=None,
                      tool_functions=None):
    """
    Genera una respuesta usando la API de Anthropic con soporte para:
    - Cache Management automático (máximo 4 bloques, TTL 5 min)
    - Extended Thinking (budget_tokens: 1200)
    - Tool Use con manejo de errores
    - Cálculo de costos acumulativos

    Args:
        api_key: API key de Anthropic
        message: Mensaje del usuario
        assistant_content_text: System prompt
        thread_id: ID del hilo de conversación
        event: threading.Event para señalizar completado
        subscriber_id: ID del suscriptor (para tools)
        use_cache_control: Habilitar cache control
        llmID: ID del modelo (default: claude-haiku-4-5-20251001)
        cost_base_input: Costo por millón de tokens de input
        cost_cache_write_5m: Costo por millón de tokens de cache write
        cost_cache_read: Costo por millón de tokens de cache read
        cost_output: Costo por millón de tokens de output
        tools: Lista de herramientas (formato Anthropic con input_schema)
        tool_functions: Diccionario {nombre_tool: función}
    """
    if not llmID:
        llmID = "claude-haiku-4-5-20251001"  # Modelo por defecto

    if tools is None:
        tools = []

    if tool_functions is None:
        tool_functions = {}

    logger.info("Intentando adquirir lock para thread_id: %s", thread_id)
    lock = thread_locks.get(thread_id)
    if not lock:
        logger.error("No se encontró lock para thread_id: %s", thread_id)
        thread_locks[thread_id] = threading.Lock()
        lock = thread_locks[thread_id]

    if lock and lock.locked():
        if ANTHROPIC_DEBUG:
            logger.info("Lock ocupado para thread_id: %s", thread_id)

    with lock:
        logger.info("Lock adquirido para thread_id: %s", thread_id)
        start_time = time.time()

        try:
            # Registrar la hora de última actividad para limpieza
            conversations[thread_id]["last_activity"] = time.time()

            client = anthropic.Anthropic(api_key=api_key)
            conversation_history = conversations[thread_id]["messages"]

            # ========================================
            # SISTEMA AUTOMÁTICO DE CACHE MANAGEMENT
            # ========================================
            cache_blocks_used = 0
            max_cache_blocks = 4
            current_time = time.time()

            # Verificar si necesitamos resetear cache (290 segundos = 4 min 50 seg)
            last_activity_time = conversations[thread_id].get("last_activity", 0)
            cache_expired_by_inactivity = (current_time - last_activity_time) > 290
            is_new_conversation = last_activity_time == 0 or len(conversation_history) == 0

            if is_new_conversation:
                conversations[thread_id]["cache_reset"] = True
                conversations[thread_id]["last_activity"] = current_time
                logger.info("Cache inicial para nueva conversación thread_id: %s", thread_id)
            elif cache_expired_by_inactivity:
                conversations[thread_id]["cache_reset"] = True
                conversations[thread_id]["last_activity"] = current_time
                logger.info("Cache reseteado por inactividad para thread_id: %s", thread_id)
            else:
                conversations[thread_id]["cache_reset"] = False
                conversations[thread_id]["last_activity"] = current_time
                time_remaining = 290 - (current_time - last_activity_time)
                logger.info("Cache activo para thread_id: %s (TTL restante: %.0f segundos)", thread_id, time_remaining)

            # Análisis de conversación para cache inteligente
            messages_count = len(conversation_history)
            current_stage = conversations[thread_id].get("assistant", 0)

            # Tokens mínimos para cache según modelo
            model_cache_minimum = 2048 if "haiku" in llmID.lower() else 1024

            def estimate_tokens(text):
                return len(text) // 4

            def clean_existing_cache_controls(conv_history):
                for msg in conv_history:
                    if "content" in msg and isinstance(msg["content"], list):
                        for content_item in msg["content"]:
                            if isinstance(content_item, dict) and "cache_control" in content_item:
                                del content_item["cache_control"]
                return conv_history

            def count_existing_cache_blocks(conv_history):
                cache_count = 0
                for msg in conv_history:
                    if "content" in msg and isinstance(msg["content"], list):
                        for content_item in msg["content"]:
                            if isinstance(content_item, dict) and "cache_control" in content_item:
                                cache_count += 1
                return cache_count

            # Limpiar cache existentes si hay reset
            if conversations[thread_id].get("cache_reset", False):
                conversation_history = clean_existing_cache_controls(conversation_history)
                cache_blocks_used = 0
                logger.info("Cache controls limpiados para thread_id: %s", thread_id)
            else:
                cache_blocks_used = count_existing_cache_blocks(conversation_history)
                logger.info("Cache existente mantenido para thread_id: %s (%d bloques)", thread_id, cache_blocks_used)

            # Agregar mensaje del usuario
            user_message_content = {"type": "text", "text": message}
            conversation_history.append({
                "role": "user",
                "content": [user_message_content]
            })

            # Cache incremental del historial
            if cache_blocks_used < max_cache_blocks and len(conversation_history) > 1:
                previous_message = conversation_history[-2]
                if "content" in previous_message and isinstance(previous_message["content"], list):
                    for content_item in previous_message["content"]:
                        if isinstance(content_item, dict) and "cache_control" not in content_item:
                            content_item["cache_control"] = {"type": "ephemeral"}
                            cache_blocks_used += 1
                            logger.info("Historial cached (bloque %d/4) para thread_id: %s", cache_blocks_used, thread_id)
                            break

            # Preparar tools para combinar con system
            tools_text = ""
            tools_tokens = 0
            if tools:
                tools_text = f"\n\n<tools>\n{json.dumps(tools, ensure_ascii=False, indent=2)}\n</tools>\n\n"
                tools_tokens = estimate_tokens(tools_text)
                logger.info("Tools preparadas (%d tokens) para thread_id: %s", tools_tokens, thread_id)

            # Configurar system prompt con cache
            should_apply_system_cache = conversations[thread_id].get("cache_reset", False)

            if should_apply_system_cache and cache_blocks_used < max_cache_blocks:
                combined_content = tools_text + assistant_content_text
                total_tokens = estimate_tokens(combined_content)

                if total_tokens >= model_cache_minimum:
                    assistant_content = [{
                        "type": "text",
                        "text": combined_content,
                        "cache_control": {"type": "ephemeral"}
                    }]
                    cache_blocks_used += 1
                    logger.info("System cached (bloque %d/4) para thread_id: %s", cache_blocks_used, thread_id)
                else:
                    assistant_content = [{"type": "text", "text": assistant_content_text}]
                    logger.info("System sin cache (tokens insuficientes) para thread_id: %s", thread_id)
            else:
                combined_content = tools_text + assistant_content_text
                assistant_content = [{
                    "type": "text",
                    "text": combined_content,
                    "cache_control": {"type": "ephemeral"}
                }]
                cache_blocks_used += 1

            # Cache summary
            cache_summary = {
                "bloques_usados": cache_blocks_used,
                "maximo_permitido": max_cache_blocks,
                "modelo": llmID,
                "stage_actual": current_stage,
                "mensajes_count": messages_count,
            }
            logger.info("CACHE SUMMARY para thread_id %s: %s", thread_id, cache_summary)
            conversations[thread_id]["cache_stats"] = cache_summary

            # Loop de interacción con el modelo
            while True:
                if not validate_conversation_history(conversation_history):
                    logger.error("Estructura de mensajes inválida: %s", conversation_history)
                    raise ValueError("Estructura de conversación inválida")

                try:
                    if ANTHROPIC_DEBUG:
                        logger.info("PAYLOAD ANTHROPIC: %s", conversation_history)

                    logger.info("Llamando a Anthropic API para thread_id: %s", thread_id)
                    api_call_started = time.time()

                    # Preparar headers para cache TTL extendido
                    extra_headers = {}
                    if use_cache_control and any(
                        tool.get("cache_control", {}).get("ttl") == "1h"
                        for tool in tools if isinstance(tool, dict)
                    ):
                        extra_headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11"

                    # Llamar a la API
                    response = call_anthropic_api(
                        client=client,
                        model=llmID,
                        max_tokens=2000,
                        thinking={
                            "type": "enabled",
                            "budget_tokens": 1200
                        },
                        system=assistant_content,
                        tools=tools,
                        tool_choice={
                            "type": "auto",
                            "disable_parallel_tool_use": True
                        },
                        messages=conversation_history,
                        **extra_headers
                    )

                    api_call_elapsed = time.time() - api_call_started

                    if ANTHROPIC_DEBUG:
                        logger.info("Fin llamada Anthropic (%.2fs)", api_call_elapsed)
                        logger.info("RESPUESTA RAW ANTHROPIC: %s", response)

                    # Agregar respuesta al historial - Serializar bloques solo con campos permitidos
                    def serialize_block(block):
                        """Convierte un bloque a dict con solo campos permitidos por Anthropic."""
                        block_type = get_field(block, "type")
                        if block_type == "thinking":
                            return {
                                "type": "thinking",
                                "thinking": get_field(block, "thinking"),
                                "signature": get_field(block, "signature")
                            }
                        elif block_type == "text":
                            return {
                                "type": "text",
                                "text": get_field(block, "text") or ""
                            }
                        elif block_type == "tool_use":
                            return {
                                "type": "tool_use",
                                "id": get_field(block, "id"),
                                "name": get_field(block, "name"),
                                "input": get_field(block, "input")
                            }
                        else:
                            # Para otros tipos, usar model_dump pero limpiar cache_control
                            if hasattr(block, 'model_dump'):
                                d = block.model_dump()
                                d.pop("cache_control", None)
                                return d
                            return dict(block) if isinstance(block, dict) else {"type": block_type}

                    filtered_content = []
                    for block in response.content:
                        block_dict = serialize_block(block)
                        # Filtrar bloques de texto vacíos
                        if block_dict.get("type") == "text" and not block_dict.get("text"):
                            continue
                        filtered_content.append(block_dict)

                    conversation_history.append({
                        "role": "assistant",
                        "content": filtered_content
                    })

                    # Almacenar tokens
                    current_usage = {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
                        "cache_read_input_tokens": response.usage.cache_read_input_tokens,
                    }

                    # Acumular tokens
                    if "total_usage" not in conversations[thread_id]:
                        conversations[thread_id]["total_usage"] = {
                            "total_input_tokens": 0,
                            "total_output_tokens": 0,
                            "total_cache_creation_tokens": 0,
                            "total_cache_read_tokens": 0
                        }

                    conversations[thread_id]["total_usage"]["total_input_tokens"] += current_usage["input_tokens"]
                    conversations[thread_id]["total_usage"]["total_output_tokens"] += current_usage["output_tokens"]
                    conversations[thread_id]["total_usage"]["total_cache_creation_tokens"] += current_usage["cache_creation_input_tokens"]
                    conversations[thread_id]["total_usage"]["total_cache_read_tokens"] += current_usage["cache_read_input_tokens"]

                    # Calcular costos
                    def calculate_costs(tokens, cost_per_mtok):
                        return (tokens / 1_000_000) * cost_per_mtok

                    current_cost_input = calculate_costs(current_usage["input_tokens"], cost_base_input)
                    current_cost_output = calculate_costs(current_usage["output_tokens"], cost_output)
                    current_cost_cache_creation = calculate_costs(current_usage["cache_creation_input_tokens"], cost_cache_write_5m)
                    current_cost_cache_read = calculate_costs(current_usage["cache_read_input_tokens"], cost_cache_read)
                    current_total_cost = current_cost_input + current_cost_output + current_cost_cache_creation + current_cost_cache_read

                    if "total_costs" not in conversations[thread_id]:
                        conversations[thread_id]["total_costs"] = {
                            "total_cost_input": 0.0,
                            "total_cost_output": 0.0,
                            "total_cost_cache_creation": 0.0,
                            "total_cost_cache_read": 0.0,
                            "total_cost_all": 0.0
                        }

                    conversations[thread_id]["total_costs"]["total_cost_input"] += current_cost_input
                    conversations[thread_id]["total_costs"]["total_cost_output"] += current_cost_output
                    conversations[thread_id]["total_costs"]["total_cost_cache_creation"] += current_cost_cache_creation
                    conversations[thread_id]["total_costs"]["total_cost_cache_read"] += current_cost_cache_read
                    conversations[thread_id]["total_costs"]["total_cost_all"] += current_total_cost

                    conversations[thread_id]["usage"] = current_usage

                    logger.info("Tokens - Input: %d, Output: %d, Cache Read: %d, Cache Create: %d",
                                current_usage["input_tokens"], current_usage["output_tokens"],
                                current_usage["cache_read_input_tokens"], current_usage["cache_creation_input_tokens"])

                    # Procesar herramientas
                    if response.stop_reason == "tool_use":
                        tool_use_blocks = [
                            block for block in response.content
                            if get_field(block, "type") == "tool_use"
                        ]
                        logger.info("Tool calls detectadas: %s", tool_use_blocks)

                        if not tool_use_blocks:
                            assistant_response_text = ""
                            for content_block in response.content:
                                if get_field(content_block, "type") == "text":
                                    assistant_response_text += (get_field(content_block, "text") or "")
                            conversations[thread_id]["response"] = assistant_response_text
                            conversations[thread_id]["status"] = "completed"
                            break

                        tool_use = tool_use_blocks[0]
                        tool_name = get_field(tool_use, "name")
                        tool_input = get_field(tool_use, "input")

                        if tool_name in tool_functions:
                            try:
                                result = tool_functions[tool_name](tool_input, subscriber_id)
                                result_json = json.dumps(result)

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
                                conversation_history.append({
                                    "role": "user",
                                    "content": [{
                                        "type": "tool_result",
                                        "tool_use_id": get_field(tool_use, "id"),
                                        "content": f"Error ejecutando '{tool_name}': {str(tool_error)}",
                                        "is_error": True
                                    }],
                                })
                        else:
                            logger.warning("Herramienta desconocida: %s", tool_name)
                            conversation_history.append({
                                "role": "user",
                                "content": [{
                                    "type": "tool_result",
                                    "tool_use_id": get_field(tool_use, "id"),
                                    "content": f"Error: Tool '{tool_name}' is not available",
                                    "is_error": True
                                }],
                            })
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
                    if ANTHROPIC_DEBUG:
                        try:
                            elapsed_api = time.time() - api_call_started
                            logger.warning("Error Anthropic tras %.2fs | thread_id=%s | %s",
                                          elapsed_api, thread_id, api_error)
                        except Exception:
                            logger.warning("Error Anthropic | thread_id=%s | %s", thread_id, api_error)

                    logger.exception("Error en llamada a API para thread_id %s: %s", thread_id, api_error)
                    conversations[thread_id]["response"] = f"error API anthropic: {str(api_error)}"
                    conversations[thread_id]["status"] = "error"
                    break

        except Exception as e:
            logger.exception("Error en generate_response para thread_id %s: %s", thread_id, e)
            conversations[thread_id]["response"] = f"error API anthropic: {str(e)}"
            conversations[thread_id]["status"] = "error"
        finally:
            event.set()
            elapsed_time = time.time() - start_time
            logger.info("Generación completada en %.2f segundos para thread_id: %s", elapsed_time, thread_id)


# ============================================
# EJEMPLO DE USO
# ============================================
"""
# En tu main.py:

from generate_response_anthropic import generate_response, conversations, thread_locks
import threading
import uuid

# Crear thread_id
thread_id = f"thread_{uuid.uuid4()}"

# Inicializar conversación
conversations[thread_id] = {
    "status": "processing",
    "response": None,
    "messages": [],
    "assistant": 0,
    "usage": None,
    "last_activity": 0
}

# Crear lock
thread_locks[thread_id] = threading.Lock()

# Crear evento
event = threading.Event()

# Definir tools (formato Anthropic)
tools = [
    {
        "name": "mi_herramienta",
        "description": "Descripción de la herramienta",
        "input_schema": {
            "type": "object",
            "required": ["parametro"],
            "properties": {
                "parametro": {
                    "type": "string",
                    "description": "Descripción del parámetro"
                }
            }
        }
    }
]

# Definir funciones de tools
def mi_herramienta(tool_input, subscriber_id):
    return {"resultado": "ok"}

tool_functions = {
    "mi_herramienta": mi_herramienta
}

# Ejecutar en hilo
thread = threading.Thread(
    target=generate_response,
    args=(
        os.getenv("ANTHROPIC_API_KEY"),
        "Hola, necesito ayuda",
        "Eres un asistente útil",
        thread_id,
        event,
        "subscriber_123",
        True,  # use_cache_control
        "claude-haiku-4-5-20251001",  # llmID
        3.0,   # cost_base_input
        3.75,  # cost_cache_write_5m
        0.30,  # cost_cache_read
        15.0,  # cost_output
        tools,
        tool_functions
    )
)
thread.start()
event.wait(timeout=60)

# Obtener respuesta
print(conversations[thread_id]["response"])
"""
