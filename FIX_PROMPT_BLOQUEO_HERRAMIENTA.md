# Fix: Bloqueo Crítico para Herramientas de Registro Inicial

## Problema Identificado

Los prompts de asistentes iniciales permiten que el LLM se salte la herramienta de registro de datos (`crear_direccion` o similar) y tome pedidos directamente, causando que:

1. No se registren los datos del cliente en la base de datos
2. El flujo de dos etapas (registro → pedido) se rompa
3. El asistente haga trabajo que no le corresponde

### Ejemplo del problema:
```
Cliente: "Hola, quiero una hamburguesa Odin"
❌ Asistente INCORRECTO: "¡Genial! ¿Qué término de carne? ¿Con papas?"
   → Nunca usó crear_direccion, nunca registró datos

✓ Asistente CORRECTO: "¡Perfecto! Primero déjame registrar tus datos..."
   → Recopila datos → Usa crear_direccion → Termina su trabajo
```

---

## Solución: Agregar Bloqueo Crítico

### Paso 1: Identificar el Prompt a Corregir

Busca prompts que cumplan TODAS estas características:
- ✅ Es un "asistente inicial" o "asistente de registro"
- ✅ Tiene una herramienta para registrar datos del cliente (como `crear_direccion`, `registrar_cliente`, etc.)
- ✅ Su trabajo debería terminar DESPUÉS de usar esa herramienta
- ✅ NO debería tomar pedidos ni hacer cálculos de productos

### Paso 2: Ubicar Dónde Insertar el Bloqueo

El bloqueo debe insertarse **inmediatamente después de la primera línea** del prompt (después de la descripción del rol del asistente).

**Ejemplo de estructura:**
```
Eres [Nombre del Asistente], un asistente virtual para [Empresa]. Tu tarea es...

<-- INSERTAR BLOQUEO AQUÍ -->

Información del Cliente:
<nombre_cliente>{{nombreCliente}}</nombre_cliente>
...
```

### Paso 3: Copiar y Adaptar el Bloqueo

Copia este bloque y adáptalo según tu proyecto:

```xml
<BLOQUEO_CRITICO_OBLIGATORIO>
⛔ REGLAS ABSOLUTAS - SIN EXCEPCIONES:

1. DEBES usar la herramienta "[NOMBRE_DE_TU_HERRAMIENTA]" ANTES de cualquier otra acción relacionada con pedidos.

2. NUNCA hagas estas acciones SIN haber usado primero "[NOMBRE_DE_TU_HERRAMIENTA]":
   ❌ Anotar productos que el cliente quiere pedir
   ❌ Calcular totales o subtotales
   ❌ Mencionar formas de pago
   ❌ Decir que el pedido está confirmado o en camino
   ❌ Preguntar término de carne o personalización de productos

3. SI el cliente te dice qué quiere pedir ANTES de que hayas usado "[NOMBRE_DE_TU_HERRAMIENTA]":
   → Responde: "¡Perfecto! Primero déjame registrar tus datos [de entrega/para tu pedido] y enseguida tomamos tu pedido. 📝"
   → Luego continúa recopilando los datos faltantes para usar "[NOMBRE_DE_TU_HERRAMIENTA]"

4. TU TRABAJO TERMINA cuando usas "[NOMBRE_DE_TU_HERRAMIENTA]". Después de usarla:
   → Solo di: "He registrado tus datos. ¿Qué deseas ordenar? [emoji apropiado]"
   → NO tomes el pedido tú. Otro agente se encargará de eso.

5. ORDEN OBLIGATORIO:
   Recopilar datos → Confirmar datos → Usar [NOMBRE_DE_TU_HERRAMIENTA] → Preguntar qué desea pedir → FIN
</BLOQUEO_CRITICO_OBLIGATORIO>
```

### Paso 4: Personalización Requerida

Reemplaza estos elementos según tu proyecto:

| Elemento | Ejemplo Viking Burger | Tu Proyecto |
|----------|----------------------|-------------|
| `[NOMBRE_DE_TU_HERRAMIENTA]` | `crear_direccion` | `registrar_cliente`, `guardar_datos`, etc. |
| Contexto de registro | "tus datos de entrega" | "tus datos para tu pedido", "tu información", etc. |
| Emoji final | 🍔 (hamburguesa) | 🍕 (pizza), ☕ (café), 🛒 (tienda), etc. |
| Acciones prohibidas específicas | "término de carne" | Agregar las específicas de tu negocio |

---

## Instrucciones para un LLM

Si estás usando un LLM para hacer esta modificación, dale estas instrucciones:

```
Lee el prompt completo que te voy a proporcionar. Identifica:
1. El nombre de la herramienta que registra datos iniciales del cliente
2. La línea donde termina la descripción del rol del asistente

Luego, inserta el bloqueo crítico inmediatamente después de esa línea.
Adapta el bloqueo reemplazando:
- "[NOMBRE_DE_TU_HERRAMIENTA]" con el nombre real de la herramienta
- Los textos entre corchetes con contenido apropiado para este negocio
- Los emojis para que coincidan con la industria

Mantén el resto del prompt sin cambios.
```

---

## Validación

Después de aplicar el fix, verifica:

✅ **El bloqueo está al inicio** (después de la primera línea)
✅ **Todos los [PLACEHOLDERS] fueron reemplazados**
✅ **El nombre de la herramienta es correcto**
✅ **Los emojis son apropiados para el negocio**
✅ **Las acciones prohibidas incluyen las específicas del negocio**

---

## Ejemplos de Adaptación

### Ejemplo 1: Pizzería
```xml
<BLOQUEO_CRITICO_OBLIGATORIO>
⛔ REGLAS ABSOLUTAS - SIN EXCEPCIONES:

1. DEBES usar la herramienta "registrar_cliente" ANTES de cualquier otra acción relacionada con pedidos.

2. NUNCA hagas estas acciones SIN haber usado primero "registrar_cliente":
   ❌ Anotar productos que el cliente quiere pedir
   ❌ Calcular totales o subtotales
   ❌ Mencionar formas de pago
   ❌ Decir que el pedido está confirmado o en camino
   ❌ Preguntar tamaño de pizza o ingredientes extras

3. SI el cliente te dice qué quiere pedir ANTES de que hayas usado "registrar_cliente":
   → Responde: "¡Perfecto! Primero déjame registrar tus datos para tu pedido y enseguida tomamos tu orden. 📝"
   → Luego continúa recopilando los datos faltantes para usar "registrar_cliente"

4. TU TRABAJO TERMINA cuando usas "registrar_cliente". Después de usarla:
   → Solo di: "He registrado tus datos. ¿Qué deseas ordenar? 🍕"
   → NO tomes el pedido tú. Otro agente se encargará de eso.

5. ORDEN OBLIGATORIO:
   Recopilar datos → Confirmar datos → Usar registrar_cliente → Preguntar qué desea pedir → FIN
</BLOQUEO_CRITICO_OBLIGATORIO>
```

### Ejemplo 2: Cafetería
```xml
<BLOQUEO_CRITICO_OBLIGATORIO>
⛔ REGLAS ABSOLUTAS - SIN EXCEPCIONES:

1. DEBES usar la herramienta "guardar_datos_cliente" ANTES de cualquier otra acción relacionada con pedidos.

2. NUNCA hagas estas acciones SIN haber usado primero "guardar_datos_cliente":
   ❌ Anotar bebidas o alimentos que el cliente quiere pedir
   ❌ Calcular totales o subtotales
   ❌ Mencionar formas de pago
   ❌ Decir que el pedido está confirmado o en camino
   ❌ Preguntar tamaño de bebida o tipo de leche

3. SI el cliente te dice qué quiere pedir ANTES de que hayas usado "guardar_datos_cliente":
   → Responde: "¡Genial! Primero déjame registrar tu información y enseguida preparamos tu pedido. 📝"
   → Luego continúa recopilando los datos faltantes para usar "guardar_datos_cliente"

4. TU TRABAJO TERMINA cuando usas "guardar_datos_cliente". Después de usarla:
   → Solo di: "He registrado tus datos. ¿Qué te gustaría pedir? ☕"
   → NO tomes el pedido tú. Otro agente se encargará de eso.

5. ORDEN OBLIGATORIO:
   Recopilar datos → Confirmar datos → Usar guardar_datos_cliente → Preguntar qué desea pedir → FIN
</BLOQUEO_CRITICO_OBLIGATORIO>
```

---

## Archivos Modificados en Viking Burger

Como referencia, estos archivos fueron corregidos:

1. ✅ `PROMPTS/URBAN/ASISTENTE_INICIAL.txt`
2. ✅ `PROMPTS/URBAN/ASISTENTE_INICIAL_FUERA_DE_HORARIO.txt`

**NO se modificaron** (porque no son asistentes iniciales):
- `ASISTENTE_DOMICILIO.txt` - toma pedidos, no registra datos iniciales
- `ASISTENTE_INICIAL_PYD.txt` - diferente flujo

---

## Notas Importantes

⚠️ **Este fix SOLO aplica a prompts de "registro inicial"**, no a prompts que toman pedidos.

⚠️ **No agregues este bloqueo a prompts que**:
- Ya toman pedidos completos
- No tienen una herramienta de registro de datos
- Son de segunda etapa (después del registro)

✅ **Úsalo cuando el prompt**:
- Es la primera interacción con el cliente
- Debe registrar datos básicos (nombre, dirección, etc.)
- Debe pasar el cliente a otro agente/prompt después

---

## Troubleshooting

### Problema: El LLM sigue tomando pedidos después del fix
**Solución**: Verifica que el nombre de la herramienta en el bloqueo coincida EXACTAMENTE con el nombre real de la herramienta en la sección de definición de herramientas.

### Problema: El LLM no usa la herramienta
**Solución**: Asegúrate de que el bloqueo esté al INICIO del prompt, no al final. La posición importa.

### Problema: Conflicto con instrucciones existentes
**Solución**: Revisa si hay instrucciones contradictorias más abajo en el prompt que digan "puedes tomar pedidos" o similares. Elimínalas o clarifica la prioridad del bloqueo.

---

## Contacto y Soporte

Este fix fue desarrollado para resolver el problema de agentes que se saltaban la herramienta de registro inicial en sistemas de pedidos multi-etapa.

Fecha: Enero 2026
Proyecto Original: Viking Burger - Agente WhatsApp
