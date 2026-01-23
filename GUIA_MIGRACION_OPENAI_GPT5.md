# Guia de Migracion: OpenAI Responses API con GPT-5.2

Esta guia documenta los cambios necesarios para migrar una funcion `generate_response_openai` al nuevo formato de la API de OpenAI con soporte para:
- Rol `system` en el array `input`
- Manejo de bloques `reasoning` (obligatorio para gpt-5.2+)
- Conversion recursiva de herramientas con `additionalProperties: false`

---

## 1. Agregar Import de `copy`

Al inicio del archivo, agregar:

```python
import copy
```

---

## 2. Modificar Firma de la Funcion

**ANTES:**
```python
def generate_response_openai(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    llmID=None
):
```

**DESPUES:**
```python
def generate_response_openai(
    message,
    assistant_content_text,
    thread_id,
    event,
    subscriber_id,
    llmID=None,
    developer_content=None  # Nuevo parametro para rol system
):
```

---

## 3. Agregar Funcion Recursiva para `additionalProperties`

Agregar esta funcion ANTES del bucle de conversion de herramientas:

```python
# Funcion recursiva para agregar additionalProperties: false a todos los objetos
def add_additional_properties_false(schema):
    """Agrega additionalProperties: false recursivamente a todos los objetos del schema."""
    if not isinstance(schema, dict):
        return schema

    # Si es un objeto, agregar additionalProperties: false
    if schema.get("type") == "object":
        if "additionalProperties" not in schema:
            schema["additionalProperties"] = False
        # Procesar propiedades del objeto
        if "properties" in schema:
            for prop_name, prop_value in schema["properties"].items():
                add_additional_properties_false(prop_value)

    # Si es un array, procesar los items
    if schema.get("type") == "array" and "items" in schema:
        add_additional_properties_false(schema["items"])

    return schema
```

---

## 4. Modificar Conversion de Herramientas

**ANTES:**
```python
# Convertir herramientas al formato de OpenAI Function Calling
tools_openai_format = []
for tool in tools_anthropic_format:
    parameters = tool.get("parameters", tool.get("input_schema", {}))

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
```

**DESPUES:**
```python
# Convertir herramientas al formato de OpenAI Function Calling
tools_openai_format = []
for tool in tools_anthropic_format:
    parameters = tool.get("parameters", tool.get("input_schema", {}))

    # Si se usa strict mode, aplicar additionalProperties: false recursivamente
    if tool.get("strict", True):
        # Hacer una copia profunda para no modificar el original
        parameters = copy.deepcopy(parameters)
        add_additional_properties_false(parameters)

    openai_tool = {
        "type": "function",
        "name": tool["name"],
        "description": tool["description"],
        "parameters": parameters,
        "strict": tool.get("strict", True)
    }
    tools_openai_format.append(openai_tool)
tools = tools_openai_format
```

---

## 5. Agregar Mensaje `system` al Construir `input_messages`

Despues de inicializar `input_messages = []`, agregar:

```python
# Preparar los mensajes para la nueva API
input_messages = []

# Agregar mensaje system si se proporciona (para gpt-5.2+)
if developer_content:
    logger.info("Agregando mensaje con rol 'system' al inicio de la conversacion")
    input_messages.append({
        "role": "system",
        "content": [{"type": "input_text", "text": developer_content}]
    })
```

---

## 6. Agregar Manejo de `reasoning` en el Bucle de Mensajes

En el bucle que procesa `conversation_history`, agregar manejo para tipo `reasoning`:

```python
# Verificar si el mensaje tiene 'type' (function calls, outputs y reasoning)
elif "type" in msg:
    if msg["type"] == "function_call":
        input_messages.append(msg)
    elif msg["type"] == "function_call_output":
        input_messages.append(msg)
    elif msg["type"] == "reasoning":
        # Agregar bloques reasoning directamente (requerido por OpenAI gpt-5.2+)
        input_messages.append(msg)
        logger.debug(f"Reasoning agregado a input_messages con ID: {msg.get('id')}")
```

---

## 7. Modificar Llamada a la API

**ANTES:**
```python
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
```

**DESPUES:**
```python
response = client.responses.create(
    model=llmID,
    instructions=assistant_content_text,
    input=input_messages,
    tools=tools,
    max_output_tokens=2000,
    reasoning={
        "summary": None
    },
    store=True,
    include=["reasoning.encrypted_content"]
)
```

> **Nota:** `temperature` y `top_p` pueden comentarse o eliminarse segun necesidad.

---

## 8. Capturar Bloque `reasoning` del Response

Agregar variable y logica para capturar reasoning ANTES de procesar la respuesta:

```python
# Variables para rastrear el tipo de respuesta
assistant_response_text = None
message_id = None
function_called = False
reasoning_item = None  # Para capturar el bloque reasoning

# Procesar la respuesta
if hasattr(response, 'output') and response.output:
    # Primero, buscar y capturar el bloque reasoning
    for output_item in response.output:
        if hasattr(output_item, 'type') and output_item.type == 'reasoning':
            reasoning_item = {
                "type": "reasoning",
                "id": getattr(output_item, 'id', None),
                "summary": getattr(output_item, 'summary', []),
                "encrypted_content": getattr(output_item, 'encrypted_content', None)
            }
            logger.info("Bloque reasoning capturado con ID: %s", reasoning_item.get('id'))
            break
```

---

## 9. Guardar `reasoning` ANTES del Mensaje `assistant`

Cuando se guarda un mensaje del assistant en `conversation_history`, agregar el reasoning primero:

```python
# Si encontramos un texto de respuesta y no hubo llamada a funcion
if assistant_response_text and not function_called:
    # IMPORTANTE: Guardar reasoning ANTES del mensaje assistant
    if reasoning_item:
        conversation_history.append(reasoning_item)
        logger.info("Reasoning guardado en historial antes del mensaje assistant")

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
```

---

## 10. Guardar `reasoning` ANTES del `function_call`

Cuando se procesa una llamada a funcion:

```python
function_output_entry = {
    "type": "function_call_output",
    "call_id": call_id,
    "output": result_str
}

# IMPORTANTE: Guardar reasoning ANTES del function_call
if reasoning_item:
    conversation_history.append(reasoning_item)
    input_messages.append(reasoning_item)
    logger.info("Reasoning guardado en historial antes del function_call")

conversation_history.append(function_call_entry)
conversation_history.append(function_output_entry)

# Preparar entrada para la siguiente iteracion
input_messages.append(function_call_entry)
input_messages.append(function_output_entry)
```

---

## 11. Capturar `reasoning` de `continue_response`

Cuando se hace una segunda llamada despues de ejecutar una funcion:

```python
# Solicitar continuacion de la conversacion despues de la llamada a la funcion
continue_response = client.responses.create(
    model=llmID,
    instructions=assistant_content_text,
    input=input_messages,
    tools=tools,
    max_output_tokens=2000,
    reasoning={
        "summary": None
    },
    store=True,
    include=["reasoning.encrypted_content"]
)

# Procesar la respuesta de continuacion
continue_message_id = None
continue_reasoning_item = None  # Capturar reasoning de la continuacion

if hasattr(continue_response, 'output') and continue_response.output:
    # Primero buscar el reasoning de la continuacion
    for continue_item in continue_response.output:
        if hasattr(continue_item, 'type') and continue_item.type == 'reasoning':
            continue_reasoning_item = {
                "type": "reasoning",
                "id": getattr(continue_item, 'id', None),
                "summary": getattr(continue_item, 'summary', []),
                "encrypted_content": getattr(continue_item, 'encrypted_content', None)
            }
            logger.info("Bloque reasoning de continuacion capturado con ID: %s", continue_reasoning_item.get('id'))
            break

    # Luego buscar el mensaje
    for continue_item in continue_response.output:
        if hasattr(continue_item, 'type') and continue_item.type == 'message':
            continue_message_id = getattr(continue_item, 'id', None)
            if hasattr(continue_item, 'content'):
                for content_item in continue_item.content:
                    if hasattr(content_item, 'type') and content_item.type == 'output_text':
                        assistant_response_text = content_item.text
                        break

# Si obtuvimos una respuesta de texto, guardarla CON reasoning
if assistant_response_text:
    conversations[thread_id]["response"] = assistant_response_text
    conversations[thread_id]["status"] = "completed"

    # IMPORTANTE: Guardar reasoning de continuacion ANTES del mensaje assistant
    if continue_reasoning_item:
        conversation_history.append(continue_reasoning_item)
        logger.info("Reasoning de continuacion guardado en historial")

    final_message = {
        "role": "assistant",
        "content": assistant_response_text
    }
    if continue_message_id:
        final_message["id"] = continue_message_id

    conversation_history.append(final_message)
```

---

## 12. Modificar Endpoint para Pasar `developer_content`

En el endpoint `/sendmensaje`, extraer el parametro y pasarlo a la funcion:

```python
# Extraer parametros principales
llmID = data.get('llmID')
developer_content = data.get('developer')  # Nuevo parametro para rol system

# En keys_to_remove agregar 'developer'
keys_to_remove = [
    'api_key', 'message', 'assistant', 'thread_id', 'subscriber_id',
    'thinking', 'modelID', 'direccionCliente', 'llmID', 'developer',  # <-- agregar
    # ... resto de keys
]

# Al crear el thread para OpenAI
elif modelID == 'llm':
    thread = Thread(target=generate_response_openai,
                    args=(message, assistant_content, thread_id, event,
                          subscriber_id, llmID, developer_content))  # <-- agregar parametro
```

---

## Estructura Correcta del Historial

El historial debe seguir este orden:

```
[system] -> [user] -> [reasoning] -> [assistant]
                   -> [reasoning] -> [function_call] -> [function_call_output] -> [reasoning] -> [assistant]
```

**IMPORTANTE:** Cada mensaje `assistant` DEBE estar precedido por su bloque `reasoning` correspondiente, de lo contrario OpenAI retornara error 400.

---

## Errores Comunes y Soluciones

| Error | Causa | Solucion |
|-------|-------|----------|
| `'name null is not defined'` | Usar `null` en lugar de `None` | Cambiar `"summary": null` por `"summary": None` |
| `'additionalProperties' is required` | Objetos anidados sin `additionalProperties: false` | Usar funcion recursiva `add_additional_properties_false()` |
| `message was provided without its required 'reasoning' item` | Falta el bloque reasoning antes del assistant | Guardar reasoning en conversation_history antes de cada assistant |

---

## Ejemplo de Request al Endpoint

```json
{
  "message": "hola",
  "modelID": "llm",
  "llmID": "gpt-5.2",
  "subscriber_id": "123456",
  "thread_id": "thread_abc123",
  "assistant": 0,
  "developer": "Eres un asistente de servicio al cliente..."
}
```

---

## Notas Importantes

1. **`copy.deepcopy()`**: Se usa para no modificar los archivos JSON originales de herramientas que tambien usa Anthropic
2. **`include=["reasoning.encrypted_content"]`**: Necesario para que OpenAI devuelva el contenido encriptado del reasoning
3. **`reasoning={"summary": None}`**: Configuracion requerida para habilitar reasoning en la respuesta
4. **El parametro `developer` es opcional**: Si no se proporciona, solo se usara `instructions`
