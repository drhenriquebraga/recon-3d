# -*- coding: utf-8 -*-
import os
import threading

import radai_menu
import radai_recon3d_gl
import radai_web


SOLTAR_APOS_S = 10 * 60
_VOL = {"chave": None, "v": None, "esp": None, "sentido": None,
        "origem": None, "direcao": None, "visto": 0.0, "relogio": None}
_TRAVA_VOL = threading.Lock()

TETO_CACHE_MALHAS_MB = 96
_CONJ = {"chave": None, "c": None}
_MALHAS = {}
_ORDEM_MALHAS = []
_TRAVA_MALHA = threading.Lock()


def _esquecer_malhas(fora_da_serie=None):
    if fora_da_serie is None or (_CONJ["chave"] is not None
                                 and _CONJ["chave"][:2] != fora_da_serie):
        _CONJ.update({"chave": None, "c": None})
    for k in list(_ORDEM_MALHAS):
        if fora_da_serie is None or k[:2] != fora_da_serie:
            _ORDEM_MALHAS.remove(k)
            _MALHAS.pop(k, None)


def _guardar_malha(chave, dados):
    _MALHAS[chave] = dados
    if chave in _ORDEM_MALHAS:
        _ORDEM_MALHAS.remove(chave)
    _ORDEM_MALHAS.append(chave)
    teto = TETO_CACHE_MALHAS_MB * 1024 * 1024
    while (len(_ORDEM_MALHAS) > 1
           and sum(len(_MALHAS[k]) for k in _ORDEM_MALHAS) > teto):
        velha = _ORDEM_MALHAS.pop(0)
        _MALHAS.pop(velha, None)


def _esquecer_serie():
    _VOL.update({"chave": None, "v": None, "esp": None, "sentido": None,
                 "origem": None, "direcao": None})


def _armar_relogio(segundos):
    if _VOL.get("relogio") is not None:
        return
    t = threading.Timer(max(1.0, float(segundos)), _soltar_se_parada)
    t.daemon = True
    _VOL["relogio"] = t
    t.start()


def _soltar_se_parada(agora=None, rearmar=True):
    import time
    agora = time.time() if agora is None else float(agora)
    soltar_malhas = False
    with _TRAVA_VOL:
        _VOL["relogio"] = None
        if _VOL["v"] is None and _CONJ["c"] is None and not _MALHAS:
            return None
        parada = agora - float(_VOL.get("visto") or 0.0)
        if parada >= SOLTAR_APOS_S:
            _esquecer_serie()
            soltar_malhas = True
            falta = None
        else:
            falta = SOLTAR_APOS_S - parada
            if rearmar:
                _armar_relogio(falta)
    if soltar_malhas:
        with _TRAVA_MALHA:
            _esquecer_malhas()
    return falta


def _marcar_visto():
    import time
    with _TRAVA_VOL:
        _VOL["visto"] = time.time()
        _armar_relogio(SOLTAR_APOS_S)


def _snapshot_do_volume(pasta, uid):
    import time
    chave = (str(pasta), str(uid or ""))
    with _TRAVA_VOL:
        if _VOL["chave"] == chave and _VOL["v"] is not None:
            _VOL["visto"] = time.time()
            return (_VOL["v"], _VOL["esp"], _VOL["sentido"],
                    _VOL.get("origem") or (0.0, 0.0, 0.0),
                    _VOL.get("direcao") or (1, 0, 0, 0, 1, 0, 0, 0, 1))
        _esquecer_serie()
        import engine
        import SimpleITK as sitk
        img = engine.load_sitk(pasta, uid)
        v = sitk.GetArrayFromImage(img)
        esp = tuple(float(e) for e in reversed(img.GetSpacing()))
        try:
            import radai_geom
            sentido = tuple(radai_geom.Grade.de_sitk(img).sentido)
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(
                u"reconstrucoes 3D, orientacao", e,
                bilhete=u"%s\x00%s" % (pasta, uid or u""))
            sentido = None
        origem = tuple(float(o) for o in img.GetOrigin())
        direcao = tuple(float(d) for d in img.GetDirection())
        _VOL.update({"chave": chave, "v": v, "esp": esp, "sentido": sentido,
                     "origem": origem, "direcao": direcao,
                     "visto": time.time()})
        _armar_relogio(SOLTAR_APOS_S)
        return v, esp, sentido, origem, direcao


def _volume(pasta, uid):
    return _snapshot_do_volume(pasta, uid)[:3]


def sentido_cranial(sentido):
    primeiro = (tuple(sentido or ()) + (None,))[0]
    return 1 if primeiro == "sup" else (-1 if primeiro == "inf" else 0)


def _volume_lps(pasta, uid):
    v, esp, _s, origem, direcao = _snapshot_do_volume(pasta, uid)
    return v, esp, origem, direcao



MARCAR_TODAS_ATE = 45
MAX_NUVEM_POR_PEDIDO = 24


class SemSerie(Exception):
    pass


def arquivos_da_serie(pasta, uid=u""):
    import radai_recon3d as R
    e = R.estado_da_serie(pasta)
    arqs = [c for c in (e.get("conjuntos") or []) if c.get("arquivo")]
    if uid:
        import radai_sets
        meus = set(radai_sets.arquivos_da_serie([c["arquivo"] for c in arqs],
                                                uid))
        arqs = [c for c in arqs if c["arquivo"] in meus]
    ordem = {"oar": 0, "fast": 1, "full": 2}

    def _peso(c):
        if c.get("conjunto") in ordem:
            return ordem[c.get("conjunto")]
        return 4 if (c.get("plugin") or not c.get("conjunto")) else 3
    arqs.sort(key=lambda c: (_peso(c), c["arquivo"]))
    if uid:
        mapa = _rotulos_meta(pasta, uid)
        if mapa is not None:
            arqs.append({"arquivo": ARQUIVO_ROTULOS, "conjunto": "rotulos",
                         "nome": NOME_ROTULOS, "plugin": False,
                         "protocolos": list(mapa.get("protocolos") or [])})
    return arqs


ARQUIVO_ROTULOS = u"@rotulos"
NOME_ROTULOS = u"Estudo 3D (mapa de rótulos)"


def _rotulos_meta(pasta, uid):
    try:
        import radai_rotulos
        return radai_rotulos.meta(pasta, uid)
    except Exception:
        return None


def _conjunto_de_rotulos(pasta, uid):
    import numpy as np
    import radai_recon3d as R
    import radai_rotulos
    mapa = radai_rotulos.ler(pasta, uid)
    if mapa is None:
        raise SemSerie(u"sem mapa de rótulos")
    g = mapa.meta.get("geometria") or {}
    esp_xyz = [float(v) for v in (g.get("spacing") or (1.0, 1.0, 1.0))]
    origem = [float(v) for v in (g.get("origin") or (0.0, 0.0, 0.0))]
    direcao = [float(v) for v in (g.get("direction")
                                  or (1, 0, 0, 0, 1, 0, 0, 0, 1))]
    D = np.asarray(direcao, dtype=np.float64).reshape(3, 3)
    rois, lo, hi = [], [], []
    for i, t in enumerate(mapa.tabela):
        vol = mapa._vol.get(t["chave"])
        if vol is None:
            continue
        ind = np.argwhere(np.asarray(vol) == int(t["indice"]))
        if not len(ind):
            continue
        a, b = ind.min(axis=0), ind.max(axis=0)
        cantos = []
        for z in (a[0], b[0]):
            for y in (a[1], b[1]):
                for x in (a[2], b[2]):
                    q = np.array([x, y, z], dtype=np.float64) * esp_xyz
                    cantos.append(np.asarray(origem) + D.dot(q))
        cantos = np.asarray(cantos)
        c0, c1 = cantos.min(axis=0), cantos.max(axis=0)
        lo.append(c0)
        hi.append(c1)
        try:
            import engine
            cor = [int(v) for v in engine._color(t.get("rotulo") or t["nome"])]
        except Exception:
            cor = list(R._PALETA_RESERVA[i % len(R._PALETA_RESERVA)])
        rois.append({u"nome": t["nome"], u"cor": cor[:3],
                     u"opacidade": (1.0 if t.get("achado") else
                                    R.opacidade_inicial(t.get("rotulo")
                                                        or t["nome"])),
                     u"casca": R.e_casca(t["nome"]),
                     u"achado": bool(t.get("achado")),
                     u"caixa": [[round(float(v), 2) for v in c0],
                                [round(float(v), 2) for v in c1]]})
    caixa = None
    if lo:
        caixa = [[round(float(v), 2) for v in np.min(lo, axis=0)],
                 [round(float(v), 2) for v in np.max(hi, axis=0)]]
    return {u"tipo": u"rotulos", u"rois": rois, u"caixa": caixa,
            u"mapa": mapa, u"contornos": dict((r[u"nome"], True)
                                               for r in rois),
            u"esp_zyx": tuple(esp_xyz[::-1]), u"origem": tuple(origem),
            u"direcao": tuple(direcao)}


def conjunto_da_serie(b, rs=u""):
    import os
    import radai_recon3d as R
    import radai_thumbnail
    pasta, uid = radai_thumbnail.resolver(b)
    if not pasta:
        raise SemSerie(u"bilhete")
    if not uid:
        # GUARDA: sem o UID, a pasta daria o contorno de outra série dela.
        raise SemSerie(u"sem UID")
    arquivos = arquivos_da_serie(pasta, uid)
    nomes = [c["arquivo"] for c in arquivos]
    if not nomes:
        raise SemSerie(u"sem RTSTRUCT")
    rs = str(rs or u"") or nomes[0]
    if rs not in nomes:
        raise KeyError(rs)
    if rs == ARQUIVO_ROTULOS:
        import radai_rotulos
        caminho = radai_rotulos.caminho(pasta, uid)
    else:
        caminho = os.path.join(pasta, rs)
    chave = (pasta, uid, rs, os.path.getmtime(caminho))
    with _TRAVA_MALHA:
        _esquecer_malhas(fora_da_serie=(pasta, uid))
        if _CONJ["chave"] != chave:
            _CONJ.update({"chave": None, "c": None})
            c = (_conjunto_de_rotulos(pasta, uid) if rs == ARQUIVO_ROTULOS
                 else R.abrir_conjunto(caminho))
            _CONJ.update({"chave": chave, "c": c})
        c = _CONJ["c"]
    _marcar_visto()
    return c, rs, arquivos, chave


def _modalidade(b):
    try:
        import radai_thumbnail
        s = radai_thumbnail.serie_do_bilhete(b) or {}
        return str(s.get("modalidade") or u"").upper()
    except Exception:
        return u""


def _camadas(b):
    import radai_recon3d as R
    mod = _modalidade(b)
    camadas = []
    # GUARDA: camada de densidade só em TC; o limiar é de Hounsfield.
    if not mod or mod == "CT":
        for cam in (u"osso", u"pele"):
            camadas.append({"camada": cam, "cor": list(R.CORES_3D[cam]),
                            "opacidade": R.OPACIDADE_CAMADA[cam]})
    return camadas


def _caixa_da_serie(b):
    import numpy as np
    import radai_thumbnail
    try:
        pasta, uid = radai_thumbnail.resolver(b)
        if not pasta:
            return None
        v, esp, origem, direcao = _volume_lps(pasta, uid or u"")
        n_xyz = np.array(v.shape[::-1], dtype=float) - 1.0
        d = np.array(direcao, dtype=float).reshape(3, 3)
        idx = np.array([[i, j, k] for i in (0, n_xyz[0]) for j in (0, n_xyz[1])
                        for k in (0, n_xyz[2])])
        pts = np.array(origem, dtype=float) + (idx * np.array(esp[::-1])) @ d.T
        return [[round(float(x), 2) for x in pts.min(axis=0)],
                [round(float(x), 2) for x in pts.max(axis=0)]]
    except Exception:
        return None


def estruturas_da_serie(b, rs=u""):
    import radai_recon3d as R
    try:
        c, rs, arquivos, _k = conjunto_da_serie(b, rs)
    except SemSerie as e:
        if str(e) == u"sem RTSTRUCT":
            return {"estruturas": [], "arquivos": [], "rs": u"",
                    "camadas": _camadas(b), "eixos": list(R.EIXOS_LPS),
                    "marcar_ate": MARCAR_TODAS_ATE, "sem_segmentacao": True,
                    "caixa": _caixa_da_serie(b), "erro": u""}
        return {"estruturas": [], "arquivos": [],
                "erro": u"recarregue a lista de séries"}
    except KeyError:
        return {"estruturas": [], "arquivos": [],
                "erro": u"este arquivo não está mais ao lado da série"}
    except Exception as e:
        import radai_thumbnail
        radai_thumbnail.registrar_falha(u"reconstrucoes 3D, estruturas", e,
                                        bilhete=b)
        return {"estruturas": [], "arquivos": [], "tipo": type(e).__name__,
                "erro": u"não consegui ler este RTSTRUCT"}
    return {"rs": rs,
            "arquivos": [{"arquivo": a["arquivo"], "nome": a.get("nome", ""),
                          "conjunto": a.get("conjunto", ""),
                          "plugin": bool(a.get("plugin"))} for a in arquivos],
            "estruturas": [{"nome": r["nome"], "cor": r["cor"],
                            "opacidade": r["opacidade"],
                            "casca": bool(r.get("casca")),
                            "achado": bool(r.get("achado")),
                            "vaso": R.e_vaso(r.get("padrao") or r["nome"]),
                            "osso": R.e_osso(r.get("padrao") or r["nome"]),
                            "caixa": r.get("caixa")} for r in c["rois"]],
            "caixa": c.get("caixa"), "eixos": list(R.EIXOS_LPS),
            "camadas": _camadas(b), "marcar_ate": MARCAR_TODAS_ATE,
            "sem_segmentacao": False, "erro": u""}


def malha_stl(b, rs=u"", nome=u"", camada=u""):
    import radai_recon3d as R
    import radai_thumbnail
    if camada:
        if camada not in R.CORES_3D:
            raise KeyError(camada)
        pasta, uid = radai_thumbnail.resolver(b)
        if not pasta:
            raise SemSerie(u"bilhete")
        mod = _modalidade(b)
        if mod and mod != "CT":
            raise ValueError(u"camada de densidade só em TC")
        uid = uid or u""
        chave = (pasta, uid, u"@TC", 0.0, camada, R.VERSAO_MALHA)
        with _TRAVA_MALHA:
            dados = _MALHAS.get(chave)
        if dados is not None:
            _marcar_visto()
            return dados
        # GUARDA: a série é pedida ANTES da trava da malha (ver `_soltar_se_parada`).
        v, esp, origem, direcao = _volume_lps(pasta, uid)
        with _TRAVA_MALHA:
            _esquecer_malhas(fora_da_serie=(pasta, uid))
            dados = _MALHAS.get(chave)
            if dados is None:
                verts, faces, _info = R.malha_da_camada(v, esp, origem,
                                                        direcao, camada)
                dados = R.stl_da_malha(verts, faces)
                _guardar_malha(chave, dados)
        _marcar_visto()
        return dados
    c, rs, _arqs, chave_c = conjunto_da_serie(b, rs)
    if nome not in c["contornos"]:
        raise KeyError(nome)
    chave = tuple(chave_c) + (nome, R.VERSAO_MALHA)
    with _TRAVA_MALHA:
        dados = _MALHAS.get(chave)
        if dados is None:
            if c.get(u"tipo") == u"rotulos":
                verts, faces, _info = R.malha_de_rotulo(
                    c[u"mapa"].mascara(nome), c[u"esp_zyx"], c[u"origem"],
                    c[u"direcao"])
            else:
                verts, faces, _info = R.malha_do_conjunto(c, nome)
            dados = R.stl_da_malha(verts, faces)
            _guardar_malha(chave, dados)
        else:
            _guardar_malha(chave, dados)
    return dados


def malha_do_desenho(b, cortes):
    import radai_recon3d as R
    import radai_recon3d_desenho as D
    import radai_thumbnail
    pasta, uid = radai_thumbnail.resolver(b)
    if not pasta:
        raise SemSerie(u"bilhete")
    v, esp, origem, direcao = _volume_lps(pasta, uid or u"")
    Z, Y, X = v.shape
    por_corte = {}
    for c in list(cortes or ())[:D.TETO_CORTES]:
        try:
            z = D.indice_do_corte(float(c.get("pos")), Z)
        except (TypeError, ValueError, AttributeError):
            continue
        polis = []
        for p in (c.get("pontos") or ()):
            pv = D.poligono_em_voxel(p, (Y, X))
            if len(pv) >= 3:
                polis.append(pv)
        if polis:
            por_corte.setdefault(z, []).extend(polis)
    if not por_corte:
        raise ValueError(u"nada desenhado")
    vol = D.volume_do_desenho(por_corte, (Z, Y, X), esp)
    verts, faces, _info = R.malha_de_rotulo(vol, esp, origem, direcao)
    _marcar_visto()
    return R.stl_da_malha(verts, faces), sorted(por_corte)


def _cortes_para_mpr(conjunto, esp, origem, direcao):
    import numpy as np
    geometria = (tuple(esp), tuple(origem), tuple(direcao))
    with _TRAVA_MALHA:
        cache = conjunto.get("_mpr")
        if cache and cache[0] == geometria:
            return cache[1]
        inversa = np.linalg.inv(np.asarray(direcao).reshape(3, 3))
        por_nome = {}
        plano = conjunto.get("plano")
        for nome, contornos in conjunto.get("contornos", {}).items():
            cortes = {}
            for pontos in contornos:
                p = np.asarray(pontos, dtype=np.float64)
                if plano is not None:
                    p = p.dot(plano)
                idx = ((p - origem).dot(inversa.T)
                       / np.asarray(esp[::-1]))
                z = int(round(float(np.median(idx[:, 2]))))
                cortes.setdefault(z, []).append(idx[:, :2])
            por_nome[nome] = cortes
        conjunto["_mpr"] = (geometria, por_nome)
        return por_nome


def _mascara_do_plano(cortes, forma, eixo, indice):
    import numpy as np
    import radai_recon3d as R
    if eixo == 0:
        return R._par_impar(cortes.get(indice, ()), 0, 0, 1,
                             forma[2], forma[1])
    largura = forma[2] if eixo == 1 else forma[1]
    m = np.zeros((forma[0], largura), dtype=bool)
    for z, polis in cortes.items():
        if not 0 <= z < forma[0]:
            continue
        p = polis if eixo == 1 else [a[:, [1, 0]] for a in polis]
        m[z] = R._par_impar(p, 0, indice, 1, largura, 1)[0]
    return m


def _segmentacoes_do_plano(conjunto, forma, esp, origem, direcao,
                           eixo, indice, nomes):
    import numpy as np
    if conjunto.get("tipo") == "rotulos":
        if (any(tuple(v.shape) != tuple(forma)
                for v in conjunto["mapa"]._vol.values())
                or not np.allclose(conjunto["esp_zyx"], esp)
                or not np.allclose(conjunto["origem"], origem)
                or not np.allclose(conjunto["direcao"], direcao)):
            raise ValueError("mapa fora da geometria da serie")
        tabela = {t["nome"]: t for t in conjunto["mapa"].tabela}
        for roi in conjunto["rois"]:
            if nomes is not None and roi["nome"] not in nomes:
                continue
            t = tabela[roi["nome"]]
            vol = conjunto["mapa"]._vol[t["chave"]]
            yield roi, np.take(vol, indice, axis=eixo) == int(t["indice"])
        return
    cortes = _cortes_para_mpr(conjunto, esp, origem, direcao)
    for roi in conjunto["rois"]:
        if nomes is not None and roi["nome"] not in nomes:
            continue
        yield roi, _mascara_do_plano(cortes.get(roi["nome"], {}), forma,
                                     eixo, indice)


def _png_com_contornos(png, conjunto, forma, esp, origem, direcao,
                       sentido, eixo, indice, nomes):
    import base64
    import struct
    import radai_recon3d as R
    import radai_viewseg
    largura, altura = struct.unpack(">II", png[16:24])
    paths = []
    for roi, m in _segmentacoes_do_plano(
            conjunto, forma, esp, origem, direcao, eixo, indice, nomes):
        d = radai_viewseg.bordas_svg(R.plano_para_a_tela(m, eixo, esp, sentido))
        if d:
            cor = [max(0, min(255, int(v))) for v in roi["cor"][:3]]
            paths.append('<path d="%s" stroke="rgb(%d,%d,%d)"/>'
                         % (d, cor[0], cor[1], cor[2]))
    imagem = base64.b64encode(png).decode("ascii")
    return ('<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'viewBox="0 0 %d %d" width="%d" height="%d">'
            '<image width="%d" height="%d" '
            'xlink:href="data:image/png;base64,%s"/>'
            '<g fill="none" stroke-width="1.2" stroke-linejoin="round">%s'
            '</g></svg>' % (largura, altura, largura, altura, largura, altura,
                            imagem, "".join(paths))).encode("utf-8")


CSS = u"""
.r3-wrap{--r3-altura:calc(min(68vh,620px) - 78px);max-width:1612px;margin:0 auto;padding:28px 22px 40px}
.r3-wrap .ps-cx{margin-top:22px}
.r3-serie{display:flex;flex-direction:column;gap:8px;margin-top:22px}
.r3-lista{display:flex;flex-direction:column;gap:6px;max-height:262px;overflow:auto;
 padding:2px}
.r3-item{display:grid;grid-template-columns:minmax(120px,1.2fr) minmax(0,1.6fr) auto auto;
 align-items:center;gap:12px;width:100%;text-align:left;cursor:pointer;
 padding:9px 12px;border-radius:var(--r-md,8px);border:1px solid var(--line);
 background:var(--panel-2);color:var(--text);font:inherit;font-size:12.5px;
 transition:border-color .15s,background-color .15s,transform .12s}
.r3-item:hover{border-color:var(--mod-recon)}
.r3-item:active{transform:translateY(1px)}
.r3-item:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.r3-item[aria-selected="true"]{border-color:var(--mod-recon);background:var(--mod-recon-fraco)}
.r3-i-pri{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.r3-i-meta{font-family:var(--mono);font-size:11px;color:var(--text-muted);
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.r3-i-n{font-size:11.5px;color:var(--text-muted);white-space:nowrap}
.r3-i-n b{color:var(--text);font-weight:600}
.r3-tag{font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;
 text-transform:uppercase;padding:3px 8px;border-radius:999px;white-space:nowrap;
 border:1px solid var(--mod-recon);color:var(--mod-recon)}
.r3-tag.apagada{border-color:var(--line-strong);color:var(--text-dim)}
.r3-vazio{margin:6px 2px;font-size:12.5px;color:var(--text-muted)}
.r3-pasta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.r3-pasta-campo{display:flex;gap:6px;align-items:stretch;flex:1 1 320px;min-width:0}
.r3-filtro{margin:0 0 10px}
#r3_busca{margin:0 0 8px}
.r3-pasta input{flex:1 1 auto;min-width:0;padding:8px 10px;border-radius:6px;
 border:1px solid var(--line-strong);background:var(--panel-2);color:var(--text);
 font-family:var(--mono);font-size:12px}
.r3-pasta input:focus{outline:none;border-color:var(--accent)}
.r3-estado{margin-top:12px;font-size:12.5px;color:var(--text-muted);line-height:1.55}
.r3-estado:empty{display:none}
.r3-estado.falta{border-left:2px solid var(--aviso);padding:4px 0 4px 12px}
.r3-estado .ui-bt{margin-left:8px}
.r3-3d{display:grid;grid-template-columns:minmax(0,944px) 256px 320px;gap:12px;align-items:stretch}
.r3-ferramentas{display:flex;flex-direction:column;gap:12px;min-width:0;
 height:var(--r3-altura);min-height:234px;overflow:auto;border:1px solid var(--line);
 border-radius:8px;background:var(--panel-2)}
.r3-ferramentas .r3-inc3d{padding:10px;flex-direction:column;align-items:stretch;gap:14px}
.r3-ferramentas .r3-inc3d .g{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
.r3-ferramentas .r3-barra{flex-wrap:wrap;justify-content:space-between}
.r3-ferramentas .r3-barra input[type=range]{width:calc(100% - 66px);min-width:80px}
.r3-ferramentas .r3-barra b{width:100%;text-align:center}
.r3-ferramentas .r3-grav{margin-top:auto}
@media (max-width:1500px){.r3-wrap{max-width:1320px}
 .r3-3d{grid-template-columns:minmax(0,1fr) 320px}
 .r3-ferramentas{grid-column:1/-1;grid-row:2;height:auto;min-height:0;display:grid;
 grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:start}
 .r3-ferramentas .r3-inc3d{grid-row:span 2}.r3-ferramentas .r3-grav{margin-top:0}}
@media (max-width:980px){.r3-3d{grid-template-columns:minmax(0,1fr)}
 .r3-ferramentas{grid-column:auto;grid-row:auto;display:flex}.r3-l3d{grid-row:2}}
.r3-col3d{display:flex;flex-direction:column;gap:6px;min-width:0;
 height:var(--r3-altura);min-height:234px}
.r3-tela3d{position:relative;border-radius:8px;background:var(--img-fundo);overflow:hidden;
 flex:1 1 auto;min-height:220px}
.r3-inc3d{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;flex:none}
.r3-inc3d .g{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.r3-inc{display:inline-flex;flex-direction:column;align-items:flex-start;gap:1px;
 padding:3px 8px;min-height:28px;border-radius:6px;border:1px solid var(--line);
 background:var(--panel);color:var(--text-muted);font-size:11px;line-height:1.15;cursor:pointer}
.r3-inc small{font-family:var(--mono);font-size:10px;color:var(--text-dim)}
.r3-inc:hover{color:var(--text);border-color:var(--line-strong)}
.r3-inc[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}
.r3-inc[aria-pressed="true"] small{color:inherit}
.r3-inc:focus-visible,.r3-atraves:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.r3-barra{display:inline-flex;align-items:center;gap:6px}
.r3-barra .r3-bl{font-family:var(--mono);font-size:11px;color:var(--text-muted)}
.r3-barra input[type=range]{width:140px;accent-color:var(--mod-recon)}
.r3-barra.cra input[type=range]{width:96px}
.r3-barra b{font-family:var(--mono);font-size:11.5px;font-weight:500;color:var(--text);
 min-width:60px}
.r3-atraves[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}
.r3-tela3d canvas{position:absolute;left:0;top:0;display:block;width:100%;height:100%;
 cursor:grab;touch-action:none}
.r3-tela3d canvas:active{cursor:grabbing}
.r3-tela3d canvas[hidden]{display:none}
#cv3Db{pointer-events:none}
.r3-dica3d{position:absolute;left:10px;right:max(10px,28%);bottom:8px;
 font-family:var(--mono);font-size:10.5px;color:var(--img-texto-fraco,#a3b1c6);
 pointer-events:none}
.r3-vistas{position:absolute;top:8px;right:8px;display:flex;gap:4px}
.r3-vistas button{width:26px;height:26px;padding:0;font-size:11px;line-height:1;
 border-radius:6px;border:1px solid var(--line);background:var(--panel);
 color:var(--text-muted);cursor:pointer;font-family:var(--mono)}
.r3-vistas button:hover,.r3-vistas button:focus-visible{color:var(--text);
 border-color:var(--mod-recon);outline:none}
.r3-rec{position:absolute;top:10px;left:10px;display:flex;align-items:center;gap:6px;
 font-family:var(--mono);font-size:11px;color:var(--text);
 background:var(--panel);border:1px solid var(--perigo);border-radius:999px;
 padding:3px 10px;pointer-events:none}
.r3-rec i{width:8px;height:8px;border-radius:50%;background:var(--perigo);
 animation:r3pulsa 1.2s ease-in-out infinite}
.r3-rec[hidden]{display:none}
@keyframes r3pulsa{50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.r3-rec i{animation:none}}
.r3-l3d{border:1px solid var(--line);border-radius:8px;background:var(--panel-2);
 display:flex;flex-direction:column;min-width:0;height:var(--r3-altura);min-height:234px}
@media (max-width:980px){.r3-l3d{height:auto;max-height:none}}
.r3-l3cab{padding:9px 10px 7px;border-bottom:1px solid var(--line);
 display:flex;flex-direction:column;gap:7px}
.r3-l3cab label{font-size:10.5px;color:var(--text-dim);letter-spacing:.04em}
.r3-l3cab select,.r3-l3cab input{width:100%;padding:5px 8px;border-radius:6px;
 font-size:12px;border:1px solid var(--line);background:var(--panel);color:var(--text)}
.r3-l3cab input:focus,.r3-l3cab select:focus{outline:none;border-color:var(--accent)}
.r3-l3acoes{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.r3-l3acoes button{padding:3px 9px;font-size:11px;border-radius:6px;
 border:1px solid var(--line);background:var(--panel);color:var(--text-muted);cursor:pointer}
.r3-l3acoes button:hover{color:var(--text);border-color:var(--accent)}
.r3-l3acoes .sub{margin-left:auto;font-size:10.5px}
.r3-l3rolar{overflow:auto;flex:1 1 auto;min-height:90px;padding:4px 0 6px}
.r3-l3sub{font-family:var(--mono);font-size:9.5px;letter-spacing:.11em;
 text-transform:uppercase;color:var(--text-dim);padding:9px 10px 3px}
.r3e{display:grid;grid-template-columns:minmax(0,1fr) 78px 34px 12px;
 align-items:center;gap:6px;padding:2px 10px;font-size:12px;min-height:26px}
.r3e[hidden]{display:none}
.r3e:hover{background:var(--panel)}
.r3e-l{display:flex;align-items:center;gap:6px;min-width:0;cursor:pointer}
.r3e-l input{margin:0;flex:0 0 auto;accent-color:var(--accent)}
.r3e-sw{flex:0 0 auto;width:10px;height:10px;border-radius:3px;
 box-shadow:0 0 0 1px var(--line-strong) inset}
.r3e-n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 font-family:var(--mono);font-size:11.5px;color:var(--text)}
.r3e.desenho .r3e-n{font-family:inherit;font-weight:600}
.r3e-a{width:78px;margin:0;accent-color:var(--accent)}
.r3e-a:disabled{opacity:.35}
.r3e-v{font-weight:400;font-family:var(--mono);font-size:10.5px;
 color:var(--text-dim);text-align:right}
.r3e-s{width:10px;height:10px;border-radius:50%}
.r3e-s.fila{box-shadow:0 0 0 1px var(--text-dim) inset}
.r3e-s.montando{border:2px solid var(--accent);border-right-color:transparent;
 animation:r3gira .8s linear infinite}
.r3e-s.erro{background:var(--perigo)}
@keyframes r3gira{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.r3e-s.montando{animation:none}}
.r3-dsn,.r3-grav{border-top:1px solid var(--line);padding:10px;display:flex;
 flex-direction:column;gap:8px}
.r3-ferr-cab{display:flex;align-items:center;justify-content:space-between;gap:8px;
 font-family:var(--mono);font-size:9.5px;letter-spacing:.11em;
 text-transform:uppercase;color:var(--text-dim)}
.r3-crono{font-size:12px;letter-spacing:.04em;color:var(--text);font-variant-numeric:tabular-nums}
.r3-fmt{display:inline-flex;border:1px solid var(--line-strong);border-radius:6px;overflow:hidden}
.r3-fmt button{padding:4px 12px;font-size:11px;border:0;background:var(--panel);
 color:var(--text-muted);cursor:pointer;font-family:var(--mono)}
.r3-fmt button+button{border-left:1px solid var(--line-strong)}
.r3-fmt button.on{background:var(--mod-recon-fraco);color:var(--text)}
.r3-fmt button:disabled{opacity:.4;cursor:not-allowed}
.r3-grav-linha{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.r3-grav-linha .ui-bt{flex:1 1 auto;justify-content:center}
#r3_gravar.gravando{background:var(--perigo);border-color:var(--perigo);color:var(--bg-0)}
.r3-grav-aviso{display:flex;gap:8px;align-items:flex-start;margin:8px 0 0;font-size:12px;
 line-height:1.5;color:var(--text)}
.r3-grav-aviso .pt{width:7px;height:7px;border-radius:50%;flex:0 0 auto;margin-top:6px;
 background:var(--warn)}
.r3-grav-decl{display:flex;align-items:flex-start;gap:2px;margin:6px 0 0}
.r3-grav-decl .ui-ajuda{margin-top:1px}
.r3-grav-ato{display:flex;gap:6px;align-items:flex-start;font-size:12px;
 line-height:1.45;color:var(--text-muted);cursor:pointer}
.r3-grav-msg,.r3-dsn-msg{margin:0;font-size:11px;color:var(--text-muted);min-height:1em}
.r3-dsn .ui-bt{justify-content:center}
.r3-aviso3d{margin:9px 0 0;font-size:11.5px;color:var(--text-dim);
 border-left:2px solid var(--aviso);padding-left:10px;line-height:1.55}
.r3-aviso3d[hidden]{display:none}
.r3-grade{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:14px}
@media (max-width:980px){.r3-grade{grid-template-columns:repeat(2,minmax(0,1fr))}}
.r3-quadro{border:1px solid var(--line);border-radius:10px;padding:8px;background:var(--panel);
 min-width:0}
.r3-quadro .rot{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--text-dim);display:flex;justify-content:space-between;
 align-items:center;gap:6px;margin-bottom:6px}
.r3-quadro .rot b{font-weight:400;color:var(--text-muted)}
.r3-tela{border-radius:6px;background:#000;display:flex;justify-content:center;
 align-items:center;aspect-ratio:1/1;overflow:hidden}
.r3-tela img{max-width:100%;max-height:100%;image-rendering:pixelated;user-select:none;
 cursor:zoom-in}
.r3-quadro input[type=range]{width:100%;margin-top:6px;accent-color:var(--mod-recon)}
.r3-pctl{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px;font-size:11px}
.r3-pctl select{padding:2px 6px;border-radius:5px;border:1px solid var(--line);
 background:var(--panel-2);color:var(--text);font-size:11px}
.r3-pctl input[type=range]{flex:1 1 60px;margin:0;min-width:60px}
.r3-q{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;
 border-radius:50%;border:1px solid var(--line-strong);background:var(--panel-2);
 color:var(--text-muted);font-size:11px;cursor:pointer;padding:0;line-height:1}
.r3-q:hover,.r3-q:focus-visible{color:var(--text);border-color:var(--mod-recon);outline:none}
.r3-ctrl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0 0}
.r3-ctrl .sub{font-size:11px;color:var(--text-dim);margin-right:2px}
button.jan{padding:4px 10px;font-size:11.5px;border-radius:6px;border:1px solid var(--line);
 background:var(--panel);color:var(--text-muted);cursor:pointer}
button.jan:hover{color:var(--text)}
button.jan.on{border-color:var(--mod-recon);color:var(--text);background:var(--mod-recon-fraco)}
.r3-edu{display:flex;flex-direction:column;gap:10px;font-size:13px;line-height:1.6;
 color:var(--text-muted)}
.r3-edu p{margin:0}
.r3-edu-f{margin:4px 0 0;display:flex;align-items:center;gap:14px}
.r3-edu-f svg{width:200px;height:96px;flex:0 0 auto}
.r3-edu-f figcaption{font-size:12.5px;color:var(--text)}
.r3-edu-raios line{stroke:var(--line-strong);stroke-width:1.4;stroke-dasharray:3 3}
.r3-edu-laje{fill:var(--mod-recon-fraco);stroke:var(--mod-recon);stroke-width:1.2}
.r3-edu-claro{fill:white}
.r3-edu-escuro{fill:#000;stroke:silver}
.r3-edu-det{fill:#000;stroke:var(--line-strong)}
.r3-edu-det.claro{fill:silver}
.r3-dsn-m{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:16px}
@media (max-width:820px){.r3-dsn-m{grid-template-columns:minmax(0,1fr)}}
.r3-dsn-palco{position:relative;background:#000;border-radius:8px;display:flex;
 justify-content:center;align-items:center;min-height:300px;overflow:hidden}
.r3-dsn-palco img{display:block;max-width:100%;image-rendering:pixelated;user-select:none}
.r3-dsn-palco canvas{position:absolute;cursor:crosshair;touch-action:none}
.r3-dsn-cmd{display:flex;flex-direction:column;gap:10px;font-size:12.5px;color:var(--text-muted)}
.r3-dsn-cmd input[type=range]{width:100%;accent-color:var(--mod-recon)}
.r3-dsn-dica{margin:0;line-height:1.55}
.r3-dsn-rot{margin:0}
.r3-dsn-rot b{color:var(--text);font-variant-numeric:tabular-nums}
.r3-dsn-bts{display:flex;flex-direction:column;gap:6px}
.r3-dsn-bts .ui-bt{justify-content:center}
"""

JS_SERIE = u"""
// GUARDA: a série viaja por BILHETE (`b`), nunca pelo caminho; `<img src>` é GET.
var R3 = {fer: 'geral', jan: 'pulmao', modo: 'mip', laje: 10,
          pos: {0: 0.5, 1: 0.5, 2: 0.5}, proj: 0, b: '', forma: null, cranial: 0,
          lista: [], acervo: [], tabela: null, ficha: false, abrindo: false,
          rotulo: '', rotuloFraco: false};

function r3El(i){ return document.getElementById(i) }
function r3Esc(t){ return String(t == null ? '' : t).replace(/&/g, '&amp;')
 .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') }
function r3Frase(t){ return '<span data-radai-frase>' + r3Esc(t) + '</span>' }
function r3Valor(t){ return '<span data-radai-t="1" translate="no">' + r3Esc(t) + '</span>' }
function r3Traduzir(){ try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(e){} }
function r3DataBr(d){
 d = (d == null ? '' : ('' + d)).trim();
 if(d.length >= 8 && !isNaN(+d.slice(0, 8)))
  return d.slice(6, 8) + '/' + d.slice(4, 6) + '/' + d.slice(0, 4);
 return d;
}
function r3Post(url, corpo){
 return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(corpo || {})}).then(function(r){ return r.json() });
}
function r3Vazio(alvo, frase){
 alvo.innerHTML = '<p class="r3-vazio">' + r3Frase(frase) + '</p>';
 r3Traduzir();
}

function r3Acervo(){
 var alvo = r3El('r3_acervo'); if(!alvo) return;
 if(!window.uiTabelaAcervo){ r3Vazio(alvo, 'não consegui ler o acervo desta estação'); return }
 R3.tabela = window.uiTabelaAcervo(alvo, {
  url: '/api/recon3d/acervo?ferramenta=' + encodeURIComponent(R3.fer),
  vazioTexto: R3.fer === 'toracica'
   ? 'Nenhuma série desta estação rodou o protocolo Anatomia Torácica.' : '',
  aoAbrir: function(linha){ r3Desmarcar(); r3Abrir(linha.bilhete, r3RotuloDaLinha(linha)) },
  aoCarregar: function(L){ R3.acervo = L || []; r3RotuloDoAcervo() }
 });
}
function r3RotuloDaLinha(l){
 return [r3DataBr(l.date), l.pid, l.modalidade].filter(function(x){ return x }).join(' · ');
}
function r3RotuloDoAcervo(){
 if(!R3.b || (R3.rotulo && !R3.rotuloFraco)) return;
 var l = (R3.acervo || []).filter(function(s){ return s.bilhete === R3.b })[0];
 if(l) r3Cartao(r3RotuloDaLinha(l));
}
function r3Cartao(t, fraco){
 R3.rotulo = t || ''; R3.rotuloFraco = !!fraco;
 if(window.uiCartaoRotulo) uiCartaoRotulo('r3_cartao', R3.rotulo, !!fraco);
}
function r3Popup(){
 return window.uiPopupSerie ? uiPopupSerie('r3_escolha') : null;
}
function r3SemSerie(){
 var p = r3Popup();
 if(!R3.b && p) p.abrir();
}
function r3Desmarcar(){
 Array.prototype.forEach.call(document.querySelectorAll('.r3-item[aria-selected="true"]'),
  function(x){ x.setAttribute('aria-selected', 'false') });
}
function r3LinhaPasta(s){
 var meta = [r3DataBr(s.date), s.modalidade || '', (+s.cortes || 0)]
            .filter(function(x){ return x !== '' }).join(' · ');
 var nome = [s.pid, s.desc || s.curto].filter(function(x){ return x }).join(' · ');
 return '<button type="button" class="r3-item" role="option" aria-selected="false"'
  + ' data-b="' + r3Esc(s.bilhete) + '">'
  + '<span class="r3-i-pri">' + r3Valor(nome || '—') + '</span>'
  + '<span class="r3-i-meta">' + r3Valor(meta) + ' ' + r3Frase('cortes')
  + (s.espessura_mm != null ? ' · ' + r3Valor(s.espessura_mm + ' mm') : '') + '</span>'
  + '<span class="r3-i-n"></span>'
  + (s.segmentada ? '<span class="r3-tag">' + r3Frase('segmentada') + '</span>'
                  : '<span class="r3-tag apagada">' + r3Frase('sem segmentação') + '</span>')
  + '</button>';
}
var R3_USO_DA_VARREDURA = 'recon3d';
function r3Listar(pasta){
 var alvo = r3El('r3_lista_pasta'); if(!alvo) return;
 pasta = (pasta || '').trim();
 if(!pasta){ if(window.uiTremer) window.uiTremer(r3El('r3_pasta')); return }
 if(!window.uiVarrerLista){ r3Vazio(alvo, 'não consegui listar esta pasta'); return }
 window.uiVarrerLista({alvo: 'r3_lista_pasta', estado: 'r3_busca',
  uso: R3_USO_DA_VARREDURA, chave: 'recon3d', pasta: pasta, dias: 'r3_dias',
  linha: r3LinhaPasta, vazio: 'Nenhuma série nesta pasta.'});
}
function r3Outra(){
 r3Listar(r3El('r3_pasta').value || '');
}
function r3Procurar(bt){
 if(!window.uiExplorador) return;
 uiExplorador({titulo: 'Escolher a pasta', origem: bt,
  inicial: (r3El('r3_pasta').value || '').trim(),
  aoUsar: function(c){ r3El('r3_pasta').value = c || ''; if(c) r3Listar(c) }});
}
function r3Escolher(el){
 r3Desmarcar();
 if(R3.tabela) R3.tabela.marcar(null);
 el.setAttribute('aria-selected', 'true');
 var pri = el.querySelector ? el.querySelector('.r3-i-pri') : null;
 r3Abrir(el.getAttribute('data-b'), pri ? pri.textContent : '');
}
function r3Abrir(b, rotulo){
 if(!b) return;
 var pp = r3Popup(); if(pp) pp.fechar();
 R3.b = b; R3.forma = null; R3.cranial = 0;
 r3Cartao(rotulo || ''); r3RotuloDoAcervo();
 r3Carregando(true);
 if(R3.fer === 'toracica' && window.R3M && !R3M.preset)
  R3M.preset = {rs: '@rotulos', nomes: []};
 if(window.r3mAbrir) r3mAbrir(b);
 fetch('/api/recon3d/estado?b=' + encodeURIComponent(b))
  .then(function(r){ return r.json() })
  .then(function(d){
   R3.forma = d && d.forma ? d.forma : null;
   R3.cranial = (d && (d.cranial === 1 || d.cranial === -1)) ? d.cranial : 0;
   r3Estado(d, ''); r3PintarTudo();
   if(d && d.nao_le){ r3Carregando(false); if(window.r3mSemTC) r3mSemTC() }
   if(window.r3DesenhoPronto) r3DesenhoPronto();
   if(window.r3AoAbrir) r3AoAbrir(d);
  })
  .catch(function(){ r3Carregando(false); r3PintarTudo() });
}
function r3Carregando(sim){
 R3.abrindo = !!sim;
 var t = r3El('r3_tela3d');
 if(t && window.uiCarregando) uiCarregando(t, sim, 'abrindo a série…');
}
function r3AoCarregar(d){ r3Carregando(false) }
function r3Estado(d, erro){
 var e = r3El('r3_estado'); if(!e) return;
 function pinta(cls, h){ e.className = 'r3-estado' + (cls ? ' ' + cls : '');
  if(window.uiHTML) window.uiHTML(e, h); else e.innerHTML = h }
 if(erro){ pinta('falta', r3Frase(erro)); return }
 if(!d) return;
 if(d.nao_le){
  pinta('falta', '<b>' + r3Frase('Esta série não pôde ser lida.') + '</b> '
   + '<span class="sub"><span data-radai-frase>' + r3Esc(d.nao_le) + '</span>'
   + (d.tipo ? ' <code>' + r3Esc(d.tipo) + '</code>' : '') + '</span>');
  return;
 }
 if(R3.fer === 'toracica' && (d.estudo_3d || []).indexOf('anatomia_toracica') < 0){
  pinta('falta', r3Frase('Esta série não rodou o protocolo Anatomia Torácica.')
   + ' <a class="ui-bt" href="/lote">' + r3Frase('Rodar agora') + '</a>');
  return;
 }
 if(!d.segmentada && R3.fer === 'vascular'){
  pinta('falta', r3Frase('Sem segmentação: a angiografia funciona; a superfície dos vasos, não.')
   + (d.rota_para_segmentar ? ' <a class="ui-bt" href="' + r3Esc(d.rota_para_segmentar) + '">'
      + r3Frase('Rodar agora') + '</a>' : ''));
  return;
 }
 if(!d.segmentada){
  pinta('falta', r3Frase('Sem segmentação: o 3D mostra osso e pele pela densidade da TC.')
   + (d.rota_para_segmentar ? ' <a class="ui-bt" href="' + r3Esc(d.rota_para_segmentar) + '">'
      + r3Frase('Rodar agora') + '</a>' : ''));
  return;
 }
 pinta('', '');
}

var R3_PLANOS = [{eixo: 0, rot: 'axial'}, {eixo: 1, rot: 'coronal'},
                 {eixo: 2, rot: 'sagital'}];
function r3UrlDe(eixo, laje, pos, jan, modo, segmentacao){
 var extra = '';
 if(segmentacao && window.R3M && R3M.b === R3.b && R3M.rs){
  var nomes = R3M.estr.filter(function(e){ return R3M.lig[e.nome] }).map(function(e){ return e.nome });
  extra = '&segmentacao=true&rs=' + encodeURIComponent(R3M.rs)
   + '&nomes=' + encodeURIComponent(JSON.stringify(nomes));
 }
 return '/api/recon3d/projecao?b=' + encodeURIComponent(R3.b)
   + '&modo=' + modo + '&eixo=' + eixo + '&janela=' + jan
    + '&laje=' + laje + '&pos=' + pos + extra;
}
function r3Url(eixo, laje){ return r3UrlDe(eixo, laje, R3.pos[eixo], R3.jan, R3.modo, laje === 0) }
function r3Ampliar(p, img){
 if(!R3.b || !R3.forma || !window.uiVisor) return;
 var n = R3.forma[p.eixo], v = null;
 v = uiVisor({titulo: p.rot, total: n, origem: img, janela: R3.jan,
  inicial: Math.round((R3.pos[p.eixo] || 0) * (n - 1)),
  cranial: p.eixo === 0 ? R3.cranial : 0,
  janelas: [{chave: 'pulmao', rotulo: 'pulmão'}, {chave: 'mediastino', rotulo: 'mediastino'},
            {chave: 'osso', rotulo: 'osso'}, {chave: 'cerebro', rotulo: 'cérebro'}],
   src: function(i, j){ return r3UrlDe(p.eixo, 0, n > 1 ? i / (n - 1) : 0, j, 'mip', true) },
  cabecalho: function(i){ return [['corte', (i + 1) + ' / ' + n]] },
  aoFechar: function(){
   if(!v) return;
   R3.pos[p.eixo] = n > 1 ? v.corte() / (n - 1) : 0;
   var s = r3El('r3_pos' + p.eixo); if(s) s.value = Math.round(R3.pos[p.eixo] * 100);
   var e = r3El('r3_posv' + p.eixo); if(e) e.textContent = Math.round(R3.pos[p.eixo] * 100) + '%';
   r3Pintar(p.eixo);
  }});
}
function r3Pintar(eixo){
 if(!R3.b) return;
 var img = r3El('r3_img' + eixo); if(!img) return;
 img.onerror = function(){ img.removeAttribute('src') };
  img.src = r3Url(eixo, 0);
}
function r3Proj(){
 if(!R3.b) return;
 var img = r3El('r3_imgp'); if(!img) return;
 img.onerror = function(){ img.removeAttribute('src') };
 img.src = r3Url(R3.proj, R3.laje);
}
function r3PintarPlanos(){ if(R3.forma) R3_PLANOS.forEach(function(p){ r3Pintar(p.eixo) }) }
function r3PintarTudo(){ r3PintarPlanos(); r3Proj() }
function r3Jan(j){ R3.jan = j; r3Marcar(); r3PintarTudo() }
function r3Modo(m){ R3.modo = m; r3Marcar(); r3Proj() }
function r3Marcar(){
 ['pulmao', 'mediastino', 'osso', 'cerebro'].forEach(function(j){
  var b = r3El('j_' + j);
  if(b){ b.classList.toggle('on', R3.jan === j); b.setAttribute('aria-pressed', R3.jan === j ? 'true' : 'false') }
 });
 ['mip', 'minip'].forEach(function(m){
  var b = r3El('m_' + m);
  if(b){ b.classList.toggle('on', R3.modo === m); b.setAttribute('aria-pressed', R3.modo === m ? 'true' : 'false') }
 });
}

function r3AjudaMip(bt){
 var h = '<div class="r3-edu">'
  + '<figure class="r3-edu-f">' + R3_SVG_MIP + '<figcaption><b>MIP</b> · '
  + r3Frase('Projeção de intensidade máxima') + '</figcaption></figure>'
  + '<p>' + r3Frase('Cada raio guarda o voxel mais denso da laje: realça osso, vaso contrastado e nódulo.') + '</p>'
  + '<figure class="r3-edu-f">' + R3_SVG_MINIP + '<figcaption><b>MinIP</b> · '
  + r3Frase('Projeção de intensidade mínima') + '</figcaption></figure>'
  + '<p>' + r3Frase('Cada raio guarda o voxel menos denso: realça via aérea e enfisema.') + '</p>'
  + '<p>' + r3Frase('A laje vai de 1 a 100 mm: fina parece um corte; grossa mostra o trajeto e sobrepõe o resto.') + '</p>'
  + '<p>' + r3Frase('A projeção mostra; não mede nem procura nada.') + '</p>'
  + '</div>';
 if(window.uiModal) uiModal({titulo: 'MIP e MinIP', html: h, largura: 640, origem: bt});
}
var R3_SVG_RAIOS = '<g class="r3-edu-raios">'
 + [24, 40, 56, 72].map(function(y){ return '<line x1="8" y1="' + y + '" x2="152" y2="' + y + '"/>' }).join('')
 + '</g><rect class="r3-edu-laje" x="44" y="12" width="72" height="72" rx="4"/>';
var R3_SVG_MIP = '<svg viewBox="0 0 200 96" aria-hidden="true">' + R3_SVG_RAIOS
 + '<circle class="r3-edu-claro" cx="70" cy="40" r="7"/><circle class="r3-edu-claro" cx="92" cy="72" r="5"/>'
 + '<rect class="r3-edu-det" x="162" y="12" width="26" height="72" rx="3"/>'
 + '<rect class="r3-edu-claro" x="166" y="34" width="18" height="12" rx="2"/>'
 + '<rect class="r3-edu-claro" x="166" y="66" width="18" height="12" rx="2"/></svg>';
var R3_SVG_MINIP = '<svg viewBox="0 0 200 96" aria-hidden="true">' + R3_SVG_RAIOS
 + '<circle class="r3-edu-escuro" cx="84" cy="24" r="7"/><circle class="r3-edu-escuro" cx="62" cy="56" r="5"/>'
 + '<rect class="r3-edu-det claro" x="162" y="12" width="26" height="72" rx="3"/>'
 + '<rect class="r3-edu-escuro" x="166" y="18" width="18" height="12" rx="2"/>'
 + '<rect class="r3-edu-escuro" x="166" y="50" width="18" height="12" rx="2"/></svg>';

function r3Ficha(){
 var f = '';
 try{ f = new URLSearchParams(location.search).get('ficha') || '' }catch(e){}
 if(!f) return false;
 R3.ficha = true;
 r3Post('/api/recon3d/ficha', {ficha: f}).then(function(d){
  if(!d || d.erro || !d.b){
   R3.ficha = false;
   r3Estado(null, (d && d.erro) || 'a ficha venceu: escolha a série no acervo');
   r3SemSerie(); return;
  }
  if(window.R3M) R3M.preset = {rs: d.rs || '', nomes: d.estruturas || []};
  r3Abrir(d.b, '');
  if(!R3.rotulo) r3Cartao('Ver segmentação', true);
 }).catch(function(){ R3.ficha = false; r3SemSerie() });
 return true;
}

function r3IniciarTela(){
 var w = document.querySelector('.r3-wrap');
 R3.fer = (w && w.getAttribute('data-ferramenta')) || 'geral';
 r3Marcar();
 R3_PLANOS.forEach(function(p){
  var s = r3El('r3_pos' + p.eixo);
  if(s) s.oninput = function(){
   R3.pos[p.eixo] = +s.value / 100;
   var v = r3El('r3_posv' + p.eixo); if(v) v.textContent = s.value + '%';
   r3Pintar(p.eixo);
  };
  var im = r3El('r3_img' + p.eixo);
  if(im) im.addEventListener('dblclick', function(){ r3Ampliar(p, im) });
 });
 var l = r3El('r3_laje');
 if(l) l.oninput = function(){ R3.laje = +l.value; r3El('r3_lajev').textContent = l.value + ' mm'; r3Proj() };
 var sp = r3El('r3_posp');
 if(sp) sp.oninput = function(){ R3.pos[R3.proj] = +sp.value / 100; r3Proj() };
 var ep = r3El('r3_eixop');
 if(ep) ep.onchange = function(){ R3.proj = +ep.value; r3Proj() };
 var lp = r3El('r3_lista_pasta');
 if(lp) lp.addEventListener('click', function(e){
  var it = e.target.closest ? e.target.closest('.r3-item') : null;
  if(it) r3Escolher(it);
 });
 var pa = r3El('r3_pasta');
 if(pa) pa.addEventListener('keydown', function(e){ if(e.key === 'Enter'){ e.preventDefault(); r3Outra() } });
 var fl = r3El('r3_filtro');
 if(fl) fl.addEventListener('input', function(){ if(window.r3mFiltrar) r3mFiltrar(fl.value) });
 if(window.r3mIniciar) r3mIniciar();
 if(window.r3vIniciar) r3vIniciar();
 if(R3.fer === 'vascular' && window.R3M) R3M.soVasos = true;
 if(window.uiPopupSerie)
  uiPopupSerie('r3_escolha', {sozinho: function(){ return !R3.ficha && !R3.b }});
 r3Ficha();
 r3Acervo();
}
window.addEventListener('DOMContentLoaded', r3IniciarTela);
"""

JS_DESENHO = u"""
var R3D = {cortes: {}, i: 0, modal: null, img: null, cv: null, tra: null};

function r3DesenhoPronto(){
 var b = r3El('r3_desenhar');
 if(b) b.disabled = !(R3.b && R3.forma);
 R3D.cortes = {}; r3DesenhoContar();
}
function r3DesenhoContar(){
 var n = Object.keys(R3D.cortes).filter(function(k){ return R3D.cortes[k].length }).length;
 var e = r3El('r3_dsn_n'); if(e) e.textContent = n ? String(n) : '';
 var l = r3El('r3d_lista');
 if(l){
  var ks = Object.keys(R3D.cortes).filter(function(k){ return R3D.cortes[k].length })
   .map(Number).sort(function(a, b){ return a - b });
  l.textContent = ks.length ? ks.map(function(k){ return k + 1 }).join(' · ') : '—';
 }
}
function r3DesenharAbrir(bt){
 if(!R3.b || !R3.forma) return;
 var Z = R3.forma[0];
 R3D.i = Math.round((Z - 1) * (R3.pos[0] || 0.5));
 var no = document.createElement('div');
 no.className = 'r3-dsn-m';
 no.innerHTML = '<div class="r3-dsn-palco"><img alt="" draggable="false"><canvas></canvas></div>'
  + '<div class="r3-dsn-cmd">'
  + '<p class="r3-dsn-dica">' + r3Frase('Contorne com o mouse em dois ou mais cortes: o volume é interpolado entre eles.') + '</p>'
  + '<label class="r3-dsn-rot">' + r3Frase('corte') + ' <b class="r3d-i"></b> / ' + Z + '</label>'
  + '<input type="range" class="r3d-pos" min="0" max="' + (Z - 1) + '" value="' + R3D.i + '" aria-label="corte axial">'
  + '<p class="r3-dsn-rot">' + r3Frase('cortes desenhados') + ': <b id="r3d_lista">—</b></p>'
  + '<div class="r3-dsn-bts">'
  + '<button type="button" class="ui-bt" data-r3d="limpar">' + r3Frase('Limpar este corte') + '</button>'
  + '<button type="button" class="ui-bt" data-r3d="tudo">' + r3Frase('Limpar tudo') + '</button>'
  + '<button type="button" class="ui-bt pri" data-r3d="montar">' + r3Frase('Montar o volume') + '</button>'
  + '</div><p class="r3-dsn-msg" role="status"></p></div>';
 R3D.img = no.querySelector('img'); R3D.cv = no.querySelector('canvas');
 R3D.modal = uiModal({titulo: 'Desenhar no axial', no: no, largura: 1040, origem: bt,
                      aoFechar: function(){ R3D.modal = null }});
 var pos = no.querySelector('.r3d-pos');
 pos.addEventListener('input', function(){ R3D.i = +pos.value; r3DesenhoCorte() });
 no.addEventListener('click', function(e){
  var b = e.target.closest ? e.target.closest('[data-r3d]') : null; if(!b) return;
  var a = b.getAttribute('data-r3d');
  if(a === 'limpar'){ delete R3D.cortes[R3D.i]; r3DesenhoPintar(); r3DesenhoContar() }
  else if(a === 'tudo'){ R3D.cortes = {}; r3DesenhoPintar(); r3DesenhoContar() }
  else if(a === 'montar') r3DesenhoMontar(no);
 });
 R3D.img.addEventListener('load', r3DesenhoPintar);
 r3DesenhoLigar(R3D.cv);
 if(window.ResizeObserver){ try{ new ResizeObserver(r3DesenhoPintar).observe(R3D.img.parentNode) }catch(e){} }
 r3DesenhoCorte(); r3DesenhoContar();
}
function r3DesenhoCorte(){
 var Z = R3.forma[0];
 var no = R3D.img && R3D.img.closest('.r3-dsn-m');
 if(no){ var e = no.querySelector('.r3d-i'); if(e) e.textContent = String(R3D.i + 1) }
 R3D.img.src = r3UrlDe(0, 0, Z > 1 ? R3D.i / (Z - 1) : 0, R3.jan, 'mip');
}
function r3DesenhoPintar(){
 var c = R3D.cv, im = R3D.img; if(!c || !im) return;
 var pal = im.parentNode;
 if(im.naturalWidth && pal){
  var W = pal.clientWidth, H = Math.max(240, Math.min(window.innerHeight * 0.66, 680));
  var k = Math.min(W / im.naturalWidth, H / im.naturalHeight);
  im.style.width = Math.round(im.naturalWidth * k) + 'px';
  im.style.height = Math.round(im.naturalHeight * k) + 'px';
 }
 var w = im.clientWidth, h = im.clientHeight;
 c.style.width = w + 'px'; c.style.height = h + 'px';
 c.style.left = im.offsetLeft + 'px'; c.style.top = im.offsetTop + 'px';
 var d = window.devicePixelRatio || 1;
 c.width = Math.max(1, Math.round(w * d)); c.height = Math.max(1, Math.round(h * d));
 var g = c.getContext('2d'); g.clearRect(0, 0, c.width, c.height);
 var cor = 'rgb(' + R3_COR_DESENHO.join(',') + ')';
 g.lineWidth = 2 * d; g.strokeStyle = cor; g.fillStyle = 'rgba(' + R3_COR_DESENHO.join(',') + ',0.18)';
 var polis = (R3D.cortes[R3D.i] || []).concat(R3D.tra ? [R3D.tra] : []);
 polis.forEach(function(p, k){
  if(p.length < 2) return;
  g.beginPath();
  p.forEach(function(q, j){ var x = q[0] * c.width, y = q[1] * c.height;
   if(j) g.lineTo(x, y); else g.moveTo(x, y) });
  if(p !== R3D.tra){ g.closePath(); g.fill() }
  g.stroke();
 });
}
function r3DesenhoLigar(c){
 function ponto(e){
  var r = c.getBoundingClientRect();
  return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
          Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
 }
 c.addEventListener('pointerdown', function(e){
  R3D.tra = [ponto(e)];
  try{ c.setPointerCapture(e.pointerId) }catch(_){}
  e.preventDefault();
 });
 c.addEventListener('pointermove', function(e){
  if(!R3D.tra) return;
  var p = ponto(e), u = R3D.tra[R3D.tra.length - 1];
  if(Math.abs(p[0] - u[0]) + Math.abs(p[1] - u[1]) < 0.003) return;
  R3D.tra.push(p); r3DesenhoPintar();
 });
 function fim(){
  var t = R3D.tra; R3D.tra = null;
  if(t && t.length >= 3){
   (R3D.cortes[R3D.i] = R3D.cortes[R3D.i] || []).push(t);
   r3DesenhoContar();
  }
  r3DesenhoPintar();
 }
 c.addEventListener('pointerup', fim);
 c.addEventListener('pointercancel', fim);
}
function r3DesenhoMontar(no){
 var Z = R3.forma[0], cortes = [];
 Object.keys(R3D.cortes).forEach(function(k){
  var polis = R3D.cortes[k]; if(!polis || !polis.length) return;
  cortes.push({pos: Z > 1 ? (+k) / (Z - 1) : 0, pontos: polis });
 });
 var msg = no.querySelector('.r3-dsn-msg');
 function diz(f){ if(window.uiTexto) uiTexto(msg, f); else msg.textContent = f }
 if(!cortes.length){ diz('desenhe em pelo menos um corte'); return }
 if(!R3G.gl){ diz('o desenho em 3D precisa de WebGL'); return }
 diz('montando o volume…');
 fetch('/api/recon3d/desenho', {method: 'POST', headers: {'Content-Type': 'application/json'},
   body: JSON.stringify({b: R3.b, cortes: cortes})})
  .then(function(r){
   if(!r.ok) return r.json().then(function(j){ throw new Error(j.erro || 'erro') });
   return r.arrayBuffer();
  })
  .then(function(buf){
   var m = r3gLerStl(buf);
   if(!m.T){ diz('nada desenhado'); return }
   r3mDesenho(m);
   if(R3D.modal) R3D.modal.fechar();
  })
  .catch(function(e){ diz((e && e.message) || 'não consegui montar o volume') });
}
"""

JS_GRAVAR = u"""
// GUARDA: grava só o visor 3D composto; nunca a página, a malha nem STL.
var R3V_TETO_S = 600;
var R3V_TIPOS = {mp4: ['video/mp4;codecs=avc1.42E01E', 'video/mp4;codecs=avc1',
                       'video/mp4'],
                 webm: ['video/webm;codecs=vp9', 'video/webm;codecs=vp8',
                        'video/webm']};
var R3V = {fmt: '', rec: null, partes: [], t0: 0, relogio: 0, cv: null,
           g: null, laco: 0, tipo: ''};

function r3vTipo(fmt){
 try{
  if(!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
  var l = R3V_TIPOS[fmt] || [];
  for(var i = 0; i < l.length; i++) if(MediaRecorder.isTypeSupported(l[i])) return l[i];
 }catch(e){}
 return '';
}
function r3vIniciar(){
 var bts = document.querySelectorAll('[data-r3v-fmt]');
 var algum = '';
 Array.prototype.forEach.call(bts, function(b){
  var f = b.getAttribute('data-r3v-fmt'), ok = !!r3vTipo(f);
  b.disabled = !ok;
  if(!ok) b.setAttribute('title', 'este navegador não grava neste formato');
  if(ok && !algum) algum = f;
 });
 var g = r3El('r3_gravar');
 R3V.podeGravar = !!algum;
 if(!algum){
  if(g){ g.disabled = true }
  r3vMsg('este navegador não grava vídeo');
  return;
 }
 r3vFormato(r3vTipo('mp4') ? 'mp4' : algum);
 r3vAtoMudou();
}
function r3vFormato(f){
 if(R3V.rec || !r3vTipo(f)) return;
 R3V.fmt = f;
 Array.prototype.forEach.call(document.querySelectorAll('[data-r3v-fmt]'), function(b){
  var sel = b.getAttribute('data-r3v-fmt') === f;
  b.setAttribute('aria-checked', sel ? 'true' : 'false');
  b.classList.toggle('on', sel);
 });
}
function r3vMsg(frase){
 var e = r3El('r3_grav_msg'); if(!e) return;
 if(window.uiTexto) window.uiTexto(e, frase || ''); else e.textContent = frase || '';
}
function r3vFontes(){
 if(R3M.modo === 'gl') return [r3El('cvGL'), r3El('cv3Db')];
 return [r3El('cv3D')];
}
// GUARDA: chamada no fim do desenho da malha, com o buffer do WebGL inteiro.
function r3vQuadro(){
 if(!R3V.rec || !R3V.g) return;
 var f = r3vFontes(), base = f[0]; if(!base) return;
 var w = base.width, h = base.height;
 if(R3V.cv.width !== w || R3V.cv.height !== h){ R3V.cv.width = w; R3V.cv.height = h }
 R3V.g.fillStyle = 'black';
 R3V.g.fillRect(0, 0, w, h);
 f.forEach(function(c){ if(c && !c.hidden && c.width) R3V.g.drawImage(c, 0, 0, w, h) });
}
function r3vLaco(){
 if(!R3V.rec) return;
 if(R3M.modo === 'gl') r3gDesenhar(); else r3vQuadro();
 R3V.laco = (window.requestAnimationFrame || setTimeout)(r3vLaco);
}
function r3vCrono(){
 var s = Math.floor((Date.now() - R3V.t0) / 1000);
 var t = ('0' + Math.floor(s / 60)).slice(-2) + ':' + ('0' + (s % 60)).slice(-2);
 ['r3_crono', 'r3_rec_t'].forEach(function(id){ var e = r3El(id); if(e) e.textContent = t });
 if(s >= R3V_TETO_S) r3vParar();
}
function r3vAlternar(){ if(R3V.rec) r3vParar(); else r3vGravar() }
function r3vAtoMarcado(){ var c = r3El('r3_grav_ato'); return !!(c && c.checked) }
function r3vAtoMudou(){
 var g = r3El('r3_gravar');
 if(g && !R3V.rec) g.disabled = !(R3V.podeGravar && r3vAtoMarcado());
}
// GUARDA: o video pode mostrar o rosto; o ato e declarado e registrado A CADA gravacao, antes de capturar.
function r3vGravar(){
 var tipo = r3vTipo(R3V.fmt);
 if(!tipo){ r3vMsg('este navegador não grava vídeo'); return }
 if(!R3M.b){ r3vMsg('escolha uma série antes de gravar'); return }
 if(!r3vAtoMarcado()){ r3vMsg('marque a declaração antes de gravar'); return }
 var g0 = r3El('r3_gravar'); if(g0) g0.disabled = true;
 fetch('/api/recon3d/ato-de-gravacao', {method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({formato: R3V.fmt})})
 .then(function(r){ return r.json().then(function(d){ return [r.ok, d] }) })
 .then(function(x){
  if(g0) g0.disabled = false;
  if(!x[0] || !x[1] || !x[1].ok){ r3vMsg('o ato não pôde ser registrado; a gravação não começou'); r3vAtoMudou(); return }
  r3vComecar(tipo);
 })
 .catch(function(){ if(g0) g0.disabled = false;
  r3vMsg('o ato não pôde ser registrado; a gravação não começou'); r3vAtoMudou() });
}
function r3vComecar(tipo){
 R3V.cv = document.createElement('canvas');
 R3V.g = R3V.cv.getContext('2d');
 var fluxo;
 try{ fluxo = R3V.cv.captureStream(30) }catch(e){ fluxo = null }
 if(!fluxo){ r3vMsg('este navegador não grava vídeo'); return }
 try{ R3V.rec = new MediaRecorder(fluxo, {mimeType: tipo, videoBitsPerSecond: 8000000}) }
 catch(e){ R3V.rec = null; r3vMsg('este navegador não grava vídeo'); return }
 R3V.tipo = tipo; R3V.partes = [];
 R3V.rec.ondataavailable = function(ev){ if(ev.data && ev.data.size) R3V.partes.push(ev.data) };
 R3V.rec.onstop = r3vSalvar;
 r3vQuadro();
 R3V.rec.start(1000);
 R3V.t0 = Date.now();
 R3V.relogio = setInterval(r3vCrono, 250);
 r3vCrono();
 var g = r3El('r3_gravar');
 if(g){ g.classList.add('gravando'); g.setAttribute('aria-pressed', 'true');
  var s = g.querySelector('[data-r3v-rot]');
  if(s){ if(window.uiTexto) window.uiTexto(s, 'Parar e salvar'); else s.textContent = 'Parar e salvar' } }
 var rec = r3El('r3_rec'); if(rec) rec.hidden = false;
 r3vMsg('gravando o visor 3D');
 r3vLaco();
}
function r3vParar(){
 if(!R3V.rec) return;
 clearInterval(R3V.relogio);
 try{ R3V.rec.stop() }catch(e){ r3vSalvar() }
}
function r3vNome(){
 var d = new Date(), z = function(n){ return ('0' + n).slice(-2) };
 return 'radioterapia_ai_reconstrucao3d_' + d.getFullYear() + z(d.getMonth() + 1)
  + z(d.getDate()) + '_' + z(d.getHours()) + z(d.getMinutes()) + z(d.getSeconds())
  + '.' + (R3V.fmt === 'mp4' ? 'mp4' : 'webm');
}
function r3vSalvar(){
 var partes = R3V.partes, tipo = R3V.tipo;
 R3V.rec = null; R3V.partes = []; R3V.g = null; R3V.cv = null;
 var g = r3El('r3_gravar');
 if(g){ g.classList.remove('gravando'); g.setAttribute('aria-pressed', 'false');
  var s = g.querySelector('[data-r3v-rot]');
  if(s){ if(window.uiTexto) window.uiTexto(s, 'Iniciar gravação'); else s.textContent = 'Iniciar gravação' } }
 var rec = r3El('r3_rec'); if(rec) rec.hidden = true;
 var ato = r3El('r3_grav_ato'); if(ato) ato.checked = false;
 r3vAtoMudou();
 if(!partes.length){ r3vMsg('nada foi gravado'); return }
 var video = new Blob(partes, {type: tipo.split(';')[0]});
 var url = URL.createObjectURL(video);
 var a = document.createElement('a');
 a.href = url; a.download = r3vNome(); a.hidden = true;
 document.body.appendChild(a); a.click();
 setTimeout(function(){ URL.revokeObjectURL(url); if(a.parentNode) a.parentNode.removeChild(a) }, 4000);
 r3vMsg('o vídeo foi para a pasta de downloads do navegador');
}
"""

JS_MALHA = radai_recon3d_gl.JS + u"""
var R3_EIXOS = ['esq', 'post', 'sup'];
// GUARDA: o zoom inicial é 25% acima do quadro que cabe a cena inteira.
var R3_ZOOM_INICIAL = 1.25;
var R3_TRANSICAO_MS = 2000;
// GUARDA: (direita, cima, frente) de cada vista; as seis são de mão direita.
var R3_VISTAS6 = {ant: ['esq', 'sup', 'ant'], post: ['dir', 'sup', 'post'],
                  esq: ['post', 'sup', 'esq'], dir: ['ant', 'sup', 'dir'],
                  sup: ['dir', 'ant', 'sup'], inf: ['esq', 'ant', 'inf']};
var R3G = {gl: null, canvas: null, prog: null, loc: {}, u32: null, objs: {},
           M: null, zoom: R3_ZOOM_INICIAL, ux: 0, uy: 0, centro: [0, 0, 0],
           raio: 100, pedido: false, anim: null};
var R3M = {modo: '', b: '', rs: '', arquivos: [], estr: [], cam: [],
           linhas: [], lig: {}, alfa: {}, st: {}, fila: [], ocupado: false,
           pedido: 0, caixa: null, nuvens: {}, pedidoN: 0, tn: 0, semTC: false,
           filtro: '', soVasos: false, preset: null, desenho: false,
           semSeg: false, baseN: 0, animN: null};
var R3_DESENHO = '#desenho';
var R3_COR_DESENHO = [250, 204, 21];

function r3gDetectar(){
 var c = r3El('cvGL');
 if(!c) return 'sem o quadro do 3D';
 var gl = null, op = {antialias: true, alpha: false, depth: true,
                      premultipliedAlpha: false};
 try{ gl = c.getContext('webgl', op) || c.getContext('experimental-webgl', op) }
 catch(e){ gl = null }
 if(!gl) return 'o navegador não criou um contexto WebGL';
 var V = {};
 var motivo = r3gPrograma(V, gl);
 if(motivo) return motivo;
 R3G.gl = gl; R3G.canvas = c; R3G.prog = V.prog; R3G.loc = V.loc; R3G.u32 = V.u32;
 return '';
}
function r3gM(){ if(!R3G.M) R3G.M = n3MatrizInicial(R3_EIXOS); return R3G.M }
function r3gPedir(){
 if(R3G.pedido || !R3G.gl) return;
 R3G.pedido = true;
 (window.requestAnimationFrame || setTimeout)(r3gDesenhar);
}

function r3gSubir(chave, m, cor){
 if(!R3G.gl) return;
 r3gSoltar(chave);
 var o = r3gSubirEm(R3G, m, cor);
 if(o) R3G.objs[chave] = o;
}
function r3gSoltar(chave){
 var o = R3G.objs[chave]; if(!o) return;
 r3gSoltarObj(R3G, o);
 delete R3G.objs[chave];
}
function r3gLimpar(){ Object.keys(R3G.objs).forEach(r3gSoltar) }

function r3gCena(caixa){
 if(caixa && caixa.length === 2){
  R3G.centro = [0, 1, 2].map(function(e){ return (caixa[0][e] + caixa[1][e]) / 2 });
  var dx = caixa[1][0] - caixa[0][0], dy = caixa[1][1] - caixa[0][1],
      dz = caixa[1][2] - caixa[0][2];
  R3G.raio = Math.max(10, Math.sqrt(dx*dx + dy*dy + dz*dz) / 2);
 }
 R3G.zoom = R3_ZOOM_INICIAL; R3G.ux = 0; R3G.uy = 0; R3G.anim = null;
 R3M.baseN = 0;
}

function r3gUm(o, alfa){ r3gUmEm(R3G, o, alfa) }
function r3gDesenhar(){
 R3G.pedido = false;
 var gl = R3G.gl, c = R3G.canvas; if(!gl || !c) return;
 r3gAjustar(c);
 var w = c.width, h = c.height;
 gl.viewport(0, 0, w, h);
 gl.clearColor(0, 0, 0, 1);
 gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
 var M = r3gM(), L = R3G.loc;
 gl.useProgram(R3G.prog);
 gl.enableVertexAttribArray(L.aPos); gl.enableVertexAttribArray(L.aNrm);
 var esc = R3G.zoom * 0.46 * Math.min(w, h) / R3G.raio;
 r3gCamera(R3G, r3gOrto(M, R3G.centro, 2 * esc / w, 2 * esc / h,
                        2 * R3G.ux / w, -2 * R3G.uy / h, 1 / (R3G.raio * 2.5)),
           r3gNrmDe(M));
 r3gCorte(R3G, null); r3gLiso(R3G, false);
 var opacos = [], trans = [];
 r3mVisiveis().forEach(function(par){
  var o = par[0], a = par[1];
  if(a >= 0.995) opacos.push(par);
  else if(a > 0.005){
   var p = o.centro, cc = R3G.centro;
   var z = M[6]*(p[0]-cc[0]) + M[7]*(p[1]-cc[1]) + M[8]*(p[2]-cc[2]);
   trans.push([o, a, z]);
  }
 });
 gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true);
 gl.disable(gl.BLEND); gl.disable(gl.CULL_FACE);
 opacos.forEach(function(par){ r3gUm(par[0], 1.0) });
 trans.sort(function(a, b){ return a[2] - b[2] });
 gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
 gl.depthMask(false); gl.enable(gl.CULL_FACE);
 trans.forEach(function(par){
  gl.cullFace(gl.FRONT); r3gUm(par[0], par[1]);
  gl.cullFace(gl.BACK); r3gUm(par[0], par[1]);
 });
 gl.depthMask(true); gl.disable(gl.BLEND); gl.disable(gl.CULL_FACE);
 var cb = r3El('cv3Db');
 if(cb && typeof n3Bussola === 'function'){
  r3gAjustar(cb);
  var g = cb.getContext('2d');
  g.clearRect(0, 0, cb.width, cb.height);
  if(window.N3) N3.eixos = R3_EIXOS;
  n3Bussola(g, cb, M);
 }
 if(typeof r3IncSincronizar === 'function') r3IncSincronizar();
 if(window.r3vQuadro) r3vQuadro();
}

function r3gLigar(c){
 var ax = 0, ay = 0, arr = false, mover = false;
 c.addEventListener('pointerdown', function(e){
  arr = true; mover = e.shiftKey || e.button === 2 || e.button === 1;
  ax = e.clientX; ay = e.clientY;
  try{ c.setPointerCapture(e.pointerId) }catch(_){}
  e.preventDefault();
 });
 c.addEventListener('pointermove', function(e){
  if(!arr) return;
  var dx = e.clientX - ax, dy = e.clientY - ay;
  ax = e.clientX; ay = e.clientY;
  if(mover){ var d = window.devicePixelRatio || 1; R3G.ux += dx * d; R3G.uy += dy * d }
  else { R3G.anim = null; R3G.M = n3Girar(r3gM(), dx, dy) }
  r3gPedir();
 });
 function solta(e){ arr = false; try{ c.releasePointerCapture(e.pointerId) }catch(_){} }
 c.addEventListener('pointerup', solta);
 c.addEventListener('pointercancel', solta);
 c.addEventListener('contextmenu', function(e){ e.preventDefault() });
 c.addEventListener('wheel', function(e){
  e.preventDefault();
  R3G.zoom = Math.max(0.2, Math.min(25, R3G.zoom * ((e.deltaY < 0) ? 1.12 : 0.89)));
  r3gPedir();
 }, {passive: false});
 c.addEventListener('webglcontextlost', function(e){
  e.preventDefault();
  r3mRecuo('o contexto WebGL foi perdido (o driver de vídeo reiniciou)');
 });
 window.addEventListener('resize', r3gPedir);
 if(window.ResizeObserver){
  try{ new ResizeObserver(function(){ r3gPedir() }).observe(c) }catch(_){}
 }
}

function r3MatrizDaVista6(nome){
 var t = R3_VISTAS6[nome]; if(!t) return null;
 var X = n3Dir(t[0], R3_EIXOS), Y = n3Dir(t[1], R3_EIXOS), Z = n3Dir(t[2], R3_EIXOS);
 if(!X || !Y || !Z) return null;
 return [X[0], X[1], X[2], Y[0], Y[1], Y[2], Z[0], Z[1], Z[2]];
}
function r3Quat(M){
 var m00 = M[0], m01 = M[1], m02 = M[2], m10 = M[3], m11 = M[4], m12 = M[5],
     m20 = M[6], m21 = M[7], m22 = M[8], tr = m00 + m11 + m22, s, q;
 if(tr > 0){ s = Math.sqrt(tr + 1) * 2;
  q = [0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s] }
 else if(m00 > m11 && m00 > m22){ s = Math.sqrt(1 + m00 - m11 - m22) * 2;
  q = [(m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s] }
 else if(m11 > m22){ s = Math.sqrt(1 + m11 - m00 - m22) * 2;
  q = [(m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s] }
 else { s = Math.sqrt(1 + m22 - m00 - m11) * 2;
  q = [(m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s] }
 var n = Math.sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3]) || 1;
 return [q[0] / n, q[1] / n, q[2] / n, q[3] / n];
}
function r3MatrizDoQuat(q){
 var w = q[0], x = q[1], y = q[2], z = q[3];
 return [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y),
         2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x),
         2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)];
}
function r3Slerp(a, b, t){
 var d = a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3];
 if(d < 0){ b = [-b[0], -b[1], -b[2], -b[3]]; d = -d }
 if(d > 0.9995){
  var r = [a[0] + t*(b[0]-a[0]), a[1] + t*(b[1]-a[1]), a[2] + t*(b[2]-a[2]), a[3] + t*(b[3]-a[3])];
  var n = Math.sqrt(r[0]*r[0] + r[1]*r[1] + r[2]*r[2] + r[3]*r[3]) || 1;
  return [r[0] / n, r[1] / n, r[2] / n, r[3] / n];
 }
 var th = Math.acos(Math.min(1, d)), s = Math.sin(th);
 var ka = Math.sin((1 - t) * th) / s, kb = Math.sin(t * th) / s;
 return [ka*a[0] + kb*b[0], ka*a[1] + kb*b[1], ka*a[2] + kb*b[2], ka*a[3] + kb*b[3]];
}
function r3Suave(t){ return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2 }
function r3MenosMovimento(){
 try{ return !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) }
 catch(e){ return false }
}
function r3Animar(alvo, ms){
 var de = r3Quat(r3gM()), para = r3Quat(alvo);
 var ux0 = R3G.ux, uy0 = R3G.uy, t0 = Date.now(), meu = {};
 R3G.anim = meu;
 function passo(){
  if(R3G.anim !== meu) return;
  var t = Math.min(1, (Date.now() - t0) / ms), k = r3Suave(t);
  R3G.M = r3MatrizDoQuat(r3Slerp(de, para, k));
  R3G.ux = ux0 * (1 - k); R3G.uy = uy0 * (1 - k);
  if(t >= 1){ R3G.M = alvo.slice(); R3G.anim = null }
  r3gDesenhar();
  if(R3G.anim === meu) (window.requestAnimationFrame || setTimeout)(passo);
 }
 passo();
}
function r3AnimarNuvem(alvo, ms){
 var de = r3Quat(n3M()), para = r3Quat(alvo);
 var ux0 = N3.ux || 0, uy0 = N3.uy || 0, t0 = Date.now(), meu = {};
 R3M.animN = meu;
 function passo(){
  if(R3M.animN !== meu) return;
  var t = Math.min(1, (Date.now() - t0) / ms), k = r3Suave(t);
  N3.M = r3MatrizDoQuat(r3Slerp(de, para, k));
  N3.chaveM = JSON.stringify(N3.eixos || null);
  N3.ux = ux0 * (1 - k); N3.uy = uy0 * (1 - k);
  if(t >= 1){ N3.M = alvo.slice(); R3M.animN = null }
  n3Desenhar();
  if(R3M.animN === meu) (window.requestAnimationFrame || setTimeout)(passo);
 }
 passo();
}
function r3VistaNuvem(qual){
 if(typeof n3Desenhar !== 'function' || typeof N3 === 'undefined') return;
 var M = (qual === 'inicial') ? n3MatrizInicial(R3_EIXOS) : r3MatrizDaVista6(qual);
 if(!M) return;
 if(qual === 'inicial' && R3M.baseN) N3.escala = R3M.baseN * R3_ZOOM_INICIAL;
 if(r3MenosMovimento()){
  R3M.animN = null; N3.M = M; N3.chaveM = JSON.stringify(N3.eixos || null);
  N3.ux = 0; N3.uy = 0; n3Desenhar(); return;
 }
 r3AnimarNuvem(M, R3_TRANSICAO_MS);
}
function r3Vista(qual){
 if(R3M.modo !== 'gl'){ r3VistaNuvem(qual); return }
 var M = (qual === 'inicial') ? n3MatrizInicial(R3_EIXOS) : r3MatrizDaVista6(qual);
 if(!M) return;
 if(qual === 'inicial') R3G.zoom = R3_ZOOM_INICIAL;
 if(r3MenosMovimento() || !R3G.gl){
  R3G.anim = null; R3G.M = M; R3G.ux = 0; R3G.uy = 0; r3gPedir(); return;
 }
 r3Animar(M, R3_TRANSICAO_MS);
}

function r3IncAng(v, pos, neg){
 var n = Math.round(+v || 0);
 return (n < 0 ? neg : pos) + ' ' + Math.abs(n) + '°';
}
function r3MatrizDaIncidencia(lao, cra){
 var b = radaiIncidencia(lao, cra);
 return [b.r[0], b.r[1], b.r[2], b.u[0], b.u[1], b.u[2], b.d[0], b.d[1], b.d[2]];
}
// GUARDA: a frente da tela (linha 3 de M) é o detector; dela saem o LAO e o CRA da convenção do Nidus.
function r3IncDe(M){
 var cra = Math.asin(Math.max(-1, Math.min(1, M[8]))) * 180 / Math.PI;
 var lao = (Math.abs(M[8]) > 0.99999) ? 0 : Math.atan2(M[6], -M[7]) * 180 / Math.PI;
 return [Math.round(lao), Math.round(cra)];
}
function r3IncSincronizar(lao, cra){
 var r = r3El('r3_lao'), c = r3El('r3_cra');
 if(!r || !c) return;
 if(lao == null){
  var M = (R3M.modo === 'gl') ? R3G.M : ((typeof N3 !== 'undefined') ? N3.M : null);
  if(!M) return;
  var a = r3IncDe(M); lao = a[0]; cra = a[1];
 }
 if(R3M.incVisto === lao + ',' + cra) return;
 R3M.incVisto = lao + ',' + cra;
 r.value = String(lao); c.value = String(cra);
 var lv = r3El('r3_lao_v'), cv = r3El('r3_cra_v');
 if(lv) lv.textContent = r3IncAng(lao, 'LAO', 'RAO');
 if(cv) cv.textContent = r3IncAng(cra, 'CRA', 'CAU');
 var bs = document.querySelectorAll ? document.querySelectorAll('.r3-inc') : [];
 for(var i = 0; i < bs.length; i++)
  bs[i].setAttribute('aria-pressed', (+bs[i].getAttribute('data-lao') === lao
   && +bs[i].getAttribute('data-cra') === cra) ? 'true' : 'false');
}
function r3IncAplicar(lao, cra, animar){
 var M = r3MatrizDaIncidencia(lao, cra);
 if(R3M.modo !== 'gl'){
  if(typeof N3 !== 'undefined' && typeof n3Desenhar === 'function'){
   R3M.animN = null; N3.M = M; N3.chaveM = JSON.stringify(N3.eixos || null);
   N3.ux = 0; N3.uy = 0; n3Desenhar();
  }
 } else if(animar && R3G.gl && !r3MenosMovimento()){
  r3Animar(M, R3_TRANSICAO_MS);
 } else {
  R3G.anim = null; R3G.M = M; r3gPedir();
 }
 r3IncSincronizar(Math.round(lao), Math.round(cra));
}
function r3IncBarra(){
 var r = r3El('r3_lao'), c = r3El('r3_cra'); if(!r || !c) return;
 r3IncAplicar(+r.value || 0, +c.value || 0, false);
}
var R3_ATRAVES = {osso: 0.1, pele: 0.03};
function r3AtravesAlvo(k){
 if(k === '@osso') return R3_ATRAVES.osso;
 if(k === '@pele') return R3_ATRAVES.pele;
 for(var i = 0; i < R3M.estr.length; i++){
  var e = R3M.estr[i];
  if(e.nome !== k) continue;
  if(e.casca) return R3_ATRAVES.pele;
  if(e.osso) return R3_ATRAVES.osso;
 }
 return null;
}
function r3AtravesPintar(){
 var b = r3El('r3_atraves'); if(!b) return;
 b.setAttribute('aria-pressed', R3M.atraves ? 'true' : 'false');
 b.disabled = (R3M.modo !== 'gl');
}
// GUARDA: o Ver através guarda a opacidade de antes e a devolve; nunca sobe a de quem já estava mais baixa.
function r3Atraves(){
 if(R3M.modo !== 'gl') return;
 if(!R3M.atraves){
  R3M.atravesAntes = {};
  r3mChaves().forEach(function(k){
   var a = r3AtravesAlvo(k); if(a == null) return;
   var atual = (R3M.alfa[k] == null) ? 1 : R3M.alfa[k];
   R3M.atravesAntes[k] = R3M.alfa[k];
   R3M.alfa[k] = Math.min(a, atual);
  });
  R3M.atraves = true;
 } else {
  for(var k in (R3M.atravesAntes || {})) R3M.alfa[k] = R3M.atravesAntes[k];
  R3M.atravesAntes = {}; R3M.atraves = false;
 }
 r3AtravesPintar(); r3mPintarLista(); r3gPedir();
}

function r3mIniciar(){
 r3mOuvir();
 var motivo = r3gDetectar();
 if(motivo){ r3mRecuo(motivo); return }
 R3M.modo = 'gl';
 var c = r3El('cvGL'), n = r3El('cv3D'), b = r3El('cv3Db');
 if(c) c.hidden = false; if(b) b.hidden = false; if(n) n.hidden = true;
 r3mModo('WebGL');
 r3gLigar(c);
 r3AtravesPintar();
 r3gPedir();
}
function r3mRecuo(motivo){
 var jaEra = (R3M.modo === 'nuvem');
 R3M.modo = 'nuvem';
 R3G.gl = null;
 var c = r3El('cvGL'), n = r3El('cv3D'), b = r3El('cv3Db');
 if(c) c.hidden = true; if(b) b.hidden = true; if(n) n.hidden = false;
 var av = r3El('r3_aviso3d');
 if(av){
  av.hidden = false;
  var m = r3El('r3_motivo3d'); if(m) m.textContent = motivo || '';
 }
 r3mModo('nuvem de pontos');
 R3M.atraves = false; r3AtravesPintar();
 if(!jaEra && R3M.estr.length){ r3mPintarLista(); r3mSincronizar() }
}
function r3mModo(t){
 var e = r3El('r3_modo3d'); if(!e) return;
 if(window.uiTexto) window.uiTexto(e, t); else e.textContent = t;
}
function r3mDica(html){
 var e = r3El('dica3d'); if(!e) return;
 if(window.uiHTML) window.uiHTML(e, html); else e.innerHTML = html;
}

function r3mAbrir(b){
 R3M.b = b; R3M.rs = ''; R3M.desenho = false; R3M.semSeg = false;
 r3gLimpar(); R3M.nuvens = {};
 R3M.semTC = false;
 r3mEstruturas((R3M.preset && R3M.preset.rs) || '');
}
function r3mSemTC(){
 R3M.semTC = true;
 R3M.cam = [];
 r3mPintarLista();
}
function r3mEstruturas(rs){
 var meu = ++R3M.pedido;
 R3M.fila = []; R3M.ocupado = false;
 R3M.estr = []; R3M.cam = []; R3M.linhas = [];
 r3mPintarLista();
 r3mDica('<span data-radai-frase>lendo o RTSTRUCT…</span>');
 fetch('/api/recon3d/estruturas', {method: 'POST',
   headers: {'Content-Type': 'application/json'},
   body: JSON.stringify({b: R3M.b, rs: rs || ''})})
  .then(function(r){ return r.json() })
  .then(function(d){
   if(meu !== R3M.pedido) return;
   if(d.erro && !(d.estruturas || []).length){
    if(rs && R3M.preset){ R3M.preset.rs = ''; r3mEstruturas(''); return }
    if(window.r3AoCarregar) r3AoCarregar(d);
    r3mDica('<span data-radai-frase>' + r3Esc(d.erro) + '</span>'
            + (d.tipo ? ' <code>' + r3Esc(d.tipo) + '</code>' : ''));
    return;
   }
   R3M.rs = d.rs || ''; R3M.arquivos = d.arquivos || [];
   R3M.estr = (d.estruturas || []).filter(function(e){
    return !R3M.soVasos || e.vaso });
   R3M.semSeg = !!d.sem_segmentacao;
   R3M.atraves = false; R3M.atravesAntes = {}; r3AtravesPintar();
   R3M.cam = R3M.semTC ? [] : (d.camadas || []);
   R3M.caixa = d.caixa || null;
   r3gCena(R3M.caixa);
   var todas = R3M.estr.length <= (+d.marcar_ate || 45);
   R3M.lig = {}; R3M.alfa = {}; R3M.st = {};
   R3M.estr.forEach(function(e){
    R3M.lig[e.nome] = todas && (R3M.modo === 'gl' || +e.opacidade >= 0.5);
    R3M.alfa[e.nome] = +e.opacidade;
   });
   R3M.cam.forEach(function(c){
    var k = '@' + c.camada;
    R3M.lig[k] = !R3M.estr.length && !R3M.soVasos; R3M.alfa[k] = +c.opacidade;
   });
   var pre = R3M.preset; R3M.preset = null;
   if(pre && pre.nomes && pre.nomes.length){
    var quer = {};
    pre.nomes.forEach(function(n){ quer[n] = 1 });
    R3M.estr.forEach(function(e){ R3M.lig[e.nome] = !!quer[e.nome] });
   }
   if(window.r3AoCarregar) r3AoCarregar(d);
   r3mPintarArquivos();
   r3mPintarLista();
   r3mSincronizar();
  })
  .catch(function(){
   if(meu !== R3M.pedido) return;
   if(window.r3AoCarregar) r3AoCarregar(null);
   r3mDica('<span data-radai-frase>não consegui ler este RTSTRUCT</span>');
  });
}
function r3mPintarArquivos(){
 var s = r3El('r3_rs'); if(!s) return;
 s.innerHTML = R3M.arquivos.map(function(a){
  return '<option value="' + r3Esc(a.arquivo) + '"'
    + (a.arquivo === R3M.rs ? ' selected' : '') + '>'
    + r3Esc(a.nome || a.conjunto || a.arquivo) + '</option>';
 }).join('');
}
function r3mTrocarArquivo(){
 var s = r3El('r3_rs'); if(!s || !s.value || s.value === R3M.rs) return;
 R3M.nuvens = {};
 r3mEstruturas(s.value);
}

function r3mChave(k){
 var c = k.charAt(0); return (c === '@' || c === '#') ? k : (R3M.rs + '|' + k) }
function r3mCor(k){
 if(k === R3_DESENHO) return R3_COR_DESENHO;
 if(k.charAt(0) === '@'){
  for(var i = 0; i < R3M.cam.length; i++)
   if('@' + R3M.cam[i].camada === k) return R3M.cam[i].cor;
  return [200, 200, 200];
 }
 for(var j = 0; j < R3M.estr.length; j++)
  if(R3M.estr[j].nome === k) return R3M.estr[j].cor;
 return [170, 170, 170];
}
function r3mChaves(){
 return (R3M.desenho ? [R3_DESENHO] : [])
  .concat(R3M.estr.map(function(e){ return e.nome }))
  .concat(R3M.cam.map(function(c){ return '@' + c.camada }));
}
function r3mVisiveis(){
 var fora = [];
 r3mChaves().forEach(function(k){
  var o = R3G.objs[r3mChave(k)];
  if(o && R3M.lig[k]) fora.push([o, R3M.alfa[k]]);
 });
 return fora;
}

function r3mPintarLista(){
 var alvo = r3El('r3_estr'); if(!alvo) return;
 R3M.linhas = r3mChaves();
 var semGL = (R3M.modo !== 'gl');
 var OPAC_CAMADA = {osso: 'opacidade da camada de osso',
                    pele: 'opacidade da camada de pele'};
 function linha(k, i, nome){
  var a = Math.round(100 * (R3M.alfa[k] == null ? 1 : R3M.alfa[k]));
  var cor = r3mCor(k);
  var camada = (k.charAt(0) === '@');
  var rotA = (camada && OPAC_CAMADA[nome]) ? OPAC_CAMADA[nome]
             : 'opacidade de %s'.replace('%s', nome);
  var desenho = (k === R3_DESENHO);
  var oculta = !camada && !desenho && R3M.filtro
               && nome.toLowerCase().indexOf(R3M.filtro) < 0;
  return '<div class="r3e' + (desenho ? ' desenho' : '') + '" data-i="' + i + '"'
   + (oculta ? ' hidden' : '') + '>'
   + '<label class="r3e-l"><input type="checkbox" class="r3e-c"'
   + (R3M.lig[k] ? ' checked' : '') + '>'
   + '<i class="r3e-sw" style="background:rgb(' + cor.join(',') + ')"></i>'
   + ((camada || desenho)
      ? '<span class="r3e-n" data-radai-frase>' + r3Esc(desenho ? 'desenho do axial' : nome) + '</span></label>'
      : '<span class="r3e-n" translate="no" data-radai-t="1" title="' + r3Esc(nome)
        + '">' + r3Esc(nome) + '</span></label>')
   + '<input type="range" class="r3e-a" min="0" max="100" step="5" value="' + a + '"'
   + (semGL ? ' disabled' : '') + ' aria-label="' + r3Esc(rotA) + '">'
   + '<b class="r3e-v">' + a + '%</b>'
   + '<span class="r3e-s ' + (R3M.st[k] || '') + '"></span></div>';
 }
 var h = '';
 R3M.linhas.forEach(function(k, i){
  if(k.charAt(0) === '@') return;
  h += linha(k, i, k);
 });
 if(!R3M.estr.length) h += '<p class="sub" style="padding:6px 10px">—</p>';
 var hc = '';
 R3M.linhas.forEach(function(k, i){
  if(k.charAt(0) !== '@') return;
  hc += linha(k, i, k.slice(1));
 });
 alvo.innerHTML = h;
 var ac = r3El('r3_camadas3d');
 if(ac) ac.innerHTML = hc;
 var cab = r3El('r3_cab_camadas');
 if(cab) cab.hidden = !hc;
 r3mContar();
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(x){}
}
function r3mContar(){
 var e = r3El('r3_conta'); if(!e) return;
 var n = R3M.estr.filter(function(x){ return R3M.lig[x.nome] }).length;
 e.textContent = n + '/' + R3M.estr.length;
}
function r3mOuvir(){
 var nv = r3El('cv3D');
 if(nv) nv.addEventListener('contextmenu', function(e){ e.preventDefault() });
 ['r3_estr', 'r3_camadas3d'].forEach(function(id){
  var alvo = r3El(id); if(!alvo) return;
  alvo.addEventListener('change', function(ev){
   var t = ev.target; if(!t || !t.classList.contains('r3e-c')) return;
   var k = R3M.linhas[+t.closest('.r3e').getAttribute('data-i')];
   if(k == null) return;
   R3M.lig[k] = !!t.checked; r3mContar(); r3mSincronizar();
  });
  alvo.addEventListener('input', function(ev){
   var t = ev.target; if(!t || !t.classList.contains('r3e-a')) return;
   var ln = t.closest('.r3e'), k = R3M.linhas[+ln.getAttribute('data-i')];
   if(k == null) return;
   R3M.alfa[k] = (+t.value) / 100;
   var v = ln.querySelector('.r3e-v'); if(v) v.textContent = t.value + '%';
   r3gPedir();
  });
 });
}
function r3mTodas(sim){
 R3M.estr.forEach(function(e){
  if(R3M.filtro && e.nome.toLowerCase().indexOf(R3M.filtro) < 0) return;
  R3M.lig[e.nome] = !!sim });
 r3mPintarLista(); r3mSincronizar();
}
function r3mStatus(k){
 var i = R3M.linhas.indexOf(k); if(i < 0) return;
 var el = document.querySelector('.r3e[data-i="' + i + '"] .r3e-s');
 if(el) el.className = 'r3e-s ' + (R3M.st[k] || '');
}

function r3mSincronizar(){
 if(window.r3PintarPlanos) r3PintarPlanos();
 if(R3M.modo === 'nuvem'){ r3nCarregar(); return }
 var falta = r3mChaves().filter(function(k){
  return k.charAt(0) !== '#' && R3M.lig[k] && !R3G.objs[r3mChave(k)] && R3M.st[k] !== 'erro'
         && R3M.fila.indexOf(k) < 0 && R3M.st[k] !== 'montando';
 });
 falta.sort(function(a, b){ return (R3M.alfa[b] || 0) - (R3M.alfa[a] || 0) });
 falta.forEach(function(k){ R3M.fila.push(k); R3M.st[k] = 'fila'; r3mStatus(k) });
 r3gPedir();
 r3mProximo();
}
function r3mProximo(){
 if(R3M.ocupado) return;
 var k;
 while(R3M.fila.length){
  k = R3M.fila.shift();
  if(R3M.lig[k] && !R3G.objs[r3mChave(k)]) break;
  if(R3M.st[k] === 'fila'){ R3M.st[k] = ''; r3mStatus(k) }
  k = undefined;
 }
 if(k === undefined){ r3mPronto(); return }
 R3M.ocupado = true; R3M.st[k] = 'montando'; r3mStatus(k);
 r3mAndamento();
 var meu = R3M.pedido, chave = r3mChave(k);
 var corpo = (k.charAt(0) === '@') ? {b: R3M.b, camada: k.slice(1)}
                                   : {b: R3M.b, rs: R3M.rs, nome: k};
 fetch('/api/recon3d/malha', {method: 'POST',
   headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)})
  .then(function(r){
   if(!r.ok) return r.json().then(function(j){ throw new Error(j.erro || ('HTTP ' + r.status)) });
   return r.arrayBuffer();
  })
  .then(function(buf){
   if(meu !== R3M.pedido) return;
   var m = r3gLerStl(buf);
   r3gSubir(chave, m, r3mCor(k));
   R3M.st[k] = m.T ? '' : 'erro';
  })
  .catch(function(e){
   if(meu !== R3M.pedido) return;
   R3M.st[k] = 'erro';
   var i = R3M.linhas.indexOf(k);
   var el = document.querySelector('.r3e[data-i="' + i + '"] .r3e-s');
   if(el) el.title = (e && e.message) || '';
  })
  .then(function(){
   if(meu !== R3M.pedido) return;
   R3M.ocupado = false; r3mStatus(k); r3gPedir(); r3mProximo();
  });
}
function r3mAndamento(){
 var total = 0, prontas = 0;
 r3mChaves().forEach(function(k){
  if(!R3M.lig[k]) return;
  total++;
  if(R3G.objs[r3mChave(k)]) prontas++;
 });
 r3mDica('<span data-radai-frase>montando as malhas</span> <b>'
         + prontas + '/' + total + '</b>');
}
function r3mPronto(){
 var n = r3mVisiveis().length;
 if(!n && !R3M.estr.length){ r3mDica('<span data-radai-frase>nenhuma camada ligada</span>'); return }
 if(!n){ r3mDica('<span data-radai-frase>marque uma estrutura para ver em 3D</span>'); return }
 r3mDica('<span data-radai-frase>arraste para girar · roda para aproximar · botão direito para mover</span>');
}

function r3nCarregar(){
 clearTimeout(R3M.tn);
 R3M.tn = setTimeout(function(){
  var nomes = R3M.estr.filter(function(e){
   return R3M.lig[e.nome] && !R3M.nuvens[R3M.rs + '|' + e.nome] }).map(function(e){ return e.nome });
  var camadas = R3M.cam.filter(function(c){
   return R3M.lig['@' + c.camada] && !R3M.nuvens['@' + c.camada] }).map(function(c){ return c.camada });
  if(!nomes.length && !camadas.length){ r3nMostrar(); return }
  var meu = ++R3M.pedidoN;
  r3mDica('<span data-radai-frase>montando a nuvem de pontos…</span>');
  fetch('/api/recon3d/nuvem', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({b: R3M.b, rs: R3M.rs, nomes: nomes.slice(0, 24),
                          camadas: camadas})})
   .then(function(r){ return r.json() })
   .then(function(d){
    if(meu !== R3M.pedidoN) return;
    (d.itens || []).forEach(function(it){
     var k = it.camada ? ('@' + it.camada) : (R3M.rs + '|' + it.nome);
     R3M.nuvens[k] = it;
    });
    r3nMostrar(d.erro);
    if(nomes.length > 24) r3nCarregar();
   })
   .catch(function(){ if(meu === R3M.pedidoN) r3nMostrar('não consegui montar o 3D') });
 }, 250);
}
function r3nMostrar(erro){
 if(typeof n3Mostrar !== 'function') return;
 var c = R3G.centro, itens = [];
 r3mChaves().forEach(function(k){
  if(!R3M.lig[k]) return;
  var it = R3M.nuvens[k.charAt(0) === '@' ? k : (R3M.rs + '|' + k)];
  if(!it) return;
  itens.push({cor: it.cor, normais: it.normais,
              pontos: (it.pontos || []).map(function(p){
               return [p[0] - c[0], p[1] - c[1], p[2] - c[2]] })});
 });
 var zoom = (R3M.baseN && N3.escala) ? N3.escala / R3M.baseN : R3_ZOOM_INICIAL;
 n3Mostrar({itens: itens, eixos: R3_EIXOS, erro: itens.length ? '' : (erro || '')},
           itens.length ? 'arraste para girar' : 'marque uma estrutura para ver em 3D');
 if(N3.escala > 0){
  R3M.baseN = N3.escala; N3.escala = R3M.baseN * zoom;
  if(typeof n3Desenhar === 'function') n3Desenhar();
 }
}

function r3mFiltrar(txt){
 R3M.filtro = String(txt || '').trim().toLowerCase();
 r3mPintarLista();
}
function r3mDesenho(m){
 if(!R3G.gl) return false;
 r3gSubir(R3_DESENHO, m, R3_COR_DESENHO);
 R3M.desenho = true; R3M.lig[R3_DESENHO] = true;
 if(R3M.alfa[R3_DESENHO] == null) R3M.alfa[R3_DESENHO] = 0.7;
 r3mPintarLista(); r3gPedir();
 return true;
}
"""


FERRAMENTAS_3D = {
    "geral": {"chave_menu": "recon_anatomia", "rota": "/recon3d/anatomia",
              "icone": u"cubo", "nome": u"Anatomia geral",
              "frase": (u"Visualize cada órgão, com ajuste de transparências "
                        u"no visor 3D, além da segmentação nos 3 planos "
                        u"(axial, sagital e coronal) e MIP e MinIP com laje "
                        u"ajustável."),
              "protocolo": u""},
    "toracica": {"chave_menu": "recon_torax", "rota": "/recon3d/toracica",
                 "icone": u"pulmoes", "nome": u"Anatomia torácica",
                 "frase": (u"Reconstrução das tarefas geradas pelo protocolo "
                           u"do ContourLab: Lobos, mediastino, "
                           u"vascularização, algoritmo de nódulos pulmonares "
                           u"e muito mais."),
                 "protocolo": u"anatomia_toracica"},
    "vascular": {"chave_menu": "recon_vascular", "rota": "/recon3d/vascular",
                 "icone": u"vaso", "nome": u"Vascular",
                 "frase": (u"Superfície, trajeto dos vasos e projeções "
                           u"bidimensionais sintéticas a partir da "
                           u"segmentação de vasos"),
                 "protocolo": u""},
}

PROTOCOLO_TORACICO = u"anatomia_toracica"

def _ajuda_exporta():
    import html
    import re
    import radai_modules
    longo = radai_modules.SEM_EXPORTACAO["recon3d"]
    miolo = html.unescape(re.sub(r"<[^>]+>", u"", longo))
    return (u" ".join(miolo.split()),
            u"O vídeo do visor 3D, quando você grava, vai para a pasta de "
            u"downloads do navegador.")


AJUDA_EXPORTA = _ajuda_exporta()

AJUDA_DA_TELA = {
    "geral": (
        u"A malha sai do RTSTRUCT ou do mapa de rótulos da série; sem "
        u"segmentação, o 3D mostra osso e pele pela densidade da TC.",
        ) + AJUDA_EXPORTA,
    "toracica": (
        u"Abre as séries que rodaram o protocolo Anatomia Torácica no "
        u"PERSONALIZADO do Rodar agora.",
        u"O desenho no axial é seu: interpolado entre os cortes, aparece no "
        u"3D e não é gravado.") + AJUDA_EXPORTA,
}

ALERTA_DA_TELA = (u"Visualização de estudo &mdash; <b>não exporta malha nem "
                  u"estrutura</b>")

AVISO_DA_GRAVACAO = (u"O vídeo pode mostrar o rosto do paciente: é dado de "
                     u"paciente. Ele vai para a pasta de downloads do "
                     u"navegador, que pode estar numa pasta que sincroniza "
                     u"com a nuvem.")
AVISO_CURTO_DA_GRAVACAO = u"pode conter o rosto; é dado de paciente"
ATO_DA_GRAVACAO = (u"Entendo que este vídeo é dado de paciente e declaro esta "
                   u"gravação.")
ARQUIVO_ATOS_DO_VIDEO = "radai_recon3d_atos.log"


def _ajuda_da_gravacao():
    import radai_ui
    return radai_ui.ajuda(AVISO_DA_GRAVACAO, direita=True)


def arquivo_de_atos_do_video():
    import radai_archive
    return os.path.join(str(radai_archive.raiz()), ARQUIVO_ATOS_DO_VIDEO)


def linha_do_ato_do_video(formato):
    return (u"gravacao do visor 3D (%s): ato declarado -- o video pode mostrar "
            u"o rosto e e dado de paciente; vai para a pasta de downloads do "
            u"navegador" % formato)


def gravar_ato_do_video(formato):
    import io
    import time
    caminho = arquivo_de_atos_do_video()
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with io.open(caminho, "a", encoding="utf-8", newline="\n") as f:
        f.write(u"[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                linha_do_ato_do_video(formato)))
        f.flush()
        os.fsync(f.fileno())
    return caminho


def _html_cabeca(fer, ajuda_paragrafos):
    import radai_ui
    f = FERRAMENTAS_3D[fer]
    return radai_ui.cabeca_de_funcao(
        f["icone"], f["nome"], f["frase"],
        radai_ui.ajuda(*ajuda_paragrafos), u"recon3d")


def _html_passo_serie():
    import radai_tabela_acervo
    import radai_ui
    acervo = radai_tabela_acervo.html(u"r3_acervo")
    pasta = (u'<div class="r3-pasta">'
             u'<div class="r3-pasta-campo">'
             u'<input type="text" id="r3_pasta" autocomplete="off" '
             u'spellcheck="false" placeholder="pasta com as séries" '
             u'aria-label="pasta com as séries">%s</div>'
             u'<button type="button" class="ui-bt" onclick="r3Procurar(this)">'
             u'%s<span data-radai-frase>Procurar</span></button>'
             u'<button type="button" class="ui-bt pri" onclick="r3Outra()">'
             u'<span data-radai-frase>Listar</span></button></div>'
             u'<div class="r3-filtro">%s</div>'
             u'<div class="ui-vl-est" id="r3_busca" role="status" '
             u'aria-live="polite"></div>'
             u'<div class="r3-lista" id="r3_lista_pasta" role="listbox" '
             u'aria-label="séries da pasta"></div>'
             % (radai_ui.botao_favorita(u"r3_pasta"), radai_ui.icone(u"pasta"),
                radai_ui.filtro_de_data(u"r3_dias")))
    abas = radai_ui.abas_de_serie(u"r3_origem",
                                  [(u"acervo", u"Acervo local", acervo),
                                   (u"pasta", u"Aponte uma pasta", pasta)],
                                  cor_var=u"--mod-recon", lembrar=True)
    return (u'<div class="r3-serie" id="r3_p1">'
            + radai_ui.cartao_de_serie(u"r3_cartao", u"r3_escolha",
                                       u"Escolha a série",
                                       chave_modulo=u"recon3d", numero=u"1")
            + u'<div class="r3-estado" id="r3_estado" role="status"></div>'
            + u'</div>'
            + radai_ui.popup_de_serie(u"r3_escolha", abas, sozinho=True))


_VISTAS = ((u"ant", u"anterior", u"A"), (u"post", u"posterior", u"P"),
           (u"esq", u"esquerda do paciente", u"E"),
           (u"dir", u"direita do paciente", u"D"),
           (u"sup", u"superior", u"S"), (u"inf", u"inferior", u"I"))


def _html_incidencias_3d():
    import radai_projection
    import radai_ui
    bts = u"".join(
        u'<button type="button" class="r3-inc" data-lao="%d" data-cra="%d" '
        u'aria-pressed="false" onclick="r3IncAplicar(%d,%d,true)">'
        u'<span>%s</span><small translate="no">%s</small>'
        u'</button>' % (int(lao), int(cra), int(lao), int(cra), nome,
                        radai_projection.rotulo_do_angulo(lao, cra))
        for nome, lao, cra in radai_projection.INCIDENCIAS)
    return (u'<div class="r3-inc3d" id="r3_inc3d">'
            u'<button type="button" class="ui-bt r3-atraves" id="r3_atraves" '
            u'aria-pressed="false" onclick="r3Atraves()" '
            u'title="osso e pele translúcidos de uma vez">%s'
            u'<span data-radai-frase>Ver através</span></button>'
            u'<span class="r3-barra"><span class="r3-bl" translate="no">RAO</span>'
            u'<input type="range" id="r3_lao" min="-180" max="180" step="1" '
            u'value="0" aria-label="LAO/RAO" oninput="r3IncBarra()">'
            u'<span class="r3-bl" translate="no">LAO</span>'
            u'<b id="r3_lao_v" translate="no">LAO 0°</b></span>'
            u'<span class="r3-barra cra"><span class="r3-bl" translate="no">CAU</span>'
            u'<input type="range" id="r3_cra" min="-90" max="90" step="1" '
            u'value="0" aria-label="CRA/CAU" oninput="r3IncBarra()">'
            u'<span class="r3-bl" translate="no">CRA</span>'
            u'<b id="r3_cra_v" translate="no">CRA 0°</b></span>'
            u'<div class="g" role="group" aria-label="incidência">%s</div></div>'
            % (radai_ui.icone(u"atraves"), bts))


def html_palco(fer, desenho=False):
    vistas = u"".join(
        u'<button type="button" onclick="r3Vista(\'%s\')" title="%s" '
        u'aria-label="%s" data-n3-lado="%s">%s</button>'
        % (k, rot, rot, k, letra) for k, rot, letra in _VISTAS)
    dsn = u""
    if desenho:
        dsn = (u'<div class="r3-dsn"><div class="r3-ferr-cab">'
               u'<span data-radai-frase>Desenho no axial</span>'
               u'<b id="r3_dsn_n" class="r3-crono"></b></div>'
               u'<button type="button" class="ui-bt" id="r3_desenhar" disabled '
               u'onclick="r3DesenharAbrir(this)">'
               u'<span data-radai-frase>Desenhar no axial</span></button></div>')
    grav = (u'<div class="r3-grav"><div class="r3-ferr-cab">'
            u'<span data-radai-frase>Gravação do visor</span>'
            u'<b class="r3-crono" id="r3_crono">00:00</b></div>'
            u'<div class="r3-grav-linha">'
            u'<span class="r3-fmt" role="radiogroup" aria-label="formato do vídeo">'
            u'<button type="button" role="radio" aria-checked="false" '
            u'data-r3v-fmt="mp4" onclick="r3vFormato(\'mp4\')">MP4</button>'
            u'<button type="button" role="radio" aria-checked="false" '
            u'data-r3v-fmt="webm" onclick="r3vFormato(\'webm\')">WebM</button>'
            u'</span>'
            u'<button type="button" class="ui-bt" id="r3_gravar" disabled '
            u'aria-pressed="false" onclick="r3vAlternar()">'
            u'<span data-r3v-rot data-radai-frase>Iniciar gravação</span>'
            u'</button></div>'
            u'<div class="r3-grav-aviso" id="r3_grav_aviso"><span class="pt" '
            u'aria-hidden="true"></span><span data-radai-frase>%s</span></div>'
            u'<div class="r3-grav-decl"><label class="r3-grav-ato">'
            u'<input type="checkbox" id="r3_grav_ato" onchange="r3vAtoMudou()"> '
            u'<span data-radai-frase>%s</span></label>%s</div>'
            u'<p class="r3-grav-msg" id="r3_grav_msg" role="status"></p></div>'
            % (AVISO_CURTO_DA_GRAVACAO, ATO_DA_GRAVACAO,
               _ajuda_da_gravacao()))
    return (
        u'<div class="r3-q3d"><div class="r3-3d"><div class="r3-col3d">'
        u'<div class="r3-tela3d" id="r3_tela3d">'
        u'<canvas id="cvGL" hidden aria-label="reconstrução 3D das estruturas">'
        u'</canvas><canvas id="cv3Db" hidden aria-hidden="true"></canvas>'
        u'<canvas id="cv3D" width="300" height="300" '
        u'aria-label="reconstrução 3D em nuvem de pontos"></canvas>'
        u'<span class="r3-vistas" role="group" aria-label="vistas">%s'
        u'<button type="button" onclick="r3Vista(\'inicial\')" '
        u'title="voltar ao início" aria-label="voltar ao início">&#8635;</button>'
        u'</span>'
        u'<span class="r3-rec" id="r3_rec" hidden><i></i>REC '
        u'<b id="r3_rec_t">00:00</b></span>'
        u'<span class="r3-dica3d" id="dica3d" data-radai-frase>escolha uma '
        u'série</span></div></div>'
        u'<div class="r3-ferramentas">%s%s%s</div>'
        u'<aside class="r3-l3d" aria-label="estruturas do 3D">'
        u'<div class="r3-l3cab">'
        u'<label for="r3_rs" data-radai-frase>conjunto de contornos</label>'
        u'<select id="r3_rs" onchange="r3mTrocarArquivo()"></select>'
        u'<input type="search" id="r3_filtro" placeholder="filtrar estruturas" '
        u'aria-label="filtrar estruturas">'
        u'<div class="r3-l3acoes">'
        u'<button type="button" onclick="r3mTodas(true)" '
        u'data-radai-frase>ligar todas</button>'
        u'<button type="button" onclick="r3mTodas(false)" '
        u'data-radai-frase>desligar todas</button>'
        u'<span class="sub" id="r3_conta"></span></div></div>'
        u'<div class="r3-l3rolar"><div id="r3_estr"></div>'
        u'<div class="r3-l3sub" id="r3_cab_camadas" hidden data-radai-frase>'
        u'osso e pele pela densidade da TC</div>'
        u'<div id="r3_camadas3d"></div></div></aside></div>'
        u'<p class="r3-aviso3d" id="r3_aviso3d" hidden><span data-radai-frase>'
        u'Este navegador não desenha WebGL: o 3D aparece em nuvem de pontos, '
        u'sem transparência.</span> <code id="r3_motivo3d"></code></p></div>'
        % (vistas, _html_incidencias_3d(), dsn, grav))


def _html_miniaturas():
    def plano(eixo, rot, aria):
        return (u'<div class="r3-quadro"><div class="rot">'
                u'<span data-radai-frase>%s</span><b id="r3_posv%d">50%%</b>'
                u'</div><div class="r3-tela" title="duplo clique amplia">'
                u'<img id="r3_img%d" alt="" draggable="false"></div><input type="range" id="r3_pos%d" '
                u'min="0" max="100" value="50" aria-label="%s"></div>'
                % (rot, eixo, eixo, eixo, aria))
    proj = (u'<div class="r3-quadro"><div class="rot">'
            u'<span data-radai-frase>projeção</span>'
            u'<b><span id="r3_lajev">10 mm</span></b></div>'
            u'<div class="r3-tela"><img id="r3_imgp" alt="" draggable="false">'
            u'</div><div class="r3-pctl">'
            u'<button type="button" class="jan" id="m_mip" '
            u'onclick="r3Modo(\'mip\')">MIP</button>'
            u'<button type="button" class="jan" id="m_minip" '
            u'onclick="r3Modo(\'minip\')">MinIP</button>'
            u'<select id="r3_eixop" aria-label="eixo da projeção">'
            u'<option value="0">axial</option><option value="1">coronal</option>'
            u'<option value="2">sagital</option></select></div>'
            u'<div class="r3-pctl"><span class="sub" data-radai-frase>laje</span>'
            u'<input type="range" id="r3_laje" min="1" max="100" value="10" '
            u'aria-label="espessura da laje">'
            u'<button type="button" class="r3-q" onclick="r3AjudaMip(this)" '
            u'aria-label="o que é MIP e MinIP" title="o que é MIP e MinIP">?'
            u'</button></div>'
            u'<input type="range" id="r3_posp" min="0" max="100" value="50" '
            u'aria-label="posição da projeção"></div>')
    janelas = u"".join(
        u'<button type="button" class="jan" id="j_%s" aria-pressed="false" '
        u'onclick="r3Jan(\'%s\')"><span data-radai-frase>%s</span></button>'
        % (k, k, rot) for k, rot in ((u"pulmao", u"pulmão"),
                                     (u"mediastino", u"mediastino"),
                                     (u"osso", u"osso"),
                                     (u"cerebro", u"cérebro")))
    return (u'<div class="r3-grade">%s%s%s%s</div>'
            u'<div class="r3-ctrl"><span class="sub" data-radai-frase>janela'
            u'</span>%s</div>'
            % (plano(0, u"axial", u"corte axial"),
               plano(1, u"coronal", u"corte coronal"),
               plano(2, u"sagital", u"corte sagital"), proj, janelas))


def pagina(ferramenta="geral"):
    import radai_ui
    import radai_viewer
    fer = ferramenta if ferramenta in ("geral", "toracica") else "geral"
    f = FERRAMENTAS_3D[fer]
    palco = radai_ui.passo(u"2", u"Reconstrução 3D",
                           html_palco(fer, desenho=(fer == "toracica"))
                           + _html_miniaturas(), ident=u"r3_p2")
    corpo = (_html_cabeca(fer, AJUDA_DA_TELA[fer]) + _html_passo_serie()
             + palco + radai_ui.alerta(ALERTA_DA_TELA))
    import radai_projection
    js = (radai_viewer.JS_3D + radai_projection.JS_CONVENCAO + JS_MALHA + JS_GRAVAR
          + JS_SERIE
          + (JS_DESENHO if fer == "toracica" else u""))
    return (u'<!doctype html><html><head><meta charset="utf-8">'
            u'<title>%s &middot; Reconstru&ccedil;&otilde;es 3D</title>'
            u'<meta name="viewport" content="width=device-width,initial-scale=1">'
            u'<style>%s</style></head><body>'
            u'<div class="r3-wrap" data-ferramenta="%s">%s</div>'
            u'<script>%s</script></body></html>'
            % (radai_ui._esc(f["nome"]), CSS, fer, corpo, js))


def montar(app):
    from fastapi import Request
    from fastapi.responses import HTMLResponse, Response

    registrar_varredura()

    @app.get("/recon3d/anatomia", response_class=HTMLResponse)
    def _tela():
        return radai_menu.aplicar(pagina("geral"), "recon_anatomia")

    @app.get("/recon3d/toracica", response_class=HTMLResponse)
    def _tela_toracica():
        return radai_menu.aplicar(pagina("toracica"), "recon_torax")

    @app.post("/api/recon3d/acervo")
    async def _acervo(request: Request, ferramenta: str = ""):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        try:
            limite = max(1, min(200, int(c.get("limite") or 60)))
        except Exception:
            limite = 60
        return await radai_web.no_threadpool(
            acervo, str(ferramenta or c.get("ferramenta") or "geral"), limite)

    @app.post("/api/recon3d/ato-de-gravacao")
    async def _ato_de_gravacao(request: Request):
        from fastapi.responses import JSONResponse
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        fmt = str((c or {}).get("formato") or u"")
        if fmt not in ("mp4", "webm"):
            return JSONResponse({"ok": False, "erro": u"formato"}, status_code=400)
        try:
            gravar_ato_do_video(fmt)
        except Exception as e:
            return JSONResponse({"ok": False, "erro": u"%s" % type(e).__name__},
                                status_code=500)
        return {"ok": True}

    @app.post("/api/recon3d/ficha")
    async def _ficha(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        return ler_ficha(str(c.get("ficha") or u""))

    @app.post("/api/recon3d/desenho")
    async def _desenho(request: Request):
        from fastapi.responses import JSONResponse
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        b = str(c.get("b") or u"")
        cortes = c.get("cortes") if isinstance(c.get("cortes"), list) else []
        try:
            dados, _zs = await radai_web.no_threadpool(malha_do_desenho, b,
                                                       cortes)
        except SemSerie:
            return JSONResponse({"erro": u"recarregue a lista de séries"},
                                status_code=404)
        except ValueError:
            return JSONResponse({"erro": u"desenhe em pelo menos um corte"},
                                status_code=422)
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"reconstrucoes 3D, desenho", e,
                                            bilhete=b)
            return JSONResponse({"erro": u"não consegui montar o volume",
                                 "tipo": type(e).__name__}, status_code=422)
        return Response(content=dados, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})

    def _pasta_do_bilhete(b):
        import radai_thumbnail
        pasta, uid = radai_thumbnail.resolver(b)
        return pasta or "", uid or ""

    @app.get("/api/recon3d/estado")
    def _estado(b: str = ""):
        import radai_recon3d
        pasta, _uid = _pasta_do_bilhete(b)
        if not pasta:
            return {"segmentada": False,
                    "o_que_fazer": u"recarregue a lista de séries"}
        fora = dict(radai_recon3d.estado_da_serie(pasta) or {})
        uid_ = _uid or u""
        meta_ = _rotulos_meta(pasta, uid_) if uid_ else None
        fora["estudo_3d"] = list((meta_ or {}).get("protocolos") or [])
        if uid_:
            import radai_sets
            meus = radai_sets.arquivos_da_serie(
                [c.get("arquivo") for c in (fora.get("conjuntos") or [])],
                uid_)
            fora["segmentada"] = bool(meus) or meta_ is not None
        try:
            _v, _e, _s = _volume(pasta, _uid)
            fora["forma"] = [int(x) for x in _v.shape]
            fora["cranial"] = sentido_cranial(_s)
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"reconstrucoes 3D, estado", e,
                                            bilhete=b)
            fora = dict(fora or {})
            fora["nao_le"] = u"a causa foi escrita no log da estação"
            fora["tipo"] = type(e).__name__
        return fora

    @app.get("/api/recon3d/projecao")
    def _projecao(b: str = "", modo: str = "mip", eixo: int = 0,
                  janela: str = "pulmao", laje: float = 10.0,
                  pos: float = 0.5, segmentacao: bool = False,
                  rs: str = "", nomes: str = ""):
        try:
            import radai_recon3d as R
            pasta, uid = _pasta_do_bilhete(b)
            if not pasta:
                return Response(status_code=404, content=b"")
            v, esp, sentido, origem, direcao = _snapshot_do_volume(pasta, uid)
            mm = float(esp[int(eixo)]) or 1.0
            n = v.shape[int(eixo)]
            espessura = max(1, int(round(float(laje) / mm)))
            centro = int(round(float(pos) * (n - 1)))
            i0 = max(0, centro - espessura // 2)
            a = R.projetar(v, int(eixo), str(modo), i0, i0 + espessura)
            a = R.plano_para_a_tela(a, int(eixo), esp, sentido)
            c, l = R.JANELAS.get(str(janela), R.JANELAS["mediastino"])
            png = R.para_png(a, c, l)
            if segmentacao and float(laje) == 0.0:
                import json
                quer = set(json.loads(nomes)) if nomes else None
                try:
                    conjunto, _rs, _arqs, _k = conjunto_da_serie(b, rs)
                except SemSerie:
                    conjunto = None
                if conjunto is not None:
                    svg = _png_com_contornos(
                        png, conjunto, v.shape, esp, origem, direcao, sentido,
                        int(eixo), max(0, min(n - 1, centro)), quer)
                    return Response(content=svg, media_type="image/svg+xml",
                                    headers={"Cache-Control": "no-store"})
            return Response(content=png, media_type="image/png",
                            headers={"Cache-Control": "no-store"})
        except Exception:
            return Response(status_code=404, content=b"")

    @app.get("/api/recon3d/nuvem")
    async def _nuvem(b: str = ""):
        return await radai_web.no_threadpool(cena_da_serie, b)

    @app.post("/api/recon3d/nuvem")
    async def _nuvem_post(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        nomes = [str(x) for x in (c.get("nomes") or [])][:MAX_NUVEM_POR_PEDIDO]
        camadas = [str(x) for x in (c.get("camadas") or [])
                   if str(x) in (u"osso", u"pele")]
        return await radai_web.no_threadpool(
            cena_da_serie, str(c.get("b") or u""), str(c.get("rs") or u""),
            nomes, camadas)

    @app.post("/api/recon3d/estruturas")
    async def _estruturas(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        return await radai_web.no_threadpool(
            estruturas_da_serie, str(c.get("b") or u""),
            str(c.get("rs") or u""))

    @app.post("/api/recon3d/malha")
    async def _malha(request: Request):
        from fastapi.responses import JSONResponse
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        b = str(c.get("b") or u"")
        try:
            dados = await radai_web.no_threadpool(
                malha_stl, b, str(c.get("rs") or u""),
                str(c.get("nome") or u""), str(c.get("camada") or u""))
        except SemSerie:
            return JSONResponse({"erro": u"recarregue a lista de séries"},
                                status_code=404)
        except KeyError:
            return JSONResponse({"erro": u"esta estrutura não está no arquivo"},
                                status_code=404)
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"reconstrucoes 3D, malha", e,
                                            bilhete=b)
            return JSONResponse({"erro": u"não consegui montar a malha",
                                 "tipo": type(e).__name__}, status_code=422)
        return Response(content=dados, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})

    try:
        import radai_recon3d_vascular
        radai_recon3d_vascular.montar(app)
    except Exception as e:
        import radai_thumbnail
        radai_thumbnail.registrar_falha(u"reconstrucoes 3D, vascular", e)
    return app


def acervo(ferramenta, limite=60):
    import radai_tabela_acervo
    import radai_thumbnail
    cfg = FERRAMENTAS_3D.get(ferramenta) or FERRAMENTAS_3D["geral"]
    d = radai_tabela_acervo.linhas(limite=200)
    fora = []
    for linha in d.get("series") or ():
        pasta, uid = radai_thumbnail.resolver(linha.get("bilhete"))
        meta = _rotulos_meta(pasta, uid) if (pasta and uid) else None
        protos = list((meta or {}).get("protocolos") or [])
        if cfg["protocolo"] and cfg["protocolo"] not in protos:
            continue
        if (ferramenta != "vascular" and linha.get("estado") == "sem_rs"
                and meta is None):
            continue
        fora.append(dict(linha, estudo_3d=protos))
        if len(fora) >= int(limite or 60):
            break
    r = {"series": fora, "sumiram": int(d.get("sumiram") or 0)}
    if d.get("erro"):
        r["erro"] = d["erro"]
    return r


USO_DA_VARREDURA = "recon3d"
MIN_CORTES = 2


def linha_da_pasta(linha, pasta, s):
    if int(s.get("cortes") or 0) < MIN_CORTES:
        return False
    import radai_sets
    uid = str(s.get("uid") or u"")
    try:
        nomes = [n for n in os.listdir(pasta) if n.startswith("RS_RadAI_")]
    except OSError:
        nomes = []
    meta = _rotulos_meta(pasta, uid) if uid else None
    linha["segmentada"] = (bool(radai_sets.arquivos_da_serie(nomes, uid))
                           or meta is not None)
    linha["estudo_3d"] = list((meta or {}).get("protocolos") or [])
    return True


def registrar_varredura():
    import radai_varrer
    return radai_varrer.registrar_series_de_pasta(USO_DA_VARREDURA,
                                                  enriquecer=linha_da_pasta)


def ler_ficha(ficha):
    import radai_fichas
    import radai_thumbnail
    d = radai_fichas.ler(ficha)
    if not isinstance(d, dict):
        return {"erro": u"a ficha venceu: escolha a série no acervo"}
    pasta = str(d.get("pasta") or u"")
    uid = str(d.get("uid") or u"")
    if not pasta or not os.path.isdir(pasta):
        return {"erro": u"a série não está mais nesta pasta"}
    rs = str(d.get("rs") or d.get("arquivo") or d.get("conjunto") or u"")
    rs = os.path.basename(rs.replace(u"\\", u"/"))
    if rs.lower() in (u"rotulos", u"mapa", ARQUIVO_ROTULOS):
        rs = ARQUIVO_ROTULOS
    nomes = d.get("estruturas") or d.get("visiveis") or d.get("nomes") or []
    if not isinstance(nomes, (list, tuple)):
        nomes = []
    return {"b": radai_thumbnail.bilhete(pasta, uid), "rs": rs,
            "estruturas": [str(n) for n in nomes][:1000], "erro": u""}


def cena_da_serie(b, rs=u"", nomes=(), camadas=(u"osso", u"pele")):
    import time
    import radai_recon3d as R
    import radai_thumbnail
    pasta, uid = radai_thumbnail.resolver(b)
    if not pasta:
        return {"itens": [], "erro": u"recarregue a lista de séries"}
    try:
        t0 = time.time()
        gasto = 0.0
        itens = []
        if nomes:
            c, rs, _arqs, _k = conjunto_da_serie(b, rs)
            cores = dict((r["nome"], r["cor"]) for r in c["rois"])
            for nome in list(nomes)[:MAX_NUVEM_POR_PEDIDO]:
                if nome not in c["contornos"]:
                    continue
                with _TRAVA_MALHA:
                    it = R.nuvem_do_conjunto(c, nome, cores.get(nome))
                if it.get("pontos"):
                    itens.append(it)
        gasto += time.time() - t0
        if camadas:
            mod = _modalidade(b)
            if mod and mod != "CT":
                if not itens:
                    return {"itens": [], "modalidade": mod,
                            "erro": u"o 3D por densidade existe só para TC, "
                                    u"e esta série não é TC"}
            else:
                v, esp, origem, direcao = _volume_lps(pasta, uid)
                t1 = time.time()
                for cam in camadas:
                    it = R.nuvem_da_camada(v, esp, origem, direcao, cam)
                    if it is not None:
                        itens.append(it)
                gasto += time.time() - t1
        return {"itens": itens, "eixos": list(R.EIXOS_LPS), "lps": True,
                "segundos": round(gasto, 2),
                "erro": u"" if itens
                else u"nada acima dos limiares nesta série"}
    except SemSerie:
        return {"itens": [], "erro": u"recarregue a lista de séries"}
    except Exception as e:
        radai_thumbnail.registrar_falha(u"reconstrucoes 3D, cena", e,
                                        bilhete=b)
        return {"itens": [], "erro": u"não consegui montar o 3D",
                "tipo": type(e).__name__}
