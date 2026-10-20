# -*- coding: utf-8 -*-
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)
import _cleanup
_cleanup.adotar_prefixo("radai_t_r3v84_")
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_t_r3v84_")
_CFG = os.path.join(os.environ["RADAI_CALIB_DIR"], "radai_watcher.config")
io.open(_CFG, "w", encoding="utf-8").write(u"ROOT=\n")
os.environ["RADAI_CONFIG"] = _CFG

import numpy as np

OK = 0
FALHOU = []


def secao(t):
    print(u"\n-- %s --" % t)


def checar(rotulo, cond, detalhe=""):
    global OK
    if cond:
        OK += 1
        print(u"  ok     %s" % rotulo)
    else:
        FALHOU.append(rotulo)
        print(u"  FALHA  %s  [%s]" % (rotulo, str(detalhe)[:300]))


def _tmp():
    return tempfile.mkdtemp(prefix="radai_t_r3v84_")


def _funcao_js(js, nome):
    i = js.find(u"function %s(" % nome)
    if i < 0:
        return u""
    k, prof = js.find(u"{", i), 0
    for j in range(k, len(js)):
        if js[j] == u"{":
            prof += 1
        elif js[j] == u"}":
            prof -= 1
            if prof == 0:
                return js[i:j + 1]
    return u""


def _node(prog):
    node = shutil.which("node")
    if not node:
        return None, u"sem node"
    d = _tmp()
    alvo = os.path.join(d, "t.js")
    io.open(alvo, "w", encoding="utf-8").write(prog)
    r = subprocess.run([node, alvo], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    for ln in reversed((r.stdout or u"").splitlines()):
        if ln.startswith(u"JSON:"):
            return json.loads(ln[5:]), u""
    return None, ((r.stderr or u"") + (r.stdout or u""))[-500:]


def _texto_visivel(p):
    import html
    p = re.sub(r"(?s)<script.*?</script>", u" ", p)
    p = re.sub(r"(?s)<style.*?</style>", u" ", p)
    p = re.sub(r"(?s)<!--.*?-->", u" ", p)
    return html.unescape(re.sub(r"<[^>]+>", u" ", p))


def _esfera_vol(forma, centro, raio_mm, esp):
    z, y, x = np.indices(forma).astype(np.float64)
    d = (((z - centro[0]) * esp[0]) ** 2 + ((y - centro[1]) * esp[1]) ** 2
         + ((x - centro[2]) * esp[2]) ** 2)
    return d <= raio_mm ** 2


def teste_a_malha_do_rotulo_cai_no_lugar():
    secao(u"a malha de uma máscara da série cai no lugar dela, em mm LPS")
    import radai_recon3d as R
    esp = (3.0, 0.8, 0.8)
    forma = (40, 96, 96)
    m = _esfera_vol(forma, (25, 30, 60), 15.0, esp)
    origem = (-40.0, -20.0, 100.0)
    v, f, info = R.malha_de_rotulo(m, esp, origem)
    checar(u"a malha existe e cabe no teto", 0 < len(f) <= R.TETO_TRIANGULOS * 1.2,
           len(f))
    centro = v.mean(axis=0)
    esperado = np.array([origem[0] + 60 * esp[2], origem[1] + 30 * esp[1],
                         origem[2] + 25 * esp[0]])
    checar(u"o centro da malha é o centro da esfera (±1,5 mm)",
           np.abs(centro - esperado).max() < 1.5, (centro, esperado))
    ext = v.max(axis=0) - v.min(axis=0)
    checar(u"e o diâmetro é o da esfera (30 mm ±3)",
           np.all(np.abs(ext - 30.0) < 3.0), ext)
    import radai_recon3d as R2
    sem = R2._mascara_em_lps
    try:
        R2._mascara_em_lps = lambda vv, ff, e, o, d, desl: sem(
            vv, ff, e, o, d, (0.0, 0.0, 0.0))
        v2, _f2, _i = R2.malha_de_rotulo(m, esp, origem)
    finally:
        R2._mascara_em_lps = sem
    checar(u"(isca) sem o deslocamento do recorte a malha sai do lugar",
           np.abs(v2.mean(axis=0) - esperado).max() > 10, v2.mean(axis=0))
    v0, f0, _ = R.malha_de_rotulo(np.zeros(forma, bool), esp, origem)
    checar(u"máscara vazia devolve malha vazia, sem levantar", len(f0) == 0)


def teste_o_filtro_de_vaso():
    secao(u"o filtro de vaso da Vascular")
    import radai_recon3d as R
    sim = (u"A_Aorta_ai", u"V_Venacava_S_ai", u"aorta", u"pulmonary_vein",
           u"common_carotid_artery_left", u"lung_vessels", u"portal_vein_and_splenic_vein",
           u"iliac_artery_right", u"A_Pulmonary_ai")
    nao = (u"Heart_ai", u"Lung_L_ai", u"liver", u"Esophagus_ai", u"vertebrae_T4",
           u"Skin", u"lung_trachea_bronchia")
    checar(u"os vasos são vaso", all(R.e_vaso(n) for n in sim),
           [n for n in sim if not R.e_vaso(n)])
    checar(u"e os órgãos não", not any(R.e_vaso(n) for n in nao),
           [n for n in nao if R.e_vaso(n)])


def _circulo_norm(cx, cy, r, n=48):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return [[cx + r * np.cos(t), cy + r * np.sin(t)] for t in a]


def teste_o_desenho_interpola_entre_os_cortes():
    secao(u"o desenho no axial: polígonos em cortes viram um volume")
    import radai_recon3d_desenho as D
    forma = (31, 100, 100)
    esp = (2.0, 1.0, 1.0)
    p10 = D.poligono_em_voxel(_circulo_norm(0.5, 0.5, 0.10), forma[1:])
    p30 = D.poligono_em_voxel(_circulo_norm(0.5, 0.5, 0.30), forma[1:])
    vol = D.volume_do_desenho({10: [p10], 30: [p30]}, forma, esp)

    def raio(z):
        return np.sqrt(vol[z].sum() / np.pi)
    checar(u"o corte desenhado sai como foi desenhado (raio 10 px)",
           abs(raio(10) - 10.0) < 1.0, raio(10))
    checar(u"o corte do meio sai com o raio do meio (20 px ±1,5)",
           abs(raio(20) - 20.0) < 1.5, raio(20))
    checar(u"fora do intervalo desenhado, nada",
           not vol[:10].any() and not vol[31 - 0:].any() and vol[30].any())
    checar(u"cortes 0 a 9 vazios", not vol[0:10].any())
    copia = np.zeros_like(vol)
    for z in range(10, 31):
        copia[z] = vol[10] if z < 20 else vol[30]
    checar(u"(isca) a cópia do corte vizinho não é a interpolação",
           abs(np.sqrt(copia[20].sum() / np.pi) - 20.0) > 1.5 or
           abs(np.sqrt(copia[19].sum() / np.pi) - 19.0) > 1.5)
    checar(u"a fração do deslizador vira o corte da rota da projeção",
           D.indice_do_corte(0.5, 31) == 15 and D.indice_do_corte(0.0, 31) == 0
           and D.indice_do_corte(1.0, 31) == 30)
    pv = D.poligono_em_voxel([[0.0, 0.0], [1.0, 1.0]], (100, 200))
    checar(u"a fração da imagem vira a fração do corte (linha, coluna)",
           pv[0] == (-0.5, -0.5) and pv[1] == (99.5, 199.5), pv)
    checar(u"ponto inválido é descartado, e não levanta",
           D.poligono_em_voxel([[u"x", 1], [float("nan"), 0.2]], (10, 10)) == [])
    vazio = D.volume_do_desenho({5: [[(1, 1), (2, 2)]]}, (8, 10, 10), (1, 1, 1))
    checar(u"polígono com menos de 3 pontos não desenha nada", not vazio.any())


def _rtstruct(caminho, estruturas):
    import test_recon3d as T
    T._rtstruct_sintetico(caminho, estruturas)


def _serie(base, pid, n=24):
    from datetime import datetime
    import make_test_series
    pasta = os.path.join(base, pid, "CT")
    uid = make_test_series.escreve_serie(pasta, pid, datetime.now(), n)
    return pasta, uid


def _esfera_contornos(cx, cy, cz, r, dz=3.0):
    fora = []
    for z in np.arange(cz - r + dz / 2, cz + r, dz):
        rr = np.sqrt(max(0.0, r * r - (z - cz) ** 2))
        if rr < 1:
            continue
        a = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        fora.append(np.column_stack([cx + rr * np.cos(a), cy + rr * np.sin(a),
                                     np.full(40, z)]))
    return fora


def _mapa(pasta, uid, protocolos, forma=(24, 128, 128)):
    import radai_rotulos
    import SimpleITK as sitk
    z, y, x = np.indices(forma)
    bola = ((z - 12) ** 2 * 9 + (y - 64) ** 2 * 4 + (x - 50) ** 2 * 4) < 400
    vaso = ((y - 64) ** 2 + (x - 90) ** 2) < 16
    ref = sitk.Image(forma[2], forma[1], forma[0], sitk.sitkInt16)
    ref.SetSpacing((2.0, 2.0, 3.0))
    ref.SetOrigin((-128.0, -128.0, 0.0))
    return radai_rotulos.gravar(pasta, uid, {"total_v3": {"heart": bola,
                                                          "aorta": vaso}},
                                ref=ref, protocolos=protocolos,
                                modalidade="CT")


def _cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import radai_recon3d_screen as S
    app = FastAPI()
    S.montar(app)
    return TestClient(app)


def teste_o_acervo_por_ferramenta():
    secao(u"o Acervo Local de cada ferramenta (bilhete, nunca caminho)")
    import radai_archive
    import radai_recon3d_screen as S
    base = _tmp()
    pa, ua = _serie(base, "PAC_TORAX")
    pb, ub = _serie(base, "PAC_GERAL")
    pc, uc = _serie(base, "PAC_SEM_NADA")
    rsa = u"RS_RadAI_20261001_%s.dcm" % ua[-8:]
    rsb = u"RS_RadAI_20261001_%s.dcm" % ub[-8:]
    _rtstruct(os.path.join(pa, rsa), [(u"Heart_ai", (200, 50, 50),
                                       _esfera_contornos(0, 0, 30, 15))])
    _rtstruct(os.path.join(pb, rsb), [(u"Heart_ai", (200, 50, 50),
                                       _esfera_contornos(0, 0, 30, 15))])
    _mapa(pa, ua, ["anatomia_toracica"])
    _mapa(pb, ub, ["anatomia_geral"])
    radai_archive.registrar_serie(ua, pa, rsa, date="20261001", pid="PAC_TORAX",
                                  estruturas=1)
    radai_archive.registrar_serie(ub, pb, rsb, date="20261002", pid="PAC_GERAL",
                                  estruturas=1)
    radai_archive.registrar_serie(uc, pc, u"RS_RadAI_x_%s.dcm" % uc[-8:],
                                  date="20261003", pid="PAC_SEM_NADA")
    t = S.acervo("toracica")
    checar(u"a Torácica lista só o que rodou o protocolo torácico",
           [s["pid"] for s in t["series"]] == ["PAC_TORAX"], t["series"])
    g = S.acervo("geral")
    checar(u"a Anatomia geral lista o que tem RTSTRUCT ou mapa",
           sorted(s["pid"] for s in g["series"]) == ["PAC_GERAL", "PAC_TORAX"],
           [s["pid"] for s in g["series"]])
    v = S.acervo("vascular")
    checar(u"a Vascular lista toda série que está no lugar",
           len(v["series"]) == 3, [s["pid"] for s in v["series"]])
    corpo = json.dumps(g)
    checar(u"nenhuma linha leva caminho de pasta",
           base.replace("\\", "\\\\") not in corpo and "pasta" not in corpo,
           corpo[:200])
    import radai_thumbnail
    b = [s["bilhete"] for s in t["series"]][0]
    checar(u"a linha leva o bilhete da série certa",
           radai_thumbnail.resolver(b) == (pa, ua))
    checar(u"e é a linha da tabela da Suite (C2), mais o estudo 3D",
           set(t["series"][0]) == {"bilhete", "uid8", "pid", "date",
                                   "estruturas", "secs", "quando", "estado",
                                   "estudo_3d"}, sorted(t["series"][0]))
    cli = _cliente()
    via = cli.post(u"/api/recon3d/acervo?ferramenta=toracica",
                   json={"limite": 60}).json()
    checar(u"a rota filtra pela ferramenta do endereço, como a tabela pede",
           [s["pid"] for s in via.get("series") or []] == ["PAC_TORAX"],
           [s.get("pid") for s in via.get("series") or []])
    checar(u"e diz o estudo 3D que ela rodou",
           t["series"][0]["estudo_3d"] == ["anatomia_toracica"])
    salvo = S.FERRAMENTAS_3D["toracica"]["protocolo"]
    try:
        S.FERRAMENTAS_3D["toracica"]["protocolo"] = u""
        isca = S.acervo("toracica")
    finally:
        S.FERRAMENTAS_3D["toracica"]["protocolo"] = salvo
    checar(u"(isca) sem o filtro do protocolo, a Torácica listaria a geral",
           len(isca["series"]) >= 2)


def teste_a_demo_saiu_do_acervo():
    secao(u"a demo saiu das Reconstruções 3D")
    import radai_recon3d_screen as S
    import radai_recon3d_vascular as V
    for nome in ("radai_recon3d_screen.py", "radai_recon3d_vascular.py",
                 "radai_recon3d.py", "radai_recon3d_desenho.py"):
        cod = io.open(os.path.join(APP, nome), encoding="utf-8").read()
        checar(u"%s não usa o módulo da demo" % nome, u"radai_demo" not in cod)
    for fer in ("geral", "toracica", "vascular"):
        a = S.acervo(fer)
        checar(u"[%s] o acervo devolve só as séries da estação" % fer,
               set(a) == {"series", "sumiram"}, sorted(a))
        checar(u"[%s] e a ferramenta não aponta mais conjunto de demo" % fer,
               "demo" not in S.FERRAMENTAS_3D[fer])
    for fer, p in sorted(_paginas().items()):
        checar(u"[%s] a tela não pinta linha DEMO" % fer,
               u"DEMO" not in p and u"r3LinhaDemo" not in p)
    checar(u"(isca) a linha DEMO de antes seria acusada",
           u"DEMO" in u'<span class="r3-tag demo">DEMO</span>')


def teste_os_conjuntos_da_serie_e_o_mapa():
    secao(u"os conjuntos da série: só os desta série, e o mapa de rótulos")
    import radai_thumbnail
    import radai_recon3d_screen as S
    base = _tmp()
    pa, ua = _serie(base, "PAC_DUAS")
    import make_test_series
    from datetime import datetime
    ub = make_test_series.escreve_serie(pa, "PAC_DUAS", datetime.now(), 24)
    rsa = u"RS_RadAI_20261001_%s.dcm" % ua[-8:]
    rsb = u"RS_RadAI_20261001_%s.dcm" % ub[-8:]
    _rtstruct(os.path.join(pa, rsa), [(u"Heart_ai", (200, 50, 50),
                                       _esfera_contornos(0, 0, 30, 15))])
    _rtstruct(os.path.join(pa, rsb), [(u"Liver_ai", (150, 90, 40),
                                       _esfera_contornos(0, 0, 30, 15))])
    _mapa(pa, ua, ["anatomia_toracica"])
    arq = [c["arquivo"] for c in S.arquivos_da_serie(pa, ua)]
    checar(u"com duas séries na pasta, a série vê só o RTSTRUCT dela e o mapa",
           arq == [rsa, S.ARQUIVO_ROTULOS], arq)
    checar(u"(isca) sem o UID, a pasta inteira (o recuo que a série não usa)",
           len(S.arquivos_da_serie(pa)) == 2)
    cli = _cliente()
    b = radai_thumbnail.bilhete(pa, ua)
    d = cli.post("/api/recon3d/estruturas", json={"b": b,
                                                   "rs": S.ARQUIVO_ROTULOS}).json()
    nomes = sorted(e["nome"] for e in d.get("estruturas") or [])
    checar(u"o mapa de rótulos abre como conjunto, com os nomes do modelo",
           nomes == ["aorta", "heart"], d)
    vaso = dict((e["nome"], e["vaso"]) for e in d.get("estruturas") or [])
    checar(u"  e cada estrutura diz se é vaso", vaso == {"aorta": True,
                                                         "heart": False}, vaso)
    r = cli.post("/api/recon3d/malha", json={"b": b, "rs": S.ARQUIVO_ROTULOS,
                                              "nome": "heart"})
    checar(u"a malha da estrutura do mapa sai em STL, sem Content-Disposition",
           r.status_code == 200 and len(r.content) > 84
           and "content-disposition" not in {k.lower() for k in r.headers},
           r.status_code)
    import struct
    n = struct.unpack("<I", r.content[80:84])[0]
    checar(u"  e o STL fecha (84 + 50·n bytes)", len(r.content) == 84 + 50 * n)
    pe, ue = _serie(base, "PAC_ESTADO")
    _mapa(pe, ue, ["anatomia_toracica"])
    e = cli.get("/api/recon3d/estado",
                params={"b": radai_thumbnail.bilhete(pe, ue)}).json()
    checar(u"o estado diz o estudo 3D e a forma da série",
           e.get("estudo_3d") == ["anatomia_toracica"]
           and e.get("forma") == [24, 128, 128], e)
    pc, uc = _serie(base, "PAC_CRU")
    bc = radai_thumbnail.bilhete(pc, uc)
    d2 = cli.post("/api/recon3d/estruturas", json={"b": bc}).json()
    checar(u"série sem segmentação devolve osso e pele, e diz que não há",
           d2.get("sem_segmentacao") is True and not d2.get("erro")
           and [c["camada"] for c in d2.get("camadas") or []] == [u"osso", u"pele"],
           d2)
    import engine
    import SimpleITK as sitk
    img = engine.load_sitk(pc, uc)
    tam = img.GetSize()
    cantos = np.array([img.TransformIndexToPhysicalPoint((i, j, k))
                       for i in (0, tam[0] - 1) for j in (0, tam[1] - 1)
                       for k in (0, tam[2] - 1)])
    cx = d2.get("caixa")
    checar(u"  e a caixa da cena é a da própria série (o 3D abre centrado)",
           cx is not None and np.allclose(cx[0], cantos.min(axis=0), atol=0.05)
           and np.allclose(cx[1], cantos.max(axis=0), atol=0.05),
           (cx, cantos.min(axis=0).tolist(), cantos.max(axis=0).tolist()))
    del sitk
    e2 = cli.get("/api/recon3d/estado", params={"b": bc}).json()
    checar(u"  e o estado dela diz não segmentada", e2.get("segmentada") is False)


def teste_a_ficha_do_ver_segmentacao():
    secao(u"a ficha do «Ver segmentação» abre o conjunto visível")
    import radai_fichas
    import radai_thumbnail
    import radai_recon3d_screen as S
    base = _tmp()
    pa, ua = _serie(base, "PAC_FICHA")
    rs = u"RS_RadAI_20261001_%s.dcm" % ua[-8:]
    _rtstruct(os.path.join(pa, rs), [(u"Heart_ai", (200, 50, 50),
                                      _esfera_contornos(0, 0, 30, 15))])
    cli = _cliente()
    f = radai_fichas.guardar({"pasta": pa, "uid": ua,
                              "rs": os.path.join(pa, rs),
                              "estruturas": ["Heart_ai"]})
    d = cli.post("/api/recon3d/ficha", json={"ficha": f}).json()
    checar(u"a ficha vira o bilhete da série", radai_thumbnail.resolver(
        d.get("b")) == (pa, ua), d)
    checar(u"o conjunto volta só pelo NOME, nunca pelo caminho",
           d.get("rs") == rs, d.get("rs"))
    checar(u"e as estruturas visíveis voltam", d.get("estruturas") == ["Heart_ai"])
    checar(u"a resposta não traz caminho", base not in json.dumps(d))
    f2 = radai_fichas.guardar({"pasta": pa, "uid": ua, "conjunto": "rotulos",
                               "visiveis": ["heart"]})
    d2 = S.ler_ficha(f2)
    checar(u"os outros nomes dos campos também valem (conjunto, visiveis)",
           d2.get("rs") == S.ARQUIVO_ROTULOS and d2.get("estruturas") == ["heart"])
    checar(u"ficha desconhecida diz que venceu",
           u"venceu" in (S.ler_ficha(u"nao-existe").get("erro") or u""))
    p = S.pagina("geral")
    checar(u"a tela lê `?ficha=` e pede ao servidor por POST",
           "get('ficha')" in p and "/api/recon3d/ficha" in p
           and "R3M.preset = {rs: d.rs" in p)


def teste_a_rota_do_desenho():
    secao(u"a rota do desenho do axial")
    import radai_thumbnail
    cli = _cliente()
    base = _tmp()
    pa, ua = _serie(base, "PAC_DESENHO")
    b = radai_thumbnail.bilhete(pa, ua)
    cortes = [{"pos": 0.2, "pontos": [_circulo_norm(0.5, 0.5, 0.1)]},
              {"pos": 0.8, "pontos": [_circulo_norm(0.5, 0.5, 0.2)]}]
    r = cli.post("/api/recon3d/desenho", json={"b": b, "cortes": cortes})
    checar(u"o desenho vira STL, por POST, sem Content-Disposition",
           r.status_code == 200 and len(r.content) > 84
           and "content-disposition" not in {k.lower() for k in r.headers},
           r.status_code)
    r2 = cli.post("/api/recon3d/desenho", json={"b": b, "cortes": []})
    checar(u"sem desenho, 422 com a frase", r2.status_code == 422
           and u"desenhe" in r2.json().get("erro", u""))
    r3 = cli.post("/api/recon3d/desenho", json={"b": "morto", "cortes": cortes})
    checar(u"bilhete morto manda recarregar (404)", r3.status_code == 404)
    nada = os.listdir(pa)
    checar(u"e nada foi gravado ao lado da série",
           not [n for n in nada if not n.lower().startswith("ct_")], nada)


def teste_a_vascular_projeta_e_inverte():
    secao(u"a Vascular: a angiografia sintética, e a cor invertida")
    import radai_thumbnail
    cli = _cliente()
    base = _tmp()
    pa, ua = _serie(base, "PAC_ANGIO", n=30)
    b = radai_thumbnail.bilhete(pa, ua)
    r = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
    checar(u"a projeção sai em PNG, sem cache", r.status_code == 200
           and r.headers.get("content-type") == "image/png"
           and r.headers.get("cache-control") == "no-store", r.status_code)
    ri = cli.get("/api/recon3d/vascular/projecao",
                 params={"b": b, "lado": 256, "inverter": 1})
    import zlib
    import struct

    def pix(png):
        i, dados, w, h = 8, b"", 0, 0
        while i < len(png):
            n = struct.unpack(">I", png[i:i + 4])[0]
            tipo = png[i + 4:i + 8]
            if tipo == b"IHDR":
                w, h = struct.unpack(">II", png[i + 8:i + 16])
            if tipo == b"IDAT":
                dados += png[i + 8:i + 8 + n]
            i += 12 + n
        raw = zlib.decompress(dados)
        linha = len(raw) // h
        return np.frombuffer(raw, np.uint8).reshape(h, linha)[:, 1:].astype(int)
    a, bi = pix(r.content), pix(ri.content)
    checar(u"invertida é o complemento da normal (255 − v)",
           a.shape == bi.shape and np.abs((255 - a) - bi).max() <= 1,
           (a.shape, bi.shape))
    checar(u"(isca) a normal não é igual à invertida", np.abs(a - bi).max() > 50)
    rm = cli.get("/api/recon3d/vascular/projecao", params={"b": "morto"})
    checar(u"bilhete morto é 404 vazio", rm.status_code == 404 and not rm.content)


def _cranio_sintetico():
    import SimpleITK as sitk
    forma, esp = (60, 80, 80), (2.0, 2.0, 2.0)
    z, y, x = np.indices(forma).astype(np.float64)
    r = np.sqrt(((z - 30) * 2) ** 2 + ((y - 40) * 2) ** 2 + ((x - 40) * 2) ** 2)
    a = np.full(forma, -1000, np.int16)
    a[r < 66] = 40
    casca = (r >= 60) & (r < 66)
    a[casca] = 1200
    vaso = (((y - 40) * 2) ** 2 + ((x - 46) * 2) ** 2 < 9) & (r < 54)
    a[vaso] = 350
    img = sitk.GetImageFromArray(a)
    img.SetSpacing(esp)
    return img, casca, vaso


def teste_a_vascular_tira_a_calota():
    secao(u"a Vascular: o osso sai da projeção, e o vaso fica")
    import SimpleITK as sitk
    import radai_nidus as N
    import radai_recon3d_vascular as V
    img, casca, vaso = _cranio_sintetico()
    sem = sitk.GetArrayFromImage(V.retirar_osso(img))
    checar(u"a calota sai do volume (vira o fundo da série)",
           bool((sem[casca] <= -1000).all()), int((sem[casca] > -1000).sum()))
    checar(u"o vaso contrastado fica, valor a valor",
           bool((sem[vaso] == 350).all()), int((sem[vaso] != 350).sum()))
    s = N.abrir(img, "CT")
    com, _i = N.projetar(s.img, 0, 0, "mip", "angio", lado=128, escala=s.escala)
    c, l = _i["centro"], _i["largura"]
    sat = lambda p: float((p >= c + l / 2.0).mean())
    tira, _i2 = N.projetar(V.volume_da_projecao(s, com_osso=False), 0, 0, "mip",
                           "angio", lado=128, escala=s.escala)
    checar(u"com o osso a projeção satura (a isca: a calota esconde o vaso)",
           sat(com) > 0.15, sat(com))
    checar(u"sem o osso, nada satura", sat(tira) < 0.01, sat(tira))
    checar(u"e o vaso aparece acima do encéfalo na projeção",
           float(tira.max()) >= 300.0, float(tira.max()))
    checar(u"a RM não perde nada: sem HU, o volume é o mesmo",
           V.volume_da_projecao(N.abrir(img, "MR"), com_osso=False) is not None
           and V.volume_da_projecao(N.abrir(img, "MR"), com_osso=False).GetSize()
           == img.GetSize())
    checar(u"a tela tira o osso de fábrica e oferece «mostrar o osso»",
           "osso: false" in V.JS and "'&osso=' + (VX.osso ? 1 : 0)" in V.JS
           and u'data-vx="osso"' in V.pagina()
           and u"mostrar o osso" in V.pagina())
    cli = _cliente()
    import radai_thumbnail
    base = _tmp()
    pa, ua = _serie(base, "PAC_OSSO", n=30)
    b = radai_thumbnail.bilhete(pa, ua)
    vistos = []
    orig = V.volume_da_projecao

    def espia(s, com_osso=False):
        vistos.append(com_osso)
        return orig(s, com_osso)
    V.volume_da_projecao = espia
    try:
        r0 = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
        r1 = cli.get("/api/recon3d/vascular/projecao",
                     params={"b": b, "lado": 256, "osso": 1})
    finally:
        V.volume_da_projecao = orig
    checar(u"a rota tira o osso sem pedido e o devolve com osso=1",
           r0.status_code == 200 and r1.status_code == 200
           and vistos == [False, True], (r0.status_code, r1.status_code, vistos))


def _paginas():
    import radai_recon3d_screen as S
    import radai_recon3d_vascular as V
    return {"geral": S.pagina("geral"), "toracica": S.pagina("toracica"),
            "vascular": V.pagina()}


_AMPLIAR_JS = u"""
var CR = [];
function uiVisor(o){ CR.push(o.cranial === undefined ? 'sem' : o.cranial);
 return {corte: function(){ return 0 }} }
window.uiVisor = uiVisor;
function r3UrlDe(){ return '' }
function r3El(){ return null }
function r3Pintar(){}
var R3 = {b: 'b1', forma: [24, 128, 128], pos: {0: 0.5, 1: 0.5, 2: 0.5},
          jan: 'pulmao', cranial: -1};
r3Ampliar({eixo: 0, rot: 'axial'}, null);
r3Ampliar({eixo: 1, rot: 'coronal'}, null);
R3.cranial = 1;
r3Ampliar({eixo: 0, rot: 'axial'}, null);
console.log('JSON:' + JSON.stringify(CR));
"""


def teste_a_roda_vai_para_caudal_no_axial():
    secao(u"o visor ampliado do axial: a roda para baixo vai para caudal")
    import pydicom
    import radai_thumbnail
    import radai_recon3d_screen as S
    casos = ((("sup", "post", "esq"), 1), (("inf", "post", "dir"), -1),
             (("ant", "sup", "esq"), 0), (None, 0), ((), 0))
    checar(u"o sentido do eixo 0: sup 1, inf -1, outro ou nenhum 0",
           all(S.sentido_cranial(s) == e for s, e in casos),
           [S.sentido_cranial(s) for s, _e in casos])
    base = _tmp()
    pc, uc = _serie(base, "PAC_CABECA", n=8)
    pp, up = _serie(base, "PAC_PES", n=8)
    for nome in os.listdir(pp):
        f = os.path.join(pp, nome)
        ds = pydicom.dcmread(f)
        ds.ImageOrientationPatient = [-1, 0, 0, 0, 1, 0]
        ds.PatientPosition = "FFS"
        ds.save_as(f)
    cli = _cliente()
    ec = cli.get("/api/recon3d/estado",
                 params={"b": radai_thumbnail.bilhete(pc, uc)}).json()
    ep = cli.get("/api/recon3d/estado",
                 params={"b": radai_thumbnail.bilhete(pp, up)}).json()
    checar(u"o estado diz o sentido: cabeça primeiro 1, pés primeiro -1",
           ec.get("cranial") == 1 and ep.get("cranial") == -1,
           (ec.get("cranial"), ep.get("cranial"), ec.get("nao_le"),
            ep.get("nao_le")))
    js = S.JS_SERIE
    abrir = _funcao_js(js, "r3Abrir")
    checar(u"abrir a série guarda o sentido que o estado mandou (e zera antes)",
           u"R3.cranial = 0;" in abrir and u"d.cranial === 1" in abrir
           and u"R3.cranial = (d &&" in abrir, abrir[:200])
    amp = _funcao_js(js, "r3Ampliar")
    d, err = _node(_DOM + amp + _AMPLIAR_JS)
    checar(u"o visor ampliado recebe o sentido só no axial (o coronal segue "
           u"o índice)", d == [-1, 0, 1], d if d is not None else err)
    trecho = u"  cranial: p.eixo === 0 ? R3.cranial : 0,\n"
    checar(u"  (a isca acha o trecho)", trecho in amp)
    d2, _e = _node(_DOM + amp.replace(trecho, u"") + _AMPLIAR_JS)
    checar(u"  (isca) sem passar o sentido, o axial fica sem ele",
           d2 is not None and d2 != [-1, 0, 1], d2)


def teste_as_tres_telas_no_padrao():
    secao(u"as três telas no padrão: tag, frase, «?», abas, alerta")
    import radai_recon3d_screen as S
    for fer, p in _paginas().items():
        f = S.FERRAMENTAS_3D[fer]
        checar(u"[%s] a cabeça é a tag de função na cor do módulo" % fer,
               'class="ui-fn-tag"' in p and "--mod-recon" in p
               and u">%s</span></h1>" % f["nome"] in p)
        checar(u"[%s] a frase é a do autor" % fer,
               u'<p class="ui-fn-frase" data-radai-frase>%s</p>' % f["frase"] in p)
        checar(u"[%s] o «?» ao lado do título" % fer,
               re.search(r'<div class="ui-fn-tit">.*?class="ui-ajuda', p, re.S)
               is not None)
        checar(u"[%s] o item 1 tem as abas Acervo local · Aponte uma pasta" % fer,
               u'data-guia="acervo"' in p and u'data-guia="pasta"' in p
               and u"Acervo local" in p and u"Aponte uma pasta" in p)
        checar(u"[%s] «Procurar» abre o explorador de pastas" % fer,
               "uiExplorador(" in p and 'onclick="r3Procurar(this)"' in p)
        checar(u"[%s] o alerta de uma linha fecha a tela" % fer,
               p.rfind('class="ui-alerta') > p.rfind('class="ps-cx'))
        vis = _texto_visivel(p)
        checar(u"[%s] a tela não cita TPS" % fer, u"TPS" not in vis,
               vis[vis.find(u"TPS") - 60:vis.find(u"TPS") + 20])
        checar(u"[%s] sem parágrafo longo de fronteira na tela" % fer,
               "r3-semexp" not in p and "md-semexp" not in p)
        checar(u"[%s] a gravação do visor está na coluna da lista" % fer,
               re.search(r'<aside class="r3-l3d".*?class="r3-grav"', p, re.S)
               is not None)
    ger = _paginas()["geral"]
    i3d, igr, ijan = (ger.find('class="r3-3d"'), ger.find('class="r3-grade"'),
                      ger.find('id="j_pulmao"'))
    checar(u"as miniaturas vêm abaixo do 3D, e as janelas abaixo delas",
           0 < i3d < igr < ijan, (i3d, igr, ijan))
    checar(u"a miniatura é funcional: duplo clique abre o plano no visor de série",
           "addEventListener('dblclick', function(){ r3Ampliar(p, im) })" in ger
           and "uiVisor({titulo: p.rot" in ger)
    checar(u"o «?» da laje abre o MIP/MinIP educativo",
           'onclick="r3AjudaMip(this)"' in ger and "R3_SVG_MIP" in ger
           and "uiModal({titulo: 'MIP e MinIP'" in ger)
    checar(u"só a Torácica desenha no axial",
           'id="r3_desenhar"' in _paginas()["toracica"]
           and 'id="r3_desenhar"' not in ger)
    checar(u"a Vascular tem a projeção à esquerda e os comandos à direita",
           re.search(r'class="vx-palco"><div class="vx-proj".*?class="vx-cmd"',
                     _paginas()["vascular"], re.S) is not None)


def teste_os_cartoes_navegam():
    secao(u"os três cartões navegam, e as rotas existem")
    import radai_modules as M
    import radai_breadcrumb as B
    fs = dict((f[0], f) for f in M.FERRAMENTAS["recon3d"])
    for k, rota in (("recon_anatomia", "/recon3d/anatomia"),
                    ("recon_torax", "/recon3d/toracica"),
                    ("recon_vascular", "/recon3d/vascular")):
        f = fs.get(k) or ()
        checar(u"%s leva a %s" % (k, rota), len(f) > 3 and f[3] == rota, f[:4])
        checar(u"  e não está travado", not (len(f) > 5 and M.nao_navega(f[5])),
               f[5:6])
        checar(u"  e a trilha o conhece", (B.ARVORE.get(k) or ("", ""))[1] == rota)
    texto = u" ".join([M.MODULOS["recon3d"].get("frase", u"")]
                      + list((M.AJUDA.get("recon3d") or {}).get(u"O que não faz") or ()))
    checar(u"a fronteira das Reconstruções nomeia o ContourLab, e não o "
           u"Auto-Contorno", u"ContourLab" in texto
           and u"Auto-Contorno" not in texto, texto[:160])
    cli = _cliente()
    for rota in ("/recon3d/anatomia", "/recon3d/toracica", "/recon3d/vascular"):
        r = cli.get(rota)
        checar(u"%s responde 200" % rota, r.status_code == 200, r.status_code)


def _js_tela():
    import radai_recon3d_screen as S
    import radai_viewer
    return radai_viewer.JS_3D + S.JS_MALHA


_DOM = u"""
var document = {getElementById: function(){ return null },
  querySelectorAll: function(){ return [] }, querySelector: function(){ return null },
  addEventListener: function(){}, documentElement: {getAttribute: function(){ return 'pt-BR' }}};
var window = {devicePixelRatio: 1, addEventListener: function(){},
  matchMedia: function(){ return {matches: false} }};
var navigator = {};
function setTimeout(f){ return 0 }
var requestAnimationFrame = null;
"""


def teste_as_seis_vistas_e_o_zoom():
    secao(u"as seis vistas: mão direita, transição de 2 s, o zoom fica")
    prog = (_DOM + _js_tela() + u"""
var det = function(M){ return M[0]*(M[4]*M[8]-M[5]*M[7]) - M[1]*(M[3]*M[8]-M[5]*M[6])
  + M[2]*(M[3]*M[7]-M[4]*M[6]) };
var fora = {};
['ant','post','esq','dir','sup','inf'].forEach(function(k){
  var M = r3MatrizDaVista6(k); fora[k] = M ? Math.round(det(M)) : null });
var Ms = ['ant','post','esq','dir','sup','inf'].map(function(k){ return r3MatrizDaVista6(k).join(',') });
var distintas = Ms.filter(function(x, i){ return Ms.indexOf(x) === i }).length;
var a = r3MatrizDaVista6('ant'), b = r3MatrizDaVista6('dir');
var meio = r3MatrizDoQuat(r3Slerp(r3Quat(a), r3Quat(b), 0.5));
var orto = Math.abs(det(meio) - 1);
var ida = r3MatrizDoQuat(r3Quat(b)).map(function(v, i){ return Math.abs(v - b[i]) });
R3M.modo = 'gl'; R3G.gl = {}; R3G.zoom = 2.7;
var desenhou = 0; r3gDesenhar = function(){ desenhou++ };
var agora = 0; Date.now = function(){ return agora };
var fila = []; window.requestAnimationFrame = function(f){ fila.push(f) };
r3Vista('esq');
agora = 1000; while(fila.length){ var f = fila.shift(); f(); if(agora < 2500) agora += 500 }
var M = R3G.M, alvo = r3MatrizDaVista6('esq');
var chegou = M.every(function(v, i){ return Math.abs(v - alvo[i]) < 1e-9 });
var zoom_depois = R3G.zoom;
r3Vista('inicial');
console.log('JSON:' + JSON.stringify({det: fora, distintas: distintas, orto: orto,
  ida: Math.max.apply(null, ida), chegou: chegou, zoom: zoom_depois, quadros: desenhou,
  zoom_inicial: R3G.zoom, ms: R3_TRANSICAO_MS, z0: R3_ZOOM_INICIAL}));
""")
    d, err = _node(prog)
    if d is None:
        checar(u"o JS das vistas roda no node", False, err)
        return
    checar(u"as seis vistas existem e são de mão direita (det = +1)",
           d["det"] == {k: 1 for k in ("ant", "post", "esq", "dir", "sup", "inf")},
           d["det"])
    checar(u"  e são seis poses diferentes", d["distintas"] == 6, d["distintas"])
    checar(u"a interpolação esférica continua sendo rotação", d["orto"] < 1e-6)
    checar(u"matriz → quatérnio → matriz volta igual", d["ida"] < 1e-9)
    checar(u"a transição dura 2 s e termina na pose pedida",
           d["ms"] == 2000 and d["chegou"] and d["quadros"] >= 3, d)
    checar(u"o zoom em uso fica depois da vista", d["zoom"] == 2.7, d["zoom"])
    checar(u"o zoom inicial é 25% acima (1,25), e o ↻ volta a ele",
           d["z0"] == 1.25 and d["zoom_inicial"] == 1.25, d)
    js = _js_tela()
    velho = _funcao_js(js, "r3Vista").replace(
        "if(qual === 'inicial') R3G.zoom = R3_ZOOM_INICIAL;", "R3G.zoom = 1;")
    d2, _e = _node(_DOM + js + velho + u"""
R3M.modo = 'gl'; R3G.gl = {}; R3G.zoom = 2.7;
r3gDesenhar = function(){}; window.requestAnimationFrame = function(f){};
r3Vista('esq');
console.log('JSON:' + JSON.stringify({zoom: R3G.zoom}));""")
    checar(u"(isca) a vista de antes, que zerava o zoom, reprovaria",
           d2 is not None and d2["zoom"] != 2.7, d2)
    checar(u"quem pediu menos movimento vai direto, sem animar",
           "r3MenosMovimento()" in _funcao_js(js, "r3Vista"))
    recuo = u"""
R3M.modo = 'nuvem'; R3G.gl = null; N3.eixos = R3_EIXOS;
var desenhou = 0; n3Desenhar = function(){ desenhou++ };
var agora = 0; Date.now = function(){ return agora };
var fila = []; window.requestAnimationFrame = function(f){ fila.push(f) };
n3Mostrar = function(){ N3.escala = 10 };
r3nMostrar();
var e0 = N3.escala;
N3.escala = e0 * 2;
r3nMostrar();
var e1 = N3.escala;
r3Vista('dir');
var q0 = desenhou;
agora = 1000; while(fila.length){ var f = fila.shift(); f(); if(agora < 2500) agora += 500 }
var alvo = r3MatrizDaVista6('dir');
var chegou = !!N3.M && N3.M.every(function(v, i){ return Math.abs(v - alvo[i]) < 1e-9 });
var e2 = N3.escala;
r3Vista('inicial');
console.log('JSON:' + JSON.stringify({e0: e0, e1: e1, e2: e2, e3: N3.escala,
  quadros: desenhou, chegou: chegou}));"""
    d3, err3 = _node(_DOM + js + recuo)
    checar(u"sem WebGL, a nuvem abre com o zoom inicial de 1,25",
           d3 is not None and abs(d3["e0"] - 12.5) < 1e-9, d3 or err3)
    checar(u"  e o zoom de quem usa fica quando a lista muda",
           d3 is not None and abs(d3["e1"] - 25.0) < 1e-9, d3)
    checar(u"  as vistas da nuvem também giram em 2 s até a pose pedida",
           d3 is not None and d3["chegou"] and d3["quadros"] >= 4, d3)
    checar(u"  e mantêm o zoom; o ↻ volta a 1,25",
           d3 is not None and abs(d3["e2"] - 25.0) < 1e-9
           and abs(d3["e3"] - 12.5) < 1e-9, d3)
    velho_r = _funcao_js(js, "r3Vista")
    velho_r = velho_r[:velho_r.find(u"{") + 1] + u"""
 if(R3M.modo !== 'gl'){
  if(typeof n3Vista === 'function' && (qual === 'inicial' || N3_VISTAS[qual])) n3Vista(qual);
  else if(typeof n3Desenhar === 'function' && window.N3){
   var Mn = r3MatrizDaVista6(qual); if(Mn){ N3.M = Mn; n3Desenhar() }
  }
  return;
 }}"""
    d4, _e4 = _node(_DOM + js + velho_r + recuo)
    checar(u"(isca) o recuo de antes, que pulava para a vista, reprovaria",
           d4 is not None and not (d4["quadros"] >= 4 and d4["chegou"]
                                   and abs(d4["e3"] - 12.5) < 1e-9), d4 or _e4)


def teste_a_gravacao_do_visor():
    secao(u"a gravação do visor: MP4 ou WebM, cronômetro, Downloads")
    import radai_recon3d_screen as S
    g = S.JS_GRAVAR
    checar(u"grava pelo MediaRecorder, sobre o canvas composto do visor",
           "new MediaRecorder(" in g and ".captureStream(" in g
           and "cvGL" in g and "cv3Db" in g)
    checar(u"MP4 e WebM, conferidos no navegador (isTypeSupported)",
           "video/mp4" in g and "video/webm" in g and "isTypeSupported" in g)
    checar(u"o arquivo sai pelo download do navegador, com nome sem paciente",
           "a.download = r3vNome()" in g
           and "radioterapia_ai_reconstrucao3d_" in g)
    checar(u"o cronômetro corre e tem teto", "R3V_TETO_S" in g
           and "r3_crono" in g)
    proibidos = ("todataurl", "toblob", "stl", "showsavefilepicker")
    g_cod = re.sub(r"(?m)^\s*//[^\n]*", u" ", g).lower()
    achou = [x for x in proibidos if x in g_cod]
    checar(u"a gravação não tira imagem parada nem malha", not achou, achou)
    checar(u"(isca) um toDataURL na gravação seria acusado",
           "todataurl" in (g + "cvGL.toDataURL()").lower())
    for fer, p in sorted(_paginas().items()):
        scripts = u"".join(re.findall(r"(?is)<script[^>]*>(.*?)</script>", p))
        sem = re.sub(r"(?m)^\s*//[^\n]*", u" ",
                     scripts.replace(g, u"")).lower()
        html_ = re.sub(r"(?is)<script.*?</script>", u" ", p).lower()
        export = [x for x in ("download", "createobjecturl", "new blob",
                              ".mp4", ".webm", "todataurl", "toblob")
                  if x in sem]
        export += [x for x in ("download=",) if x in html_]
        checar(u"[%s] fora da gravação, a tela não exporta nada" % fer,
               not export, export)
    checar(u"a gravação só é chamada no fim do desenho e pelo laço",
           "if(window.r3vQuadro) r3vQuadro();" in S.JS_MALHA)
    prog = (_DOM + u"""
var tipos = {'video/webm;codecs=vp9': true, 'video/webm': true};
var MediaRecorder = function(){}; MediaRecorder.isTypeSupported = function(t){ return !!tipos[t] };
window.MediaRecorder = MediaRecorder;
""" + g + u"""
console.log('JSON:' + JSON.stringify({mp4: r3vTipo('mp4'), webm: r3vTipo('webm')}));""")
    d, err = _node(prog)
    checar(u"sem MP4 no navegador, oferece WebM e recusa MP4",
           d is not None and d["mp4"] == "" and d["webm"].startswith("video/webm"),
           d or err)


def teste_a_gravacao_declara_e_registra_o_ato():
    secao(u"a gravação: aviso de dado de paciente, ato declarado e registrado")
    import radai_recon3d_screen as S
    for fer, p in sorted(_paginas().items()):
        sem_balao = re.sub(r'(?is)<span class="ui-balao">.*?</span></span>', u" ", p)
        checar(u"[%s] a linha curta do rosto está à vista, fora de balão" % fer,
               u'id="r3_grav_aviso"' in sem_balao
               and S.AVISO_CURTO_DA_GRAVACAO in sem_balao)
        checar(u"[%s] o texto longo (rosto, Downloads, nuvem) saiu da vista" % fer,
               S.AVISO_DA_GRAVACAO not in sem_balao)
        depois = re.search(
            r'(?is)' + re.escape(S.ATO_DA_GRAVACAO)
            + r'</span></label>\s*<span class="ui-ajuda[^"]*"[^>]*>\?'
            r'<span class="ui-balao">(.*?)</span></span>', p)
        checar(u"[%s] e mora no «?» logo depois de «declaro esta gravação», "
               u"fora do rótulo da caixa" % fer,
               depois is not None and S.AVISO_DA_GRAVACAO in depois.group(1))
        checar(u"[%s] a declaração é uma caixa, e o botão nasce desligado" % fer,
               u'id="r3_grav_ato"' in p and u'id="r3_gravar" disabled' in p)
    isca = (u'<div id="r3_grav_aviso"><span>%s</span></div>'
            % S.AVISO_DA_GRAVACAO)
    checar(u"(isca) o aviso longo à vista, como era, reprova",
           S.AVISO_DA_GRAVACAO in re.sub(
               r'(?is)<span class="ui-balao">.*?</span></span>', u" ", isca))
    checar(u"a linha curta é a combinada",
           S.AVISO_CURTO_DA_GRAVACAO == u"pode conter o rosto; é dado de paciente")
    g = S.JS_GRAVAR
    grava = _funcao_js(g, u"r3vGravar") or u""
    checar(u"r3vGravar registra o ato ANTES de abrir o MediaRecorder",
           u"/api/recon3d/ato-de-gravacao" in grava and u"new MediaRecorder(" not in grava
           and u"r3vComecar(tipo)" in grava)
    checar(u"  e recusa sem a caixa marcada", u"if(!r3vAtoMarcado())" in grava)
    salva = _funcao_js(g, u"r3vSalvar") or u""
    checar(u"  e o ato vale para UMA gravação (a caixa desmarca ao salvar)",
           u"ato.checked = false" in salva)
    base = _tmp()
    velho = os.environ.get("RADAI_CALIB_DIR")
    os.environ["RADAI_CALIB_DIR"] = base
    try:
        c = _cliente()
        r = c.post(u"/api/recon3d/ato-de-gravacao", json={u"formato": u"mp4"})
        arq = os.path.join(base, S.ARQUIVO_ATOS_DO_VIDEO)
        txt = io.open(arq, encoding="utf-8").read() if os.path.exists(arq) else u""
        checar(u"a rota grava o ato no arquivo de atos, sem identificador",
               r.status_code == 200 and r.json().get("ok") and u"(mp4)" in txt
               and u"ato declarado" in txt, (r.status_code, txt[:120]))
        r2 = c.post(u"/api/recon3d/ato-de-gravacao", json={u"formato": u"avi"})
        checar(u"  formato desconhecido é recusado", r2.status_code == 400)
        guardada = S.gravar_ato_do_video

        def _quebra(_f):
            raise OSError("disco")
        S.gravar_ato_do_video = _quebra
        try:
            r3 = c.post(u"/api/recon3d/ato-de-gravacao", json={u"formato": u"webm"})
        finally:
            S.gravar_ato_do_video = guardada
        checar(u"  sem conseguir gravar o ato, a rota diz não (a gravação não começa)",
               r3.status_code == 500 and not r3.json().get("ok"))
    finally:
        if velho is None:
            os.environ.pop("RADAI_CALIB_DIR", None)
        else:
            os.environ["RADAI_CALIB_DIR"] = velho
    checar(u"(isca) o r3vGravar de antes, que abria o MediaRecorder direto, reprova",
           u"/api/recon3d/ato-de-gravacao" not in
           u"function r3vGravar(){ R3V.rec = new MediaRecorder(fluxo) }")


def teste_a_lista_filtra_e_liga():
    secao(u"a lista do 3D: filtrar, ligar todas, desligar todas")
    prog = (_DOM + _js_tela() + u"""
r3mPintarLista = function(){};
r3mSincronizar = function(){};
R3M.estr = [{nome: 'Lung_L_ai'}, {nome: 'Lung_R_ai'}, {nome: 'Heart_ai'}];
R3M.lig = {};
R3M.filtro = 'lung';
r3mTodas(true);
var a = JSON.parse(JSON.stringify(R3M.lig));
R3M.filtro = '';
r3mTodas(false);
console.log('JSON:' + JSON.stringify({filtrado: a, todas: R3M.lig}));""")
    d, err = _node(prog)
    checar(u"«ligar todas» com filtro liga só as que o filtro mostra",
           d is not None and d["filtrado"] == {"Lung_L_ai": True, "Lung_R_ai": True},
           d or err)
    checar(u"«desligar todas» sem filtro desliga todas",
           d is not None and not any(d["todas"].values()), d)


EXTRA_JS = (
    u"Nenhuma série foi contornada nesta máquina ainda.",
    u"Nenhuma série desta estação rodou o protocolo Anatomia Torácica.",
    u"não consegui ler o acervo desta estação", u"não consegui listar esta pasta",
    u"Nenhuma série nesta pasta.", u"escolha a pasta com as séries",
    u"a ficha venceu: escolha a série no acervo",
    u"a série não está mais nesta pasta", u"desenho do axial",
    u"este navegador não grava neste formato", u"não consegui montar o volume",
    u"projetando", u"Parar e salvar", u"Iniciar gravação", u"carregando…",
    u"abrindo a série…", u"todo o volume")


FRASES_QUE_ESPERAM_A_TRADUCAO = ()


def teste_as_frases_novas_tem_os_doze_idiomas():
    secao(u"toda frase nova das três telas está nos doze idiomas")
    import radai_phrases as F
    tab = {}
    for t in F.TABELA:
        tab[F.normalizar(t[0])] = t
    import html
    frases = set()
    for fer, p in _paginas().items():
        for m in re.finditer(r"data-radai-frase>([^<]+)<", p):
            frases.add(F.normalizar(html.unescape(m.group(1))))
        for m in re.finditer(r'<p class="ui-fn-frase" data-radai-frase>([^<]+)<', p):
            frases.add(F.normalizar(html.unescape(m.group(1))))
        bal = re.search(r'<div class="ui-fn-tit">.*?<span class="ui-balao">(.*?)</span></span>',
                        p, re.S)
        for par in re.findall(r"<p>(.*?)</p>", bal.group(1) if bal else u""):
            frases.add(F.normalizar(html.unescape(re.sub(r"<[^>]+>", u"", par))))
        for m in re.finditer(r"r3Frase\('([^']+)'\)", p):
            frases.add(F.normalizar(m.group(1)))
        for m in re.finditer(r"(?:uiTexto\([^,]+,|r3vMsg\(|diz\()\s*'([^']+)'", p):
            frases.add(F.normalizar(m.group(1)))
        for m in re.finditer(r'(?:placeholder|aria-label|title)="([^"]+)"', p):
            frases.add(F.normalizar(html.unescape(m.group(1))))
        for m in re.finditer(r'class="ui-alerta[^"]*">.*?<span data-radai-frase>(.*?)</span></div>',
                             p, re.S):
            frases.add(F.normalizar(html.unescape(re.sub(r"<[^>]+>", u"", m.group(1)))))
    import radai_recon3d_screen as S
    import radai_recon3d_vascular as V
    frases.update(F.normalizar(x) for x in EXTRA_JS)
    frases.update(F.normalizar(x) for x in S.AJUDA_EXPORTA + V.AJUDA)
    frases.add(F.normalizar(S.NOME_ROTULOS))
    import radai_modules as M
    for f in M.FERRAMENTAS["recon3d"]:
        for tag in (f[6] if len(f) > 6 else ()):
            frases.add(F.normalizar(tag))
    for v in M.secoes_de_ajuda(u"recon3d").values():
        for par in v:
            frases.add(F.normalizar(html.unescape(re.sub(r"<[^>]+>", u"", par))))
    frases = set(f for f in frases if f and "' +" not in f
                 and not re.match(r"^[\W\d_]+$", f)
                 and f not in (u"DEMO", u"MIP", u"MinIP", u"MP4", u"WebM",
                               u"LAO/RAO", u"CRA/CAU", u"ajuda", u"angio", u"3D")
                 and not f.endswith(u"—"))
    pendentes = set(F.normalizar(x) for x in FRASES_QUE_ESPERAM_A_TRADUCAO)
    faltam = sorted(f for f in frases if f not in tab and f not in pendentes)
    checar(u"toda frase tem chave no dicionário", not faltam, faltam[:12])
    resolvidas = sorted(f for f in pendentes if f in tab)
    checar(u"frase que já ganhou tradução sai da lista de espera",
           not resolvidas, resolvidas)
    sumidas = sorted(f for f in pendentes if f not in frases)
    checar(u"e a lista de espera só tem frase que a tela usa",
           not sumidas, sumidas)
    incompletas = sorted(f for f in frases if f in tab
                         and sum(1 for c in tab[f][1:] if c) < 11)
    checar(u"e as onze traduções", not incompletas, incompletas[:8])
    checar(u"(isca) uma frase inventada seria acusada",
           u"frase que ninguém escreveu" not in tab)


def main():
    print(u"test_recon3d_v84 | as Reconstruções 3D da v8.4")
    testes = [teste_a_malha_do_rotulo_cai_no_lugar,
              teste_o_filtro_de_vaso,
              teste_o_desenho_interpola_entre_os_cortes,
              teste_o_acervo_por_ferramenta,
              teste_a_demo_saiu_do_acervo,
              teste_os_conjuntos_da_serie_e_o_mapa,
              teste_a_roda_vai_para_caudal_no_axial,
              teste_a_ficha_do_ver_segmentacao,
              teste_a_rota_do_desenho,
              teste_a_vascular_projeta_e_inverte,
              teste_a_vascular_tira_a_calota,
              teste_as_tres_telas_no_padrao,
              teste_os_cartoes_navegam,
              teste_as_seis_vistas_e_o_zoom,
              teste_a_gravacao_do_visor,
              teste_a_gravacao_declara_e_registra_o_ato,
              teste_a_lista_filtra_e_liga,
              teste_as_frases_novas_tem_os_doze_idiomas]
    todos = set(k for k, v in globals().items()
                if k.startswith("teste_") and callable(v))
    fora = sorted(todos - set(f.__name__ for f in testes))
    checar(u"todo teste do arquivo está na lista do main()", not fora, fora)
    for t in testes:
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            checar(u"%s (exceção inesperada)" % t.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
    print(u"\n" + u"=" * 64)
    if FALHOU:
        print(u"FALHOU: %d de %d checagens" % (len(FALHOU), OK + len(FALHOU)))
        for n in FALHOU:
            print(u"  - %s" % n)
    else:
        print(u"OK: %d checagens, todas passaram" % OK)
    print(u"=" * 64)
    return 1 if FALHOU else 0


if __name__ == "__main__":
    sys.exit(main())
