import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np

from simula import GG, Bootstrap, ribilancia, ricentra, simula

CAP, ANNI = 5000.0, 2


def run(M, porte, seed=1, n=40, costo=0.0, versamento=0, cap=CAP):
    return simula(Bootstrap(M, 20), porte, n, ANNI, cap, versamento, costo, [1, 2], seed, 252, chunk=n)


def rand_M(seed=0, L=500, k=3):
    return np.random.default_rng(seed).normal(0.0004, 0.015, (L, k))


def test_zero_rendimento_nessun_versamento_valore_invariato():
    M = np.zeros((300, 3))
    res = run(M, {"p": (np.arange(3), np.full(3, 1 / 3))}, costo=0.001)
    assert np.allclose(res["p"]["mensile"], CAP)
    assert np.allclose(res["p"]["mdd"][2], 0)


def test_titolo_singolo_ha_le_metriche_del_titolo():
    M = rand_M()
    res = run(M, {"solo": (np.array([1]), np.array([1.0])), "altro": (np.array([0, 2]), np.array([0.5, 0.5]))})
    # stessa estrazione del generatore, calcolata a mano
    rng = np.random.default_rng(1)
    g = Bootstrap(M, 20)
    g.prepara(40, ANNI * 252, rng)
    v = CAP * np.cumprod(1 + M[g.idx, 1], axis=1)
    cm = np.maximum.accumulate(np.concatenate([np.full((40, 1), CAP), v], 1), axis=1)[:, 1:]
    mdd = (v / cm - 1).min(1)
    assert np.allclose(res["solo"]["mensile"][:, -1], v[:, -1], rtol=1e-4)
    assert np.allclose(res["solo"]["mdd"][2], mdd, atol=1e-5)


def test_ricentratura_da_esattamente_il_rendimento_richiesto():
    M = rand_M(3, 800, 4)
    out = ricentra(M, 0.06)
    assert np.allclose((1 + out.mean(0)) ** 252 - 1, 0.06, atol=1e-12)
    ter = np.array([0, 0, 0, 0.002])
    out = ricentra(M, 0.06, ter)
    assert np.allclose((1 + out[:, 3].mean() + 0.002 / 252) ** 252 - 1, 0.06, atol=1e-12)
    assert np.allclose(out.std(0), M.std(0))  # la volatilità non cambia


def test_stesso_seed_stessi_risultati():
    M = rand_M()
    p = {"p": (np.arange(3), np.full(3, 1 / 3))}
    a, b, c = run(M, p, seed=5), run(M, p, seed=5), run(M, p, seed=6)
    assert np.array_equal(a["p"]["mensile"], b["p"]["mensile"])
    assert not np.array_equal(a["p"]["mensile"], c["p"]["mensile"])


def test_ribilanciamento_riporta_ai_pesi_target():
    H = np.array([[500.0, 1500.0, 3000.0], [100.0, 100.0, 100.0]])
    w = np.array([0.5, 0.3, 0.2])
    for costo in (0.0, 0.001):
        N = ribilancia(H, w, costo)
        assert np.allclose(N / N.sum(1, keepdims=True), w)
    assert np.allclose(ribilancia(H, w, 0.0).sum(1), H.sum(1))  # senza costi non si perde nulla
    assert (ribilancia(H, w, 0.001).sum(1) < H.sum(1)).all()  # con costi sì
    assert np.allclose(ribilancia(np.array([[100.0, 100.0]]), np.array([0.5, 0.5]), 0.001), 100.0)  # già a target: nessun costo


def test_numero_di_percorsi_generati():
    """Il motore genera esattamente i percorsi richiesti, anche quando non sono multipli del blocco di calcolo."""
    M = rand_M()
    p = {"a": (np.arange(3), np.full(3, 1 / 3)), "b": (np.array([0]), np.array([1.0]))}
    for n, chunk in ((1000, 1000), (2500, 1000), (777, 300)):
        res = simula(Bootstrap(M, 20), p, n, ANNI, CAP, 0, 0.0, [1, 2], 3, 252, chunk=chunk)
        assert res["_n"] == n
        for k in p:
            assert res[k]["mensile"].shape == (n, ANNI * 12 + 1)
            assert res[k]["mdd"][2].shape == (n,)
    g = Bootstrap(M, 20)
    g.prepara(50, ANNI * 252, np.random.default_rng(0))
    assert g.idx.shape == (50, ANNI * 252)  # percorsi x giorni
    assert g.blocco(0).shape == (50, GG, 3)  # percorsi x giorni del mese x titoli
