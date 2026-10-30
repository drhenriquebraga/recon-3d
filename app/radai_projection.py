# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
import math

SEM_VOLUME = (
    u"A interseção é uma construção geométrica a partir do desenho do "
    u"usuário — não é um volume de tratamento, e este módulo não calcula "
    u"nem exibe o volume dela em cm³."
)

LIMITACAO_CLINICA = (
    u"Reconstrução por projeção a partir de angiotomografia. Não substitui "
    u"angiografia digital e não mostra dinâmica de fluxo — na angioTC a veia "
    u"de drenagem e a artéria nutridora têm o mesmo brilho, e é por isso que "
    u"a definição de nidus por uma difere da definição pela outra."
)

LIMITACAO_RM = (
    u"Na RM com gadolínio vale o mesmo: a imagem é estática e artéria e veia "
    u"realçam as duas. E o sinal da RM não é HU — as janelas são relativas "
    u"ao sinal da própria série, e o brilho de uma série não se compara com "
    u"o de outra."
)

INCIDENCIAS = (
    (u"AP", 0.0, 0.0),
    (u"Perfil D", -90.0, 0.0),
    (u"Perfil E", 90.0, 0.0),
    (u"Oblíqua ant. D", -45.0, 0.0),
    (u"Oblíqua ant. E", 45.0, 0.0),
    (u"Towne", 0.0, 30.0),
    (u"Caldwell", 0.0, -15.0),
    (u"Submento-vértex", 0.0, 90.0),
)


def matriz_da_incidencia(lao_rao=0.0, cra_cau=0.0):
    a, b = math.radians(float(lao_rao)), math.radians(float(cra_cau))
    ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
    # GUARDA: linhas r, v, u (direita da tela, direção do olhar, alto da tela) do arco em C (DICOM): LAO põe o detector à esquerda, CRA o inclina para a cabeça.
    return ((ca, sa, 0.0),
            (-sa * cb, ca * cb, -sb),
            (-sa * sb, ca * sb, cb))


def rotulo_do_angulo(lao_rao=0.0, cra_cau=0.0):
    a, b = int(round(float(lao_rao))), int(round(float(cra_cau)))
    partes = []
    if a:
        partes.append((u"LAO %d" if a > 0 else u"RAO %d") % abs(a))
    if b:
        partes.append((u"CRA %d" if b > 0 else u"CAU %d") % abs(b))
    return u" / ".join(partes) or u"0 / 0"


JS_CONVENCAO = u"""
function radaiIncidencia(lao, cra){
 var a=(+lao||0)*Math.PI/180, b=(+cra||0)*Math.PI/180;
 var ca=Math.cos(a), sa=Math.sin(a), cb=Math.cos(b), sb=Math.sin(b);
 return {r:[ca, sa, 0], v:[-sa*cb, ca*cb, -sb], u:[-sa*sb, ca*sb, cb],
         d:[sa*cb, -ca*cb, sb]};
}
"""

JANELAS = {
    "angio": (300.0, 700.0),
    "vaso_fino": (200.0, 400.0),
    "osso": (400.0, 1800.0),
    "parenquima": (40.0, 80.0),
}

JANELAS_RELATIVAS = {
    "angio": (90.0, 99.9),
    "vaso_fino": (99.0, 99.95),
    "parenquima": (1.0, 99.0),
    "ampla": (0.0, 99.99),
}
_PERCENTIS = tuple(sorted(set(p for par in JANELAS_RELATIVAS.values()
                              for p in par)))


def estatistica(img):
    import numpy as np
    import SimpleITK as sitk
    a = sitk.GetArrayViewFromImage(img)[::2, ::3, ::3]
    v = np.percentile(np.asarray(a, dtype=np.float32), _PERCENTIS)
    return dict(zip(_PERCENTIS, (float(x) for x in v)))


def tem_hu(modalidade=None, minimo=None):
    if modalidade:
        return str(modalidade).strip().upper() == "CT"
    return minimo is None or float(minimo) < -500.0


def escala_de(img, modalidade=None):
    import SimpleITK as sitk
    f = sitk.MinimumMaximumImageFilter()
    f.Execute(img)
    lo, hi = float(f.GetMinimum()), float(f.GetMaximum())
    e = {"hu": tem_hu(modalidade, lo), "min": lo, "max": hi}
    if not e["hu"]:
        e["percentis"] = estatistica(img)
    return e


def janela_de(nome, escala=None):
    if not escala or escala.get("hu", True) or not escala.get("percentis"):
        return JANELAS.get(nome, JANELAS["angio"])
    p = escala["percentis"]
    par = JANELAS_RELATIVAS.get(
        "ampla" if nome == "osso" else nome, JANELAS_RELATIVAS["angio"])
    lo, hi = float(p[par[0]]), float(p[par[1]])
    if hi <= lo:
        hi = lo + 1.0
    return ((lo + hi) / 2.0, hi - lo)

LADO_PADRAO = 512

LADO_ALTA = 1024

FUNDO_MAXIMO = 384


class SerieRecusada(ValueError):
    pass


RECUSA_COR = (
    u"A série é uma imagem colorida (%d componentes por pixel) — captura de "
    u"tela ou reconstrução exportada —, e não os cortes da angioTC ou da RM: "
    u"escolha a série de cortes.")

RECUSA_DIMENSAO = (
    u"O volume desta série não é 3D (dimensão %d): ela não é uma pilha de "
    u"cortes, e não dá projeção. Escolha a série de cortes.")

RECUSA_POUCOS_CORTES = (
    u"A série tem %d corte(s): não há volume para projetar.")


def conferir_serie(img):
    import SimpleITK as sitk
    comp = int(img.GetNumberOfComponentsPerPixel())
    if comp != 1:
        raise SerieRecusada(RECUSA_COR % comp)
    if u"vector" in str(img.GetPixelIDTypeAsString()).lower():
        img = sitk.VectorIndexSelectionCast(img, 0)
    dim = int(img.GetDimension())
    if dim != 3:
        raise SerieRecusada(RECUSA_DIMENSAO % dim)
    if min(int(s) for s in img.GetSize()) < 2:
        raise SerieRecusada(RECUSA_POUCOS_CORTES % min(img.GetSize()))
    return img

def lado_para_o_exame(img, teto=LADO_ALTA):
    import math as _m
    try:
        ext = [s * e for s, e in zip(img.GetSize(), img.GetSpacing())]
        diag = _m.sqrt(sum(x * x for x in ext))
        fino = min(float(e) for e in img.GetSpacing())
        ideal = int(round(diag / max(fino, 1e-6)))
        for cand in (256, 512, 768, LADO_ALTA):
            if cand >= ideal:
                return cand
        return teto
    except Exception:
        return LADO_PADRAO


def centro_da_grade(img):
    return tuple(float(x) for x in img.TransformContinuousIndexToPhysicalPoint(
        [(s - 1) / 2.0 for s in img.GetSize()]))


def _transformada(img, lao_rao, cra_cau):
    import SimpleITK as sitk
    t = sitk.AffineTransform(3)
    t.SetMatrix([x for linha in matriz_da_incidencia(lao_rao, cra_cau)
                 for x in linha])
    t.SetCenter(centro_da_grade(img))
    return t


def eixos_da_incidencia(lao_rao=0.0, cra_cau=0.0):
    r, v, u = matriz_da_incidencia(lao_rao, cra_cau)
    fora = {}
    for nome, k in ((u"L", 0), (u"P", 1), (u"S", 2)):
        # GUARDA: mesma matriz de `projetar`; coluna = r, linha = -u (crânio em cima), profundidade = v.
        fora[nome] = (round(r[k], 4), round(-u[k], 4), round(v[k], 4))
    return fora


def caixa_de_texto(texto):
    try:
        v = [min(1.0, max(0.0, float(x))) for x in str(texto or u"").split(u",")]
    except (TypeError, ValueError):
        return None
    if len(v) != 6:
        return None
    pares = [tuple(sorted(v[i:i + 2])) for i in (0, 2, 4)]
    if any(b - a <= 0.0 for a, b in pares):
        return None
    if all(a <= 0.0 and b >= 1.0 for a, b in pares):
        return None
    return tuple(round(x, 4) for par in pares for x in par)


def _medidas_da_grade(img, lado, fundo=None):
    extensao = [s * e for s, e in zip(img.GetSize(), img.GetSpacing())]
    diag = math.sqrt(sum(x * x for x in extensao))
    passo = diag / float(lado)
    fundo = int(fundo or min(lado, FUNDO_MAXIMO))
    passo_fundo = diag / float(fundo)
    return diag, passo, passo_fundo, fundo


def _grade(img, lado, fundo=None):
    import SimpleITK as sitk
    diag, passo, passo_fundo, fundo = _medidas_da_grade(img, lado, fundo)
    ref = sitk.Image([lado, fundo, lado], sitk.sitkFloat32)
    ref.SetSpacing((passo, passo_fundo, passo))
    return ref, diag, passo, passo_fundo


def projetar(img, lao_rao=0.0, cra_cau=0.0, modo="mip", janela="angio",
             lado=LADO_PADRAO, laje_mm=None, fundo=None, escala=None,
             amostra=None):
    import numpy as np
    import SimpleITK as sitk

    if escala is None:
        escala = escala_de(img)
    t = _transformada(img, lao_rao, cra_cau)
    ref, diag, passo, passo_fundo = _grade(img, lado, fundo)
    c = t.GetCenter()
    ref.SetOrigin((c[0] - diag / 2.0, c[1] - diag / 2.0, c[2] - diag / 2.0))
    fora = float(escala["min"] if modo == "mip" else escala["max"])
    r = sitk.Resample(img if amostra is None else amostra, ref, t.GetInverse(),
                      sitk.sitkLinear, fora)
    a = sitk.GetArrayViewFromImage(r)

    if laje_mm:
        espessura = max(1, int(round(float(laje_mm) / passo_fundo)))
        meio = a.shape[1] // 2
        i0 = max(0, meio - espessura // 2)
        a = a[:, i0:i0 + espessura, :]
    plano = a.max(axis=1) if modo == "mip" else a.min(axis=1)
    plano = np.ascontiguousarray(plano[::-1])

    centro, largura = janela_de(janela, escala)
    return plano, {"lao_rao": lao_rao, "cra_cau": cra_cau, "modo": modo,
                   "janela": janela, "centro": centro, "largura": largura,
                   "passo_mm": passo, "lado": lado,
                   "passo_fundo_mm": passo_fundo,
                   "fundo": int(ref.GetSize()[1]),
                   "hu": bool(escala.get("hu", True))}


def tubo(img, poligono, lao_rao=0.0, cra_cau=0.0, lado=LADO_PADRAO,
         fundo=None):
    import numpy as np
    import SimpleITK as sitk

    t = _transformada(img, lao_rao, cra_cau)
    diag, passo, _pf, _f = _medidas_da_grade(img, lado)
    c = t.GetCenter()

    plano = _mascara_poligono(poligono, lado)[::-1]
    extrudado = np.ascontiguousarray(np.broadcast_to(
        plano.astype(np.uint8)[:, None, :], (lado, 2, lado)))
    m = sitk.GetImageFromArray(extrudado)
    m.SetSpacing((passo, diag, passo))
    m.SetOrigin((c[0] - diag / 2.0, c[1] - diag / 2.0, c[2] - diag / 2.0))

    voltou = sitk.Resample(m, img, t, sitk.sitkNearestNeighbor, 0)
    return sitk.GetArrayFromImage(voltou).view(np.bool_)


def _mascara_poligono(poligono, lado, largura=None):
    import numpy as np
    alt, larg = int(lado), int(lado if largura is None else largura)
    m = np.zeros((alt, larg), dtype=bool)
    pts = [(float(x), float(y)) for x, y in (poligono or ())]
    if len(pts) < 3:
        return m
    xs_p = [p[0] for p in pts]
    ys_p = [p[1] for p in pts]
    c0 = max(0, int(math.floor(min(xs_p) - 0.5)))
    c1 = min(larg, int(math.ceil(max(xs_p) - 0.5)) + 1)
    l0 = max(0, int(math.floor(min(ys_p) - 0.5)))
    l1 = min(alt, int(math.ceil(max(ys_p) - 0.5)) + 1)
    if c1 <= c0 or l1 <= l0:
        return m
    p = np.asarray(pts, dtype=np.float64)
    ax, ay = p[:, 0], p[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    ok = ay != by
    ax, ay, bx, by = ax[ok], ay[ok], bx[ok], by[ok]
    xs = np.arange(c0, c1, dtype=np.float64) + 0.5
    yc = np.arange(l0, l1, dtype=np.float64)[:, None] + 0.5
    cruza = (ay[None, :] > yc) != (by[None, :] > yc)
    linha, aresta = np.nonzero(cruza)
    if not linha.size:
        return m
    yy = yc[linha, 0]
    # GUARDA: mesma conta de antes; o pixel conta a aresta que cruza à direita do centro dele.
    xint = ((bx[aresta] - ax[aresta]) * (yy - ay[aresta])
            / (by[aresta] - ay[aresta]) + ax[aresta])
    k = np.searchsorted(xs, xint, side="left")
    h = np.zeros((l1 - l0, c1 - c0 + 1), dtype=np.int32)
    np.add.at(h, (linha, k), 1)
    direita = h[:, ::-1].cumsum(axis=1)[:, ::-1][:, 1:]
    m[l0:l1, c0:c1] = (direita % 2) == 1
    return m


OSSO_DILATACAO_VOXELS = 1


def dilatar(m, voltas=1):
    import numpy as np
    m = np.asarray(m, dtype=bool)
    for _ in range(int(voltas)):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        d[:, :, 1:] |= m[:, :, :-1]
        d[:, :, :-1] |= m[:, :, 1:]
        m = d
    return m


def mascara_dos_cortes(cortes, forma, destino=None):
    import numpy as np
    forma = tuple(int(s) for s in forma)
    m = np.zeros(forma, dtype=bool) if destino is None else destino
    for z, polis in (cortes or {}).items():
        z = int(z)
        if not 0 <= z < forma[0]:
            continue
        plano = np.zeros(forma[1:], dtype=bool)
        for p in polis or ():
            # GUARDA: paridade entre os contornos do corte; o furo (por XOR ou por fenda) fica furo.
            plano ^= _mascara_poligono([(float(x), float(y)) for x, y in p],
                                       forma[1], forma[2])
        m[z] |= plano
    return m


def sem_osso(img, osso, valor):
    import numpy as np
    import SimpleITK as sitk
    a = sitk.GetArrayFromImage(img)
    m = dilatar(osso, OSSO_DILATACAO_VOXELS)
    if m.shape != a.shape:
        raise ValueError(u"a máscara do osso não tem a forma desta série")
    a[m] = np.asarray(valor).astype(a.dtype)
    out = sitk.GetImageFromArray(a)
    out.CopyInformation(img)
    return out


def eixos_lps(img):
    import itertools as _it
    d = [float(x) for x in img.GetDirection()]
    col = [(d[0 + n], d[3 + n], d[6 + n]) for n in range(3)]
    melhor, alvo = None, -1.0
    for p in _it.permutations(range(3)):
        s = sum(abs(col[p[f]][f]) for f in range(3))
        if s > alvo:
            melhor, alvo = p, s
    esp = img.GetSpacing()
    perm, inverter, mm = [], [], []
    for a in range(3):
        f = 2 - a
        n = melhor[f]
        perm.append(2 - n)
        inverter.append(col[n][f] < 0)
        mm.append(float(esp[n]))
    return tuple(perm), tuple(inverter), tuple(mm)


def para_lps(a, eixos):
    import numpy as np
    perm, inverter = eixos[0], eixos[1]
    if np.ndim(a) != len(perm):
        raise SerieRecusada(RECUSA_DIMENSAO % np.ndim(a))
    v = np.transpose(a, perm)
    fatia = tuple(slice(None, None, -1) if inv else slice(None)
                  for inv in inverter)
    return v[fatia]


def corte(v, eixo, indice):
    if isinstance(v, Compacto):
        f = v.fatia(eixo, indice)
        return f if eixo == 0 else f[::-1]
    if eixo == 0:
        return v[indice, :, :]
    if eixo == 1:
        return v[::-1, indice, :]
    return v[::-1, :, indice]


def mm_do_corte(mm_zyx, eixo):
    z, y, x = (float(e) for e in mm_zyx)
    return {0: (y, x), 1: (z, x), 2: (z, y)}[int(eixo)]


from radai_recon3d import (TETO_DA_TELA, grade_da_tela,
                           para_a_tela)


def escalar(segmentos, fator_lin, fator_col):
    return [((round(c0 * fator_col, 2), round(l0 * fator_lin, 2)),
             (round(c1 * fator_col, 2), round(l1 * fator_lin, 2)))
            for (c0, l0), (c1, l1) in segmentos]


class Compacto(object):

    __slots__ = ("bits", "shape")

    def __init__(self, bits, shape):
        self.bits = bits
        self.shape = tuple(int(s) for s in shape)

    def fatia(self, eixo, indice):
        import numpy as np
        nx = self.shape[2]
        if eixo == 0:
            return np.unpackbits(self.bits[indice], axis=-1,
                                 count=nx).astype(bool)
        if eixo == 1:
            return np.unpackbits(self.bits[:, indice, :], axis=-1,
                                 count=nx).astype(bool)
        byte, bit = divmod(int(indice), 8)
        return ((self.bits[:, :, byte] >> (7 - bit)) & 1).astype(bool)

    def any(self):
        return bool(self.bits.any())


def compactar(m):
    import numpy as np
    a = np.ascontiguousarray(np.asarray(m, dtype=bool))
    return Compacto(np.packbits(a, axis=-1), a.shape)


def intersecao(*tubos):
    import numpy as np
    if len(tubos) == 1 and isinstance(tubos[0], (list, tuple)):
        tubos = tuple(tubos[0])
    tubos = [t for t in tubos if t is not None]
    if not tubos:
        return None
    if all(isinstance(t, Compacto) for t in tubos):
        b = tubos[0].bits.copy()
        for t in tubos[1:]:
            np.bitwise_and(b, t.bits, out=b)
        return Compacto(b, tubos[0].shape)
    r = np.asarray(tubos[0], dtype=bool)
    for t in tubos[1:]:
        r = np.logical_and(r, np.asarray(t, dtype=bool))
    return r


def contorno_do_tubo(mascara, eixo, indice):
    import numpy as np
    plano = np.asarray(corte(mascara, eixo, indice), dtype=bool)
    if not plano.any():
        return []
    segs = []
    alt, larg = plano.shape
    for l in range(alt):
        linha = plano[l]
        muda = np.flatnonzero(np.diff(linha.astype(np.int8)))
        for c in muda:
            segs.append(((int(c) + 1, l), (int(c) + 1, l + 1)))
    for c in range(larg):
        col = plano[:, c]
        muda = np.flatnonzero(np.diff(col.astype(np.int8)))
        for l in muda:
            segs.append(((c, int(l) + 1), (c + 1, int(l) + 1)))
    return segs


class Serie(object):

    def __init__(self, img, modalidade=None):
        import SimpleITK as sitk
        img = conferir_serie(img)
        self.img = img
        self.modalidade = str(modalidade or u"")
        self.eixos = eixos_lps(img)
        self.v = para_lps(sitk.GetArrayViewFromImage(img), self.eixos)
        self.mm = self.eixos[2]
        self.escala = escala_de(img, modalidade)
        self.lado_util = lado_para_o_exame(img)
        self._recorte = (None, None)
        self.osso = None
        self._sem_osso = None

    @property
    def forma_do_array(self):
        return tuple(int(s) for s in reversed(self.img.GetSize()))

    def tirar_osso(self, mascara, info=None):
        import numpy as np
        m = np.asarray(mascara, dtype=bool)
        if m.shape != self.forma_do_array:
            raise ValueError(u"a máscara do osso não tem a forma desta série")
        self._recorte = (None, None)
        if not m.any():
            self.osso, self._sem_osso, self._osso_bits = None, None, None
            return False
        self._sem_osso = sem_osso(self.img, m, self.escala["min"])
        self._osso_bits = np.packbits(m, axis=-1)
        self.osso = dict(info or {}, voxels=int(m.sum()))
        return True

    def mascara_do_osso_em(self, ini, ext):
        import numpy as np
        bits = getattr(self, "_osso_bits", None)
        if bits is None:
            return None
        x0, y0, z0 = (int(v) for v in ini)
        nx, ny, nz = (int(v) for v in ext)
        b = bits[z0:z0 + nz, y0:y0 + ny]
        m = np.unpackbits(b, axis=-1, count=self.forma_do_array[2])
        return m[:, :, x0:x0 + nx].astype(bool)

    def indices_da_caixa(self, caixa, margem_mm=0.0):
        perm, inverter = self.eixos[0], self.eixos[1]
        tam = list(self.img.GetSize())
        esp = self.img.GetSpacing()
        ini, ext = [0, 0, 0], list(tam)
        for eixo in range(3):
            # GUARDA: eixo da vista -> eixo do array (`perm`) -> dimensão do sitk (2 - eixo do array).
            dim = 2 - perm[eixo]
            n = tam[dim]
            i0 = max(0, int(math.floor(caixa[2 * eixo] * n)))
            i1 = min(n, int(math.ceil(caixa[2 * eixo + 1] * n)))
            if inverter[eixo]:
                i0, i1 = n - i1, n - i0
            if margem_mm:
                folga = int(math.ceil(float(margem_mm) / max(float(esp[dim]), 1e-6)))
                i0, i1 = max(0, i0 - folga), min(n, i1 + folga)
            ini[dim], ext[dim] = i0, max(1, i1 - i0)
        return ini, ext

    def base(self, modo="mip", osso=False):
        # GUARDA: o osso só sai no MIP; no MinIP o valor que o apaga viraria buraco escuro.
        if osso and modo == "mip" and self._sem_osso is not None:
            return self._sem_osso
        return self.img

    def img_na_caixa(self, caixa, modo="mip", osso=False):
        import SimpleITK as sitk
        base = self.base(modo, osso)
        if caixa is None:
            return base
        chave = (tuple(caixa), base is not self.img)
        if self._recorte[0] == chave:
            return self._recorte[1]
        self._recorte = (None, None)
        ini, ext = self.indices_da_caixa(caixa)
        out = sitk.RegionOfInterest(base, ext, ini)
        self._recorte = (chave, out)
        return out

    @property
    def forma(self):
        return tuple(int(s) for s in self.v.shape)

    def passos(self, lados):
        return {str(l): round(float(_medidas_da_grade(self.img, l)[1]), 3)
                for l in lados}

    def tubo(self, poligono, lao_rao, cra_cau, lado):
        return compactar(para_lps(
            tubo(self.img, poligono, lao_rao, cra_cau, lado=lado),
            self.eixos))


def abrir(img, modalidade=None):
    return Serie(img, modalidade)


def matriz_para_caixa(img, eixos):
    import numpy as np
    perm, inverter = eixos[0], eixos[1]
    D = np.asarray(img.GetDirection(), dtype=np.float64).reshape(3, 3)
    O = np.asarray(img.GetOrigin(), dtype=np.float64)
    esp, tam = img.GetSpacing(), img.GetSize()
    A = np.eye(4)
    for eixo in range(3):
        n = 2 - perm[eixo]
        # GUARDA: fração do centro do voxel, (i + 0,5) / N, a mesma conta de `indices_da_caixa`.
        lin = D[:, n] / (float(esp[n]) * float(tam[n]))
        b = -lin.dot(O) + 0.5 / float(tam[n])
        if inverter[eixo]:
            lin, b = -lin, 1.0 - b
        A[eixo, :3], A[eixo, 3] = lin, b
    return A


def geometria_da_serie(serie):
    import numpy as np
    A = matriz_para_caixa(serie.img, serie.eixos)
    diag = _medidas_da_grade(serie.img, LADO_ALTA)[0]
    return {"para_caixa": [round(float(x), 12) for x in A.ravel()],
            "da_caixa": [round(float(x), 12) for x in np.linalg.inv(A).ravel()],
            "centro": [round(float(x), 6) for x in centro_da_grade(serie.img)],
            "diag": round(float(diag), 6)}


def pegada_da_caixa(serie, caixa, lao_rao, cra_cau, lado):
    import numpy as np
    g = geometria_da_serie(serie)
    Q = np.asarray(g["da_caixa"], dtype=np.float64).reshape(4, 4)
    c = np.asarray(g["centro"], dtype=np.float64)
    r, _v, u = (np.asarray(x) for x in matriz_da_incidencia(lao_rao, cra_cau))
    passo = float(g["diag"]) / float(lado)
    fora = []
    for i in range(8):
        f = (caixa[1 if i & 1 else 0], caixa[3 if i & 2 else 2],
             caixa[5 if i & 4 else 4], 1.0)
        p = Q.dot(f)[:3] - c
        fora.append((float((p.dot(r) + g["diag"] / 2.0) / passo + 0.5),
                     float(lado - 0.5 - (p.dot(u) + g["diag"] / 2.0) / passo)))
    return fora


TETOS_DA_MALHA = ((u"vaso", 50000), (u"osso", 20000), (u"pele", 10000))

QUAIS_DA_MALHA = tuple(q for q, _t in TETOS_DA_MALHA)

PASSOS_DO_VASO_MM = (0.5, 0.75, 1.0)

MARGEM_DA_MALHA_MM = 4.0

LIMIAR_VASO_HU = 180.0

SEM_CAIXA_PARA_O_3D = (
    u"ligue a caixa de recorte e aperte-a em volta do ninho para ver o 3D do "
    u"que fica dentro dela")

OSSO_NAO_SEPARADO = (
    u"osso não separado: sem a segmentação, o vaso por limiar leva o osso junto")

VASO_DEMAIS = (
    u"vaso demais nesta caixa para o 3D sem perder o ramo fino: aperte a caixa "
    u"em volta do ninho")

RM_SEM_PELE = u"na RM não há pele no 3D: o sinal não é HU"


class MalhaRecusada(ValueError):
    pass


def limiar_do_vaso(escala):
    if not escala or escala.get("hu", True) or not escala.get("percentis"):
        return LIMIAR_VASO_HU
    return janela_de("angio", escala)[0]


def malha_da_caixa(serie, caixa, qual):
    import numpy as np
    import SimpleITK as sitk
    import radai_recon3d as R
    tetos = dict(TETOS_DA_MALHA)
    if qual not in tetos:
        raise KeyError(qual)
    if caixa is None:
        raise MalhaRecusada(SEM_CAIXA_PARA_O_3D)
    ini, ext = serie.indices_da_caixa(caixa, MARGEM_DA_MALHA_MM)
    x0, y0, z0 = ini
    nx, ny, nz = ext
    a = sitk.GetArrayViewFromImage(serie.img)[z0:z0 + nz, y0:y0 + ny,
                                              x0:x0 + nx]
    osso = serie.mascara_do_osso_em(ini, ext)
    info = {u"qual": qual, u"motivo": u"", u"passo_mm": 0.0, u"triangulos": 0}
    opcoes = {}
    m = None
    if qual == u"vaso":
        m = np.asarray(a) >= limiar_do_vaso(serie.escala)
        if osso is None:
            info[u"motivo"] = OSSO_NAO_SEPARADO
        else:
            m &= ~dilatar(osso, OSSO_DILATACAO_VOXELS)
        # GUARDA: o ramo fino some com passo acima de 1 mm ou com suavização; acima do teto, recusa em vez de engrossar.
        opcoes = {"passos_mm": PASSOS_DO_VASO_MM, "suavizar_mm": 0.0,
                  "recusar_acima": True}
    elif qual == u"osso":
        if osso is None:
            info[u"motivo"] = OSSO_NAO_SEPARADO
        else:
            m = osso
    elif serie.escala.get("hu", True):
        m = np.asarray(a) > R.LIMIAR_PELE_HU
    else:
        info[u"motivo"] = RM_SEM_PELE
    vazio = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    if m is None or not m.any():
        return vazio[0], vazio[1], info
    origem = serie.img.TransformIndexToPhysicalPoint([int(v) for v in ini])
    esp_zyx = tuple(float(e) for e in reversed(serie.img.GetSpacing()))
    lps, faces, i2 = R.malha_de_rotulo(m, esp_zyx, origem,
                                       serie.img.GetDirection(),
                                       teto_triangulos=tetos[qual], **opcoes)
    if i2.get(u"excedeu"):
        raise MalhaRecusada(VASO_DEMAIS)
    info.update(i2)
    return lps, faces, info
