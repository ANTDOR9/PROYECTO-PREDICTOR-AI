"""Apariencia común del tablero y del asistente (modo claro y oscuro).

Regla de este archivo: ningún color de fondo o de letra se fija en blanco/negro. Todo lo que
se pinta encima del tema usa colores translúcidos o hereda el color del tema, así una tabla,
una tarjeta o un globo se leen igual con el tema claro que con el oscuro.

    import estilo
    estilo.aplicar()                      # una vez, al inicio de la página
    st.dataframe(df, **estilo.ANCHO)      # ancho completo, sin el aviso de use_container_width
"""
from __future__ import annotations

import html

import streamlit as st

ACENTO = "#1E8449"            # verde de la marca; es también el primaryColor de .streamlit/config.toml


def _version() -> tuple[int, int]:
    try:
        a, b = st.__version__.split(".")[:2]
        return int(a), int(b)
    except (ValueError, AttributeError):
        return (0, 0)


# Streamlit 1.50+ reemplazó use_container_width=True por width="stretch" y avisa en la consola.
ANCHO = {"width": "stretch"} if _version() >= (1, 50) else {"use_container_width": True}


# Colores de estado para las filas de las tablas: translúcidos, no pasteles opacos.
# Con un pastel opaco la letra del tema oscuro (casi blanca) quedaba ilegible sobre fondo claro.
FONDO_ESTADO = {
    "ok":     "rgba(30, 132, 73, 0.30)",
    "pronto": "rgba(235, 160, 20, 0.32)",
    "malo":   "rgba(222, 60, 60, 0.30)",
    "neutro": "rgba(128, 128, 128, 0.20)",
}


def fondo(clave: str) -> str:
    """Estilo CSS de una celda para Styler: `df.style.apply(lambda f: [estilo.fondo('ok')] * len(f), axis=1)`."""
    return f"background-color: {FONDO_ESTADO.get(clave, FONDO_ESTADO['neutro'])}"


CSS = """
<style>
/* ---------- espacio general ---------- */
.block-container { padding-top: 4rem; padding-bottom: 5rem; }
h1, h2, h3 { letter-spacing: -0.01em; }

/* ---------- barra de navegación superior ---------- */
[class*="st-key-sel_"] button { white-space: nowrap; border-radius: 10px; font-weight: 600; }
[class*="st-key-sel_"] button p { overflow: hidden; text-overflow: ellipsis; }

/* ---------- tarjetas (st.container(border=True)) ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
    border-radius: 14px;
}
.st-key-tarjeta, [class*="st-key-tarjeta_"] {
    border: 1px solid rgba(128, 128, 128, 0.28);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    background: rgba(128, 128, 128, 0.06);
}

/* ---------- métricas ---------- */
[data-testid="stMetricLabel"] { opacity: 0.75; font-size: 0.82rem; }
[data-testid="stMetricValue"] { font-size: 1.55rem; line-height: 1.25; }

/* ---------- chat ---------- */
[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.55rem;
    background: rgba(128, 128, 128, 0.07);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: rgba(30, 132, 73, 0.14);
}
.st-key-chat_col { max-width: 1000px; margin-left: auto; margin-right: auto; }
[data-testid="stBottom"] [data-testid="stChatInput"] { max-width: 1000px; margin-left: auto; margin-right: auto; }

/* ---------- globitos de sugerencias (st.pills) ---------- */
[data-testid="stPills"] button, [class*="st-key-chip"] button {
    border-radius: 999px;
    padding: 0.3rem 0.95rem;
    border: 1px solid rgba(128, 128, 128, 0.40);
    font-size: 0.92rem;
}
[data-testid="stPills"] button:hover, [class*="st-key-chip"] button:hover {
    border-color: #1E8449;
}

/* ---------- indicadores de estado ---------- */
.pill {
    display: inline-block; padding: 0.18rem 0.75rem; border-radius: 999px;
    font-size: 0.82rem; font-weight: 600; border: 1px solid transparent; white-space: nowrap;
}
.pill.ok   { background: rgba(30, 132, 73, 0.22);  border-color: rgba(30, 132, 73, 0.55); }
.pill.warn { background: rgba(235, 160, 20, 0.22); border-color: rgba(235, 160, 20, 0.60); }
.pill.off  { background: rgba(222, 60, 60, 0.20);  border-color: rgba(222, 60, 60, 0.55); }
.sub { opacity: 0.72; font-size: 0.9rem; }

/* ---------- barras de desplazamiento de las tablas ---------- */
[data-testid="stDataFrame"] div::-webkit-scrollbar { height: 14px !important; width: 14px !important; }
[data-testid="stDataFrame"] div::-webkit-scrollbar-thumb {
    background: rgba(128, 128, 128, 0.60) !important; border-radius: 8px !important;
}
[data-testid="stDataFrame"] div::-webkit-scrollbar-track { background: rgba(128, 128, 128, 0.15) !important; }
</style>
"""


def aplicar() -> None:
    """Inyecta el CSS común. Se puede llamar más de una vez: el navegador no lo duplica."""
    st.markdown(CSS, unsafe_allow_html=True)


def pastilla(texto: str, tipo: str = "ok") -> str:
    """HTML de un indicador redondeado. tipo: ok | warn | off."""
    return f'<span class="pill {tipo}">{html.escape(texto)}</span>'


def tarjeta(clave: str):
    """Contenedor con borde y fondo suave. Si esta versión de Streamlit no admite `key`, cae a uno con borde."""
    try:
        return st.container(key=f"tarjeta_{clave}")
    except TypeError:
        return st.container(border=True)


def columna_chat():
    """Columna centrada y angosta para el chat (en pantalla ancha un chat a todo el ancho cansa la vista)."""
    try:
        return st.container(key="chat_col")
    except TypeError:
        return st.container()
