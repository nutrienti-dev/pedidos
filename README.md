# Nutrienti — Ordenes de Cosecha

App en Streamlit para que los puntos (restaurantes) de Nutrienti hagan sus
pedidos en linea, y luego confirmen la recepcion de cada pedido (para medir
tiempo de entrega). Todo queda registrado automaticamente en una Google
Sheet.

La app tiene dos pestañas:

- **📦 Hacer Pedido**: el flujo de siempre (elegir productos y cantidades,
  revisar, confirmar).
- **✅ Confirmar Recepción**: el punto busca su nombre, ve sus pedidos
  pendientes (los que aun no ha confirmado que recibio) y los marca como
  recibidos, con un cuadro de observaciones opcional.

## Como funciona

- **Clientes**: se cargan en vivo desde la hoja "Datos" (columna A) de
  [este Google Sheet](https://docs.google.com/spreadsheets/d/1LGjtIWTwrWSUw3LKC8jTmj-NMlwhygbAelD_C3hL-tQ)
  — se usan solo internamente para la sugerencia automatica de nombre, nunca
  se le muestran al punto.
- **Productos**: se cargan en vivo desde
  [esta Google Sheet](https://docs.google.com/spreadsheets/d/1b2_qDS9GMZGCJnAFBM690DBj3b_4qp5tqLDuQo7U5Bw)
  ("Nutrienti - Productos y Precios (pedidos web)", columna Producto —
  tambien tiene Unidad/Precio, pero el precio no se usa en el pedido, ver
  nota mas abajo). Se creo esta copia porque el archivo original,
  "BASE DE DATOS PRODUCTOS ACTIVOS.xlsx", es un Excel subido a Drive y la
  API de Google Sheets no puede leer archivos de Office directamente
  (error `APIError: [400] ... must not be an Office file`). Si el archivo
  original cambia, hay que actualizar esta copia a mano (o migrar el
  original a formato Google Sheets nativo con "Archivo > Guardar como
  Hojas de cálculo de Google" y apuntar la app a ese nuevo archivo).
- **Pedidos**: al confirmar, cada linea del pedido se agrega (append) a la
  hoja ["Pedidos Web - Registro de Solicitudes"](https://docs.google.com/spreadsheets/d/1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY),
  ubicada en la carpeta "Integracion AI" del Drive de Nutrienti. Se usa
  `append_rows` (no escritura por indice de fila), lo que es seguro para
  varios puntos enviando pedidos al mismo tiempo. Columnas actuales: Fecha
  Solicitud, Fecha Despacho Deseada, Cliente (texto ingresado), Cliente
  (sugerencia automatica), Similitud (%), Producto, Unidad, Cantidad,
  **Codigo Pedido, Estado, Fecha Recepcion, Observaciones** (las ultimas 4
  son para la confirmacion de recepcion, ver mas abajo). El encabezado se
  actualiza solo la primera vez que corre la app (`ensure_dest_headers()`),
  sin tocar filas de datos ya existentes.

> **Nota sobre precios (en pausa):** por decision del negocio, la app
> **ya no calcula ni muestra precios** — el pedido es solo producto +
> cantidad, y la hoja de destino tampoco guarda precio ni total. El
> trabajo de precios por cliente sigue en el codigo (funciones
> `price_for_client`, `get_pricing_data`, `build_price_matrix` en
> `app.py`, mas la matriz descrita abajo) pero no esta conectado al
> formulario de pedido. Para reactivarlo: volver a llamar
> `price_for_client(cliente, producto, clients)` al agregar cada item al
> carrito (como se hizo antes) y agregar de nuevo las columnas de precio
> a `DEST_HEADERS` / `append_order_to_sheet`.

## Confirmacion de recepcion ("✅ Confirmar Recepción")

Se agrego para poder medir el tiempo real de entrega: hasta ahora la hoja
solo registraba cuando se **pedia**, no cuando se **recibia**.

- Cada pedido enviado desde "📦 Hacer Pedido" genera un **Codigo Pedido**
  unico (ej. `240924-A1B2C`, fecha + 5 caracteres al azar) que se guarda en
  cada una de sus filas (una fila por producto), junto con `Estado =
  Pendiente`. El codigo se le muestra al punto en la pantalla final de
  confirmacion.
- En la pestaña "✅ Confirmar Recepción", el punto escribe su nombre (mismo
  campo "Nombre de Punto" que en el pedido) y ve todos sus pedidos con
  `Estado = Pendiente`, agrupados por Codigo Pedido (todos los productos de
  ese pedido juntos).
- Puede escribir una observacion libre (ej. "llego todo completo", "falto
  1kg de lechuga") y hacer clic en **"✅ Pedido Recibido"**. Esto marca
  **todas** las filas de ese Codigo Pedido a la vez: `Estado = Recibido`,
  `Fecha Recepcion` (fecha y hora), y `Observaciones`. La confirmacion es
  por pedido completo, no producto por producto.
- Los pedidos ya confirmados dejan de aparecer en la lista de pendientes
  (quedan en la hoja con `Estado = Recibido`, para reportes de tiempo de
  entrega despues).

### Como se identifica el "nombre del punto" (matching mejorado)

Antes, tanto para guardar el pedido como para (ahora) buscar los pedidos
pendientes, el nombre que escribe el punto se comparaba directo contra la
lista plana de clientes (`best_client_match`, similitud de texto). Eso
falla cuando el nombre del punto no se parece en nada a la razon social /
nombre de la cadena — por ejemplo "Astoria", "Bombay" o "Sexy Seoul" son
puntos de "ALTAS VISTAS SAS"; "Osaki" o "Sorella" son puntos de "TAKAMI
SA". Este mismo problema ya se habia detectado y resuelto en el otro
proyecto (`facturacion_repo`), asi que aca se **porto la misma solucion**
en vez de reinventarla:

- `resolve_cliente(texto, clients, nc_rows)` intenta primero contra la hoja
  ["RAZONES SOCIALES - NOMBRES COMERCIALES"](https://docs.google.com/spreadsheets/d/1_IbW0IhpSxiCVL9Xn97XsIe5wE4AWnWMjG8szdoWSNI)
  (columnas "Razon Social" / "Nombre Comercial"), que es la fuente de
  verdad de que nombre de punto pertenece a que cliente. Si encuentra un
  match confiable (`match_nombre_comercial`, umbral 72%), usa ese nombre
  comercial tal cual esta en la hoja.
  - **Si, se cruza con esa tabla** (era una de las preguntas pendientes):
    tanto el formulario de pedido como la busqueda de "mis pedidos" usan
    ahora esta misma logica, portada de
    `facturacion_repo/lib/matching.py` y `lib/data.py`, donde ya se probo
    con datos reales.
- Si esa hoja no tiene un match confiable (punto nuevo, nombre raro,
  hoja no disponible), cae de respaldo al metodo anterior
  (`best_client_match` contra la lista plana de clientes), asi la app
  nunca deja de funcionar por esto.
- Es importante que el nombre que se guarda como "Cliente (sugerencia
  automatica)" en cada pedido sea siempre el mismo nombre canonico que
  despues se usa para buscar "mis pedidos pendientes" — por eso ambos
  flujos usan la misma funcion `resolve_cliente()`.

## Matriz de precios por cliente (en pausa, ver nota arriba)

Pestaña **"matriz precios"** en la
[hoja de productos](https://docs.google.com/spreadsheets/d/1b2_qDS9GMZGCJnAFBM690DBj3b_4qp5tqLDuQo7U5Bw):
una fila por cliente, una columna por producto.

- **Celdas en verde**: precio real conocido para ese cliente (viene de las
  listas de precios de "BASE DE DATOS PRODUCTOS ACTIVOS.xlsx"). Como el
  sistema solo registra un precio especifico para un cliente cuando hay un
  acuerdo/pedido real, estas celdas tambien indican, a simple vista, **que
  productos pide habitualmente cada cliente**.
- **Celdas sin color**: no hay precio conocido para ese cliente en ese
  producto, asi que se usa el precio mas comun (moda) entre los demas
  clientes que si tienen precio para ese producto (o el precio general de
  la hoja de productos si nadie tiene precio conocido).

Los datos fuente viven en `precios_por_cliente.csv` (precios ya cruzados
contra la lista oficial de clientes) y `precios_sin_resolver.csv` (precios
de la fuente original que **no** se pudieron asignar con confianza a un
cliente exacto — nombres ambiguos como "Zona K", "GLUCK", "VENTURA", etc. —
y por lo tanto no estan en la matriz).

**Para crear o actualizar la matriz:** abre la app con `?admin=matriz` al
final de la URL (por ejemplo `https://tu-app.streamlit.app/?admin=matriz`)
y haz clic en "Construir / actualizar matriz de precios". Ahi mismo se
muestra la lista de precios sin resolver, por si quieren revisarla o
corregir `precios_por_cliente.csv` a mano.

> Nota sobre nombres de clientes en cadena (Poke, Cabrera, Crick, Famiglia,
> Il forno, La biferia, Mistral, Montolivo, Oliveto, Seratta, Storia de
> Amore): la fuente original solo tenia el nombre de la cadena, sin
> especificar sede, asi que el mismo precio se aplico a **todas** las sedes
> de esa cadena en la matriz. Si el precio realmente varia por sede,
> hay que corregirlo a mano en `precios_por_cliente.csv` o directamente en
> la hoja.

## Autenticacion con Google (ya configurada)

Tu organizacion de Google Cloud bloquea la creacion de llaves de cuenta de
servicio (politica `iam.disableServiceAccountKeyCreation`), asi que esta app
**no usa una cuenta de servicio**. En su lugar reutiliza las credenciales
OAuth que ya tenias en `D:\Otros_proyectos\nutrienti\secret.json` y
`gsheets_token.json` — la app se autentica como tu propia cuenta de Google,
que ya es dueña de las hojas involucradas (clientes, productos, pedidos, y
ahora tambien razones sociales/nombres comerciales), asi que no hace falta
compartir nada nuevo.

**`.streamlit/secrets.toml` ya fue creado y completado automaticamente** con
esas credenciales (esta en `.gitignore`, nunca se sube a git). Si necesitas
recrearlo en otra maquina, usa `.streamlit/secrets.toml.example` como
plantilla — la Opcion A explica como reutilizar tus credenciales OAuth.

> Nota: el refresh_token no expira mientras no lo revoques (o cambies tu
> contraseña de Google / permisos de la app). Si en algun momento la app
> deja de poder autenticarse, puede que haga falta regenerar el
> `gsheets_token.json` y volver a copiar `refresh_token` a `secrets.toml`.

## Instalar dependencias y correr localmente

```bash
cd "D:\Otros_proyectos\nutrienti\facturacion\pedidos_repo"
python -m venv .venv
.venv\Scripts\activate        # en Windows
pip install -r requirements.txt
streamlit run app.py
```

Se abrira en `http://localhost:8501`. No se agregaron dependencias nuevas
para esta version (el matching usa solo libreria estandar de Python:
`difflib`, `re`, `unicodedata`).

## Desplegar en Streamlit Community Cloud (gratis)

1. Sube el `app.py` actualizado a GitHub (mismo nombre de archivo,
   reemplaza al que ya esta en la raiz del repo). Si usas la interfaz web
   de GitHub: "Add file → Upload files", arrastra `app.py` y confirma —
   no hace falta subir ningun archivo nuevo, la hoja de Razon
   Social/Nombre Comercial se lee en vivo, no desde un CSV.
2. Streamlit Community Cloud redeploya solo al detectar el commit en
   `main`.

> Streamlit Community Cloud es gratis pero "duerme" la app tras un rato sin
> uso (tarda unos segundos en despertar con la primera visita). Si esto es
> un problema, se puede mover a un hosting pequeño de pago (Render,
> Railway, etc.) sin cambiar el codigo.

## Estructura del proyecto

```
pedidos_repo/
├── app.py                          # App principal de Streamlit (2 tabs + admin oculto)
├── precios_por_cliente.csv         # Precios reales conocidos por cliente (para la matriz, en pausa)
├── precios_sin_resolver.csv        # Precios que no se pudieron asignar a un cliente exacto
├── requirements.txt                # Dependencias Python
├── .gitignore                      # Excluye secrets y archivos temporales
├── .streamlit/
│   ├── config.toml                 # Tema visual (colores Nutrienti)
│   ├── secrets.toml                # Credenciales reales (NO se sube a git)
│   └── secrets.toml.example        # Plantilla de credenciales (sin datos reales)
└── README.md
```

## Pendientes / mejoras futuras

- Cruzar cliente → ruta de despacho (para la hoja de Remision con colores
  por ruta) — pendiente por definir con el equipo.
- Precios diferenciados por cliente usando la hoja "precios por cliente".
- Validaciones adicionales (cantidades minimas, dias de despacho
  disponibles, etc.) si el negocio lo requiere.
- Reportes de tiempo de entrega (Fecha Solicitud/Despacho vs Fecha
  Recepcion) — los datos ya quedan en la hoja, falta el reporte/dashboard.
- Revisar las ~3 filas historicas de prueba en la hoja de destino que
  tienen una columna extra entre "Similitud (%)" y "Producto" (dato viejo,
  no afecta filas nuevas).
