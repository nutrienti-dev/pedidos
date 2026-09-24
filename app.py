"""
Nutrienti - Sistema de Pedidos Web
Permite a los clientes (restaurantes) hacer pedidos que se guardan
automaticamente en una Google Sheet, y luego confirmar la recepcion de esos
pedidos para poder medir el tiempo de entrega.
"""
import streamlit as st
import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as SACredentials
from google.auth.transport.requests import Request
from datetime import date, datetime
import difflib
import re
import unicodedata
import uuid
import csv as csv_module
import os
from collections import Counter

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Nutrienti | Ordenes de Cosecha",
    page_icon="🥬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

CLIENTS_SHEET_ID = "1LGjtIWTwrWSUw3LKC8jTmj-NMlwhygbAelD_C3hL-tQ"
CLIENTS_TAB_CANDIDATES = ["Datos", "DATOS", "datos"]

PRODUCTS_SHEET_ID = "1b2_qDS9GMZGCJnAFBM690DBj3b_4qp5tqLDuQo7U5Bw"
PRODUCTS_TAB_CANDIDATES = ["Hoja 1", "Sheet1", "Productos"]

DEST_SHEET_ID = "1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY"

# "RAZONES SOCIALES - NOMBRES COMERCIALES": fuente de verdad para resolver
# el nombre del punto (nombre comercial) cuando no se parece en nada a la
# razon social / nombre de cadena (ej. "Astoria" es un punto de "ALTAS
# VISTAS SAS"). El matching de este archivo (match_nombre_comercial) viene
# portado de facturacion_repo/lib/matching.py, donde ya se probo con datos
# reales -- ver README para mas contexto.
RAZONES_SOCIALES_SHEET_ID = "1_IbW0IhpSxiCVL9Xn97XsIe5wE4AWnWMjG8szdoWSNI"
UMBRAL_NOMBRE_COMERCIAL = 0.72

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# --------------------------------------------------------------------------
# Estilos - branding de negocio de vegetales / restaurantes
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .nutrienti-header {
        background: linear-gradient(135deg, #2E7D32 0%, #66BB6A 100%);
        padding: 1.6rem 1.4rem;
        border-radius: 14px;
        color: white;
        margin-bottom: 1.4rem;
    }
    .nutrienti-header h1 {
        margin: 0;
        font-size: 1.6rem;
    }
    div[data-testid="stForm"] {
        border: 1px solid #E0E0E0;
        border-radius: 12px;
        padding: 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="nutrienti-header">
        <h1>🥬 Nutrienti - Ordenes de Cosecha</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Conexion a Google Sheets
#
# Soporta dos formas de autenticacion (se usa la primera que encuentre en
# st.secrets):
#   1. gcp_oauth: credenciales OAuth de usuario (client_id/client_secret +
#      refresh_token). Util cuando la organizacion bloquea la creacion de
#      llaves de cuentas de servicio (politica iam.disableServiceAccountKeyCreation).
#      Autentica como el usuario que autorizo el refresh_token, asi que ese
#      usuario debe ser dueno (o tener acceso de editor) de las 3 hojas.
#   2. gcp_service_account: cuenta de servicio clasica (requiere compartir
#      cada hoja con el correo de la cuenta de servicio).
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    if "gcp_oauth" in st.secrets:
        o = st.secrets["gcp_oauth"]
        creds = UserCredentials(
            token=None,
            refresh_token=o["refresh_token"],
            token_uri=o.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=o["client_id"],
            client_secret=o["client_secret"],
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return gspread.authorize(creds)

    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = SACredentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)

    return None


def _find_worksheet(sh, candidates):
    titles = {ws.title.strip().lower(): ws for ws in sh.worksheets()}
    for c in candidates:
        if c.strip().lower() in titles:
            return titles[c.strip().lower()]
    return sh.sheet1


def best_client_match(typed, choices):
    """Sugiere el cliente conocido mas parecido al texto que el usuario
    escribio, comparando directo contra la lista de clientes (difflib,
    libreria estandar de Python). Es el metodo de respaldo cuando el mapa
    de nombres comerciales (resolve_cliente, mas abajo) no encuentra nada
    confiable. Nunca se muestra la lista completa de clientes al usuario;
    solo se usa para sugerir, en la hoja de destino, cual cliente
    registrado probablemente quiso decir.
    """
    typed_norm = " ".join((typed or "").strip().split())
    if not typed_norm or not choices:
        return "", 0.0
    matches = difflib.get_close_matches(typed_norm, choices, n=1, cutoff=0.0)
    if not matches:
        return "", 0.0
    best = matches[0]
    score = difflib.SequenceMatcher(None, typed_norm.lower(), best.lower()).ratio()
    return best, round(score * 100, 1)


# --------------------------------------------------------------------------
# Resolucion de "nombre del punto" contra el mapa Razon Social / Nombre
# Comercial (fuente de verdad, ver nota en RAZONES_SOCIALES_SHEET_ID mas
# arriba). Portado de facturacion_repo/lib/matching.py y lib/data.py
# (match_nombre_comercial / load_nombre_comercial_map), donde ya se probo
# con datos reales -- evita el bug documentado ahi: nombres de punto que no
# se parecen en nada a la cadena/razon social (ej. "Astoria"/"Bombay"/"Sexy
# Seoul" -> "ALTAS VISTAS SAS"; "Osaki"/"Sorella" -> "TAKAMI SA") terminaban
# sugiriendo un cliente equivocado con el matching plano anterior.
# --------------------------------------------------------------------------
def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s):
    s = strip_accents(str(s or "")).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similarity(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


@st.cache_data(ttl=300, show_spinner=False)
def load_nombre_comercial_map():
    """Carga "RAZONES SOCIALES - NOMBRES COMERCIALES". Devuelve lista de
    dicts {razon_social, nombre_comercial}."""
    gc = get_gspread_client()
    ws = gc.open_by_key(RAZONES_SOCIALES_SHEET_ID).sheet1
    records = ws.get_all_records()
    rows = []
    for r in records:
        # Las llaves de get_all_records() vienen tal cual el encabezado de
        # la hoja (espacios inconsistentes) -- se buscan de forma robusta.
        razon = ""
        nombre_comercial = ""
        for k, v in r.items():
            key_norm = str(k or "").strip().lower()
            if key_norm == "razon social":
                razon = str(v or "").strip()
            elif key_norm == "nombre comercial":
                nombre_comercial = str(v or "").strip()
        if not nombre_comercial:
            continue
        rows.append({"razon_social": razon or nombre_comercial, "nombre_comercial": nombre_comercial})
    return rows


def match_nombre_comercial(candidatos, nc_rows):
    """candidatos: string o lista de strings (ej. texto ingresado y una
    sugerencia previa) -- se prueban todos. nc_rows: lista de dicts
    razon_social/nombre_comercial (ver load_nombre_comercial_map).
    Devuelve (razon_social_o_None, nombre_comercial_o_None, score_0_a_100).
    """
    if not nc_rows:
        return None, None, 0.0
    if isinstance(candidatos, str):
        candidatos = [candidatos]
    candidatos_norm = [normalize(c) for c in candidatos]
    candidatos_norm = [c for c in candidatos_norm if c]
    if not candidatos_norm:
        return None, None, 0.0

    best_row = None
    best_score = 0.0
    for row in nc_rows:
        nc_norm = normalize(row.get("nombre_comercial", ""))
        if not nc_norm:
            continue
        for text_norm in candidatos_norm:
            if text_norm == nc_norm:
                score = 1.0
            elif text_norm.startswith(nc_norm) or nc_norm.startswith(text_norm):
                shorter = min(len(text_norm), len(nc_norm))
                longer = max(len(text_norm), len(nc_norm))
                score = 0.85 + 0.15 * (shorter / longer)
            else:
                score = _similarity(text_norm, nc_norm)
            if score > best_score:
                best_score = score
                best_row = row

    if best_row is not None and best_score >= UMBRAL_NOMBRE_COMERCIAL:
        razon = (best_row.get("razon_social") or "").strip() or None
        nc = (best_row.get("nombre_comercial") or "").strip() or None
        return razon, nc, round(best_score * 100, 1)
    return None, None, round(best_score * 100, 1)


def resolve_cliente(cliente_texto, clients, nc_rows):
    """Resuelve el nombre del punto a su version canonica, en dos pasos:
    1) mapa Razon Social/Nombre Comercial (fuente de verdad) -- resuelve
       puntos que no se parecen en nada a su razon social.
    2) si el mapa no tiene un match confiable (sheet no cargo, punto nuevo
       que aun no esta en el mapa, etc.), respaldo: comparar directo contra
       la lista de clientes conocidos (best_client_match).
    Devuelve (cliente_sugerido, similitud_0_a_100, fuente) donde fuente es
    "mapa" o "lista" (para trazabilidad si hace falta depurar).
    """
    _, nombre_comercial, score_mapa = match_nombre_comercial(cliente_texto, nc_rows)
    if nombre_comercial:
        return nombre_comercial, score_mapa, "mapa"
    sugerido, similitud = best_client_match(cliente_texto, clients)
    return sugerido, similitud, "lista"


@st.cache_data(ttl=300, show_spinner="Cargando lista de clientes...")
def load_clients():
    gc = get_gspread_client()
    sh = gc.open_by_key(CLIENTS_SHEET_ID)
    ws = _find_worksheet(sh, CLIENTS_TAB_CANDIDATES)
    col = ws.col_values(1)
    names = []
    seen = set()
    for v in col[1:]:
        v = " ".join(str(v).split())
        if v and v.lower() not in seen:
            seen.add(v.lower())
            names.append(v)
    names.sort(key=lambda s: s.lower())
    return names


@st.cache_data(ttl=300, show_spinner="Cargando lista de productos...")
def load_products():
    # Lee de una hoja de Google Sheets nativa (Producto, Unidad, Precio) que
    # se genero a partir de "BASE DE DATOS PRODUCTOS ACTIVOS.xlsx" -- ese
    # archivo original es un Excel subido a Drive, y la API de Sheets no
    # puede leer archivos de Office directamente, por eso se uso esta copia
    # simplificada en formato nativo de Google Sheets.
    gc = get_gspread_client()
    sh = gc.open_by_key(PRODUCTS_SHEET_ID)
    ws = _find_worksheet(sh, PRODUCTS_TAB_CANDIDATES)
    values = ws.get_all_values()
    products = []
    for row in values[1:]:
        if len(row) < 3:
            continue
        desc = row[0].strip()
        unidad = row[1].strip()
        precio_raw = row[2].strip()
        if not desc:
            continue
        try:
            precio = float(precio_raw.replace(",", ".")) if precio_raw else 0
        except ValueError:
            precio = 0
        if precio > 0:
            products.append({"producto": desc, "unidad": unidad or "und", "precio": precio})
    products.sort(key=lambda p: p["producto"].lower())
    return products


DEST_HEADERS = [
    "Fecha Solicitud",
    "Fecha Despacho Deseada",
    "Cliente (texto ingresado)",
    "Cliente (sugerencia automatica)",
    "Similitud (%)",
    "Producto",
    "Unidad",
    "Cantidad",
    "Codigo Pedido",
    "Estado",
    "Fecha Recepcion",
    "Observaciones",
]

ESTADO_PENDIENTE = "Pendiente"
ESTADO_RECIBIDO = "Recibido"

# Suficientemente ancho para cubrir encabezados viejos con mas o menos
# columnas que la version actual, y dejar las que sobran en blanco.
_DEST_HEADER_CLEAR_RANGE = "A1:Z1"


@st.cache_resource(show_spinner=False)
def ensure_dest_headers():
    """Se asegura de que la hoja de destino tenga el encabezado esperado.
    No toca ninguna fila de datos ya existente -- solo escribe la fila 1 si
    hace falta, y limpia columnas de encabezado viejas que ya no se usan.
    @st.cache_resource hace que esto corra una sola vez por proceso.
    """
    gc = get_gspread_client()
    sh = gc.open_by_key(DEST_SHEET_ID)
    ws = sh.sheet1
    current = ws.row_values(1)
    if current != DEST_HEADERS:
        ws.batch_clear([_DEST_HEADER_CLEAR_RANGE])
        ws.update("A1", [DEST_HEADERS])
    return True


def append_order_to_sheet(codigo_pedido, fecha_solicitud, fecha_despacho, cliente, cliente_sugerido, similitud, items):
    gc = get_gspread_client()
    sh = gc.open_by_key(DEST_SHEET_ID)
    ws = sh.sheet1
    rows = []
    for it in items:
        rows.append(
            [
                fecha_solicitud.strftime("%Y-%m-%d"),
                fecha_despacho.strftime("%Y-%m-%d"),
                cliente,
                cliente_sugerido,
                similitud,
                it["producto"],
                it["unidad"],
                it["cantidad"],
                codigo_pedido,
                ESTADO_PENDIENTE,
                "",
                "",
            ]
        )
    # append_rows uses the Sheets API's append endpoint, which is safe for
    # concurrent submissions from multiple clients (no manual row-index math).
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# --------------------------------------------------------------------------
# Confirmacion de recepcion ("Mis Pedidos")
#
# Cada pedido queda repartido en varias filas (una por producto) que
# comparten el mismo "Codigo Pedido". Para mostrar los pedidos pendientes
# de un punto, se agrupan las filas por codigo; al confirmar recepcion se
# actualizan TODAS las filas de ese codigo de una vez (Estado, Fecha
# Recepcion, Observaciones).
# --------------------------------------------------------------------------
@st.cache_data(ttl=15, show_spinner=False)
def load_pedidos_rows():
    """Lee todas las filas de la hoja de destino. TTL corto (15s, no 300
    como clientes/productos) porque el estado cambia con cada confirmacion
    y varias personas pueden estar consultando a la vez."""
    gc = get_gspread_client()
    sh = gc.open_by_key(DEST_SHEET_ID)
    ws = sh.sheet1
    return ws.get_all_records()


def pedidos_pendientes_para(cliente_sugerido):
    """Devuelve un dict {codigo_pedido: {fecha_solicitud, fecha_despacho,
    items: [...]}} con los pedidos en Estado=Pendiente de ese cliente
    (comparando contra la columna "Cliente (sugerencia automatica)", que es
    la version canonica guardada en el pedido, no el texto libre)."""
    objetivo = (cliente_sugerido or "").strip().lower()
    if not objetivo:
        return {}
    pedidos = {}
    for r in load_pedidos_rows():
        if str(r.get("Cliente (sugerencia automatica)", "")).strip().lower() != objetivo:
            continue
        if str(r.get("Estado", "")).strip().lower() != ESTADO_PENDIENTE.lower():
            continue
        codigo = str(r.get("Codigo Pedido", "")).strip()
        if not codigo:
            continue
        pedido = pedidos.setdefault(
            codigo,
            {
                "fecha_solicitud": r.get("Fecha Solicitud", ""),
                "fecha_despacho": r.get("Fecha Despacho Deseada", ""),
                "items": [],
            },
        )
        pedido["items"].append(
            {
                "producto": r.get("Producto", ""),
                "unidad": r.get("Unidad", ""),
                "cantidad": r.get("Cantidad", ""),
            }
        )
    return pedidos


def marcar_pedido_recibido(codigo_pedido, observaciones):
    """Actualiza Estado/Fecha Recepcion/Observaciones en todas las filas
    que compartan codigo_pedido. Devuelve cuantas filas se actualizaron."""
    gc = get_gspread_client()
    sh = gc.open_by_key(DEST_SHEET_ID)
    ws = sh.sheet1
    headers = ws.row_values(1)
    col_codigo = headers.index("Codigo Pedido") + 1
    col_estado = headers.index("Estado") + 1
    col_fecha_recepcion = headers.index("Fecha Recepcion") + 1
    col_obs = headers.index("Observaciones") + 1

    cells = ws.findall(codigo_pedido, in_column=col_codigo)
    if not cells:
        return 0

    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M")
    updates = []
    for cell in cells:
        updates.append({"range": rowcol_to_a1(cell.row, col_estado), "values": [[ESTADO_RECIBIDO]]})
        updates.append(
            {"range": rowcol_to_a1(cell.row, col_fecha_recepcion), "values": [[fecha_hora]]}
        )
        updates.append({"range": rowcol_to_a1(cell.row, col_obs), "values": [[observaciones or ""]]})
    ws.batch_update(updates, value_input_option="USER_ENTERED")
    load_pedidos_rows.clear()
    return len(cells)


# --------------------------------------------------------------------------
# Matriz de precios por cliente (admin, en pausa)
#
# "precios_por_cliente.csv" contiene precios REALES conocidos por cliente,
# extraidos de las listas de precios de "BASE DE DATOS PRODUCTOS ACTIVOS.xlsx"
# (columnas Nombre/Valor Lista Precios 1-6), ya cruzados contra la lista
# oficial de clientes. "precios_sin_resolver.csv" son precios de esa misma
# fuente que NO se pudieron asignar con confianza a un cliente exacto (nombre
# ambiguo o cliente no encontrado) -- quedan pendientes de revision manual.
#
# build_price_matrix() crea/reconstruye la pestaña "matriz precios" en la
# hoja de productos: una fila por cliente, una columna por producto. Cada
# celda usa el precio real del cliente si se conoce (resaltada en verde); si
# no, usa el precio mas comun (moda) entre los demas clientes para ese
# producto. NOTA: esta funcionalidad de precios esta en pausa (ver README) y
# no esta conectada al formulario de pedido -- se deja el codigo listo por
# si se reactiva mas adelante.
# --------------------------------------------------------------------------
MATRIX_TAB_NAME = "matriz precios"
CLIENT_PRICES_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precios_por_cliente.csv")
UNRESOLVED_PRICES_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precios_sin_resolver.csv")

REAL_PRICE_COLOR = {"red": 0.80, "green": 0.94, "blue": 0.80}  # verde claro
HEADER_COLOR = {"red": 0.88, "green": 0.88, "blue": 0.88}


def _read_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv_module.DictReader(f))


@st.cache_data(ttl=60, show_spinner=False)
def load_client_prices():
    """Devuelve lista de (cliente, producto, precio) con precios reales
    conocidos por cliente."""
    out = []
    for row in _read_csv_rows(CLIENT_PRICES_CSV):
        try:
            precio = float(row["Precio"])
        except (KeyError, ValueError, TypeError):
            continue
        cliente = (row.get("Cliente") or "").strip()
        producto = (row.get("Producto") or "").strip()
        if cliente and producto:
            out.append((cliente, producto, precio))
    return out


@st.cache_data(ttl=60, show_spinner=False)
def load_unresolved_prices():
    """Precios de la fuente original que no se pudieron asignar a un cliente
    exacto -- para revision manual, no se usan en la matriz."""
    return _read_csv_rows(UNRESOLVED_PRICES_CSV)


def get_pricing_data():
    """Devuelve (known, fallback):
    - known: dict {(cliente, producto): precio} con los precios reales
      conocidos por cliente (de precios_por_cliente.csv).
    - fallback: dict {producto: precio} con el precio a usar cuando no hay
      precio real conocido para un cliente -- el mas comun (moda) entre los
      demas clientes para ese producto, o el precio general de la hoja de
      productos si ningun cliente tiene precio conocido.
    Se recalcula (barato, son ~46 productos / ~280 precios conocidos) cada
    vez que se llama; no se cachea aca porque depende de `products`, que ya
    esta cacheado por separado con `load_products()`.
    """
    client_prices = load_client_prices()
    known = {}
    prices_by_product = {}
    for cliente, producto, precio in client_prices:
        known[(cliente, producto)] = precio
        prices_by_product.setdefault(producto, []).append(precio)

    flat_price = {p["producto"]: p["precio"] for p in products}

    fallback = {}
    for p in product_names:
        vals = prices_by_product.get(p)
        fallback[p] = Counter(vals).most_common(1)[0][0] if vals else flat_price.get(p, 0)

    return known, fallback


# Umbral de similitud (mismo criterio que best_client_match) a partir del
# cual se confia en el nombre escrito por el cliente para buscarle SU precio
# real. Por debajo de esto, se usa el precio de respaldo (moda) en vez de
# arriesgarse a cobrarle el precio negociado de otro cliente distinto.
CLIENT_PRICE_MATCH_THRESHOLD = 85.0


def price_for_client(cliente_texto, producto, clients):
    """Precio que le corresponde a `producto` para el cliente que escribio
    `cliente_texto`. Usa el precio real del cliente mas parecido si la
    similitud supera CLIENT_PRICE_MATCH_THRESHOLD; si no, usa el precio de
    respaldo (moda entre los demas clientes) para ese producto."""
    known, fallback = get_pricing_data()
    sugerido, similitud = best_client_match(cliente_texto, clients)
    if sugerido and similitud >= CLIENT_PRICE_MATCH_THRESHOLD:
        precio_real = known.get((sugerido, producto))
        if precio_real is not None:
            return precio_real
    return fallback.get(producto, 0)


def build_price_matrix():
    """Construye o reconstruye la pestaña 'matriz precios'. Devuelve un
    diccionario con estadisticas (clientes, productos, celdas reales,
    celdas de respaldo) para mostrar en pantalla."""
    gc = get_gspread_client()
    sh = gc.open_by_key(PRODUCTS_SHEET_ID)

    known, fallback = get_pricing_data()

    try:
        ws = sh.worksheet(MATRIX_TAB_NAME)
        sh.del_worksheet(ws)
    except gspread.exceptions.WorksheetNotFound:
        pass
    ws = sh.add_worksheet(title=MATRIX_TAB_NAME, rows=len(clients) + 1, cols=len(product_names) + 1)

    header = ["Cliente"] + product_names
    data_rows = []
    real_cells = []  # (fila, columna) 1-based, tal como aparecen en la hoja
    for r, cliente in enumerate(clients, start=2):
        row = [cliente]
        for c, producto in enumerate(product_names, start=2):
            precio_real = known.get((cliente, producto))
            if precio_real is not None:
                row.append(precio_real)
                real_cells.append((r, c))
            else:
                row.append(fallback[producto])
        data_rows.append(row)

    ws.update("A1", [header] + data_rows, value_input_option="USER_ENTERED")

    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1},
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"backgroundColor": HEADER_COLOR, "textFormat": {"bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
    ]
    for (r, c) in real_cells:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": r - 1,
                        "endRowIndex": r,
                        "startColumnIndex": c - 1,
                        "endColumnIndex": c,
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": REAL_PRICE_COLOR}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )

    CHUNK = 400
    for i in range(0, len(requests), CHUNK):
        sh.batch_update({"requests": requests[i : i + CHUNK]})

    total_cells = len(clients) * len(product_names)
    return {
        "clientes": len(clients),
        "productos": len(product_names),
        "celdas_reales": len(real_cells),
        "celdas_fallback": total_cells - len(real_cells),
    }


# --------------------------------------------------------------------------
# Estado de sesion
# --------------------------------------------------------------------------
if "cart" not in st.session_state:
    st.session_state.cart = []
if "step" not in st.session_state:
    st.session_state.step = "form"
if "last_codigo_pedido" not in st.session_state:
    st.session_state.last_codigo_pedido = None

gc = get_gspread_client()
if gc is None:
    st.error(
        "No se encontraron credenciales de Google en `st.secrets`. Copia "
        "`.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y completa "
        "la seccion `[gcp_oauth]` (o `[gcp_service_account]`) — ver README.md."
    )
    st.stop()

try:
    clients = load_clients()
    products = load_products()
    ensure_dest_headers()
except Exception as e:
    st.error(f"No se pudo conectar con Google Sheets: {e}")
    st.stop()

# El mapa de nombres comerciales es un "nice to have": si por lo que sea no
# se puede leer (permisos, hoja movida, etc.), la app sigue funcionando con
# el matching de respaldo en vez de detenerse.
try:
    nc_rows = load_nombre_comercial_map()
except Exception:
    nc_rows = []
    st.warning(
        "No se pudo leer el mapa de Razon Social/Nombre Comercial -- se usa "
        "el matching de respaldo (lista de clientes) mientras tanto.",
        icon="⚠️",
    )

if not clients:
    st.warning("No se encontraron clientes en la hoja de origen.")
if not products:
    st.warning("No se encontraron productos con precio en la hoja de origen.")

product_names = [p["producto"] for p in products]
product_by_name = {p["producto"]: p for p in products}


tab_pedido, tab_estado = st.tabs(["📦 Hacer Pedido", "✅ Confirmar Recepción"])

# ==========================================================================
# TAB 1: Hacer pedido
# ==========================================================================
with tab_pedido:
    # ----------------------------------------------------------------------
    # PASO 1: formulario de pedido
    # ----------------------------------------------------------------------
    if st.session_state.step == "form":
        col1, col2 = st.columns(2)
        with col1:
            fecha_solicitud = st.date_input("Fecha de la solicitud", value=date.today())
        with col2:
            fecha_despacho = st.date_input("Fecha de despacho deseada", value=date.today())

        cliente = st.text_input(
            "Nombre de Punto",
            placeholder="Escribe el nombre de tu punto...",
            help="Escribe el nombre tal como lo conoces. No mostramos la lista de otros puntos.",
        )

        st.divider()
        st.subheader("Agregar productos")

        with st.form("add_item_form", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                producto_sel = st.selectbox(
                    "Producto",
                    options=product_names,
                    index=None,
                    placeholder="Selecciona un producto...",
                )
            with c2:
                cantidad = st.number_input("Cantidad", min_value=0.0, value=1.0, step=0.5)

            add_clicked = st.form_submit_button("➕ Agregar al pedido", use_container_width=True)

            if add_clicked:
                if not producto_sel:
                    st.warning("Selecciona un producto antes de agregarlo.")
                elif cantidad <= 0:
                    st.warning("La cantidad debe ser mayor a 0.")
                else:
                    p = product_by_name[producto_sel]
                    st.session_state.cart.append(
                        {
                            "producto": p["producto"],
                            "unidad": p["unidad"],
                            "cantidad": cantidad,
                        }
                    )
                    st.rerun()

        # Carrito actual
        if st.session_state.cart:
            st.subheader("Tu pedido")
            for idx, it in enumerate(st.session_state.cart):
                cc1, cc2, cc3 = st.columns([3, 1.5, 0.6])
                cc1.write(it["producto"])
                cc2.write(f"{it['cantidad']:g} {it['unidad']}")
                if cc3.button("🗑️", key=f"del_{idx}"):
                    st.session_state.cart.pop(idx)
                    st.rerun()

            st.write("")
            if st.button("Revisar y confirmar pedido ➜", type="primary", use_container_width=True):
                if not cliente or not cliente.strip():
                    st.warning("Escribe el nombre de tu punto antes de continuar.")
                elif not st.session_state.cart:
                    st.warning("Agrega al menos un producto antes de continuar.")
                else:
                    sugerido, similitud, _fuente = resolve_cliente(cliente, clients, nc_rows)
                    st.session_state.review_data = {
                        "cliente": cliente.strip(),
                        "cliente_sugerido": sugerido,
                        "similitud": similitud,
                        "fecha_solicitud": fecha_solicitud,
                        "fecha_despacho": fecha_despacho,
                    }
                    st.session_state.step = "review"
                    st.rerun()
        else:
            st.info("Aun no has agregado productos a tu pedido.")

    # ----------------------------------------------------------------------
    # PASO 2: revision y confirmacion
    # ----------------------------------------------------------------------
    elif st.session_state.step == "review":
        data = st.session_state.review_data
        st.subheader("Revisa tu pedido antes de enviarlo")

        r1, r2, r3 = st.columns(3)
        r1.metric("Punto", data["cliente"])
        r2.metric("Fecha solicitud", data["fecha_solicitud"].strftime("%Y-%m-%d"))
        r3.metric("Fecha despacho", data["fecha_despacho"].strftime("%Y-%m-%d"))

        st.write("")
        for it in st.session_state.cart:
            cc1, cc2 = st.columns([3, 1.5])
            cc1.write(f"**{it['producto']}**")
            cc2.write(f"{it['cantidad']:g} {it['unidad']}")

        st.write("")
        b1, b2 = st.columns(2)
        if b1.button("← Corregir pedido", use_container_width=True):
            st.session_state.step = "form"
            st.rerun()

        if b2.button("✅ Confirmar y enviar pedido", type="primary", use_container_width=True):
            codigo_pedido = f"{datetime.now():%y%m%d}-{uuid.uuid4().hex[:5].upper()}"
            try:
                append_order_to_sheet(
                    codigo_pedido=codigo_pedido,
                    fecha_solicitud=data["fecha_solicitud"],
                    fecha_despacho=data["fecha_despacho"],
                    cliente=data["cliente"],
                    cliente_sugerido=data["cliente_sugerido"],
                    similitud=data["similitud"],
                    items=st.session_state.cart,
                )
                load_pedidos_rows.clear()
                st.session_state.last_codigo_pedido = codigo_pedido
                st.session_state.step = "done"
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo enviar el pedido: {e}")

    # ----------------------------------------------------------------------
    # PASO 3: confirmacion final
    # ----------------------------------------------------------------------
    elif st.session_state.step == "done":
        st.success("🎉 ¡Tu pedido fue enviado con exito!")
        if st.session_state.last_codigo_pedido:
            st.write(f"Codigo de tu pedido: **{st.session_state.last_codigo_pedido}**")
        st.write(
            "Nuestro equipo se pondra en contacto para confirmar la entrega. "
            "Cuando lo recibas, confirma la recepcion en la pestaña **Confirmar Recepción**."
        )

        if st.button("Hacer otro pedido"):
            st.session_state.cart = []
            st.session_state.step = "form"
            st.rerun()

# ==========================================================================
# TAB 2: Confirmar recepcion ("Mis Pedidos")
# ==========================================================================
with tab_estado:
    st.subheader("Consulta y confirma tus pedidos pendientes")
    busqueda = st.text_input(
        "Nombre de Punto",
        placeholder="Escribe el nombre de tu punto...",
        help="Escribe el nombre tal como lo conoces. No mostramos la lista de otros puntos.",
        key="busqueda_punto",
    )

    if busqueda and busqueda.strip():
        sugerido, similitud, _fuente = resolve_cliente(busqueda, clients, nc_rows)
        if not sugerido or similitud < 60:
            st.info("No encontramos un punto que coincida con ese nombre.")
        else:
            pedidos = pedidos_pendientes_para(sugerido)
            if not pedidos:
                st.success(f"**{sugerido}** no tiene pedidos pendientes por confirmar. 🎉")
            else:
                st.caption(f"Pedidos pendientes de **{sugerido}**:")
                for codigo, pedido in pedidos.items():
                    with st.container(border=True):
                        st.markdown(f"**Pedido {codigo}**")
                        c1, c2 = st.columns(2)
                        c1.write(f"Fecha solicitud: {pedido['fecha_solicitud']}")
                        c2.write(f"Fecha despacho: {pedido['fecha_despacho']}")
                        for it in pedido["items"]:
                            st.write(f"- {it['producto']}: {it['cantidad']} {it['unidad']}")

                        obs_key = f"obs_{codigo}"
                        st.text_area(
                            "Observaciones",
                            key=obs_key,
                            placeholder="Ej: llego todo completo, o falto/vino mal 1kg de...",
                        )
                        if st.button("✅ Pedido Recibido", key=f"recibido_{codigo}", type="primary"):
                            n = marcar_pedido_recibido(codigo, st.session_state.get(obs_key, ""))
                            if n:
                                st.success(f"¡Gracias! Marcamos el pedido {codigo} como recibido.")
                                st.rerun()
                            else:
                                st.error("No se pudo actualizar el pedido, intenta de nuevo.")
    else:
        st.info("Escribe el nombre de tu punto para ver tus pedidos pendientes.")

# --------------------------------------------------------------------------
# Admin oculto: construir/actualizar la matriz de precios por cliente.
# Solo aparece si la URL de la app incluye ?admin=matriz -- un cliente
# normal nunca ve ni activa esto por accidente.
# --------------------------------------------------------------------------
try:
    _query_params = dict(st.query_params)
except Exception:
    _raw_qp = st.experimental_get_query_params()
    _query_params = {k: (v[0] if isinstance(v, list) else v) for k, v in _raw_qp.items()}

if _query_params.get("admin") == "matriz":
    st.divider()
    st.subheader("🔧 Admin: matriz de precios por cliente")
    st.caption(
        "Crea o actualiza la pestaña 'matriz precios' en la hoja de productos "
        "(una fila por cliente, una columna por producto). Las celdas en "
        "verde son precios reales conocidos para ese cliente -- esos mismos "
        "productos son, en general, los que ese cliente pide habitualmente. "
        "El resto de celdas usa el precio mas comun entre los demas clientes."
    )
    if st.button("Construir / actualizar matriz de precios"):
        with st.spinner("Construyendo matriz..."):
            try:
                stats = build_price_matrix()
                st.success(
                    f"Listo: {stats['clientes']} clientes x {stats['productos']} productos. "
                    f"{stats['celdas_reales']} celdas con precio real (resaltadas en verde), "
                    f"{stats['celdas_fallback']} con precio de respaldo."
                )
            except Exception as e:
                st.error(f"No se pudo construir la matriz: {e}")

    _unresolved = load_unresolved_prices()
    if _unresolved:
        with st.expander(
            f"⚠️ {len(_unresolved)} precios de la fuente original que no se pudieron "
            "asignar a un cliente exacto (no estan en la matriz, revisar manualmente)"
        ):
            st.dataframe(_unresolved, use_container_width=True)
