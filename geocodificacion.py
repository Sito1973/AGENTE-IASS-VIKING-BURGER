"""
Geocodificación con Anthropic Programmatic Tool Calling (code_execution_20260120).

Claude escribe código Python en un sandbox que llama a Google Maps/Places.
Incluye caché de container y keep-alive opcional para reutilizar entre llamadas.

Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling
"""

import os
import re
import json
import time
import logging
import threading

import anthropic
import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

geocodificacion_bp = Blueprint("geocodificacion", __name__)

# ─── Retry helper (misma lógica que main.py) ───────────────────────────────
def _call_anthropic(client, **kwargs):
    """Llama a la API de Anthropic con reintentos automáticos."""
    max_retries = 3
    initial_wait = 1
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except Exception as e:
            if attempt >= max_retries - 1:
                raise
            time.sleep(initial_wait * (2 ** (attempt + 1)))


# ─── Cache global del sandbox ───────────────────────────────────────────────
_container_cache = {"id": None, "expires_at": 0}
_container_lock = threading.Lock()
_keepalive_timer = {"ref": None}

KEEPALIVE_INTERVAL = 240  # segundos (sandbox expira a ~4.5 min)
KEEPALIVE_ENABLED = os.environ.get("GEOCODING_KEEPALIVE", "0").strip() in {"1", "true", "yes"}


def _get_container():
    """Retorna container_id si aún es válido, sino None."""
    with _container_lock:
        if _container_cache["id"] and time.time() < _container_cache["expires_at"] - 10:
            return _container_cache["id"]
        _container_cache["id"] = None
        return None


def _update_container(response):
    """Extrae container_id/expires_at de la respuesta y actualiza la cache."""
    raw = getattr(response, "container", None)
    if not raw:
        return None

    cid = raw.get("id") if isinstance(raw, dict) else getattr(raw, "id", None)
    expires_str = raw.get("expires_at") if isinstance(raw, dict) else getattr(raw, "expires_at", None)

    exp_ts = time.time() + 240  # fallback 4 min
    if expires_str:
        try:
            from datetime import datetime as dt
            exp_ts = dt.fromisoformat(str(expires_str).replace("Z", "+00:00")).timestamp()
        except Exception:
            pass

    with _container_lock:
        is_new = (_container_cache["id"] != cid)
        _container_cache["id"] = cid
        _container_cache["expires_at"] = exp_ts

    if is_new and cid:
        logger.info("geocoding container nuevo: %s (expira en ~4.5 min)", cid)
        if KEEPALIVE_ENABLED:
            _schedule_keepalive()

    return cid


# ─── Keep-alive (solo si GEOCODING_KEEPALIVE=1) ────────────────────────────
def _keepalive_ping():
    """Ping barato al sandbox para mantenerlo vivo. Cuesta ~100 tokens."""
    cid = _get_container()
    if not cid:
        logger.info("geocoding keepalive: container expirado, detenido")
        return

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=32,
            container=cid,
            tools=[{"type": "code_execution_20260120", "name": "code_execution"}],
            messages=[{"role": "user", "content": "print('ok')"}]
        )
        _update_container(resp)
        logger.info("geocoding keepalive: ping OK, container %s mantenido", cid)
    except Exception as e:
        logger.warning("geocoding keepalive: falló (%s), container descartado", e)
        with _container_lock:
            _container_cache["id"] = None
        return

    _schedule_keepalive()


def _schedule_keepalive():
    """Programa el siguiente ping."""
    if not KEEPALIVE_ENABLED:
        return
    if _get_container():
        t = threading.Timer(KEEPALIVE_INTERVAL, _keepalive_ping)
        t.daemon = True
        t.start()
        _keepalive_timer["ref"] = t


# ─── Función principal ──────────────────────────────────────────────────────
def generate_response_programatic_tool(
    direccion_cliente,
    indicaciones_direccion,
    ciudad_cliente,
    latitud_restaurante,
    longitud_restaurante
):
    """
    Geocodifica una dirección usando Anthropic Programmatic Tool Calling.

    Retorna dict: direccion_consultada, direccion_formateada, latitud, longitud,
    precision, fuente  (campos en 0 si no se geocodifica).
    """
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    address_query = (
        f"{direccion_cliente}, {indicaciones_direccion}, "
        f"{ciudad_cliente}, risaralda, Colombia"
    )

    # Cargar system prompt desde archivo externo
    prompt_path = os.path.join(
        os.path.dirname(__file__), "PROMPTS", "URBAN", "PROMPT_GEOCODIFICACION.txt"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()
    logger.info("Prompt geocodificación cargado desde: %s", prompt_path)

    # Cargar tools y output_schema desde archivo JSON externo
    tools_path = os.path.join(os.path.dirname(__file__), "tools_geocodificacion.json")
    with open(tools_path, "r", encoding="utf-8") as f:
        tools_data = json.load(f)
    custom_tools = tools_data["tools"]
    output_schema = tools_data["output_schema"]
    logger.info("Tools geocodificación cargadas desde: %s", tools_path)

    # Inyectar output_schema en el prompt (como el Structured Output Parser de N8N)
    schema_str = json.dumps(output_schema, ensure_ascii=False, indent=2)
    system_prompt += f"\n\nEsquema de salida obligatorio:\n```json\n{schema_str}\n```"

    # Programmatic Tool Calling: code_execution + tools con allowed_callers
    tools = [
        {"type": "code_execution_20260120", "name": "code_execution"},
        *custom_tools
    ]

    messages = [{"role": "user", "content": address_query}]
    container_id = _get_container()  # Reutilizar si hay uno vivo
    max_iterations = 15

    for iteration in range(max_iterations):
        create_kwargs = dict(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages
        )
        if container_id:
            create_kwargs["container"] = container_id

        response = _call_anthropic(client, **create_kwargs)

        container_id = _update_container(response)

        logger.info(
            "geocodificacion - iter %d, stop_reason: %s, container: %s",
            iteration + 1, response.stop_reason, container_id
        )

        messages.append({"role": "assistant", "content": response.content})

        # ── Resultado final ──
        if response.stop_reason == "end_turn":
            for block in response.content:
                block_type = (
                    block.get("type") if isinstance(block, dict)
                    else getattr(block, "type", None)
                )

                if block_type == "code_execution_tool_result":
                    block_content = (
                        block.get("content") if isinstance(block, dict)
                        else getattr(block, "content", None)
                    )
                    stdout = (
                        block_content.get("stdout", "") if isinstance(block_content, dict)
                        else getattr(block_content, "stdout", "")
                    )
                    try:
                        json_match = re.search(r'\{.*\}', stdout, re.DOTALL)
                        if json_match:
                            result = json.loads(json_match.group())
                            logger.info("geocodificacion resultado: %s", result)
                            return result
                    except Exception:
                        pass

                if block_type == "text":
                    text = (
                        block.get("text", "").strip() if isinstance(block, dict)
                        else getattr(block, "text", "").strip()
                    )
                    try:
                        json_match = re.search(r'\{.*\}', text, re.DOTALL)
                        if json_match:
                            result = json.loads(json_match.group())
                            logger.info("geocodificacion resultado (text): %s", result)
                            return result
                    except Exception:
                        pass
            break

        if response.stop_reason != "tool_use":
            logger.warning("geocodificacion stop_reason inesperado: %s", response.stop_reason)
            break

        # ── Ejecutar herramientas que el sandbox solicitó ──
        tool_results = []
        for block in response.content:
            block_type = (
                block.get("type") if isinstance(block, dict)
                else getattr(block, "type", None)
            )
            if block_type != "tool_use":
                continue

            tool_name = block.get("name") if isinstance(block, dict) else getattr(block, "name")
            tool_input = block.get("input") if isinstance(block, dict) else getattr(block, "input")
            tool_use_id = block.get("id") if isinstance(block, dict) else getattr(block, "id")

            logger.info("geocodificacion tool_use: %s | input: %s", tool_name, tool_input)

            try:
                if tool_name == "buscar_por_lugar":
                    api_resp = requests.get(
                        "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                        params={
                            "input": tool_input.get("lugar", ""),
                            "inputtype": "textquery",
                            "locationbias": f"circle:8000@{latitud_restaurante},{longitud_restaurante}",
                            "fields": "formatted_address,name,rating,opening_hours,geometry",
                            "key": GOOGLE_MAPS_API_KEY
                        },
                        timeout=10
                    )
                    tool_result = api_resp.text

                elif tool_name == "buscar_por_direccion":
                    api_resp = requests.get(
                        "https://maps.googleapis.com/maps/api/geocode/json",
                        params={
                            "address": tool_input.get("direccion", ""),
                            "components": "country:CO",
                            "key": GOOGLE_MAPS_API_KEY
                        },
                        timeout=10
                    )
                    tool_result = api_resp.text

                else:
                    tool_result = json.dumps({"error": f"Herramienta desconocida: {tool_name}"})

            except Exception as e:
                logger.error("Error herramienta geocodificacion %s: %s", tool_name, e)
                tool_result = json.dumps({"error": str(e)})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": tool_result
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    logger.warning("geocodificacion: fallback para '%s'", address_query)
    return {
        "direccion_consultada": 0,
        "direccion_formateada": 0,
        "latitud": 0,
        "longitud": 0,
        "precision": 0,
        "fuente": 0
    }


# ─── Endpoint Flask ─────────────────────────────────────────────────────────
@geocodificacion_bp.route("/geocodificar", methods=["POST"])
def geocodificar():
    """Endpoint para geocodificar una dirección."""
    logger.info("Endpoint /geocodificar llamado")
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Body JSON requerido"}), 400

        direccion_cliente = data.get("direccion_cliente", "")
        indicaciones_direccion = data.get("indicaciones_direccion", "")
        ciudad_cliente = data.get("ciudad_cliente", "")
        latitud_restaurante = data.get("latitud_restaurante", "")
        longitud_restaurante = data.get("longitud_restaurante", "")

        if not direccion_cliente or not ciudad_cliente:
            return jsonify({"error": "direccion_cliente y ciudad_cliente son obligatorios"}), 400

        resultado = generate_response_programatic_tool(
            direccion_cliente=direccion_cliente,
            indicaciones_direccion=indicaciones_direccion,
            ciudad_cliente=ciudad_cliente,
            latitud_restaurante=latitud_restaurante,
            longitud_restaurante=longitud_restaurante
        )

        logger.info("Geocodificación completada: %s", resultado)
        return jsonify(resultado)

    except Exception as e:
        logger.exception("Error en /geocodificar: %s", e)
        return jsonify({"error": str(e)}), 500
