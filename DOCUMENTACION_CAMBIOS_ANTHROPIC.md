# Documentacion de Cambios - API Anthropic con Cache y Costos

## Resumen General

Este documento detalla las modificaciones necesarias para:
1. Implementar correctamente el sistema de **Prompt Caching** de Anthropic (maximo 4 bloques)
2. Calcular y retornar **costos de tokens** en USD
3. Proteger bloques **thinking/redacted_thinking** de modificaciones
4. Manejar correctamente el **TTL de 5 minutos** del cache

---

## 1. Precios de Tokens (Claude Haiku 4.5)

### Valores por defecto para Haiku:

```python
cost_base_input = 1.0       # $1.00 por millon de tokens de entrada
cost_cache_write_5m = 1.25  # $1.25 por millon (1.25x del input)
cost_cache_read = 0.10      # $0.10 por millon (0.1x del input) - 90% ahorro
cost_output = 5.0           # $5.00 por millon de tokens de salida
```

### Valores para Sonnet (si se usa):

```python
cost_base_input = 3.0       # $3.00 por millon
cost_cache_write_5m = 3.75  # $3.75 por millon
cost_cache_read = 0.30      # $0.30 por millon
cost_output = 15.0          # $15.00 por millon
```

### Formula de calculo:

```python
def calculate_costs(tokens, cost_per_mtok):
    return (tokens / 1_000_000) * cost_per_mtok
```

---

## 2. Reglas de Cache Control de Anthropic

### Limites:

| Especificacion | Valor |
|----------------|-------|
| Maximo cache breakpoints | **4 bloques** |
| Minimo tokens Haiku | 2048 tokens |
| Minimo tokens Sonnet/Opus | 1024 tokens |
| TTL por defecto | 5 minutos |

### Bloques que NO se pueden modificar:

| Tipo de bloque | Agregar cache_control | Modificar |
|----------------|----------------------|-----------|
| `text` | SI | SI |
| `tool_use` | SI | SI |
| `tool_result` | SI | SI |
| **`thinking`** | **NO** | **NO** |
| **`redacted_thinking`** | **NO** | **NO** |

---

## 3. Cambios en `generate_response`

### 3.1 Parametros de la funcion

```python
def generate_response(api_key,
                      message,
                      assistant_content_text,
                      thread_id,
                      event,
                      subscriber_id,
                      use_cache_control,
                      llmID=None,
                      cost_base_input=1.0,      # Nuevo parametro
                      cost_cache_write_5m=1.25, # Nuevo parametro
                      cost_cache_read=0.10,     # Nuevo parametro
                      cost_output=5.0):         # Nuevo parametro
```

### 3.2 Funcion `clean_existing_cache_controls` - CORRECCION CRITICA

```python
def clean_existing_cache_controls(conversation_history):
    """Limpia cache_control existentes para implementar cache incremental.
    NO modifica bloques thinking/redacted_thinking (prohibido por Anthropic)."""
    for message in conversation_history:
        if "content" in message and isinstance(message["content"], list):
            for content_item in message["content"]:
                if isinstance(content_item, dict) and "cache_control" in content_item:
                    # CRITICO: No modificar bloques de thinking
                    block_type = content_item.get("type", "")
                    if block_type in ["thinking", "redacted_thinking"]:
                        continue  # NO TOCAR
                    del content_item["cache_control"]
    return conversation_history
```

### 3.3 Cache incremental del historial - CORRECCION CRITICA

```python
# BLOQUE EXTRA: CACHE INCREMENTAL DEL HISTORIAL
if cache_blocks_used < max_cache_blocks and len(conversation_history) > 1:
    previous_message = conversation_history[-2]
    if "content" in previous_message and isinstance(previous_message["content"], list):
        for content_item in previous_message["content"]:
            # NO agregar cache_control a bloques thinking/redacted_thinking
            if isinstance(content_item, dict) and "cache_control" not in content_item:
                block_type = content_item.get("type", "")
                # CRITICO: Excluir AMBOS tipos de thinking
                if block_type in ["thinking", "redacted_thinking"]:
                    continue  # Skip - no se pueden modificar
                content_item["cache_control"] = {"type": "ephemeral"}
                cache_blocks_used += 1
                logger.info("Historial cached (bloque %d/4)", cache_blocks_used)
                break
```

### 3.4 System cache reutilizado - CORRECCION CRITICA

```python
else:
    # Mantener cache existente del sistema si no hay reset Y hay espacio disponible
    if not conversations[thread_id].get("cache_reset", False) and cache_blocks_used < max_cache_blocks:
        # Reusar cache del sistema existente
        combined_content = tools_text + assistant_content_text
        assistant_content = [{
            "type": "text",
            "text": combined_content,
            "cache_control": {"type": "ephemeral"}
        }]
        cache_blocks_used += 1
        logger.info("System cache reutilizado (bloque %d/4)", cache_blocks_used)
    else:
        # Sin cache: limite alcanzado o es un reset
        combined_content = tools_text + assistant_content_text
        assistant_content = [{
            "type": "text",
            "text": combined_content
        }]
        reason = "limite bloques alcanzado" if cache_blocks_used >= max_cache_blocks else "cache reset"
        logger.info("System prompt sin cache (%s: %d/4)", reason, cache_blocks_used)
```

### 3.5 Calculo de costos (despues de recibir respuesta de API)

```python
# Almacenar tokens del turno actual
current_usage = {
    "input_tokens": response.usage.input_tokens,
    "output_tokens": response.usage.output_tokens,
    "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
    "cache_read_input_tokens": response.usage.cache_read_input_tokens,
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

# Guardar en la conversacion
conversations[thread_id]["usage"] = current_usage
```

---

## 4. Cambios en Endpoint `/sendmensaje`

### 4.1 Extraccion de parametros de costo

```python
@app.route('/sendmensaje', methods=['POST'])
def send_message():
    data = request.json

    # ... otros parametros ...

    # Cache control siempre habilitado internamente
    use_cache_control = True

    # Parametros de costo (precios por millon de tokens - MTok)
    cost_base_input = data.get('cost_base_input', 1.0)      # Haiku: $1/MTok
    cost_cache_write_5m = data.get('cost_cache_write_5m', 1.25)  # $1.25/MTok
    cost_cache_read = data.get('cost_cache_read', 0.10)     # $0.10/MTok
    cost_output = data.get('cost_output', 5.0)              # $5/MTok
```

### 4.2 Actualizar keys_to_remove

```python
keys_to_remove = [
    'message', 'assistant', 'thread_id', 'subscriber_id',
    'thinking', 'modelID', 'direccionCliente', 'use_cache_control', 'llmID',
    'cost_base_input', 'cost_cache_write_5m', 'cost_cache_read', 'cost_output'
]
```

### 4.3 Llamada a generate_response con parametros de costo

```python
thread = Thread(target=generate_response,
                args=(anthropic_api_key, message, assistant_content,
                      thread_id, event, subscriber_id,
                      use_cache_control, llmID,
                      cost_base_input, cost_cache_write_5m,
                      cost_cache_read, cost_output))
```

### 4.4 Estructura de respuesta con costos

```python
# Preparar respuesta final
response_data = {
    "thread_id": thread_id,
    "usage": conversations[thread_id].get("usage"),
    "finish_reason": conversations[thread_id].get("finish_reason")
}

# Agregar estadisticas de cache al usage si existen
if "cache_stats" in conversations[thread_id]:
    cache_stats = conversations[thread_id]["cache_stats"]
    if "usage" in response_data and response_data["usage"]:
        response_data["usage"].update({
            "cache_blocks_used": cache_stats.get("bloques_usados", 0),
            "cache_blocks_max": cache_stats.get("maximo_permitido", 4),
            "tools_cache_status": cache_stats.get("tools_cache", "no_applied"),
            "system_cache_status": cache_stats.get("system_cache", "no_applied"),
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

# Agregar costos del turno actual y totales acumulativos
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
```

---

## 5. Ejemplo de Response del Endpoint

```json
{
  "thread_id": "thread_abc123",
  "response": "Respuesta del asistente...",
  "usage": {
    "input_tokens": 1500,
    "output_tokens": 200,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 1200,

    "cache_blocks_used": 3,
    "cache_blocks_max": 4,
    "cache_reset": false,
    "cache_ttl_remaining_seconds": 180,

    "thread_total_input_tokens": 4500,
    "thread_total_output_tokens": 600,
    "thread_total_cache_creation_tokens": 1200,
    "thread_total_cache_read_tokens": 2400,
    "thread_total_all_tokens": 8700,

    "current_cost_input_usd": 0.0015,
    "current_cost_output_usd": 0.001,
    "current_cost_cache_creation_usd": 0.0,
    "current_cost_cache_read_usd": 0.00012,
    "current_total_cost_usd": 0.00262,

    "thread_total_cost_input_usd": 0.0045,
    "thread_total_cost_output_usd": 0.003,
    "thread_total_cost_cache_creation_usd": 0.0015,
    "thread_total_cost_cache_read_usd": 0.00024,
    "thread_total_cost_all_usd": 0.00924
  }
}
```

---

## 6. Funcion `serialize_block` - CORRECCION CRITICA

Cuando Claude responde con `tool_use` y `thinking` habilitado, la respuesta incluye bloques thinking que **DEBEN** pasarse exactamente como fueron devueltos. La funcion `serialize_block` debe usar `model_dump()` para estos bloques:

```python
def serialize_block(block):
    """Convierte un bloque a dict con solo campos permitidos por Anthropic.
    IMPORTANTE: Los bloques thinking/redacted_thinking NO se pueden modificar."""
    block_type = get_field(block, "type")

    # CRITICO: thinking y redacted_thinking deben pasarse EXACTAMENTE como vienen
    # Segun docs Anthropic: "Include the complete unmodified block back to the API"
    if block_type in ["thinking", "redacted_thinking"]:
        if hasattr(block, 'model_dump'):
            return block.model_dump()  # Preservar TODOS los campos exactamente
        return dict(block) if isinstance(block, dict) else {"type": block_type}
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
```

### Por que es importante:

Cuando hay `tool_use`, el flujo es:
1. Usuario envia mensaje
2. Claude responde con: `[thinking] + [text] + [tool_use]`
3. Tu codigo ejecuta la herramienta y envia `tool_result`
4. En el siguiente request, debes incluir el mensaje del asistente anterior **con los bloques thinking intactos**

Si reconstruyes el bloque thinking manualmente (como estaba antes), Anthropic detecta que fue modificado y rechaza el request.

---

## 7. Errores Comunes y Soluciones (ACTUALIZADO)

### Error: "A maximum of 4 blocks with cache_control may be provided"

**Causa:** Se excedio el limite de 4 bloques con cache_control.

**Solucion:** Verificar `cache_blocks_used < max_cache_blocks` ANTES de agregar cualquier cache_control.

```python
# CORRECTO
if cache_blocks_used < max_cache_blocks:
    content["cache_control"] = {"type": "ephemeral"}
    cache_blocks_used += 1

# INCORRECTO
content["cache_control"] = {"type": "ephemeral"}  # Sin verificar limite
```

---

### Error: "thinking blocks cannot be modified" (cache_control)

**Causa:** Se intento agregar/eliminar cache_control de un bloque thinking o redacted_thinking.

**Solucion:** Siempre excluir estos tipos de bloques al modificar cache:

```python
block_type = content_item.get("type", "")
if block_type in ["thinking", "redacted_thinking"]:
    continue  # NO MODIFICAR NUNCA
```

---

### Error: "thinking blocks in the latest assistant message cannot be modified" (tool_use)

**Causa:** Se reconstruyo manualmente el bloque thinking al agregarlo al historial, en lugar de pasarlo exactamente como lo devolvio la API.

**Ejemplo del error:**
```
messages.19.content.1: `thinking` or `redacted_thinking` blocks in the latest
assistant message cannot be modified. These blocks must remain as they were
in the original response.
```

**Solucion:** Usar `model_dump()` para preservar el bloque exactamente:

```python
# INCORRECTO - reconstruir manualmente
if block_type == "thinking":
    return {
        "type": "thinking",
        "thinking": get_field(block, "thinking"),
        "signature": get_field(block, "signature")
    }

# CORRECTO - usar model_dump()
if block_type in ["thinking", "redacted_thinking"]:
    if hasattr(block, 'model_dump'):
        return block.model_dump()  # Preservar TODOS los campos exactamente
```

---

### Error: "messages: text content blocks must be non-empty"

**Causa:** Anthropic genera bloques de texto vacios entre thinking blocks, pero NO permite enviarlos de vuelta en el historial.

Ejemplo de respuesta de Anthropic:
```
[thinking] -> [text vacio] -> [thinking] -> [tool_use]
```

**Solucion 1:** Filtrar al procesar NUEVAS respuestas:

```python
# Al serializar respuesta de Anthropic
if block_dict.get("type") == "text" and not block_dict.get("text"):
    continue  # No agregar al historial
filtered_content.append(block_dict)
```

**Solucion 2 (CRITICA):** Limpiar historial EXISTENTE antes de enviar a Anthropic:

Los mensajes antiguos en el historial pueden tener bloques vacios. Se deben limpiar ANTES de cada llamada a la API:

```python
# ANTES de enviar a Anthropic (dentro del while True)
for msg in conversation_history:
    if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
        # Filtrar bloques de texto vacíos, preservar thinking y otros
        msg["content"] = [
            block for block in msg["content"]
            if not (isinstance(block, dict) and
                   block.get("type") == "text" and
                   not block.get("text"))
        ]
```

**IMPORTANTE:** Esto NO afecta a los thinking blocks. Los thinking blocks se preservan exactamente con `model_dump()`, y solo los text vacios se filtran.

---

### Error: Cache no funciona (siempre WRITE, nunca READ)

**Causa:** El contenido antes del cache_control cambia entre requests.

**Solucion:** Solo cachear contenido estatico (system prompt, tools). El historial cambia siempre, no tiene sentido cachearlo.

---

## 8. Flujo de Cache Optimo

```
TURNO 1: Nueva conversacion
- cache_reset = True
- Limpiar cache_control existentes (excepto thinking)
- Agregar cache_control a System+Tools
- Resultado: WRITE (se cachea en Anthropic)

TURNO 2-N: Dentro de 5 minutos
- cache_reset = False
- Mantener cache_control existentes
- Verificar limite de 4 bloques antes de agregar mas
- Resultado: READ (90% ahorro)

TURNO despues de 5 min inactivo:
- cache_reset = True
- Limpiar y reiniciar ciclo
- Resultado: WRITE (nuevo cache)
```

---

## 9. Logs de Monitoreo de Bloques (ANTHROPIC_DEBUG)

Para diagnosticar problemas con bloques thinking y cache_control, se agregaron logs detallados que se activan con `ANTHROPIC_DEBUG = True`.

### 9.1 Log de bloques ENVIADOS a Anthropic (antes de API call)

```
============================================================
📤 MONITOREO BLOQUES ENVIADOS A ANTHROPIC
📊 Total mensajes en historial: 5
  MSG[0] role=user | content=string (len=45)
  MSG[1] role=assistant | content=list (3 bloques)
      [1.0] thinking | signature=True | thinking_field=True
      [1.1] text (len=120) | cache_control=False
      [1.2] tool_use: crear_pedido (id=toolu_01abc)
  MSG[2] role=user | content=list (1 bloques)
      [2.0] tool_result (id=toolu_01abc)
  MSG[3] role=assistant | content=list (2 bloques)
      [3.0] thinking | signature=True | thinking_field=True
      [3.1] text (len=85) | cache_control=True
  MSG[4] role=user | content=string (len=30)
============================================================
```

**Que verificar:**
- Los bloques `thinking` deben tener `signature=True` y `thinking_field=True`
- Los bloques `thinking` NO deben tener `cache_control`
- Solo otros bloques (text, tool_use, etc.) deben tener `cache_control=True`

### 9.2 Log de bloques RECIBIDOS de Anthropic (respuesta)

```
============================================================
🔍 MONITOREO DE BLOQUES - Respuesta Anthropic
📊 Total bloques recibidos: 3
  [0] Tipo: thinking
      └─ thinking (len=1245 chars)
  [1] Tipo: text
      └─ text (len=85 chars): Aqui esta el resumen de tu pedido...
  [2] Tipo: tool_use
      └─ tool_use: crear_pedido (id=toolu_02xyz)
------------------------------------------------------------
  ✅ [0] thinking serializado con model_dump() - preservado exacto
  📝 [1] text serializado manualmente
  📝 [2] tool_use serializado manualmente
------------------------------------------------------------
📋 CONTENIDO FINAL (filtered_content): 3 bloques
  [0] thinking - signature presente: True
  [1] text (len=85)
  [2] tool_use: crear_pedido
============================================================
```

**Que verificar:**
- Los bloques `thinking` deben mostrar "✅ serializado con model_dump()"
- El `filtered_content` debe mostrar `signature presente: True` para thinking
- Si hay `redacted_thinking`, debe mostrar `data presente: True`

### 9.3 Activar/Desactivar Logs

En `main.py`, al inicio del archivo:

```python
ANTHROPIC_DEBUG = True   # Activar logs detallados
ANTHROPIC_DEBUG = False  # Desactivar para produccion
```

### 9.4 Interpretacion de errores con logs

**Si ves `signature=False` en thinking:**
El bloque thinking no se esta preservando correctamente. Revisa `serialize_block`.

**Si ves `cache_control=True` en un bloque thinking:**
El cache se esta aplicando a thinking. Revisa `clean_existing_cache_controls` y el cache incremental.

**Si el total de `cache_control=True` es mayor a 4:**
Se excedio el limite. Revisa todas las secciones donde se agrega cache_control.

---

## 10. Referencias

- [Documentacion Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Extended Thinking con Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)
- [Precios Anthropic](https://www.anthropic.com/pricing)

---

## 11. Checklist de Implementacion

- [ ] Agregar parametros de costo a `generate_response`
- [ ] Proteger bloques `thinking` y `redacted_thinking` en `clean_existing_cache_controls`
- [ ] Proteger bloques `thinking` y `redacted_thinking` en cache incremental
- [ ] Verificar `cache_blocks_used < max_cache_blocks` antes de agregar cache al system
- [ ] **CRITICO: Usar `model_dump()` para bloques thinking en `serialize_block`**
- [ ] Extraer parametros de costo en endpoint `/sendmensaje`
- [ ] Pasar parametros de costo a `generate_response`
- [ ] Agregar estructura de costos al response_data
- [ ] Probar con conversacion larga (>4 mensajes) para verificar limite de bloques
- [ ] Probar con tool_use para verificar que thinking blocks no se modifican
- [ ] Activar `ANTHROPIC_DEBUG = True` para monitorear estructura de bloques
- [ ] Verificar en logs que thinking muestre `signature=True` y `thinking_field=True`

---

*Documento actualizado el 2026-01-09 - Agregados logs de monitoreo*
