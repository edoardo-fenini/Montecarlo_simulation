"""v1.3 – release automatica: nome del tag (solo vX.Y.Z) e note dal CHANGELOG. Controlla anche la forma dei workflow."""

import pathlib
import subprocess
import sys

import pytest
import yaml

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "strumenti"))
import note_release as N  # noqa: E402
from solo_repository import richiede  # noqa: E402

CHANGELOG = """# Registro

## 1.3.0 (4 novembre 2026)

Novità A

### Sezione
- punto

## 1.2.0 (3 novembre)

Vecchio
"""


@pytest.mark.parametrize("t,atteso", [("v1.3.0", "v1.3.0"), ("1.3.0", "v1.3.0"), (" v10.0.12 ", "v10.0.12")])
def test_tag_validi(t, atteso):
    assert N.normalizza_tag(t) == atteso


@pytest.mark.parametrize("t", ["V_1.2.0", "V1.2.0", "v1.3", "v1.3.0-beta", "prova", "", "1.3", "vx.y.z"])
def test_tag_non_validi(t):
    with pytest.raises(ValueError, match="vX.Y.Z"):
        N.normalizza_tag(t)


def test_note_prese_dalla_sezione_giusta():
    n = N.note_dal_changelog(CHANGELOG, "v1.3.0")
    assert n.startswith("Novità A") and "- punto" in n and "Vecchio" not in n and "1.3.0 (" not in n
    assert N.note_dal_changelog(CHANGELOG, "1.2.0").strip() == "Vecchio"


def test_sezione_mancante_o_vuota():
    with pytest.raises(ValueError, match="manca la sezione"):
        N.note_dal_changelog(CHANGELOG, "v9.9.9")
    with pytest.raises(ValueError, match="vuota"):
        N.note_dal_changelog("## 2.0.0\n\n## 1.0.0\nx\n", "v2.0.0")
    with pytest.raises(ValueError, match="manca la sezione"):  # 1.3.0 non deve combaciare con 1.3.01
        N.note_dal_changelog("## 1.3.01\nx\n", "v1.3.0")


def test_il_changelog_vero_ha_la_sezione_della_versione_corrente():
    n = N.note_dal_changelog((RADICE / "CHANGELOG.md").read_text(encoding="utf-8"), "v1.3.0")
    assert len(n) > 100


def test_riga_di_comando():
    r = subprocess.run([sys.executable, str(RADICE / "strumenti/note_release.py"), "tag", "V_1.0.1"], capture_output=True, text=True)
    assert r.returncode == 1 and "vX.Y.Z" in r.stderr
    r = subprocess.run([sys.executable, str(RADICE / "strumenti/note_release.py"), "tag", "1.3.0"], capture_output=True, text=True)
    assert r.stdout.strip() == "v1.3.0"


def test_workflow_release_ha_i_trigger_e_i_permessi():
    richiede(".github/workflows/release.yml", ".github/workflows/test.yml")
    w = yaml.safe_load((RADICE / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    on = w.get("on") or w[True]  # PyYAML legge «on» come True
    assert on["push"]["tags"] == ["v[0-9]+.[0-9]+.[0-9]+"] and "versione" in on["workflow_dispatch"]["inputs"]
    assert w["permissions"]["contents"] == "write"
    assert w["jobs"]["release"]["needs"] == "test" and w["jobs"]["test"]["uses"] == "./.github/workflows/test.yml"
    t = yaml.safe_load((RADICE / ".github/workflows/test.yml").read_text(encoding="utf-8"))
    assert "workflow_call" in (t.get("on") or t[True])


def test_script_dello_zip_usato_da_release_e_prova_mac():
    richiede(".github/workflows/release.yml", ".github/workflows/prova-mac.yml")
    for nome in ("release.yml", "prova-mac.yml"):
        assert "strumenti/crea_zip.sh" in (RADICE / ".github/workflows" / nome).read_text(encoding="utf-8")
    w = yaml.safe_load((RADICE / ".github/workflows/prova-mac.yml").read_text(encoding="utf-8"))
    passi = " ".join(str(p.get("run", "")) for p in w["jobs"]["zip-release"]["steps"])
    assert "Installa.command --non-interattivo" in passi and "-m rapido" in passi and "unzip" in passi


def test_crea_zip_esclude_i_file_del_solo_repository(tmp_path):
    import shutil

    richiede(".git", ".gitattributes")
    if not shutil.which("zipinfo") or not shutil.which("git"):
        pytest.skip("servono git e zipinfo")
    r = subprocess.run(["bash", str(RADICE / "strumenti/crea_zip.sh"), "vTEST", str(tmp_path)], capture_output=True, text=True, cwd=RADICE)
    assert r.returncode == 0, r.stderr
    import zipfile

    nomi = zipfile.ZipFile(r.stdout.strip().splitlines()[-1]).namelist()
    assert "confronta-portafogli-vTEST/app.py" in nomi and not any("/.github/" in n for n in nomi)
