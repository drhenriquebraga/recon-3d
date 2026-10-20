# -*- coding: utf-8 -*-
# GUARDA: este modulo nao exporta malha, imagem nem video: botao de exportar
# e declaracao de uso pretendido. O RTSTRUCT continua exportando pelo vigia.
import os

LAJE_PADRAO_MM = 10.0
LAJE_MAX_MM = 100.0

JANELAS = {
    "pulmao": (-600, 1500),
    "mediastino": (40, 400),
    "osso": (400, 1800),
    "cerebro": (40, 80),
}


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def projetar(volume, eixo, modo, i0, i1):
    import numpy as np
    v = np.asarray(volume)
    i0 = int(_clamp(i0, 0, v.shape[eixo] - 1))
    i1 = int(_clamp(i1, i0 + 1, v.shape[eixo]))
    fatia = [slice(None)] * 3
    fatia[eixo] = slice(i0, i1)
    laje = v[tuple(fatia)]
    return (laje.max(axis=eixo) if modo == "mip" else laje.min(axis=eixo))


def para_png(arr, centro, largura):
    import struct
    import zlib

    import numpy as np
    a = np.asarray(arr, dtype=np.float32)

    if a.ndim == 3 and a.shape[-1] in (3, 4):
        lum = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2])
        b = np.clip(lum, 0.0, 255.0).astype(np.uint8)
        alt, larg = b.shape
    else:
        if a.ndim != 2:
            raise ValueError(
                u"forma %s não é um corte 2D nem uma imagem em cor" % (a.shape,))
        lo = float(centro) - float(largura) / 2.0
        hi = float(centro) + float(largura) / 2.0
        if hi <= lo:
            hi = lo + 1.0
        b = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
        b = (b * 255.0).astype(np.uint8)
        alt, larg = b.shape

    linhas = b"".join(b"\x00" + b[y].tobytes() for y in range(alt))

    def bloco(tipo, dados):
        c = tipo + dados
        return (struct.pack(">I", len(dados)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + bloco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, 0, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(linhas, 6))
            + bloco(b"IEND", b""))


TETO_DA_TELA = 1536


def grade_da_tela(forma, mm_lin, mm_col, teto=TETO_DA_TELA):
    alt, larg = int(forma[0]), int(forma[1])
    alvo = min(float(mm_lin), float(mm_col))
    maior = max(alt * float(mm_lin), larg * float(mm_col))
    alvo = max(alvo, maior / float(teto))
    fl, fc = float(mm_lin) / alvo, float(mm_col) / alvo
    return (max(1, int(round(alt * fl))), max(1, int(round(larg * fc))),
            fl, fc)


def para_a_tela(a, mm_lin, mm_col):
    import numpy as np
    a = np.asarray(a)
    alt, larg, fl, fc = grade_da_tela(a.shape, mm_lin, mm_col)
    li = np.minimum((np.arange(alt) + 0.5) / fl, a.shape[0] - 1).astype(np.intp)
    co = np.minimum((np.arange(larg) + 0.5) / fc, a.shape[1] - 1).astype(np.intp)
    return a[li][:, co]


def mm_do_plano(esp_zyx, eixo):
    resto = [float(esp_zyx[k]) for k in range(3) if k != int(eixo)]
    return tuple((m if m > 0 else 1.0) for m in resto)


def cranio_em_cima(a, eixo, sentido):
    if not sentido:
        return a
    linhas = [k for k in range(3) if k != int(eixo)][0]
    if str(sentido[linhas]).lower() == "sup":
        return a[::-1]
    return a


def plano_para_a_tela(a, eixo, esp_zyx, sentido=None):
    ml, mc = mm_do_plano(esp_zyx, eixo)
    return para_a_tela(cranio_em_cima(a, eixo, sentido), ml, mc)


LIMIAR_OSSO_HU = 250.0
LIMIAR_PELE_HU = -400.0

PASSO_3D_MM = 2.0

MIN_OSSO_CM3 = 1.0

PONTOS_3D = {"osso": 14000, "pele": 4000}
CORES_3D = {"osso": (226, 214, 188), "pele": (190, 146, 128)}


def _encolher(m, passos):
    import numpy as np
    m = np.asarray(m, dtype=bool)
    pz, py, px = [max(1, int(p)) for p in passos]
    Z, Y, X = m.shape
    Zc, Yc, Xc = -(-Z // pz) * pz, -(-Y // py) * py, -(-X // px) * px
    if (Zc, Yc, Xc) != (Z, Y, X):
        m = np.pad(m, ((0, Zc - Z), (0, Yc - Y), (0, Xc - X)))
    return m.reshape(Zc // pz, pz, Yc // py, py, Xc // px, px).any(
        axis=(1, 3, 5))


def mascaras_3d(volume, espacamento_zyx, passo_mm=PASSO_3D_MM,
                camadas=("osso", "pele")):
    import numpy as np
    from scipy import ndimage
    v = np.asarray(volume)
    esp = [float(e) for e in espacamento_zyx]
    passos = [max(1, int(round(float(passo_mm) / e))) if e > 0 else 1
              for e in esp]
    esp_r = tuple(e * p for e, p in zip(esp, passos))
    fora = {}
    if "osso" not in camadas:
        osso = None
    else:
        osso = _encolher(v >= LIMIAR_OSSO_HU, passos)
    if osso is not None and osso.any():
        rot, n = ndimage.label(osso)
        if n:
            vox_cm3 = esp_r[0] * esp_r[1] * esp_r[2] / 1000.0
            tam = np.bincount(rot.ravel())
            fica = tam * vox_cm3 >= MIN_OSSO_CM3
            fica[0] = False
            osso = fica[rot]
    if osso is not None:
        fora["osso"] = osso
    if "pele" not in camadas:
        return fora, esp_r

    corpo = _encolher(v > LIMIAR_PELE_HU, passos)
    if corpo.any():
        rot, n = ndimage.label(corpo)
        if n > 1:
            tam = np.bincount(rot.ravel())
            tam[0] = 0
            corpo = rot == int(np.argmax(tam))
        for z in range(corpo.shape[0]):
            if corpo[z].any():
                corpo[z] = ndimage.binary_fill_holes(corpo[z])
    fora["pele"] = corpo
    return fora, esp_r


def cena_3d(volume, espacamento_zyx, sentido=None, camadas=("osso", "pele")):
    import radai_geom
    import radai_viewer3d
    mascaras, esp_r = mascaras_3d(volume, espacamento_zyx)
    grade = radai_geom.Grade(esp_r)
    itens = []
    for c in camadas:
        m = mascaras.get(c)
        if m is None or not m.any():
            continue
        d = radai_viewer3d.nuvem_de_mascara(
            m, grade, cor=CORES_3D.get(c, (160, 170, 190)),
            max_pontos=PONTOS_3D.get(c, 4000), normal="local")
        if d["pontos"]:
            d["camada"] = c
            itens.append(d)
    radai_viewer3d.recentrar(itens)
    eixos = None
    st = list(sentido or ())
    if len(st) == 3:
        eixos = [st[2], st[1], st[0]]
    return {"itens": itens, "eixos": eixos,
            "erro": u"" if itens else u"nada acima dos limiares nesta série"}


VERSAO_MALHA = u"1"

PASSO_MALHA_MM = 2.0
PASSO_MALHA_MIN_MM = 1.0
CELULAS_NO_MENOR_LADO = 6
TETO_CELULAS_MALHA = 3000000
TETO_TRIANGULOS = 80000
SUAVIZACAO_MALHA_MM = 1.0
K_TRIANGULOS_POR_AREA = 11.4
TRIANGULOS_POR_CELULA = 6.0
SO_A_FACE_EXTERNA = (u"skin",)

CABECALHO_STL_VISOR = (b"RadAI Recon3D | VIEW ONLY, in-app | UNAPPROVED AI "
                       b"contours | mm LPS")

EIXOS_LPS = [u"esq", u"post", u"sup"]

OPACIDADE_INICIAL = (
    (u"skin", 0.15), (u"body", 0.15), (u"pele", 0.15),
    (u"cavity", 0.22), (u"mediastin", 0.25),
    (u"lung", 0.35), (u"chestwall", 0.35), (u"bag_bowel", 0.4),
    (u"pericard", 0.4), (u"breast", 0.45),
)

_PALETA_RESERVA = ((120, 170, 255), (240, 160, 90), (130, 210, 140),
                   (220, 120, 190), (230, 210, 110), (120, 210, 220),
                   (190, 150, 240), (240, 120, 110))


def opacidade_inicial(nome):
    try:
        import radai_sets
        raiz = radai_sets.raiz_sem_sufixo(nome)
    except Exception:
        raiz = str(nome or u"")
    raiz = str(raiz).lower()
    for pedaco, alfa in OPACIDADE_INICIAL:
        if pedaco in raiz:
            return float(alfa)
    return 1.0


def ler_rtstruct(caminho):
    import pydicom
    return pydicom.dcmread(str(caminho), force=True)


def _mapas_do_rtstruct(ds):
    nomes = []
    for s in getattr(ds, "StructureSetROISequence", None) or []:
        try:
            nomes.append((int(s.ROINumber), str(getattr(s, "ROIName", u"")
                                                 or u"")))
        except Exception:
            continue
    contornos = {}
    for r in getattr(ds, "ROIContourSequence", None) or []:
        try:
            contornos[int(getattr(r, "ReferencedROINumber", -1))] = r
        except Exception:
            continue
    return nomes, contornos


def rois_do_rtstruct(ds):
    nomes, contornos = _mapas_do_rtstruct(ds)
    fora, vistos = [], set()
    for num, nome in nomes:
        r = contornos.get(num)
        if r is None or not nome or nome in vistos:
            continue
        n = len(getattr(r, "ContourSequence", None) or [])
        if n == 0:
            continue
        vistos.add(nome)
        cor = None
        try:
            c = getattr(r, "ROIDisplayColor", None)
            if c is not None and len(c) >= 3:
                cor = [max(0, min(255, int(float(x)))) for x in list(c)[:3]]
        except Exception:
            cor = None
        if cor is None:
            cor = list(_PALETA_RESERVA[num % len(_PALETA_RESERVA)])
        fora.append({u"nome": nome, u"numero": num, u"cor": cor,
                     u"contornos": n, u"opacidade": opacidade_inicial(nome)})
    return fora


def _numeros_crus(item, tag):
    try:
        e = item.get_item(tag)
    except Exception:
        e = None
    if e is None:
        return None
    v = e.value
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        return [float(x) for x in bytes(v).split(b"\\") if x.strip()]
    if isinstance(v, (int, float)):
        return [float(v)]
    return [float(x) for x in v]


_TAG_CONTOUR_DATA = 0x30060050


def grade_z_do_rtstruct(ds):
    import numpy as np
    zs = []
    for r in getattr(ds, "ROIContourSequence", None) or []:
        for c in getattr(r, "ContourSequence", None) or []:
            try:
                e = c.get_item(_TAG_CONTOUR_DATA)
                v = e.value if e is not None else None
                if isinstance(v, (bytes, bytearray)):
                    zs.append(float(bytes(v).split(b"\\", 3)[2]))
                elif v is not None:
                    zs.append(float(v[2]))
            except Exception:
                continue
    if not zs:
        return np.zeros(0, dtype=np.float64)
    return np.unique(np.round(np.asarray(zs, dtype=np.float64), 2))


def contornos_da_roi(ds, nome):
    import numpy as np
    nomes, contornos = _mapas_do_rtstruct(ds)
    num = None
    for n, x in nomes:
        if x == nome:
            num = n
            break
    if num is None or num not in contornos:
        raise KeyError(nome)
    fora = []
    for c in getattr(contornos[num], "ContourSequence", None) or []:
        tipo = str(getattr(c, "ContourGeometricType", u"CLOSED_PLANAR")
                   or u"CLOSED_PLANAR").strip().upper()
        if tipo != u"CLOSED_PLANAR":
            continue
        try:
            dados = _numeros_crus(c, _TAG_CONTOUR_DATA)
        except Exception:
            continue
        if not dados or len(dados) < 9 or len(dados) % 3:
            continue
        fora.append(np.asarray(dados, dtype=np.float64).reshape(-1, 3))
    return fora


def _par_impar(polys, x0, y0, r, nx, ny):
    import numpy as np
    A, B = [], []
    for p in polys:
        q = np.asarray(p, dtype=np.float64)[:, :2]
        if len(q) < 3:
            continue
        A.append(q)
        B.append(np.roll(q, -1, axis=0))
    if not A:
        return np.zeros((ny, nx), dtype=bool)
    A = np.concatenate(A)
    B = np.concatenate(B)
    ya, yb = A[:, 1], B[:, 1]
    fica = ya != yb
    A, B, ya, yb = A[fica], B[fica], ya[fica], yb[fica]
    lo = np.minimum(ya, yb)
    hi = np.maximum(ya, yb)
    i0 = np.clip(np.ceil((lo - y0) / r), 0, ny).astype(np.int64)
    i1 = np.clip(np.ceil((hi - y0) / r), 0, ny).astype(np.int64)
    cont = np.maximum(i1 - i0, 0)
    total = int(cont.sum())
    T = np.zeros((ny, nx + 1), dtype=np.int32)
    if total:
        aresta = np.repeat(np.arange(len(cont)), cont)
        ini = np.cumsum(cont) - cont
        linha = i0[aresta] + (np.arange(total) - ini[aresta])
        yl = y0 + linha * r
        xa, xb = A[aresta, 0], B[aresta, 0]
        t = (yl - ya[aresta]) / (yb[aresta] - ya[aresta])
        xc = xa + t * (xb - xa)
        j = np.clip(np.floor((xc - x0) / r).astype(np.int64) + 1, 0, nx)
        np.add.at(T, (linha, j), 1)
    return (np.cumsum(T, axis=1)[:, :nx] % 2).astype(bool)


def _niveis(contornos, tol_mm=0.05):
    import numpy as np
    pares, fora = [], 0
    for c in contornos:
        if float(np.ptp(c[:, 2])) > 0.5:
            fora += 1
            continue
        pares.append((float(np.mean(c[:, 2])), c[:, :2]))
    if not pares:
        return [], fora
    pares.sort(key=lambda p: p[0])
    niveis = []
    for z, p in pares:
        if niveis and abs(z - niveis[-1][0]) <= tol_mm:
            niveis[-1][1].append(p)
        else:
            niveis.append((z, [p]))
    return niveis, fora


def _dentro_do_poligono(ponto, poligono):
    import numpy as np
    q = np.asarray(poligono, dtype=np.float64)
    x, y = float(ponto[0]), float(ponto[1])
    a, b = q, np.roll(q, -1, axis=0)
    cruza = (a[:, 1] > y) != (b[:, 1] > y)
    if not cruza.any():
        return False
    a, b = a[cruza], b[cruza]
    xc = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return bool(int((xc > x).sum()) % 2)


def so_os_de_fora(niveis):
    fora = []
    for z, ps in niveis:
        fica = []
        for i, p in enumerate(ps):
            if not any(_dentro_do_poligono(p[0], q)
                       for j, q in enumerate(ps) if j != i):
                fica.append(p)
        fora.append((z, fica or list(ps)))
    return fora


def _cortes_com_vazios(niveis, grade_z=None, passo_mm=PASSO_MALHA_MM):
    import numpy as np
    zs = np.array([z for z, _p in niveis], dtype=np.float64)
    g = None
    if grade_z is not None:
        g = np.unique(np.asarray(grade_z, dtype=np.float64))
        if len(g) < 2:
            g = None
    if g is not None:
        dz = float(np.median(np.diff(g)))
        tol = 0.25 * dz
        perto = g[(g >= zs[0] - 1.5 * dz) & (g <= zs[-1] + 1.5 * dz)]
        k = np.clip(np.searchsorted(zs, perto), 1, len(zs)) if len(zs) > 1 \
            else np.ones(len(perto), dtype=np.int64)
        dist = np.minimum(np.abs(perto - zs[np.minimum(k, len(zs) - 1)]),
                          np.abs(perto - zs[k - 1]))
        vazios = [float(z) for z, d in zip(perto, dist) if d > tol]
    else:
        dz = float(np.median(np.diff(zs))) if len(zs) > 1 else 0.0
        if dz <= 0:
            dz = max(float(passo_mm), 1.0)
        vazios = []
        for a, b in zip(zs[:-1], zs[1:]):
            vao = b - a
            if vao > 1.5 * dz:
                n = int(round(vao / dz)) - 1
                vazios.extend(a + vao * m / float(n + 1)
                              for m in range(1, n + 1))
    todos = [(float(z), ps) for z, ps in niveis] + [(z, None) for z in vazios]
    todos.sort(key=lambda t: t[0])
    if todos[0][1] is not None:
        todos.insert(0, (todos[0][0] - dz, None))
    if todos[-1][1] is not None:
        todos.append((todos[-1][0] + dz, None))
    return todos, dz


def _tamanho_tipico(niveis):
    import numpy as np
    lados = []
    for _z, ps in niveis:
        for p in ps:
            lados.append(min(float(np.ptp(p[:, 0])), float(np.ptp(p[:, 1]))))
    return float(np.median(lados)) if lados else float(PASSO_MALHA_MM)


def _area_lateral(niveis, dz):
    import numpy as np
    per = 0.0
    for _z, ps in niveis:
        for p in ps:
            q = np.asarray(p, dtype=np.float64)
            per += float(np.linalg.norm(np.roll(q, -1, axis=0) - q,
                                        axis=1).sum())
    return per * max(float(dz), 0.0)


def _escolher_passo(tipico_mm, caixa_mm, passo_mm, teto_celulas,
                    area_mm2=0.0, teto_triangulos=None):
    p = min(float(passo_mm), max(PASSO_MALHA_MIN_MM,
                                 tipico_mm / float(CELULAS_NO_MENOR_LADO)))
    if teto_triangulos and area_mm2 > 0:
        p = max(p, (K_TRIANGULOS_POR_AREA * float(area_mm2)
                    / float(teto_triangulos)) ** 0.5)
    celulas = 1.0
    for lado in caixa_mm:
        celulas *= lado / p + 1.0
    if celulas > teto_celulas:
        p *= (celulas / float(teto_celulas)) ** (1.0 / 3.0) * 1.02
    return p


def campo_da_estrutura(contornos, grade_z=None, passo_mm=PASSO_MALHA_MM,
                       suavizar_mm=SUAVIZACAO_MALHA_MM,
                       teto_celulas=TETO_CELULAS_MALHA, face_externa=False,
                       passo_fixo=None, teto_triangulos=None):
    import numpy as np
    from scipy import ndimage
    niveis, fora_axial = _niveis(contornos)
    if not niveis:
        raise ValueError(u"a estrutura não tem contorno axial fechado")
    if face_externa:
        niveis = so_os_de_fora(niveis)
    cortes, dz = _cortes_com_vazios(niveis, grade_z, passo_mm)
    todos = np.concatenate([p for _z, ps in niveis for p in ps])
    xmin, ymin = todos.min(axis=0)
    xmax, ymax = todos.max(axis=0)
    caixa = (xmax - xmin, ymax - ymin, cortes[-1][0] - cortes[0][0])
    if passo_fixo:
        passo = float(passo_fixo)
    else:
        passo = _escolher_passo(_tamanho_tipico(niveis), caixa, passo_mm,
                                teto_celulas, _area_lateral(niveis, dz),
                                teto_triangulos)
    sig = max(0.0, float(suavizar_mm))
    margem = 2.0 * passo + 3.0 * sig
    x0, y0 = xmin - margem, ymin - margem
    ncx = int(np.ceil((xmax + margem - x0) / passo)) + 1
    ncy = int(np.ceil((ymax + margem - y0) / passo)) + 1
    r = passo / 2.0
    nfx, nfy = 2 * ncx - 1, 2 * ncy - 1
    vazio = np.full((ncy, ncx), dz / 2.0, dtype=np.float32)
    zs, planos = [], []
    for z, polys in cortes:
        zs.append(z)
        if not polys:
            planos.append(vazio)
            continue
        m = _par_impar(polys, x0, y0, r, nfx, nfy)
        if face_externa:
            m = ndimage.binary_fill_holes(m)
        if not m.any():
            planos.append(vazio)
            continue
        fora_d = ndimage.distance_transform_edt(~m) * r
        dentro_d = ndimage.distance_transform_edt(m) * r
        sd = np.where(m, -(dentro_d - r / 2.0), fora_d - r / 2.0)
        planos.append(sd[::2, ::2].astype(np.float32))
    zs = np.asarray(zs, dtype=np.float64)
    pilha = np.stack(planos)
    del planos
    nzo = int(np.floor((zs[-1] - zs[0]) / passo)) + 1
    zo = zs[0] + np.arange(nzo) * passo
    k = np.clip(np.searchsorted(zs, zo, side="right") - 1, 0, len(zs) - 2)
    t = ((zo - zs[k]) / (zs[k + 1] - zs[k])).astype(np.float32)
    F = (pilha[k] * (1.0 - t)[:, None, None]
         + pilha[k + 1] * t[:, None, None]).astype(np.float32)
    del pilha
    if sig > 0:
        sz = max(sig, 0.25 * dz) / passo
        F = ndimage.gaussian_filter(F, sigma=(sz, sig / passo, sig / passo),
                                    mode="nearest")
    F = np.pad(F, 1, mode="constant", constant_values=np.float32(passo))
    origem = np.array([x0 - passo, y0 - passo, zs[0] - passo],
                      dtype=np.float64)
    info = {u"passo_mm": round(float(passo), 3), u"cortes": len(niveis),
            u"espacamento_mm": round(float(dz), 3),
            u"fora_do_axial": int(fora_axial),
            u"face_externa": bool(face_externa)}
    return F, origem, passo, info


def _triangulos_estimados(F):
    import numpy as np
    d = F < 0
    todos = d[:-1, :-1, :-1].copy()
    algum = todos.copy()
    for dz_ in (0, 1):
        for dy_ in (0, 1):
            for dx_ in (0, 1):
                s = d[dz_:d.shape[0] - 1 + dz_, dy_:d.shape[1] - 1 + dy_,
                      dx_:d.shape[2] - 1 + dx_]
                todos &= s
                algum |= s
    return int((algum & ~todos).sum() * TRIANGULOS_POR_CELULA)


def malha_da_estrutura(contornos, grade_z=None, passo_mm=PASSO_MALHA_MM,
                       suavizar_mm=SUAVIZACAO_MALHA_MM,
                       teto_triangulos=TETO_TRIANGULOS,
                       teto_celulas=TETO_CELULAS_MALHA, face_externa=False):
    import numpy as np
    import radai_bolus
    passo_fixo = None
    suav = float(suavizar_mm)
    verts = faces = None
    for _tentativa in range(4):
        F, origem, passo_usado, info = campo_da_estrutura(
            contornos, grade_z, passo_mm, suav, teto_celulas, face_externa,
            passo_fixo, teto_triangulos)
        if not bool((F < 0).any()):
            if suav > 0:
                suav = 0.0
                continue
            verts = np.zeros((0, 3))
            faces = np.zeros((0, 3), dtype=np.int64)
            break
        est = _triangulos_estimados(F)
        if est > teto_triangulos * 1.15 and _tentativa < 3:
            passo_fixo = passo_usado * (est / float(teto_triangulos)) ** 0.5
            continue
        verts, faces = radai_bolus.superficie(F)
        del F
        if len(faces) <= teto_triangulos * 1.15 or _tentativa >= 3:
            break
        passo_fixo = passo_usado * (len(faces) / float(teto_triangulos)) ** 0.5
    lps = origem[None, :] + np.asarray(verts, dtype=np.float64) * passo_usado
    info[u"triangulos"] = int(len(faces))
    info[u"suavizada"] = bool(suav > 0)
    return lps, np.asarray(faces, dtype=np.int64), info


def malha_de_mascara(mascara, espacamento_zyx, origem_xyz=(0.0, 0.0, 0.0),
                     direcao=(1, 0, 0, 0, 1, 0, 0, 0, 1),
                     deslocamento_zyx=(0.0, 0.0, 0.0),
                     suavizar_mm=SUAVIZACAO_MALHA_MM):
    import radai_bolus
    F = _campo_da_mascara(mascara, espacamento_zyx, suavizar_mm)
    verts, faces = radai_bolus.superficie(F)
    return _mascara_em_lps(verts, faces, espacamento_zyx, origem_xyz, direcao,
                           deslocamento_zyx)


def _campo_da_mascara(mascara, espacamento_zyx, suavizar_mm):
    import numpy as np
    from scipy import ndimage
    m = np.asarray(mascara, dtype=np.float32)
    esp = [float(e) for e in espacamento_zyx]
    if suavizar_mm and float(suavizar_mm) > 0:
        m = ndimage.gaussian_filter(
            m, sigma=[float(suavizar_mm) / e for e in esp], mode="constant")
    return np.pad(np.float32(0.5) - m, 1, mode="constant",
                  constant_values=np.float32(0.5))


def _mascara_em_lps(verts, faces, espacamento_zyx, origem_xyz, direcao,
                    deslocamento_zyx):
    import numpy as np
    esp = [float(e) for e in espacamento_zyx]
    D = np.asarray(direcao, dtype=np.float64).reshape(3, 3)
    esp_xyz = np.array(esp[::-1], dtype=np.float64)
    desl_xyz = np.array([float(v) for v in deslocamento_zyx][::-1])
    quadro = (np.asarray(verts, dtype=np.float64) - 1.0) * esp_xyz + desl_xyz
    lps = np.asarray(origem_xyz, dtype=np.float64)[None, :] + quadro.dot(D.T)
    faces = np.asarray(faces, dtype=np.int64)
    if np.linalg.det(D) < 0 and len(faces):
        faces = faces[:, [0, 2, 1]]
    return lps, faces


def stl_da_malha(verts, faces):
    import radai_bolus
    return radai_bolus.stl_binario(verts, faces, cabecalho=CABECALHO_STL_VISOR)


def mascara_da_estrutura(contornos, grade_z=None, passo_mm=PASSO_MALHA_MM):
    F, origem, passo, _info = campo_da_estrutura(contornos, grade_z,
                                                 passo_mm, suavizar_mm=0.0)
    return F < 0, origem, passo


def item_em_lps(item, origem_xyz, direcao, deslocamento_xyz=(0.0, 0.0, 0.0)):
    import numpy as np
    if not item.get(u"pontos"):
        return item
    D = np.asarray(direcao, dtype=np.float64).reshape(3, 3)
    c = np.asarray(item.get(u"centro_mm") or (0.0, 0.0, 0.0),
                   dtype=np.float64)[::-1]
    quadro = (np.asarray(item[u"pontos"], dtype=np.float64) + c
              + np.asarray(deslocamento_xyz, dtype=np.float64))
    lps = np.asarray(origem_xyz, dtype=np.float64)[None, :] + quadro.dot(D.T)
    item[u"pontos"] = [[round(float(v), 2) for v in p] for p in lps]
    if item.get(u"normais"):
        n = np.asarray(item[u"normais"], dtype=np.float64).dot(D.T)
        item[u"normais"] = [[round(float(v), 3) for v in q] for q in n]
    item[u"centro_mm"] = [0.0, 0.0, 0.0]
    return item



def e_casca(nome):
    try:
        import radai_sets
        raiz = radai_sets.raiz_sem_sufixo(nome)
    except Exception:
        raiz = str(nome or u"")
    raiz = str(raiz).lower()
    return any(p in raiz for p in SO_A_FACE_EXTERNA)


def abrir_conjunto(caminho_rs):
    import numpy as np
    ds = ler_rtstruct(caminho_rs)
    grade = grade_z_do_rtstruct(ds)
    rois = rois_do_rtstruct(ds)
    contornos, lo, hi = {}, [], []
    for r in rois:
        c = contornos_da_roi(ds, r[u"nome"])
        contornos[r[u"nome"]] = c
        r[u"casca"] = e_casca(r[u"nome"])
        if c:
            todos = np.concatenate(c)
            a, b = todos.min(axis=0), todos.max(axis=0)
            r[u"caixa"] = [[round(float(v), 2) for v in a],
                           [round(float(v), 2) for v in b]]
            lo.append(a)
            hi.append(b)
        else:
            r[u"caixa"] = None
    del ds
    caixa = None
    if lo:
        caixa = [[round(float(v), 2) for v in np.min(lo, axis=0)],
                 [round(float(v), 2) for v in np.max(hi, axis=0)]]
    return {u"rois": [r for r in rois if contornos.get(r[u"nome"])],
            u"contornos": contornos, u"grade_z": grade, u"caixa": caixa}


def malha_do_conjunto(conjunto, nome):
    c = conjunto[u"contornos"][nome]
    return malha_da_estrutura(c, conjunto[u"grade_z"],
                              face_externa=e_casca(nome))


TETO_TRIANGULOS_CAMADA = {u"osso": 400000, u"pele": 150000}
PASSOS_CAMADA_MM = (2.0, 3.0, 4.0, 6.0, 8.0)
OPACIDADE_CAMADA = {u"osso": 1.0, u"pele": 0.15}


def _deslocamento_do_bloco(espacamento_zyx, passo_mm):
    fora = []
    for e in espacamento_zyx:
        e = float(e)
        p = max(1, int(round(float(passo_mm) / e))) if e > 0 else 1
        fora.append((p - 1) / 2.0 * e)
    return tuple(fora)


def _reduzir_media(m, fatores):
    import numpy as np
    m = np.asarray(m, dtype=np.float32)
    fz, fy, fx = [max(1, int(f)) for f in fatores]
    Z, Y, X = m.shape
    Zc, Yc, Xc = -(-Z // fz) * fz, -(-Y // fy) * fy, -(-X // fx) * fx
    if (Zc, Yc, Xc) != (Z, Y, X):
        m = np.pad(m, ((0, Zc - Z), (0, Yc - Y), (0, Xc - X)))
    return m.reshape(Zc // fz, fz, Yc // fy, fy, Xc // fx, fx).mean(
        axis=(1, 3, 5))


def malha_da_camada(volume, espacamento_zyx, origem_xyz, direcao, camada,
                    teto_triangulos=None):
    import numpy as np
    import radai_bolus
    if camada not in CORES_3D:
        raise KeyError(camada)
    teto = int(teto_triangulos or TETO_TRIANGULOS_CAMADA.get(camada, 150000))
    mascaras, esp0 = mascaras_3d(volume, espacamento_zyx, passo_mm=PASSO_3D_MM,
                                 camadas=(camada,))
    base = mascaras.get(camada)
    d0 = _deslocamento_do_bloco(espacamento_zyx, PASSO_3D_MM)
    if base is None or not base.any():
        return (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64),
                {u"passo_mm": PASSO_3D_MM, u"triangulos": 0})
    escolhido = None
    for passo in PASSOS_CAMADA_MM:
        f = [max(1, int(round(float(passo) / e))) for e in esp0]
        if escolhido is not None and f == escolhido[3]:
            continue
        if camada == u"osso":
            m = _encolher(base, f).astype(np.float32)
        else:
            m = _reduzir_media(base, f)
        esp_r = tuple(e * k for e, k in zip(esp0, f))
        F = np.pad(np.float32(0.5) - _suavizar(m, esp_r), 1,
                   mode="constant", constant_values=np.float32(0.5))
        del m
        escolhido = (F, esp_r, passo, f)
        if _triangulos_estimados(F) <= teto * 1.15:
            break
    F, esp_r, passo, f = escolhido
    verts, faces = radai_bolus.superficie(F)
    del F
    desl = tuple(d + (k - 1) / 2.0 * e for d, k, e in zip(d0, f, esp0))
    lps, faces = _mascara_em_lps(verts, faces, esp_r, origem_xyz, direcao,
                                 desl)
    return lps, faces, {u"passo_mm": passo, u"triangulos": int(len(faces))}


def _suavizar(m, espacamento_zyx, suavizar_mm=SUAVIZACAO_MALHA_MM):
    from scipy import ndimage
    if not suavizar_mm or float(suavizar_mm) <= 0:
        return m
    return ndimage.gaussian_filter(
        m, sigma=[float(suavizar_mm) / float(e) for e in espacamento_zyx],
        mode="constant")


def nuvem_do_conjunto(conjunto, nome, cor=None, max_pontos=None):
    import radai_geom
    import radai_viewer3d
    c = conjunto[u"contornos"][nome]
    fe = e_casca(nome)
    F, origem, passo, _info = campo_da_estrutura(
        c, conjunto[u"grade_z"], suavizar_mm=0.0, face_externa=fe,
        teto_triangulos=TETO_TRIANGULOS)
    m = F < 0
    d = radai_viewer3d.nuvem_de_mascara(
        m, radai_geom.Grade((passo, passo, passo)),
        cor=tuple(cor or (120, 170, 255)),
        max_pontos=int(max_pontos or radai_viewer3d.MAX_PONTOS))
    d[u"nome"] = nome
    return item_em_lps(d, origem, (1, 0, 0, 0, 1, 0, 0, 0, 1))


def nuvem_da_camada(volume, espacamento_zyx, origem_xyz, direcao, camada):
    import radai_geom
    import radai_viewer3d
    mascaras, esp_r = mascaras_3d(volume, espacamento_zyx,
                                  camadas=(camada,))
    m = mascaras.get(camada)
    if m is None or not m.any():
        return None
    d = radai_viewer3d.nuvem_de_mascara(
        m, radai_geom.Grade(esp_r), cor=CORES_3D.get(camada, (160, 170, 190)),
        max_pontos=PONTOS_3D.get(camada, 4000), normal="local")
    if not d[u"pontos"]:
        return None
    d[u"camada"] = camada
    desl = _deslocamento_do_bloco(espacamento_zyx, PASSO_3D_MM)[::-1]
    return item_em_lps(d, origem_xyz, direcao, desl)


def estado_da_serie(pasta):
    if not pasta or not os.path.isdir(pasta):
        return {"segmentada": False, "conjuntos": [],
                "o_que_fazer": u"escolha uma pasta de série"}
    achados = []
    try:
        import radai_sets
        for f in sorted(os.listdir(pasta)):
            if not (f.startswith("RS_RadAI_") and f.lower().endswith(".dcm")):
                continue
            c = radai_sets.do_arquivo(f)
            if c is None:
                achados.append({"arquivo": f, "conjunto": "",
                                "nome": u"conjunto desconhecido (%s)" % f})
                continue
            achados.append({"arquivo": f, "conjunto": c["cod"],
                            "nome": c.get("nome") or c["cod"],
                            "plugin": bool(c.get("plugin"))})
    except Exception:
        pass
    if not achados:
        return {
            "segmentada": False, "conjuntos": [],
            "o_que_fazer": u"esta série ainda não foi contornada. Reconstruir "
                           u"é daqui; segmentar é do Auto-Contorno.",
            "rota_para_segmentar": "/lote",
        }
    return {"segmentada": True, "conjuntos": achados,
            "o_que_fazer": u"%d conjunto(s) de contorno nesta pasta"
                           % len(achados)}


PASSOS_ROTULO_MM = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
TETO_VOXELS_ROTULO = 16000000


def malha_de_rotulo(mascara, espacamento_zyx, origem_xyz=(0.0, 0.0, 0.0),
                    direcao=(1, 0, 0, 0, 1, 0, 0, 0, 1),
                    teto_triangulos=None):
    import numpy as np
    import radai_bolus
    from scipy import ndimage
    m = np.asarray(mascara, dtype=bool)
    if m.ndim != 3 or not m.any():
        return (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64),
                {u"passo_mm": 0.0, u"triangulos": 0})
    teto = int(teto_triangulos or TETO_TRIANGULOS)
    idx = np.argwhere(m)
    lo = idx.min(axis=0) - 1
    hi = idx.max(axis=0) + 2
    esp = [float(e) if float(e) > 0 else 1.0 for e in espacamento_zyx]
    sub = np.pad(m, 1)[lo[0] + 1:hi[0] + 1, lo[1] + 1:hi[1] + 1,
                       lo[2] + 1:hi[2] + 1]
    desl = [float(a) * e for a, e in zip(lo, esp)]
    f = 1
    while sub.size / float(f * f) > TETO_VOXELS_ROTULO:
        f += 1
    if f > 1:
        # GUARDA: a distância sai em float64; o corte no plano segura a memória.
        sub = _reduzir_media(sub, (1, f, f)) >= 0.5
        desl = [desl[0], desl[1] + (f - 1) / 2.0 * esp[1],
                desl[2] + (f - 1) / 2.0 * esp[2]]
        esp = [esp[0], esp[1] * f, esp[2] * f]
    teto_mm = max(6.0, 2.0 * max(esp))
    amostra = (1.0e4, esp[1], esp[2])
    sdf = (ndimage.distance_transform_edt(~sub, sampling=amostra)
           - ndimage.distance_transform_edt(sub, sampling=amostra))
    sdf = np.clip(sdf, -teto_mm, teto_mm).astype(np.float32)
    escolhido = None
    for passo in PASSOS_ROTULO_MM:
        novo = [max(2, int(round((n - 1) * e / passo)) + 1)
                for n, e in zip(sdf.shape, esp)]
        if escolhido is not None and novo == escolhido[3]:
            continue
        if float(np.prod(novo)) > TETO_CELULAS_MALHA                 and passo != PASSOS_ROTULO_MM[-1]:
            continue
        fat = [nv / float(n) for nv, n in zip(novo, sdf.shape)]
        r = ndimage.zoom(sdf, fat, order=1, mode="nearest")
        esp_r = tuple(e * (n - 1) / float(nv - 1)
                      for e, n, nv in zip(esp, sdf.shape, novo))
        F = np.pad(_suavizar(r, esp_r), 1, mode="constant",
                   constant_values=np.float32(teto_mm))
        escolhido = (F, esp_r, passo, novo)
        if _triangulos_estimados(F) <= teto * 1.15:
            break
    F, esp_r, passo, _novo = escolhido
    verts, faces = radai_bolus.superficie(F)
    lps, faces = _mascara_em_lps(verts, faces, esp_r, origem_xyz, direcao,
                                 tuple(desl))
    return lps, faces, {u"passo_mm": float(passo),
                        u"triangulos": int(len(faces))}


_PALAVRAS_DE_VASO = (u"aort", u"arter", u"vein", u"vena", u"venous",
                     u"vessel", u"carotid", u"jugular", u"subclavian",
                     u"brachiocephalic", u"brachioceph", u"iliac", u"portal",
                     u"cava", u"venacava", u"vasc", u"pulmonary_v",
                     u"pulmonary_a")


def e_vaso(nome):
    try:
        import radai_sets
        raiz = radai_sets.raiz_sem_sufixo(nome)
    except Exception:
        raiz = str(nome or u"")
    raiz = str(raiz or u"").lower()
    if raiz.startswith(u"a_") or raiz.startswith(u"v_"):
        return True
    return any(p in raiz for p in _PALAVRAS_DE_VASO)
