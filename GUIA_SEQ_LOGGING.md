# Guía: Implementar Seq Logging en App Python/Flask

## Requisitos previos
- Seq ya está desplegado en EasyPanel
- URL de Seq interna: `http://replit_seq-proyectos:80/`
- URL de Seq externa: `https://replit-seq-proyectos.qrxwn9.easypanel.host/`

---

## Paso 1: Agregar dependencia

En `requirements.txt` agregar al final:

```
seqlog
```

---

## Paso 2: Modificar `main.py`

### 2.1 Buscar la sección de configuración de logging

Buscar código similar a:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
```

### 2.2 Reemplazar con esta configuración:

```python
import logging
import os

# Configuración de Seq para logs persistentes
SEQ_SERVER_URL = os.environ.get('SEQ_SERVER_URL')
APP_NAME = os.environ.get('APP_NAME', 'default-app')

# Crear lista de handlers
log_handlers = [logging.StreamHandler()]  # Salida a la consola

# Agregar handler de Seq si está configurado
if SEQ_SERVER_URL:
    from seqlog import SeqLogHandler
    seq_handler = SeqLogHandler(
        server_url=SEQ_SERVER_URL,
        batch_size=10,
        auto_flush_timeout=10,
        extra_properties={
            "Application": APP_NAME
        }
    )
    seq_handler.setLevel(logging.INFO)
    log_handlers.append(seq_handler)

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=log_handlers
)

logger = logging.getLogger(__name__)

if SEQ_SERVER_URL:
    logger.info("Seq logging habilitado: %s (App: %s)", SEQ_SERVER_URL, APP_NAME)
```

> **Importante:** Asegurarse que `import os` esté al inicio del archivo si no existe.

---

## Paso 3: Configurar variables de entorno en EasyPanel

En el servicio de la app:

1. Ir a **Environment**
2. Click en **+ Add Variable**
3. Agregar estas variables:

| Key | Value | Descripción |
|-----|-------|-------------|
| `SEQ_SERVER_URL` | `http://replit_seq-proyectos:80/` | URL del servidor Seq |
| `APP_NAME` | `nombre-de-tu-app` | Nombre único para identificar la app en Seq |

**Ejemplos de APP_NAME:**
- `viking-burger`
- `mi-otra-app`
- `api-pagos`

> **Nota:** Si la app está en un proyecto diferente de EasyPanel, usar la URL externa: `https://replit-seq-proyectos.qrxwn9.easypanel.host/`

---

## Paso 4: Redesplegar

Click en **Deploy** o **Implementar** en EasyPanel.

---

## Paso 5: Verificar

1. Abrir Seq: https://replit-seq-proyectos.qrxwn9.easypanel.host/
2. Login: `admin` / `[password configurado]`
3. Deberían aparecer los logs de la nueva app

---

## Resumen de cambios

| Archivo | Acción |
|---------|--------|
| `requirements.txt` | Agregar `seqlog` al final |
| `main.py` | Reemplazar/modificar configuración de logging |
| EasyPanel Environment | Agregar variable `SEQ_SERVER_URL` |

---

## Filtrar logs por aplicación en Seq

Una vez tengas varias apps enviando logs, puedes filtrarlas en Seq:

### Filtro rápido (en la barra de búsqueda):

```
Application = 'viking-burger'
```

```
Application = 'mi-otra-app'
```

### Crear un Signal (filtro guardado):

1. En Seq, ir a **Signals** (menú izquierdo)
2. Click en **Add Signal**
3. Nombre: `Viking Burger`
4. Filter: `Application = 'viking-burger'`
5. Guardar

Ahora tendrás un botón rápido para ver solo los logs de esa app.

### Ver todas las apps:

En la barra de búsqueda escribe:
```
select distinct(Application)
```

---

## Troubleshooting

| Problema | Solución |
|----------|----------|
| No llegan logs a Seq | Verificar que `SEQ_SERVER_URL` esté configurada en Environment |
| Error de conexión | Verificar que Seq esté corriendo y la URL sea correcta |
| Solo llegan logs de werkzeug | Verificar que el `SeqLogHandler` esté agregado a `log_handlers` |
| App no inicia | Verificar que `seqlog` esté en requirements.txt y se haya reinstalado |

---

## Contacto

Si hay dudas, revisar la documentación oficial de Seq: https://docs.datalust.co/docs/getting-started
