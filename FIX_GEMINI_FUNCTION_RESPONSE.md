# Fix Crítico: Respuesta de Function Calls en Gemini API

## Problema Identificado

Las respuestas de las herramientas (function responses) no están siendo procesadas correctamente por el LLM de Gemini, causando que el modelo ignore las instrucciones retornadas por las funciones y continúe como si la ejecución hubiera sido exitosa.

## Causa Raíz

El código actual tiene dos problemas en la función `generate_response_gemini`:

1. **Clave incorrecta**: Se está usando `"result"` en lugar de `"output"` en el diccionario de respuesta
2. **Serialización innecesaria**: Se está haciendo `json.dumps(result)` antes de enviar la respuesta, convirtiendo el resultado en un string JSON anidado

## Ubicación del Error

Archivo: `main.py`
Función: `generate_response_gemini`
Líneas aproximadas: ~1968-1990 (puede variar según versión)

## Código Actual (INCORRECTO)

```python
if tool_name in tool_functions:
    result = tool_functions[tool_name](
        tool_arguments,
        subscriber_id)
    logger.debug(
        "Resultado de la herramienta %s (Gemini): %s",
        tool_name, result)
    result_json = json.dumps(result)  # ← PROBLEMA 1: Serialización innecesaria
    logger.info(
        "Resultado de la herramienta %s (Gemini): %s",
        tool_name, result_json)

    # Add function response to history
    conversation_history.append(response_content)

    function_response_part = genai_types.Part.from_function_response(
        name=tool_name,
        response={
            "result": result_json  # ← PROBLEMA 2: Clave incorrecta y valor serializado
        }
    )
```

## Código Corregido (CORRECTO)

```python
if tool_name in tool_functions:
    result = tool_functions[tool_name](
        tool_arguments,
        subscriber_id)
    logger.debug(
        "Resultado de la herramienta %s (Gemini): %s",
        tool_name, result)
    logger.info(
        "Resultado de la herramienta %s (Gemini): %s",
        tool_name, result)  # ← FIX: Removida variable result_json

    # Add function response to history
    conversation_history.append(response_content)

    function_response_part = genai_types.Part.from_function_response(
        name=tool_name,
        response={
            "output": result  # ← FIX: Cambiar "result" → "output" y usar result directo
        }
    )
```

## Cambios Necesarios

### 1. Eliminar la serialización JSON
**REMOVER esta línea:**
```python
result_json = json.dumps(result)
```

**REMOVER también el log que la usa:**
```python
logger.info(
    "Resultado de la herramienta %s (Gemini): %s",
    tool_name, result_json)
```

### 2. Actualizar el log para usar `result` directamente
**MANTENER este log:**
```python
logger.info(
    "Resultado de la herramienta %s (Gemini): %s",
    tool_name, result)
```

### 3. Cambiar la clave del diccionario de respuesta
**CAMBIAR de:**
```python
response={
    "result": result_json
}
```

**A:**
```python
response={
    "output": result
}
```

## Documentación Oficial de Gemini

Según la documentación oficial de Google Gemini API, el formato correcto para function responses es:

```python
types.Part.from_function_response(
    name="nombre_funcion",
    response={
        "output": "valor_de_respuesta"
    }
)
```

**Fuente:** Google Gemini API Documentation - Function Calling

## Impacto del Fix

### Antes del fix:
- Gemini recibía: `{"result": "\"INSTRUCCION OBLIGATORIA: ...\""}`
- El LLM ignoraba las instrucciones de las herramientas
- Continuaba la conversación como si todo hubiera sido exitoso

### Después del fix:
- Gemini recibe: `{"output": "INSTRUCCION OBLIGATORIA: ..."}`
- El LLM procesa correctamente las instrucciones
- Responde al usuario según lo que retorne la herramienta

## Verificación Post-Fix

Después de aplicar el fix, verificar en los logs que aparezca:

```
Mensaje function_response enviado a Gemini (Gemini): role='user' parts=[Part(function_response=FunctionResponse(name='crear_direccion', response={'output': '...'}))]
```

**NO debe aparecer:**
```
response={'result': '"..."'}  # ← Esto indica que NO se aplicó el fix
```

## Archivos Afectados

Este fix debe aplicarse en **TODOS** los archivos `main.py` en producción que usen Gemini API con function calling:

- [ ] main.py (Viking Burger)
- [ ] main.py (Dark Burger)
- [ ] main.py (Bandidos)
- [ ] main.py (Urban)
- [ ] Cualquier otro proyecto que use Gemini con function calling

## Prioridad

🔴 **CRÍTICA** - Aplicar inmediatamente en todos los ambientes de producción

## Notas Adicionales

- Este error afecta a **todas las herramientas** (crear_direccion, crear_pedido, enviar_menu, etc.)
- El error es silencioso: no genera excepciones, solo comportamiento incorrecto
- Se requiere reiniciar el servicio después de aplicar el fix
- Probar con una conversación nueva después del fix

---

**Fecha de creación:** 2026-01-19
**Autor:** Equipo de desarrollo Viking Burger
**Versión:** 1.0
