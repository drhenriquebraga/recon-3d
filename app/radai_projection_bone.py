# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
import os

SEM_SEGMENTACAO = (
    u"esta série ainda não tem segmentação do ContourLab: o osso continua "
    u"na projeção")

SEM_UID = (
    u"sem o UID da série não dá para achar a segmentação dela: o osso "
    u"continua na projeção")

SEM_OSSO_NA_ENTREGA = (
    u"a entrega desta série não tem osso que sirva para a projeção: o osso "
    u"continua na projeção")

ORDEM_DO_OSSO = (((u"full", u"oar"), True), ((u"fast",), False))

_PALAVRAS_DE_VASO = (u"arter", u"vein", u"vena", u"vessel", u"carotid",
                     u"aorta", u"jugular", u"sinus")


def e_osso(nome):
    import engine
    n = str(nome or u"").lower()
    # GUARDA: vaso nunca sai da projeção, ainda que o nome traga palavra de osso (A_Vertebral).
    if n.startswith((u"a_", u"v_")) or any(p in n for p in _PALAVRAS_DE_VASO):
        return False
    return engine.familia_de(n) == "osso"


def _pastas_da_serie(pasta, uid):
    fora, vistos = [], set()

    def por(p):
        if not p:
            return
        k = os.path.normcase(os.path.abspath(p))
        if k in vistos or not os.path.isdir(p):
            return
        vistos.add(k)
        fora.append(p)
    por(pasta)
    if uid:
        try:
            import radai_archive
            for reg in radai_archive.ler_acervo():
                if str(reg.get("uid") or u"") == str(uid):
                    por(radai_archive.resolver_pasta(reg.get("pasta") or u""))
        except Exception:
            pass
    return fora


def _entrega_da_serie(pastas, uid):
    try:
        import radai_sets
        import radai_viewseg as V
    except Exception:
        return u""
    for p in pastas:
        try:
            nomes = os.listdir(p)
        except Exception:
            continue
        for n in sorted(radai_sets.arquivos_da_serie(nomes, uid)):
            r = V.rotulo_do_arquivo(n)
            if r.get("entregue"):
                return str(r.get("curto") or u"")
    return u""


def osso_da_segmentacao(serie, pasta, uid):
    import radai_viewseg as V
    uid = str(uid or u"")
    if not uid:
        return None, {"tem": False, "motivo": SEM_UID}
    forma = tuple(serie.forma_do_array)
    pastas = _pastas_da_serie(pasta, uid)
    for p in pastas:
        # GUARDA: FULL e OAR têm o osso exato; o OAR_Fast (contorno reduzido) só entra sem eles e sem o mapa.
        for conjuntos, com_mapa in ORDEM_DO_OSSO:
            m, info = V.mascaras_da_serie(p, uid, serie.img, aceita=e_osso,
                                          conjuntos=conjuntos,
                                          com_mapa=com_mapa)
            if m is None or tuple(m.shape) != forma:
                continue
            return m, {"tem": True, "fonte": info.get("fonte") or u"",
                       "estruturas": int(info.get("estruturas") or 0)}
    entrega = _entrega_da_serie(pastas, uid)
    if entrega:
        return None, {"tem": False, "motivo": SEM_OSSO_NA_ENTREGA,
                      "entrega": entrega}
    return None, {"tem": False, "motivo": SEM_SEGMENTACAO}
