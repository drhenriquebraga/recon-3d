# -*- coding: utf-8 -*-
import numpy as np

TETO_CORTES = 64
TETO_PONTOS = 2000


def indice_do_corte(pos, n):
    n = max(1, int(n))
    p = min(1.0, max(0.0, float(pos)))
    return int(round(p * (n - 1)))


def poligono_em_voxel(pontos, forma_yx):
    alt, larg = int(forma_yx[0]), int(forma_yx[1])
    fora = []
    for p in list(pontos or ())[:TETO_PONTOS]:
        try:
            fx, fy = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (np.isfinite(fx) and np.isfinite(fy)):
            continue
        fx = min(1.0, max(0.0, fx))
        fy = min(1.0, max(0.0, fy))
        fora.append((fy * alt - 0.5, fx * larg - 0.5))
    return fora


def mascara_do_corte(poligono, forma_yx):
    alt, larg = int(forma_yx[0]), int(forma_yx[1])
    m = np.zeros((alt, larg), dtype=bool)
    if len(poligono) < 3:
        return m
    P = np.asarray(poligono, dtype=np.float64)
    ys, xs = P[:, 0], P[:, 1]
    y0 = max(0, int(np.floor(ys.min())))
    y1 = min(alt - 1, int(np.ceil(ys.max())))
    x0 = max(0, int(np.floor(xs.min())))
    x1 = min(larg - 1, int(np.ceil(xs.max())))
    if y1 < y0 or x1 < x0:
        return m
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1].astype(np.float64)
    dentro = np.zeros(yy.shape, dtype=bool)
    yj, xj = ys[-1], xs[-1]
    for yi, xi in zip(ys, xs):
        cruza = ((yi > yy) != (yj > yy))
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = (xj - xi) * (yy - yi) / (yj - yi) + xi
        dentro ^= cruza & (xx < xc)
        yj, xj = yi, xi
    m[y0:y1 + 1, x0:x1 + 1] = dentro
    return m


def _distancia_com_sinal(m, esp_yx):
    from scipy import ndimage
    if not m.any():
        return np.full(m.shape, 1e6, dtype=np.float32)
    fora = ndimage.distance_transform_edt(~m, sampling=esp_yx)
    dentro = ndimage.distance_transform_edt(m, sampling=esp_yx)
    return (fora - dentro).astype(np.float32)


def volume_do_desenho(cortes, forma_zyx, esp_zyx):
    Z, Y, X = [int(v) for v in forma_zyx]
    vol = np.zeros((Z, Y, X), dtype=bool)
    planos = {}
    for z, polis in sorted((cortes or {}).items())[:TETO_CORTES]:
        z = int(z)
        if not 0 <= z < Z:
            continue
        m = np.zeros((Y, X), dtype=bool)
        for p in polis or ():
            m |= mascara_do_corte(p, (Y, X))
        if m.any():
            planos[z] = m
    if not planos:
        return vol
    zs = sorted(planos)
    esp_yx = (float(esp_zyx[1]), float(esp_zyx[2]))
    for z in zs:
        vol[z] = planos[z]
    for za, zb in zip(zs[:-1], zs[1:]):
        if zb - za < 2:
            continue
        da = _distancia_com_sinal(planos[za], esp_yx)
        db = _distancia_com_sinal(planos[zb], esp_yx)
        for z in range(za + 1, zb):
            t = (z - za) / float(zb - za)
            vol[z] = ((1.0 - t) * da + t * db) < 0
    return vol
