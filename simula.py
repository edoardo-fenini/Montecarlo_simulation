"""Motore di simulazione Monte Carlo. Tre generatori di rendimenti (bootstrap, Student-t, GARCH)
più un involucro per eventi idiosincratici, e un motore che simula i portafogli mese per mese."""

from __future__ import annotations

import numpy as np

GG = 21  # giorni di borsa in un mese (12 mesi = 252 giorni)


# ---------------------------------------------------------------- ricentratura
def mu_giornaliero(rend_annuo, giorni: int = 252) -> np.ndarray:
    """Rendimento medio giornaliero semplice tale che 1 € cresce in media del rend_annuo in un anno."""
    return (1.0 + np.asarray(rend_annuo, float)) ** (1.0 / giorni) - 1.0


def ricentra(M: np.ndarray, rend_annui, costi_annui=None, giorni: int = 252) -> np.ndarray:
    """M (giorni x titoli): toglie la media storica e mette quella desiderata.
    Volatilità, code e correlazioni restano quelle storiche. costi_annui = TER sottratto ogni giorno."""
    M = np.asarray(M, float)
    mu = mu_giornaliero(np.broadcast_to(rend_annui, (M.shape[1],)), giorni)
    if costi_annui is not None:
        mu = mu - np.asarray(costi_annui, float) / giorni
    return M - M.mean(axis=0) + mu


# ---------------------------------------------------------------- generatori
class Bootstrap:
    """Stationary block bootstrap: si pescano blocchi di giorni consecutivi di lunghezza casuale
    (geometrica, media `blocco`) dallo storico, tenendo insieme tutti i titoli dello stesso giorno."""

    def __init__(self, M, blocco=20):
        self.M, self.p = np.asarray(M, float), 1.0 / blocco

    def prepara(self, n, T, rng):
        L = len(self.M)
        nuovo = rng.random((n, T)) < self.p
        nuovo[:, 0] = True
        start = rng.integers(0, L, size=(n, T))
        t = np.arange(T)
        ultimo = np.maximum.accumulate(np.where(nuovo, t, 0), axis=1)
        self.idx = (np.take_along_axis(start, ultimo, axis=1) + (t - ultimo)) % L

    def blocco(self, m):
        return self.M[self.idx[:, m * GG : (m + 1) * GG]]


class StudentT:
    """Rendimenti i.i.d. da una t multivariata (code grasse) con stessa media e covarianza dello storico."""

    def __init__(self, M, gdl=5):
        M = np.asarray(M, float)
        self.mu, self.gdl = M.mean(0), gdl
        self.Lc = np.linalg.cholesky(np.cov(M.T) + 1e-14 * np.eye(M.shape[1]))

    def prepara(self, n, T, rng):
        self.n, self.rng = n, rng

    def blocco(self, m):
        z = self.rng.standard_normal((self.n, GG, len(self.mu))) @ self.Lc.T
        chi = self.rng.chisquare(self.gdl, (self.n, GG, 1))
        return self.mu + z * np.sqrt((self.gdl - 2) / chi)


class Garch:
    """GARCH(1,1) per ogni titolo; gli shock standardizzati sono ripescati (bootstrap) tenendo
    insieme lo stesso giorno per tutti i titoli, così si conservano le correlazioni."""

    def __init__(self, M):
        from arch import arch_model

        M = np.asarray(M, float)
        self.mu = M.mean(0)
        N = M.shape[1]
        par = np.zeros((N, 3))
        Z = np.zeros_like(M)
        for j in range(N):
            r = (M[:, j] - self.mu[j]) * 100
            f = arch_model(r, mean="Zero", vol="GARCH", p=1, q=1, dist="normal").fit(disp="off")
            om, al, be = f.params["omega"], f.params["alpha[1]"], f.params["beta[1]"]
            if al + be > 0.995:  # troppo persistente: riporta a un valore stazionario
                k = 0.995 / (al + be)
                al, be = al * k, be * k
            par[j] = (om, al, be)
            z = f.resid / f.conditional_volatility
            Z[:, j] = (z - z.mean()) / z.std()
        self.par, self.Z = par, Z
        self.h0 = par[:, 0] / (1 - par[:, 1] - par[:, 2])

    def prepara(self, n, T, rng):
        self.n, self.rng = n, rng
        self.h = np.tile(self.h0, (n, 1))
        self.eps2 = np.tile(self.h0, (n, 1))

    def blocco(self, m):
        om, al, be = self.par.T
        out = np.empty((self.n, GG, len(om)))
        for g in range(GG):
            self.h = om + al * self.eps2 + be * self.h
            z = self.Z[self.rng.integers(0, len(self.Z), self.n)]
            eps = np.sqrt(self.h) * z
            self.eps2 = eps**2
            out[:, g, :] = self.mu + eps / 100.0
        return out


class ConCrolli:
    """Aggiunge a un generatore la possibilità che un singolo titolo crolli dell'80-100% in un giorno
    (probabilità annua p_anno per titolo). Se compensa=True si rimette il rendimento medio perso,
    così cambia il rischio ma non il rendimento atteso."""

    def __init__(self, base, colonne, p_anno=0.015, perdita=(0.8, 1.0), compensa=True, giorni=252):
        self.base, self.col = base, list(colonne)
        self.pg, self.perd, self.comp = p_anno / giorni, perdita, compensa

    def prepara(self, n, T, rng):
        self.rng, self.n = rng, n
        self.base.prepara(n, T, rng)

    def blocco(self, m):
        r = self.base.blocco(m)
        sub = r[:, :, self.col]
        ev = self.rng.random(sub.shape) < self.pg
        k = int(ev.sum())
        if k:  # numeri casuali solo per i (rari) crolli
            L = self.rng.uniform(*self.perd, k)
            sub[ev] = (1 + sub[ev]) * (1 - L) - 1
        if self.comp:
            sub += self.pg * np.mean(self.perd)
        r[:, :, self.col] = sub
        return r


# ---------------------------------------------------------------- motore
def ribilancia(H: np.ndarray, w: np.ndarray, costo_rb: float) -> np.ndarray:
    """Riporta i valori per titolo H (n x titoli) ai pesi target w, pagando costo_rb sull'importo movimentato."""
    tot = H.sum(1)
    target = tot[:, None] * w
    costo = costo_rb * np.abs(H - target).sum(1)
    return target * ((tot - costo) / tot)[:, None]


def simula(
    gen,
    porte: dict,
    n: int,
    anni: int,
    capitale: float,
    versamento: float,
    costo_rb: float,
    checkpoint_anni: list,
    seed: int,
    giorni: int = 252,
    chunk: int = 1000,
    rib_mesi: int = 12,
    progresso=None,
) -> dict:
    """porte: {nome: (colonne, pesi)}. Ritorna dict con, per portafoglio, i valori a fine mese
    (n x mesi+1), max drawdown e tempo sott'acqua massimo ai checkpoint, più volatilità e correlazioni.
    rib_mesi: ogni quanti mesi si ribilancia (0 = mai). progresso: funzione(frazione completata)."""
    assert giorni == 12 * GG
    rng = np.random.default_rng(seed)
    mesi, nomi = anni * 12, list(porte)
    P = len(nomi)
    cpm = {int(h * 12): h for h in checkpoint_anni}
    out = {
        k: {
            "mensile": np.empty((n, mesi + 1), np.float32),
            "mdd": {h: np.empty(n, np.float32) for h in checkpoint_anni},
            "uw": {h: np.empty(n, np.float32) for h in checkpoint_anni},
        }
        for k in nomi
    }
    s1, cross, cnt = np.zeros(P), np.zeros((P, P)), 0
    fatti = 0
    while fatti < n:
        nn = min(chunk, n - fatti)
        sl = slice(fatti, fatti + nn)
        gen.prepara(nn, mesi * GG, rng)
        st = {}
        for k in nomi:
            w = np.asarray(porte[k][1], float)
            st[k] = dict(
                H=np.tile(capitale * w, (nn, 1)),
                runmax=np.full(nn, float(capitale)),
                mdd=np.zeros(nn),
                last=np.zeros(nn, int),
                uw=np.zeros(nn, int),
            )
            out[k]["mensile"][sl, 0] = capitale
        for m in range(mesi):
            blocco = gen.blocco(m)
            tabs = m * GG + np.arange(1, GG + 1)
            rets = []
            for k in nomi:
                cols, w = porte[k][0], np.asarray(porte[k][1], float)
                s = st[k]
                H = s["H"]
                if rib_mesi and m > 0 and m % rib_mesi == 0:  # ribilanciamento ai pesi target, con costo
                    H = ribilancia(H, w, costo_rb)
                if versamento and m > 0:
                    H = H + versamento * w
                V0 = H.sum(1)
                Hd = H[:, None, :] * np.cumprod(1.0 + blocco[:, :, cols], axis=1)
                Vd = Hd.sum(2)
                s["H"] = Hd[:, -1, :]
                rets.append(Vd / np.concatenate([V0[:, None], Vd[:, :-1]], 1) - 1.0)
                cm = np.maximum(s["runmax"][:, None], np.maximum.accumulate(Vd, axis=1))
                s["mdd"] = np.minimum(s["mdd"], (Vd / cm - 1.0).min(1))
                lp = np.maximum(np.maximum.accumulate(np.where(Vd >= cm, tabs, 0), axis=1), s["last"][:, None])
                s["uw"] = np.maximum(s["uw"], (tabs - lp).max(1))
                s["last"], s["runmax"] = lp[:, -1], cm[:, -1]
                out[k]["mensile"][sl, m + 1] = Vd[:, -1]
                if (m + 1) in cpm:
                    h = cpm[m + 1]
                    out[k]["mdd"][h][sl] = s["mdd"]
                    out[k]["uw"][h][sl] = s["uw"] / giorni  # in anni
            R = np.stack(rets, axis=2).reshape(-1, P)
            s1 += R.sum(0)
            cross += R.T @ R
            cnt += len(R)
        fatti += nn
        if progresso:
            progresso(fatti / n)
    # controllo: i percorsi simulati devono essere esattamente quelli richiesti
    assert fatti == n and all(out[k]["mensile"].shape[0] == n for k in nomi), "numero di percorsi diverso da quello richiesto"
    out["_n"] = fatti
    mean = s1 / cnt
    cov = cross / cnt - np.outer(mean, mean)
    sd = np.sqrt(np.diag(cov))
    for i, k in enumerate(nomi):
        out[k]["vol"] = float(sd[i] * np.sqrt(giorni))
    with np.errstate(invalid="ignore", divide="ignore"):
        out["_corr"] = (nomi, cov / np.outer(sd, sd))
    return out
