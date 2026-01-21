# Comparación: Function Responses en diferentes APIs de LLM

## Resumen Ejecutivo

Este documento explica las diferencias en cómo cada API maneja las respuestas de funciones (function responses) y el formato correcto para cada una.

---

## 1. GEMINI API (Google)

### Formato Correcto

```python
# Paso 1: Ejecutar la función
result = tool_functions[tool_name](tool_arguments, subscriber_id)

# Paso 2: Agregar la respuesta del modelo al historial
conversation_history.append(response_content)

# Paso 3: Crear function response con role="user"
function_response_part = genai_types.Part.from_function_response(
    name=tool_name,
    response={
        "output": result  # ← CLAVE: "output" + resultado directo (NO serializar)
    }
)

function_response_content = genai_types.Content(
    role="user",  # ← IMPORTANTE: role="user" para function responses
    parts=[function_response_part]
)

conversation_history.append(function_response_content)
```

### Características Clave de Gemini:
- ✅ Usa `"output"` como clave en el diccionario de respuesta
- ✅ Envía el resultado directamente (string, dict, etc.) SIN `json.dumps()`
- ✅ El function response tiene `role="user"`
- ✅ Usa objetos nativos de Gemini: `genai_types.Part.from_function_response()`

### Ejemplo en Logs:
```
Mensaje function_response enviado a Gemini:
role='user' parts=[Part(function_response=FunctionResponse(
    name='crear_direccion',
    response={'output': 'INSTRUCCION OBLIGATORIA: Informarle al cliente...'}
))]
```

---

## 2. ANTHROPIC/CLAUDE API

### Formato Correcto

```python
# Paso 1: Ejecutar la función
result = tool_functions[tool_name](tool_arguments, subscriber_id)

# Paso 2: Agregar function call output al historial
function_output_entry = {
    "type": "function_call_output",  # ← TIPO específico de Anthropic
    "call_id": call_id,
    "output": result  # ← CLAVE: "output" + resultado directo
}

conversation_history.append(function_output_entry)
```

### Características Clave de Anthropic:
- ✅ Usa `"output"` como clave en el diccionario
- ✅ Usa `"type": "function_call_output"` para identificar el mensaje
- ✅ Requiere `call_id` para vincular con el function call original
- ✅ NO usa objetos especiales, solo diccionarios Python estándar

### Ejemplo del Formato Completo:
```python
{
    "type": "function_call_output",
    "call_id": "call_ZtjF7TcGkhBULg4wwtSLtTH6",
    "output": "INSTRUCCION OBLIGATORIA: Informarle al cliente que hubo un error..."
}
```

---

## 3. OPENAI API

### ⚠️ IMPORTANTE: OpenAI tiene DOS APIs diferentes para function calling

#### 3A. OpenAI Chat Completions API (API Tradicional)

**Formato para Chat Completions:**

```python
# Paso 1: Ejecutar la función
result = tool_functions[tool_name](tool_arguments, subscriber_id)

# Paso 2: Crear mensaje de tipo "tool"
tool_message = {
    "role": "tool",  # ← IMPORTANTE: role="tool" en Chat Completions
    "tool_call_id": call_id,
    "name": tool_name,
    "content": str(result)  # ← CLAVE: "content" (no "output")
}

conversation_history.append(tool_message)
```

**Características de Chat Completions API:**
- ✅ Usa `"content"` como clave (NO "output")
- ✅ Usa `role="tool"` para function responses
- ✅ Requiere `tool_call_id` para vincular con el function call
- ✅ Requiere `"name"` de la función
- ✅ Convierte el resultado a string con `str(result)`

**Ejemplo Completo Chat Completions:**
```python
{
    "role": "tool",
    "tool_call_id": "call_abc123xyz",
    "name": "crear_direccion",
    "content": "INSTRUCCION OBLIGATORIA: Informarle al cliente..."
}
```

#### 3B. OpenAI Responses API (API Nueva)

**Formato para Responses API:**

```python
# Paso 1: Ejecutar la función
result = tool_functions[tool_name](tool_arguments, subscriber_id)
result_str = str(result)

# Paso 2: Crear function_call_output
function_output_entry = {
    "type": "function_call_output",  # ← TIPO específico de Responses API
    "call_id": call_id,
    "output": result_str  # ← CLAVE: "output" (igual que Anthropic)
}

conversation_history.append(function_output_entry)
```

**Características de Responses API:**
- ✅ Usa `"output"` como clave (igual que Anthropic)
- ✅ Usa `"type": "function_call_output"` para identificar el mensaje
- ✅ Requiere `call_id` para vincular con el function call
- ✅ Usa `str(result)` para convertir a string
- ✅ NO requiere `"name"` de la función

**Ejemplo Completo Responses API:**
```python
{
    "type": "function_call_output",
    "call_id": "call_ZtjF7TcGkhBULg4wwtSLtTH6",
    "output": "INSTRUCCION OBLIGATORIA: Informarle al cliente..."
}
```

---

## Tabla Comparativa Rápida

| Característica | Gemini | Anthropic/Claude | OpenAI Chat Completions | OpenAI Responses API |
|---------------|--------|------------------|------------------------|---------------------|
| **Clave de respuesta** | `"output"` | `"output"` | `"content"` | `"output"` |
| **Role del mensaje** | `"user"` | N/A (usa `"type"`) | `"tool"` | N/A (usa `"type"`) |
| **ID de vinculación** | No requerido | `"call_id"` | `"tool_call_id"` | `"call_id"` |
| **Tipo de mensaje** | `Part.from_function_response()` | `"type": "function_call_output"` | `"role": "tool"` | `"type": "function_call_output"` |
| **Serialización** | ❌ NO usar `json.dumps()` | ❌ NO usar `json.dumps()` | ⚠️ Usar `str()` | ⚠️ Usar `str()` |
| **Nombre de función** | Incluido en Part | No requerido | `"name"` requerido | No requerido |

---

## Errores Comunes y Cómo Detectarlos

### Error 1: Usar la clave incorrecta
```python
# ❌ INCORRECTO en Gemini/Anthropic
response={"result": result}

# ✅ CORRECTO en Gemini/Anthropic
response={"output": result}

# ✅ CORRECTO en OpenAI
{"content": str(result)}
```

### Error 2: Serialización innecesaria
```python
# ❌ INCORRECTO en todas las APIs
result_json = json.dumps(result)
response={"output": result_json}  # Esto crea doble serialización

# ✅ CORRECTO
response={"output": result}  # Enviar resultado directo
```

### Error 3: Role incorrecto
```python
# ❌ INCORRECTO en Gemini
genai_types.Content(role="assistant", parts=[...])

# ✅ CORRECTO en Gemini
genai_types.Content(role="user", parts=[...])

# ✅ CORRECTO en OpenAI
{"role": "tool", "content": "..."}
```

---

## Verificación en Logs

### Gemini - Log Correcto:
```
Mensaje function_response enviado a Gemini (Gemini):
role='user' parts=[Part(function_response=FunctionResponse(
    name='crear_direccion',
    response={'output': 'INSTRUCCION...'} ← Sin comillas dobles extras
))]
```

### Gemini - Log Incorrecto (Bug):
```
response={'result': '"INSTRUCCION..."'} ← Comillas extras = doble serialización
```

### Anthropic - Formato Correcto:
```python
{
    "type": "function_call_output",
    "call_id": "call_ZtjF7TcGkhBULg4wwtSLtTH6",
    "output": "INSTRUCCION OBLIGATORIA: ..."  # ← String directo
}
```

### OpenAI Chat Completions - Formato Correcto:
```python
{
    "role": "tool",
    "tool_call_id": "call_abc123",
    "name": "crear_direccion",
    "content": "INSTRUCCION OBLIGATORIA: ..."  # ← String directo
}
```

### OpenAI Responses API - Formato Correcto:
```python
{
    "type": "function_call_output",
    "call_id": "call_ZtjF7TcGkhBULg4wwtSLtTH6",
    "output": "INSTRUCCION OBLIGATORIA: ..."  # ← String directo
}
```

---

## Checklist de Implementación

### Para Gemini:
- [ ] Usar `"output"` como clave
- [ ] NO usar `json.dumps()` en el resultado
- [ ] Usar `role="user"` para function responses
- [ ] Usar `genai_types.Part.from_function_response()`
- [ ] Verificar logs: `response={'output': '...'}`

### Para Anthropic/Claude:
- [ ] Usar `"output"` como clave
- [ ] Usar `"type": "function_call_output"`
- [ ] Incluir `"call_id"` del function call original
- [ ] NO serializar con `json.dumps()`
- [ ] Verificar formato del diccionario

### Para OpenAI Chat Completions API:
- [ ] Usar `"content"` como clave (NO "output")
- [ ] Usar `role="tool"`
- [ ] Incluir `"tool_call_id"`
- [ ] Incluir `"name"` de la función
- [ ] Usar `str(result)` para convertir a string
- [ ] Verificar que el `tool_call_id` coincida con el call original

### Para OpenAI Responses API:
- [ ] Usar `"output"` como clave (igual que Anthropic)
- [ ] Usar `"type": "function_call_output"`
- [ ] Incluir `"call_id"` (NO "tool_call_id")
- [ ] NO incluir `"name"` de la función
- [ ] Usar `str(result)` para convertir a string
- [ ] Verificar que el `call_id` coincida con el call original

---

## Referencias a Documentación Oficial

- **Gemini API**: [Function Calling Guide](https://ai.google.dev/gemini-api/docs/function-calling)
- **Anthropic Claude**: [Tool Use Documentation](https://docs.anthropic.com/claude/docs/tool-use)
- **OpenAI**: [Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)

---

**Fecha:** 2026-01-21
**Versión:** 1.0
**Autor:** Equipo de desarrollo Viking Burger
