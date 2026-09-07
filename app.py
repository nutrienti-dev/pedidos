"""
Nutrienti - Sistema de Pedidos Web
Permite a los clientes (restaurantes) hacer pedidos que se guardan
automaticamente en una Google Sheet.
"""
import streamlit as st
import gspread
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as SACredentials
from google.auth.transport.requests import Request
from datetime import date, datetime
import uuid

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Nutrienti | Pedidos",
    page_icon="🥬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

CLIENTS_SHEET_ID = "1LGjtIWTwrWSUw3LKC8jTmj-NMlwhygbAelD_C3hL-tQ"
CLIENTS_TAB_CANDIDATES = ["Datos", "DATOS", "datos"]

PRODUCTS_SHEET_ID = "1b2_qDS9GMZGCJnAFBM690DBj3b_4qp5tqLDuQo7U5Bw"
PRODUCTS_TAB_CANDIDATES = ["Hoja 1", "Sheet1", "Productos"]

DEST_SHEET_ID = "1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CURRENCY = "$"


def fmt_money(v):
    try:
        return f"{CURRENCY}{v:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return f"{CURRENCY}0"


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
    .nutrienti-header p {
        margin: 0.2rem 0 0 0;
        opacity: 0.92;
        font-size: 0.95rem;
    }
    .cart-total {
        background: #F1F8E9;
        border: 1px solid #C5E1A5;
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
        font-size: 1.15rem;
        font-weight: 600;
        color: #1B5E20;
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
        <h1>🥬 Nutrienti — Pedidos</h1>
        <p>Frutas y verduras frescas para tu restaurante. Arma tu pedido a continuacion.</p>
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


def append_order_to_sheet(order_id, fecha_solicitud, fecha_despacho, cliente, items, total_pedido):
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
                it["producto"],
                it["unidad"],
                it["cantidad"],
                it["precio"],
                it["total"],
                order_id,
                total_pedido,
            ]
        )
    # append_rows uses the Sheets API's append endpoint, which is safe for
    # concurrent submissions from multiple clients (no manual row-index math).
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# --------------------------------------------------------------------------
# Estado de sesion
# --------------------------------------------------------------------------
if "cart" not in st.session_state:
    st.session_state.cart = []
if "step" not in st.session_state:
    st.session_state.step = "form"
if "last_order_id" not in st.session_state:
    st.session_state.last_order_id = None

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
except Exception as e:
    st.error(f"No se pudo conectar con Google Sheets: {e}")
    st.stop()

if not clients:
    st.warning("No se encontraron clientes en la hoja de origen.")
if not products:
    st.warning("No se encontraron productos con precio en la hoja de origen.")

product_names = [p["producto"] for p in products]
product_by_name = {p["producto"]: p for p in products}


def cart_total():
    return sum(it["total"] for it in st.session_state.cart)


# --------------------------------------------------------------------------
# PASO 1: formulario de pedido
# --------------------------------------------------------------------------
if st.session_state.step == "form":
    col1, col2 = st.columns(2)
    with col1:
        fecha_solicitud = st.date_input("Fecha de la solicitud", value=date.today())
    with col2:
        fecha_despacho = st.date_input("Fecha de despacho deseada", value=date.today())

    cliente = st.selectbox(
        "Cliente",
        options=clients,
        index=None,
        placeholder="Selecciona tu restaurante...",
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
                        "precio": p["precio"],
                        "cantidad": cantidad,
                        "total": round(p["precio"] * cantidad),
                    }
                )
                st.rerun()

    # Carrito actual
    if st.session_state.cart:
        st.subheader("Tu pedido")
        for idx, it in enumerate(st.session_state.cart):
            cc1, cc2, cc3, cc4, cc5 = st.columns([3, 1.3, 1.3, 1.5, 0.6])
            cc1.write(it["producto"])
            cc2.write(f"{it['cantidad']:g} {it['unidad']}")
            cc3.write(fmt_money(it["precio"]))
            cc4.write(fmt_money(it["total"]))
            if cc5.button("🗑️", key=f"del_{idx}"):
                st.session_state.cart.pop(idx)
                st.rerun()

        st.markdown(
            f'<div class="cart-total">Total del pedido: {fmt_money(cart_total())}</div>',
            unsafe_allow_html=True,
        )

        st.write("")
        if st.button("Revisar y confirmar pedido ➜", type="primary", use_container_width=True):
            if not cliente:
                st.warning("Selecciona el cliente antes de continuar.")
            elif not st.session_state.cart:
                st.warning("Agrega al menos un producto antes de continuar.")
            else:
                st.session_state.review_data = {
                    "cliente": cliente,
                    "fecha_solicitud": fecha_solicitud,
                    "fecha_despacho": fecha_despacho,
                }
                st.session_state.step = "review"
                st.rerun()
    else:
        st.info("Aun no has agregado productos a tu pedido.")

# --------------------------------------------------------------------------
# PASO 2: revision y confirmacion
# --------------------------------------------------------------------------
elif st.session_state.step == "review":
    data = st.session_state.review_data
    st.subheader("Revisa tu pedido antes de enviarlo")

    r1, r2, r3 = st.columns(3)
    r1.metric("Cliente", data["cliente"])
    r2.metric("Fecha solicitud", data["fecha_solicitud"].strftime("%Y-%m-%d"))
    r3.metric("Fecha despacho", data["fecha_despacho"].strftime("%Y-%m-%d"))

    st.write("")
    for it in st.session_state.cart:
        cc1, cc2, cc3, cc4 = st.columns([3, 1.3, 1.3, 1.5])
        cc1.write(f"**{it['producto']}**")
        cc2.write(f"{it['cantidad']:g} {it['unidad']}")
        cc3.write(fmt_money(it["precio"]))
        cc4.write(fmt_money(it["total"]))

    st.markdown(
        f'<div class="cart-total">Total del pedido: {fmt_money(cart_total())}</div>',
        unsafe_allow_html=True,
    )

    st.write("")
    b1, b2 = st.columns(2)
    if b1.button("← Corregir pedido", use_container_width=True):
        st.session_state.step = "form"
        st.rerun()

    if b2.button("✅ Confirmar y enviar pedido", type="primary", use_container_width=True):
        order_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        try:
            append_order_to_sheet(
                order_id=order_id,
                fecha_solicitud=data["fecha_solicitud"],
                fecha_despacho=data["fecha_despacho"],
                cliente=data["cliente"],
                items=st.session_state.cart,
                total_pedido=cart_total(),
            )
            st.session_state.last_order_id = order_id
            st.session_state.step = "done"
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo enviar el pedido: {e}")

# --------------------------------------------------------------------------
# PASO 3: confirmacion final
# --------------------------------------------------------------------------
elif st.session_state.step == "done":
    st.success("🎉 ¡Tu pedido fue enviado con exito!")
    st.write(f"Numero de pedido: **{st.session_state.last_order_id}**")
    st.write(f"Total: **{fmt_money(cart_total())}**")
    st.write("Nuestro equipo se pondra en contacto para confirmar la entrega.")

    if st.button("Hacer otro pedido"):
        st.session_state.cart = []
        st.session_state.step = "form"
        st.session_state.last_order_id = None
        st.rerun()
