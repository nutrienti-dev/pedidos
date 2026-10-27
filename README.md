# Nutrienti — App de Pedidos Web (Streamlit)

## Estado: ✅ DESPLEGADA Y FUNCIONANDO — 2 cambios chicos locales aun no subidos a GitHub

Repo: `github.com/nutrienti-dev/pedidos` (cuenta GitHub propia de la
empresa). Local en `D:\Otros_proyectos\nutrienti\facturacion\pedidos_repo`
(**con guion bajo** — hay una carpeta antigua `D:\Otros proyectos\nutrienti`,
con espacio, que NO es la que se usa; ver nota de carpetas mas abajo).

Flujo de trabajo de despliegue establecido: el usuario **no usa `git push`
de forma confiable** (friccion con el credential manager de Windows).
Sube/edita archivos vía la interfaz web de GitHub ("Add file → Upload
files", que reemplaza el archivo existente con el mismo nombre). Streamlit
Community Cloud redeploya solo al detectar el commit en `main`.

**2026-10-09 → 2026-10-20**: los 3 cambios que estaban pendientes (fix del
`PRODUCTS_SHEET_ID`, Razon Social + NIT, Codigo Producto) ya fueron
subidos a GitHub por el usuario y confirmados funcionando en produccion
("ok, ya funciona", 2026-10-20). Verificado con un punto real: "la
biferia santafe" → razon social `LA BIFERIA S A`, NIT `830135186`.

**⚠️ Pendiente de subir a GitHub (no bloqueante, la app funciona bien
sin esto, son solo mejoras de UX/datos)**. La logica de fecha de despacho
paso por 3 iteraciones seguidas sin llegar a subirse a GitHub ninguna de
las 2 primeras (el negocio la siguio afinando antes de desplegar nada) —
solo la ultima version (2026-10-27) importa para el proximo commit:
4. ~~Fecha de despacho = solicitud + 2 dias~~ (2026-10-20) — superada.
5. ~~Fecha de despacho = proxima martes/jueves/sabado~~ (2026-10-26) —
   superada (no distinguia bien cada dia, ver seccion propia).
6. **Fecha de despacho segun tabla fija por dia de la semana** + nueva
   columna "Fecha y Hora de Registro" (2026-10-26/27, ver seccion propia
   mas abajo) — esta es la version vigente en `app.py` local.

Ya esta aplicado en `app.py` local (entregado + escrito vía bridge el
2026-10-27) — falta que el usuario lo suba a GitHub junto con el
`requirements.txt` actualizado (agrega `tzdata`).

## ⚠️ Incidente 2026-10-09: hoja de productos borrada — RESUELTO Y DESPLEGADO

La hoja de productos (`PRODUCTS_SHEET_ID`) desaparecio de Drive (borrada,
no recuperable desde la papelera de `contacto@nutrienti.co`) y la app dejo
de cargar: `No se pudo conectar con Google Sheets: <Response [404]>`. Las
otras hojas (clientes, destino de pedidos) seguian intactas — solo
productos fallaba, confirmado probando cada `fileId` por separado.

**Solucion aplicada**: se reconstruyo la hoja desde el mismo origen de
siempre, `BASE DE DATOS PRODUCTOS ACTIVOS.xlsx` (fileId
`1At3DzHvgQXnPueF7QK_KDvTeYyAN0oiE`, que SI seguia existiendo), extrayendo
Descripción/Unidad Medida/primer precio de lista disponible para cada
producto (misma logica documentada que el original: 55 productos, 46 con
precio resuelto — coincide exacto con "46 productos con precio de prueba"
documentado antes de este incidente, buena señal de que la reconstruccion
replico el original). Se creo como Sheet nativa nueva en la carpeta
"Integracion AI", dueña `contacto@nutrienti.co` (mismo dueño que las demas,
no requiere compartir nada).

- **Primer ID nuevo** (Producto/Unidad/Precio, 3 columnas):
  `1UaciwAHXOFWdndvKWq5bO1In8zHJ_9O7aPL6CgVxuLM`. El original
  `1b2_qDS9GMZGCJnAFBM690DBj3b_4qp5tqLDuQo7U5Bw` ya NO existe, no reusar.
- **Mismo dia, segundo ID nuevo** (se agrego columna Codigo, ver seccion
  propia mas abajo): `11oSUTlnB-FZvpQcTxnk2lndeJZt5nRNne3PCv6MJgsE` — este
  es el que esta en uso ahora. El de 3 columnas (`1Uaciw...`) se renombro
  con prefijo `[REEMPLAZADA 2026-10-09, ver nueva con Codigo]` en vez de
  borrarse, por si hace falta consultarlo.
- `PRODUCTS_SHEET_ID` en `app.py` apunta al ID vigente — **ya desplegado
  en produccion** (confirmado 2026-10-20).
- Las columnas `precios_por_cliente.csv`/`precios_sin_resolver.csv` del
  repo (para la matriz, en pausa) NO se vieron afectadas por este
  incidente — son archivos locales del repo, no dependen de la hoja
  borrada.

**Recomendación para el usuario**: varias hojas de la carpeta "Integracion
AI" son dependencias en vivo de esta app (clientes, productos, destino de
pedidos, razon social/nombre comercial) — evitar borrarlas o moverlas sin
avisar. Si una desaparece, el sintoma es el mismo error 404 en pantalla al
abrir la app.

## ✨ Feature 2026-10-09: Razon Social + NIT en la hoja de pedidos — DESPLEGADA

El usuario pidio poder ver, en la hoja ["Pedidos Web - Registro de
Solicitudes"](https://docs.google.com/spreadsheets/d/1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY),
el nombre oficial del cliente (razon social) y su NIT, junto a cada
pedido — para que facturacion no tenga que cruzarlo a mano.

**Implementacion** (portada de `facturacion_repo`, que ya resolvia este
mismo problema con datos reales — ver `claude/facturacion-web-streamlit.md`):

- `resolve_cliente()` ahora devuelve un 4to valor: la razon social tal
  como aparece en la hoja "RAZONES SOCIALES - NOMBRES COMERCIALES" (solo
  cuando el match vino de esa hoja, fuente `"mapa"`; `None` si cayo al
  metodo de respaldo).
- Nueva funcion `load_client_master()`: descarga
  ["BASE DE DATOS CLIENTES ACTIVOS.xlsx"](https://drive.google.com/file/d/16GFApKVxoQ1mVURvCpgbDGNmwjCGbeka)
  (maestro de clientes World Office, mismo archivo que ya usaba
  `facturacion_repo`) vía la API de Drive (nueva funcion
  `get_drive_service()`, mismas credenciales OAuth) y lo parsea con
  `openpyxl` (es un Excel, la API de Sheets no lo puede leer directo —
  mismo patron ya usado para la hoja de productos).
- Nueva funcion `find_client_master_by_razon()`: busca esa razon social en
  el maestro de clientes ignorando sufijos societarios (SAS, S.A., LTDA,
  via nueva funcion `strip_legal_suffix()`), umbral de similitud 60%.
  Devuelve razon social oficial + NIT (columnas "Primer Nombre ó Razon
  Social" e "Identificación" del Excel).
- Nueva funcion `resolve_nit()` junta todo: a partir de la razon social
  resuelta, devuelve `(razon_social_oficial, nit)` o `("", "")` si no se
  pudo resolver con confianza.
- `DEST_HEADERS` gano 2 columnas: **"Cliente (Razon Social)"** y **"NIT"**
  (seguidas de "Codigo Producto" y "Fecha y Hora de Registro", agregadas
  despues — ver secciones siguientes). `append_order_to_sheet()` las
  escribe cuando estan disponibles, vacias si no.
- Es un "nice to have": si la hoja de razones sociales o el maestro de
  clientes no cargan (permisos, archivo movido), el pedido se sigue
  guardando normalmente, solo sin esas columnas (warning, no bloquea).
- En la pantalla de revision del pedido se muestra "Facturacion:
  **<razon social>** · NIT <nit>" cuando se resolvio, para que el punto
  (o quien revisa) lo vea antes de confirmar.
- Dependencias nuevas en `requirements.txt`: `google-api-python-client`,
  `openpyxl`.
- **Verificado en produccion 2026-10-20**: punto "la biferia santafe" →
  razon social `LA BIFERIA S A`, NIT `830135186` (confirmado contra
  "BASE DE DATOS CLIENTES ACTIVOS.xlsx").

## ✨ Feature 2026-10-09 (mismo dia): Codigo de producto en la hoja de pedidos — DESPLEGADA

El usuario reviso la hoja de pedidos, no vio todavia Razon Social/NIT
(normal, ese commit aun no se habia subido a GitHub en ese momento) y de
paso pidio una columna mas: el **codigo interno del producto** (ej.
`CET01`, `LB014`) en cada linea.

**Implementacion**:

- La hoja de productos (`PRODUCTS_SHEET_ID`) ahora tiene una columna
  `Codigo` ademas de Producto/Unidad/Precio — ver seccion del incidente
  arriba para el detalle de como se agrego (archivo nuevo, Drive API no
  permite editar contenido de una Sheet ya creada vía este conector).
  Los codigos se extrajeron del Excel original
  (`BASE DE DATOS PRODUCTOS ACTIVOS.xlsx`, columna "Código") por
  **posicion**, ya que el orden de las 55 filas coincide exacto entre el
  Excel y la copia nativa (verificado comparando cada descripcion de
  producto, cero discrepancias).
- `load_products()` lee esa columna y la incluye en cada producto del
  catalogo (`p["codigo"]`).
- El carrito (`st.session_state.cart`) ahora guarda `codigo` junto con
  producto/unidad/cantidad.
- `DEST_HEADERS` gano una 3ra columna: **"Codigo Producto"**.
  `append_order_to_sheet()` la escribe para cada linea del pedido (vacia
  si el producto no tiene codigo, no deberia pasar con el catalogo
  actual).

## 🔁 Historia de la fecha de despacho por defecto (3 iteraciones, 2026-10-20 → 2026-10-27)

El campo "Fecha de despacho deseada" paso por 3 versiones seguidas, cada
una afinando la anterior a partir de feedback real del negocio. Solo la
**ultima (2026-10-27) es la version vigente** — las 2 primeras ni
llegaron a subirse a GitHub.

**v1 (2026-10-20) — "+2 dias" fijo**: el default dejo de ser igual a
"Fecha de la solicitud" y paso a ser 2 dias despues. Implementado con
`key` + `on_change` en los `st.date_input` (patron recomendado por
Streamlit para sincronizar dos widgets sin `StreamlitAPIException`, que
se sigue usando en las versiones siguientes). **Problema detectado por el
cliente final** (vía WhatsApp, reenviado por el usuario, 2026-10-26): el
negocio solo despacha martes/jueves/sabado, y "+2 dias" a veces caia en
un dia sin despacho real (ej. pedir lunes daba miercoles).

**v2 (2026-10-26) — "proxima fecha martes/jueves/sabado"**: se reemplazo
el "+2 dias" por una funcion que buscaba la primera fecha, estrictamente
despues de la solicitud, que cayera en uno de esos 3 dias (confirmado con
el usuario vía `AskUserQuestion`: si la solicitud ya caia en un dia
valido, saltar al siguiente, nunca mismo dia). En la misma vuelta se
agrego tambien la columna "Fecha y Hora de Registro" (ver mas abajo, esa
parte **no cambio** en la v3). **Problema**: el negocio aclaro al dia
siguiente (2026-10-27) que no querian "la proxima valida sin mas" sino
una regla especifica por cada dia de la semana — con v2, miercoles
hubiera dado jueves, pero el negocio siempre quiso sabado para los
pedidos de miercoles.

**v3 (2026-10-27) — tabla fija por dia de la semana — VIGENTE**: el
usuario paso la tabla completa que el cliente final definio:

| Pedido del... | Se despacha el... |
|---|---|
| Lunes | Jueves |
| Martes | Jueves |
| Miercoles | Sabado |
| Jueves | Sabado |
| Viernes | Martes (semana siguiente) |
| Sabado | Martes |
| Domingo | Martes |

**Implementacion v3**:
- Nueva constante `DIAS_HASTA_DESPACHO`: dict `{weekday_solicitud: dias_a_sumar}`
  (`date.weekday()` de Python: lunes=0 ... domingo=6) — `{0:3, 1:2, 2:3,
  3:2, 4:4, 5:3, 6:2}`. Reemplaza por completo la `DIAS_DESPACHO_VALIDOS`
  / `proxima_fecha_despacho_valida()` de la v2 (funciones/constantes
  eliminadas, no quedan referencias viejas en el codigo).
- Nueva funcion `fecha_despacho_segun_dia_solicitud(fecha_solicitud)`:
  `fecha_solicitud + timedelta(days=DIAS_HASTA_DESPACHO[fecha_solicitud.weekday()])`.
  Se usa tanto para el valor inicial de `fecha_despacho_input` como en el
  callback `_sync_fecha_despacho()` (mismo mecanismo `on_change` que las
  versiones anteriores).
- Verificado con un barrido de una semana completa (lunes a domingo)
  contra la tabla exacta de arriba — coincide en los 7 casos.
- El campo sigue siendo un `st.date_input` normal (Streamlit no permite
  restringir dias de la semana seleccionables), asi que el usuario puede
  seguir corrigiendo la fecha a mano si hace falta; el ajuste es solo al
  valor sugerido por defecto.

## ✨ Feature 2026-10-26: Fecha y Hora de Registro automatica — DESPLEGABLE (no cambio en v3)

El cliente final tambien pidio que quedara registrada automaticamente la
hora real en que se hizo la solicitud (distinto de "Fecha Solicitud", que
es la fecha que el punto elige a mano en el formulario, sin hora).
Confirmado con el usuario vía `AskUserQuestion`: va en una **columna
nueva al final** de la hoja, no mezclada con "Fecha Solicitud".

**Implementacion** (sigue igual en la v3 de arriba, no se toco):
- Nueva columna al final de `DEST_HEADERS`: **"Fecha y Hora de
  Registro"**. `append_order_to_sheet()` calcula `datetime.now(BOGOTA_TZ)`
  (zona horaria `America/Bogota` vía `zoneinfo.ZoneInfo`, nueva constante
  `BOGOTA_TZ`) una sola vez por pedido y la escribe en todas sus filas
  como `YYYY-MM-DD HH:MM:SS`. Streamlit Community Cloud corre en UTC, por
  eso se fuerza la zona horaria en vez de usar `datetime.now()` a secas.
- Nueva dependencia en `requirements.txt`: `tzdata` (base de datos IANA
  de zonas horarias que `zoneinfo` necesita en Windows; en Linux
  normalmente ya esta en el sistema, pero no hace daño ahi y evita que
  falle si el usuario corre la app localmente en Windows).

Archivo + requirements.txt (v3 completa: tabla de despacho + hora de
registro) entregados al usuario y escritos vía bridge en
`D:\Otros_proyectos\nutrienti\facturacion\pedidos_repo\` 2026-10-27 —
falta subir a GitHub (no bloqueante, ver bloque de estado arriba).

## Como es la app hoy (actualizado 2026-10-27)

La app tiene **2 pestañas**:

- **📦 Hacer Pedido**: fecha solicitud (hoy por defecto) / fecha despacho
  (segun la tabla fija por dia de la semana, ver seccion propia arriba:
  lunes/martes→jueves, miercoles/jueves→sabado,
  viernes/sabado/domingo→martes) → nombre de "Nombre de Punto" (antes
  decia "restaurante") → agregar productos+cantidad al carrito → revisar
  (muestra razon social/NIT si se resolvio) → confirmar. **Ya NO calcula
  ni muestra precios** (ver "Simplificacion de precios" abajo) — genera
  un **Codigo Pedido** unico al confirmar, y registra automaticamente la
  fecha+hora real de envio (hora Colombia).
- **✅ Confirmar Recepción** (agregada 2026-09-24): el punto busca
  su "Nombre de Punto", ve sus pedidos con `Estado = Pendiente` agrupados
  por Codigo Pedido, escribe observaciones opcionales y confirma con
  "Pedido Recibido" — marca **todas** las filas de ese pedido a la vez
  (`Estado = Recibido`, `Fecha Recepcion`, `Observaciones`). Se creo porque
  el negocio decidio que hay que medir tiempo de entrega, y hasta entonces
  la hoja solo registraba cuando se pedia, nunca cuando se recibia.

Ademas hay un panel admin oculto (`?admin=matriz` en la URL) para
reconstruir la matriz de precios por cliente (ver mas abajo) — no
visible para los puntos normales.

### Simplificacion de precios (decision de negocio)

Por instruccion explicita del usuario, la app dejo de calcular/mostrar
precios: el pedido es solo producto + cantidad. **El codigo de precios NO
se borro**, quedo dormido en `app.py` (`price_for_client`,
`get_pricing_data`, `build_price_matrix`, la matriz "matriz precios" en la
hoja de productos) por si se reactiva mas adelante. Ver el README del repo
para el detalle exacto de que reconectar.

### Hoja de destino — columnas actuales (16, ampliadas 2026-10-09 y 2026-10-26)

`1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY` ("Pedidos Web - Registro de
Solicitudes"), hoja `sheet1` unica. **Ya no tiene columnas de precio.**
Columnas: Fecha Solicitud, Fecha Despacho Deseada, Cliente (texto
ingresado), Cliente (sugerencia automatica), Similitud (%), Producto,
Unidad, Cantidad, Codigo Pedido, Estado, Fecha Recepcion, Observaciones,
Cliente (Razon Social), NIT, Codigo Producto, **Fecha y Hora de Registro**
(esta ultima agregada 2026-10-26, las 3 antes de ella agregadas
2026-10-09 — ver secciones propias arriba; las 4 antes de "Cliente (Razon
Social)" son para "Confirmar Recepción"). El encabezado se auto-corrige
al arrancar la app (`ensure_dest_headers()`), sin tocar filas de datos
existentes — no hace falta editar la hoja a mano. Las columnas hasta
"Codigo Producto" ya estan desplegadas y confirmadas funcionando; "Fecha
y Hora de Registro" todavia esta solo en local (ver bloque de estado
arriba). El **valor por defecto** que llega a "Fecha Despacho Deseada" ya
usa la tabla fija v3 (2026-10-27).

Nota menor sin resolver: 3 filas historicas de prueba (central cevicheria
09-11, takami 09-15, osaki 09-15) parecen tener una columna extra entre
Similitud y Producto — dato viejo, no bloquea, no afecta filas nuevas.

### Matching de "nombre del punto"

El usuario pidio confirmar si el "nombre del punto" se cruza contra la
hoja ["RAZONES SOCIALES - NOMBRES
COMERCIALES"](https://docs.google.com/spreadsheets/d/1_IbW0IhpSxiCVL9Xn97XsIe5wE4AWnWMjG8szdoWSNI)
(razon social / nombre comercial). Respuesta: **antes NO se cruzaba**
(solo `best_client_match` contra la lista plana de 380 clientes); ahora
**si**, via una funcion `resolve_cliente()` portada del proyecto
hermano `facturacion_repo` (que ya habia resuelto este mismo problema con
datos reales — ver `claude/facturacion-web-streamlit.md`):

1. Intenta `match_nombre_comercial()` contra la hoja Razon Social/Nombre
   Comercial (umbral 72%) — resuelve casos donde el nombre del punto no se
   parece en nada a la razon social/cadena (ej. "Astoria"/"Bombay" →
   "ALTAS VISTAS SAS"; "Osaki"/"Sorella" → "TAKAMI SA").
2. Si no hay match confiable ahi, cae de respaldo a `best_client_match()`
   contra la lista de 380 clientes (el metodo anterior).

Se usa **tanto en el formulario de pedido como en la busqueda de "mis
pedidos pendientes"**, para que el mismo punto siempre resuelva al mismo
nombre canonico en ambos lados. Desde 2026-10-09 tambien es la base para
resolver Razon Social/NIT (ver seccion propia arriba): solo cuando el
match vino de esta hoja ("fuente mapa") hay razon social de donde partir.

## Fuentes de datos (finales, en uso)
- **Clientes**: Sheet nativa `1LGjtIWTwrWSUw3LKC8jTmj-NMlwhygbAelD_C3hL-tQ`, hoja "Datos", columna A (380 clientes). Solo para sugerencia interna, nunca se muestra al punto.
- **Productos**: Sheet nativa `11oSUTlnB-FZvpQcTxnk2lndeJZt5nRNne3PCv6MJgsE` ("Nutrienti - Productos y Precios (pedidos web)"), carpeta "Integracion AI". **ID actualizado 2 veces el 2026-10-09** (ver seccion del incidente arriba) — ni el ID original (`1b2_qDS9...`) ni el intermedio (`1Uaciw...`) existen/se usan ya. Columnas **Codigo, Producto, Unidad, Precio** — el precio ya no se usa en el pedido (ver simplificacion arriba), pero sigue ahi para la matriz en pausa; Codigo si se usa (columna "Codigo Producto" en destino). Fila sin precio > 0 en `Precio` queda excluida del dropdown del formulario (filtro en `load_products()`), ojo con eso si se edita la hoja a mano.
  - Reconstruida desde `BASE DE DATOS PRODUCTOS ACTIVOS.xlsx` (fileId `1At3DzHvgQXnPueF7QK_KDvTeYyAN0oiE`), que es un Excel subido a Drive — la API de Sheets no puede leerlo directamente (`APIError 400: must not be an Office file`), por eso sigue existiendo esta copia nativa en paralelo. Si el catalogo cambia, hay que regenerar esta copia a mano (y volver a poner los Codigo si se agregan productos nuevos).
- **Destino de pedidos**: `1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY` (ver columnas arriba). Escritura vía `append_rows` (concurrency-safe); actualizacion de recepcion vía `findall` + `batch_update`.
- **Razon Social / Nombre Comercial (usado para matching)**: `1_IbW0IhpSxiCVL9Xn97XsIe5wE4AWnWMjG8szdoWSNI` ("RAZONES SOCIALES - NOMBRES COMERCIALES"). Columnas reales: RAZON SOCIAL, NOMBRE COMERCIAL, OBSERVACION, + ~48 columnas de nombres de producto (parece doblar como tabla de "productos habituales" por cliente, no usada para eso aca). Se lee en vivo, se cachea 300s.
- **Maestro de clientes (NIT), nuevo 2026-10-09**: fileId `16GFApKVxoQ1mVURvCpgbDGNmwjCGbeka` ("BASE DE DATOS CLIENTES ACTIVOS.xlsx", World Office), carpeta Drive `1OTwNyIhnOeSpe3PbKskQz6J3TDNiUxDr` (distinta de "Integracion AI"), dueño `csanchez@nutrienti.co`. Excel subido a Drive, se lee vía Drive API + `openpyxl` (mismo patron que productos). Columnas usadas: "Primer Nombre ó Razon Social", "Identificación" (= NIT). Mismo archivo que ya usaba `facturacion_repo` (`CLIENTS_MASTER_FILE_ID`).
- **Precios por cliente para la matriz (en pausa)**: `precios_por_cliente.csv` / `precios_sin_resolver.csv` en el repo (extraidos de "BASE DE DATOS PRODUCTOS ACTIVOS.xlsx"). Distinto de la tabla `1HMNBT9Qqogz3WgZIenm-jB9wTUP7Ta_NP1BhUhoB3-s` ("Nutrienti - Precios por Cliente (World Office)", 192 filas/66 empresas) mencionada en una version anterior de este doc — esa tabla de World Office **no se termino integrando**, quedo obsoleta frente al enfoque de matriz+CSV que si se implemento.

## Autenticacion
Org de Cesar bloquea creacion de llaves de cuenta de servicio (`iam.disableServiceAccountKeyCreation`). Se usa OAuth de usuario: `[gcp_oauth]` en secrets con client_id/client_secret/refresh_token reutilizados de `secret.json`/`gsheets_token.json` (en `D:\Otros_proyectos\nutrienti`, con guion bajo). Autentica como `contacto@nutrienti.co`, dueño de las hojas usadas por la app (incluida la de Razon Social/Nombre Comercial y la de productos recreada). El maestro de clientes (NIT) tiene otro dueño (`csanchez@nutrienti.co`) pero las mismas credenciales ya tienen acceso (scope `drive` completo, no solo `drive.readonly`). Secrets ya configurados en Streamlit Cloud (Advanced settings → Secrets).

## ⚠️ Cuidado con las carpetas locales duplicadas
Existen DOS carpetas muy parecidas en la maquina del usuario:
- `D:\Otros proyectos\nutrienti` (con espacio) — **antigua/incorrecta**, solo tiene sobras ("Claude outputs", "tablas precios").
- `D:\Otros_proyectos\nutrienti` (con guion bajo) — **la correcta**, tiene `secret.json`, `gsheets_token.json`, y los repos `pedidos_repo`/`facturacion_repo`.

Si `device_list_dir` falla en la variante con espacio, es casi seguro que hay que usar la variante con guion bajo.

## Repo (pedidos_repo)
- `app.py` — fecha solicitud/despacho (despacho segun tabla fija por dia de la semana, v3, 2026-10-27), "Nombre de Punto", carrito de productos (con codigo de producto), revision/confirmacion (con razon social/NIT), envío a Sheet destino con Codigo Pedido + Fecha y Hora de Registro (hora Colombia, `BOGOTA_TZ`), tab de confirmacion de recepcion, matching mejorado (`resolve_cliente`), resolucion de NIT (`load_client_master`/`find_client_master_by_razon`/`resolve_nit`), matriz de precios en pausa, admin oculto. Soporta `gcp_oauth` (activo) y `gcp_service_account` (fallback). `PRODUCTS_SHEET_ID`, columnas Razon Social/NIT/Codigo Producto: desplegadas y confirmadas 2026-10-20. Tabla de dias de despacho (v3) + Fecha y Hora de Registro: aplicados local 2026-10-27, pendiente de subir.
- `requirements.txt` (incluye `google-api-python-client`, `openpyxl`, `tzdata`), `.gitignore`, `.streamlit/config.toml`, `.streamlit/secrets.toml` (real, no en git), `.streamlit/secrets.toml.example`, `README.md`, `precios_por_cliente.csv`, `precios_sin_resolver.csv`.
- El README del repo tiene el detalle tecnico completo (columnas, matching, deploy, incidente de productos, razon social/NIT, codigo de producto) pero **no se actualizo todavia con las features de fecha de despacho / hora de registro del 2026-10-26/27** — pendiente la proxima vez que se toque el repo (van 3 vueltas seguidas sin actualizarlo, vale la pena priorizarlo la proxima vez).

## Pendientes explícitamente diferidos por el usuario
- Cruzar cliente → ruta de despacho (para colorear en la hoja Remisión).
- Reactivar precios diferenciados por cliente (codigo dormido, ver arriba).
- Migrar `BASE DE DATOS PRODUCTOS ACTIVOS.xlsx` a Google Sheets nativo para que la app lea precios en vivo en vez de la copia estática (solo relevante si se reactivan precios).
- Reportes de tiempo de entrega (Fecha Solicitud/Despacho vs Fecha Recepcion) — los datos ya quedan en la hoja, falta el reporte/dashboard en si.
- Investigar la anomalia de 3 filas historicas con columna extra (baja prioridad).

## Siguientes pasos sugeridos (no confirmados aún por el usuario)
- **Subir el `app.py` + `requirements.txt` actualizados a GitHub** con la tabla fija de dias de despacho (v3) y "Fecha y Hora de Registro" (2026-10-27) — no bloqueante, pero sin esto el default en produccion sigue siendo el de la v1 original ("+2 dias", que ni siquiera distinguia dias validos) y no se registra la hora.
- Al tocar el repo de nuevo, actualizar `README.md` con la seccion de fecha de despacho (tabla completa) / hora de registro — quedo pendiente 3 vueltas seguidas.
- Confirmar que el Codigo Producto que aparece en la hoja coincide con el codigo real de World Office para un par de productos (los codigos se extrajeron por posicion/orden de fila, no por un cruce campo a campo) — sigue sin confirmarse explicitamente por el usuario.
- Una vez desplegado, confirmar con el cliente final que la fecha de despacho sugerida (tabla v3) y la hora de registro se ven como esperaban — especialmente los casos viernes/sabado/domingo → martes siguiente, que son los que mas se alejan de la fecha de solicitud.
