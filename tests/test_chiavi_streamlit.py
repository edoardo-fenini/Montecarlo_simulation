"""Correzione 1.3: StreamlitDuplicateElementId. Ogni elemento Streamlit che riceve un ID (widget, grafici Plotly, tabelle,
pulsanti di download) deve avere una `key` esplicita, così due elementi con gli stessi parametri non vanno mai in conflitto."""

import ast
import pathlib

RADICE = pathlib.Path(__file__).resolve().parent.parent

# elementi che Streamlit registra con un ID calcolato dai parametri (se non c'è `key`)
CON_ID = {
    "button", "download_button", "plotly_chart", "dataframe", "data_editor", "selectbox", "multiselect", "slider", "select_slider",
    "toggle", "checkbox", "radio", "text_input", "text_area", "number_input", "file_uploader", "date_input", "color_picker",
    "pills", "segmented_control", "altair_chart", "vega_lite_chart", "pydeck_chart",
}  # fmt: skip


def chiamate_senza_key(percorso):
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(albero):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in CON_ID:
            if not any(k.arg == "key" for k in n.keywords):
                out.append(f"{percorso.name}:{n.lineno} {n.func.attr}")
    return out


def test_ogni_elemento_con_id_ha_una_key():
    mancanti = []
    for f in ("app.py", "grafici_app.py"):
        mancanti += chiamate_senza_key(RADICE / f)
    assert not mancanti, "Elementi Streamlit senza key (rischio StreamlitDuplicateElementId): " + ", ".join(mancanti)


def test_le_key_fisse_non_si_ripetono():
    albero = ast.parse((RADICE / "app.py").read_text(encoding="utf-8"))
    fisse = [
        k.value.value
        for n in ast.walk(albero)
        if isinstance(n, ast.Call)
        for k in n.keywords
        if k.arg == "key" and isinstance(k.value, ast.Constant)
    ]
    doppie = {k for k in fisse if fisse.count(k) > 1}
    assert not doppie, f"key ripetute: {doppie}"
