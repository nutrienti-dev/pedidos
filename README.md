# Nutrienti — Pedidos Web

App en Streamlit para que los clientes (restaurantes) de Nutrienti hagan sus
pedidos en linea. Cada pedido queda registrado automaticamente en una Google
Sheet.

## Como funciona

- **Clientes**: se cargan en vivo desde la hoja "Datos" (columna A) de
  [este Google Sheet](https://docs.google.com/spreadsheets/d/1LGjtIWTwrWSUw3LKC8jTmj-NMlwhygbAelD_C3hL-tQ).
- **Productos y precios**: se cargan en vivo desde la hoja
  "Productos y servicios" de
  [este Google Sheet](https://docs.google.com/spreadsheets/d/1At3DzHvgQXnPueF7QK_KDvTeYyAN0oiE)
  (columna C = producto, columna AA = precio de prueba).
- **Pedidos**: al confirmar, cada linea del pedido se agrega (append) a la
  hoja ["Pedidos Web - Registro de Solicitudes"](https://docs.google.com/spreadsheets/d/1WKkqvaM27VDxCviwNPWKEI5xKblDH-vgQEi9_5oiQNY),
  ubicada en la carpeta "Integracion AI" del Drive de Nutrienti. Se usa
  `append_rows` (no escritura por indice de fila), lo que es seguro para
  varios clientes enviando pedidos al mismo tiempo.

> **Nota sobre precios (version de prueba):** el precio real de cada
> producto varia por cliente (ver hoja "precios por cliente"). Para esta
> primera version se simplifico usando **un unico precio por producto**
> (el primer precio de lista definido en "Productos y servicios"). Cuando
> quieran activar precios diferenciados por cliente, hay que ajustar
> `load_products()` en `app.py` para cruzar cliente + producto contra la
> hoja "precios por cliente".

## Configuracion inicial (una sola vez)

### 1. Crear una cuenta de servicio de Google

1. Entra a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto nuevo (o usa uno existente).
3. Habilita las APIs **Google Sheets API** y **Google Drive API**
   (menu "APIs & Services" → "Enable APIs and Services").
4. Ve a "IAM & Admin" → "Service Accounts" → "Create Service Account".
5. Una vez creada, entra a la cuenta de servicio → pestaña "Keys" →
   "Add Key" → "Create new key" → tipo **JSON**. Se descarga un archivo
   `.json`: **guardalo en un lugar seguro, nunca lo subas a GitHub.**

### 2. Compartir las 3 hojas con la cuenta de servicio

El archivo JSON descargado tiene un campo `client_email`
(algo como `nutrienti-pedidos@tu-proyecto.iam.gserviceaccount.com`).
Comparte estas 3 hojas con ese correo:

| Hoja | Permiso necesario |
|---|---|
| Clientes (Datos) | Lector |
| Productos y servicios | Lector |
| Pedidos Web - Registro de Solicitudes | **Editor** (la app escribe aqui) |

### 3. Configurar las credenciales localmente

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Abre `.streamlit/secrets.toml` y pega los valores del archivo JSON
descargado en el paso 1 (cada campo del JSON tiene su equivalente en el
TOML). Este archivo **ya esta en `.gitignore`**, no se sube a git.

### 4. Instalar dependencias y correr localmente

```bash
python -m venv .venv
.venv\Scripts\activate        # en Windows
pip install -r requirements.txt
streamlit run app.py
```

Se abrira en `http://localhost:8501`.

## Desplegar en Streamlit Community Cloud (gratis)

1. Sube este repositorio a GitHub (sin el archivo `secrets.toml`, que
   queda excluido automaticamente por `.gitignore`).
2. Entra a [share.streamlit.io](https://share.streamlit.io/) y conecta tu
   cuenta de GitHub.
3. Elige el repositorio y el archivo `app.py`.
4. En "Advanced settings" → "Secrets", pega el **contenido completo** de tu
   `.streamlit/secrets.toml` local (incluyendo `[gcp_service_account]`).
5. Deploy. Streamlit te da una URL publica que puedes compartir con tus
   clientes (por ejemplo por WhatsApp).

> Streamlit Community Cloud es gratis pero "duerme" la app tras un rato sin
> uso (tarda unos segundos en despertar con la primera visita). Si esto es
> un problema, se puede mover a un hosting pequeño de pago (Render,
> Railway, etc.) sin cambiar el codigo.

## Estructura del proyecto

```
pedidos_repo/
├── app.py                          # App principal de Streamlit
├── requirements.txt                # Dependencias Python
├── .gitignore                      # Excluye secrets y archivos temporales
├── .streamlit/
│   ├── config.toml                 # Tema visual (colores Nutrienti)
│   └── secrets.toml.example        # Plantilla de credenciales (sin datos reales)
└── README.md
```

## Pendientes / mejoras futuras

- Cruzar cliente → ruta de despacho (para la hoja de Remision con colores
  por ruta) — pendiente por definir con el equipo.
- Precios diferenciados por cliente usando la hoja "precios por cliente".
- Validaciones adicionales (cantidades minimas, dias de despacho
  disponibles, etc.) si el negocio lo requiere.
