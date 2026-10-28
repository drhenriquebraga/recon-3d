# -*- coding: utf-8 -*-
import tempfile
import shutil
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
_cleanup.adotar_prefixo('radai_ac_recon3d')
_cleanup.adotar_prefixo('r3d_')


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "radai_watcher.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)
sys.path.insert(0, APP)

import tempfile as _tempfile
import _componentes
os.environ["RADAI_CALIB_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_recon3d_")


_RESULTADOS = []

PACIENTE_COM_ESPACO = u"ISCA BELTRANO 12345"


def _tem_paciente(texto):
    return any(p in (texto or u"") for p in PACIENTE_COM_ESPACO.split())


def checar(nome, ok, detalhe=""):
    _RESULTADOS.append((nome, bool(ok), detalhe))
    if not ok:
        print("  FALHA  %s%s" % (nome, ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print("\n-- %s --" % t)


def teste_mip_e_minip_sao_max_e_min():
    secao("MIP e MinIP: o extremo da laje, e nao a fatia do meio")
    import numpy as np
    import radai_recon3d as R
    v = np.zeros((20, 8, 8), dtype=np.int16)
    v[:] = -800
    v[7, 3, 3] = 900
    v[12, 5, 5] = -1000
    mip = R.projetar(v, 0, "mip", 0, 20)
    minip = R.projetar(v, 0, "minip", 0, 20)
    checar("o MIP encontra o valor alto escondido", mip[3, 3] == 900,
           str(mip[3, 3]))
    checar("o MinIP encontra o mais baixo", minip[5, 5] == -1000,
           str(minip[5, 5]))
    checar("e o resto do MIP fica no ar", mip[0, 0] == -800, str(mip[0, 0]))
    fora = R.projetar(v, 0, "mip", 0, 5)
    checar("valor fora da laje NAO aparece", fora[3, 3] == -800, str(fora[3, 3]))


def teste_a_laje_nao_estoura_o_volume():
    secao("a laje e aparada, e nao estoura")
    import numpy as np
    import radai_recon3d as R
    v = np.zeros((10, 4, 4), dtype=np.int16)
    v[:] = 5
    for i0, i1 in ((-50, 500), (9, 9), (0, 1), (100, 200)):
        try:
            a = R.projetar(v, 0, "mip", i0, i1)
            ok = a.shape == (4, 4)
        except Exception as e:
            ok = False
            print("   %s" % e)
        checar("laje (%s, %s) nao estoura" % (i0, i1), ok)


def teste_png_sem_pil():
    secao("PNG por zlib, sem Pillow")
    import numpy as np
    import radai_recon3d as R
    a = np.array([[-1000, 0], [500, 1000]], dtype=np.int16)
    png = R.para_png(a, 40, 400)
    checar("comeca com a assinatura PNG", png[:8] == b"\x89PNG\r\n\x1a\n")
    checar("tem IHDR", b"IHDR" in png[:32])
    checar("e IEND no fim", png[-8:-4] == b"IEND" or b"IEND" in png[-12:])
    escuro = R.para_png(np.array([[-2000]], dtype=np.int16), 40, 400)
    claro = R.para_png(np.array([[3000]], dtype=np.int16), 40, 400)
    checar("valor abaixo da janela vira preto e nao estoura", len(escuro) > 40)
    checar("valor acima vira branco e nao estoura", len(claro) > 40)


def teste_serie_sem_contorno_manda_para_o_auto_contorno():
    secao("serie sem contorno: manda para o Auto-Contorno")
    import tempfile
    import radai_recon3d as R
    vazia = tempfile.mkdtemp(prefix="r3d_")
    e = R.estado_da_serie(vazia)
    checar("diz que NAO esta segmentada", e["segmentada"] is False)
    checar("e diz o que fazer", "Auto-Contorno" in e["o_que_fazer"],
           e["o_que_fazer"][:70])
    checar("com a rota para segmentar", e.get("rota_para_segmentar") == "/lote",
           str(e.get("rota_para_segmentar")))
    open(os.path.join(vazia, "RS_RadAI_20260101_abc.dcm"), "wb").write(b"x")
    open(os.path.join(vazia, "RS_RadAI_TS_20260101_abc.dcm"), "wb").write(b"x")
    e2 = R.estado_da_serie(vazia)
    checar("com contorno, diz que esta segmentada", e2["segmentada"] is True)
    checar("e reconhece os dois conjuntos", len(e2["conjuntos"]) == 2,
           str(len(e2["conjuntos"])))
    cods = sorted(c["conjunto"] for c in e2["conjuntos"])
    checar("distinguindo o entregue do `_ts`", cods == ["oar", "ts"], str(cods))


def teste_o_modulo_nao_exporta():
    secao("o modulo NAO exporta, e isso e travado")
    fonte = open(_componentes.fonte("app/radai_recon3d.py"), encoding="utf-8").read()
    codigo = "\n".join(l for l in fonte.splitlines()
                       if not l.lstrip().startswith("#"))
    for tres in (chr(34) * 3, chr(39) * 3):
        partes = codigo.split(tres)
        codigo = "".join(partes[::2])
    baixo = codigo.lower()
    for proibido in ("download", "attachment", "content-disposition",
                     "save_mesh", "salvar_malha", "exportar", "to_obj",
                     "to_stl", ".mp4", ".webm"):
        checar("o codigo nao tem `%s`" % proibido, proibido not in baixo)
    checar("o GUARDA: diz o motivo da recusa (uso pretendido) e que o "
           "RTSTRUCT continua exportando",
           any("GUARDA:" in l and "exporta" in l
               for l in fonte.splitlines())
           and "uso pretendido" in fonte
           and "RTSTRUCT continua exportando" in fonte)


def teste_nao_ha_deteccao():
    secao("nada de deteccao: renderizar e exibir")
    fonte = open(_componentes.fonte("app/radai_recon3d.py"), encoding="utf-8").read()
    codigo = "\n".join(l for l in fonte.splitlines()
                       if not l.lstrip().startswith("#"))
    for tres in (chr(34) * 3, chr(39) * 3):
        codigo = "".join(codigo.split(tres)[::2])
    baixo = codigo.lower()
    for proibido in ("candidat", "suspeit", "probabilid", "malign",
                     "realce", "lung_rads", "score", "detect"):
        checar("o codigo nao tem `%s`" % proibido, proibido not in baixo)


def _sem_prosa(caminho):
    fonte = io.open(caminho, encoding="utf-8").read()
    codigo = "\n".join(l for l in fonte.splitlines()
                       if not l.lstrip().startswith("#"))
    for tres in (chr(34) * 3, chr(39) * 3):
        codigo = "".join(codigo.split(tres)[::2])
    codigo = re.sub(r"<!--.*?-->", " ", codigo, flags=re.S)
    return fonte, codigo


def teste_a_tela_tambem_nao_exporta():
    secao("a TELA tambem nao exporta")
    fonte, codigo = _sem_prosa(_componentes.fonte("app/radai_recon3d_screen.py"))
    import tokenize
    with io.open(_componentes.fonte("app/radai_recon3d_screen.py"), "rb") as _f:
        _toks = list(tokenize.tokenize(_f.readline))
    codigo = u" ".join(x.string for x in _toks
                       if x.type not in (tokenize.STRING, tokenize.COMMENT))
    baixo = codigo.lower()
    for proibido in ("download", "attachment", "content-disposition",
                     "toblob", "todataurl", "createobjecturl", "canvas",
                     "to_obj", "to_stl", ".mp4", ".webm"):
        checar("a tela nao tem `%s`" % proibido, proibido not in baixo)
    fontes = dict((n, io.open(_componentes.fonte("app/" + n), encoding="utf-8").read())
                  for n in _MODULOS_DAS_RECONSTRUCOES
                  if os.path.isfile(_componentes.fonte("app/" + n)))
    checar("os modulos das Reconstrucoes estao todos na conferencia das rotas",
           sorted(fontes) == sorted(_MODULOS_DAS_RECONSTRUCOES), sorted(fontes))
    achados = [(n, x) for n, f in sorted(fontes.items()) for x in _rotas_que_exportam(f)]
    checar("nenhuma rota das Reconstrucoes devolve arquivo para levar "
           "(FileResponse, StreamingResponse, attachment)", not achados, str(achados))
    isca = fontes["radai_recon3d_vascular.py"] + (
        u"\n\ndef _isca(app):\n    from fastapi.responses import Response\n"
        u"    @app.get('/api/recon3d/vascular/isca')\n    def _i():\n"
        u"        return Response(b'', headers={'Content-Disposition': 'attachment; filename=v.png'})\n")
    checar("(isca) uma rota com Content-Disposition costurada na Vascular seria acusada",
           bool(_rotas_que_exportam(isca)), str(_rotas_que_exportam(isca)))
    isca2 = fontes["radai_recon3d_vascular.py"] + (
        u"\n\ndef _isca2(caminho):\n    from fastapi.responses import FileResponse\n"
        u"    return FileResponse(caminho)\n")
    checar("(isca) um FileResponse costurado seria acusado",
           bool(_rotas_que_exportam(isca2)), str(_rotas_que_exportam(isca2)))
    import radai_recon3d_screen as _S
    checar("a tela diz que nao exporta",
           u"não exporta" in _S.AJUDA_EXPORTA[0])
    checar("e diz por que", "uso pretendido" in _S.AJUDA_EXPORTA[0].lower())


_MODULOS_DAS_RECONSTRUCOES = ("radai_recon3d_screen.py", "radai_recon3d_vascular.py",
                              "radai_recon3d_desenho.py")


def _rotas_que_exportam(fonte):
    import ast
    arv = ast.parse(fonte)
    soltas = set()
    for no in ast.walk(arv):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant):
            soltas.add(id(no.value))
    fora = []
    for no in ast.walk(arv):
        if isinstance(no, ast.Name) and no.id in ("FileResponse", "StreamingResponse"):
            fora.append(no.id)
        elif isinstance(no, ast.Attribute) and no.attr in ("FileResponse", "StreamingResponse"):
            fora.append(no.attr)
        elif isinstance(no, ast.alias) and no.name.split(".")[-1] in ("FileResponse", "StreamingResponse"):
            fora.append(no.name)
        elif (isinstance(no, ast.Constant) and isinstance(no.value, str)
              and id(no) not in soltas):
            v = no.value.lower()
            if "<" in v or "function" in v:
                continue
            for x in ("attachment", "content-disposition"):
                if x in v:
                    fora.append(no.value[:60])
    return fora


def _abre_sozinho_sem_serie(js):
    ini = _funcao_js(js, "r3IniciarTela")
    return ("uiPopupSerie('r3_escolha', {sozinho: function(){ return !R3.ficha && !R3.b }})"
            in ini and "function r3PrimeiroSeNada" not in js)


def teste_a_escolha_da_serie_e_o_popup_da_casca():
    secao("a etapa 1 vira cartao; a escolha mora no popup da casca, que abre sozinho")
    import radai_recon3d_screen as S
    import radai_recon3d_vascular as V
    for nome, p in (("anatomia", S.pagina("geral")), ("toracica", S.pagina("toracica")),
                    ("vascular", V.pagina())):
        checar("[%s] o cartao «Escolha a serie» abre o popup" % nome,
               'id="r3_cartao" data-ui-ps-abre="r3_escolha"' in p
               and 'id="r3_p1"' in p and 'class="ps-cx' not in p.split('id="r3_p1"')[1][:40])
        checar("[%s]   e o popup tem as duas abas, o acervo como padrao, e abre sozinho" % nome,
               '<div class="ui-ps" id="r3_escolha" data-ui-ps' in p
               and 'data-sozinho>' in p.split('id="r3_escolha"')[1][:160]
               and 'class="ui-guias esq" id="r3_origem" data-ativa="acervo"' in p)
    js = S.JS_SERIE
    checar("abre sozinho so quando a tela chegou sem serie (sem ficha), e nenhuma serie "
           "abre sozinha atras dele", _abre_sozinho_sem_serie(js))
    isca = js.replace("return !R3.ficha && !R3.b", "return true")
    checar("  (isca) abrir sempre, mesmo com a ficha, e acusado",
           isca != js and not _abre_sozinho_sem_serie(isca))
    abrir = _funcao_js(js, "r3Abrir")
    checar("escolher fecha o popup e o cartao diz a serie",
           "pp.fechar()" in abrir and "r3Cartao(rotulo" in abrir)
    checar("a ficha que venceu reabre o popup (r3SemSerie)",
           js.count("r3SemSerie()") >= 2)


def _varrer_recon3d(S, pasta, uso=None):
    import radai_varrer
    d = radai_varrer.iniciar(uso or S.USO_DA_VARREDURA, pasta, dias=0,
                             em_segundo_plano=False)
    return dict((str(x.get("pid")), x) for x in d.get("linhas") or ()), d


def _a_pasta_lista_pela_varredura_da_casca(S):
    from datetime import datetime
    from fastapi import FastAPI
    import make_test_series
    import radai_thumbnail
    import radai_varrer
    app = FastAPI()
    S.montar(app)
    rotas = set(getattr(r, "path", "") for r in app.routes)
    checar("a rota do POST unico saiu da montagem, e o uso da varredura entrou",
           "/api/recon3d/series" not in rotas
           and radai_varrer.uso(S.USO_DA_VARREDURA) is not None,
           str(sorted(x for x in rotas if x.startswith("/api/recon3d"))))
    base = tempfile.mkdtemp(prefix="r3d_varrer_")
    try:
        p_seg = os.path.join(base, "PAC_SEG", "CT")
        uid_seg = make_test_series.escreve_serie(p_seg, "PAC_SEG",
                                                 datetime.now(), 6)
        io.open(os.path.join(p_seg, "RS_RadAI_20261025_%s.dcm"
                             % uid_seg[-8:]), "wb").close()
        make_test_series.escreve_serie(os.path.join(base, "PAC_SEM", "CT"),
                                       "PAC_SEM", datetime.now(), 6)
        make_test_series.escreve_serie(os.path.join(base, "PAC_UM", "CT"),
                                       "PAC_UM", datetime.now(), 1)
        por, d = _varrer_recon3d(S, base)
        checar("a varredura da casca acha as series da pasta (a de 1 corte "
               "fica de fora)", sorted(por) == ["PAC_SEG", "PAC_SEM"]
               and not d.get("erro"), "%s %s" % (sorted(por), d.get("erro")))
        seg, sem = por.get("PAC_SEG") or {}, por.get("PAC_SEM") or {}
        checar("  cada linha diz se a serie esta segmentada (o RS_RadAI_ dela "
               "ao lado)", seg.get("segmentada") is True
               and sem.get("segmentada") is False
               and seg.get("estudo_3d") == [], "%s %s" % (
                   seg.get("segmentada"), sem.get("segmentada")))
        pasta_b, uid_b = radai_thumbnail.resolver(seg.get("bilhete") or "")
        checar("  e o bilhete da linha abre a serie certa",
               bool(pasta_b) and uid_b == uid_seg, str(uid_b)[-8:])
        radai_varrer.registrar_series_de_pasta("recon3d_isca")
        por_i, _d = _varrer_recon3d(S, base, uso="recon3d_isca")
        checar("  (isca) sem o enriquecer da tela, a linha nao diz segmentada "
               "e a de 1 corte entra",
               "segmentada" not in (por_i.get("PAC_SEG") or {})
               and "PAC_UM" in por_i, str(sorted(por_i)))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_serie_vem_de_uma_lista():
    secao("a serie vem de uma lista, e a lista vem de quem ja a tinha")
    import radai_recon3d_screen as S
    fonte, _c = _sem_prosa(_componentes.fonte("app/radai_recon3d_screen.py"))
    p = S.pagina("geral")
    checar("o item 1 tem a aba do acervo e a da pasta",
           'data-guia="acervo"' in p and 'data-guia="pasta"' in p)
    checar("o acervo e a tabela comum da Suite (C2), no lugar da lista de botoes",
           'id="r3_acervo" data-ui-acervo' in p
           and "uiTabelaAcervo(alvo" in S.JS_SERIE
           and "r3LinhaAcervo" not in S.JS_SERIE)
    checar("  pedida a rota desta ferramenta, por POST",
           "url: '/api/recon3d/acervo?ferramenta='" in S.JS_SERIE)
    checar("e as linhas sao as da tabela da Suite (`radai_tabela_acervo.linhas`)",
           "radai_tabela_acervo.linhas(" in fonte)
    listar = _funcao_js(S.JS_SERIE, "r3Listar")
    checar("a pasta lista pela varredura da casca em segundo plano, "
           "e nao por um POST unico",
           "window.uiVarrerLista({" in listar and "r3Post(" not in listar
           and "/api/recon3d/series" not in fonte
           and "radai_varrer.registrar_series_de_pasta(" in fonte
           and ("var R3_USO_DA_VARREDURA = '%s';" % S.USO_DA_VARREDURA)
           in S.JS_SERIE and "uso: R3_USO_DA_VARREDURA" in listar, listar[:200])
    checar("  com o filtro de data e a linha de estado da casca",
           "dias: 'r3_dias'" in listar and "estado: 'r3_busca'" in listar
           and 'id="r3_dias"' in p and 'id="r3_busca"' in p)
    checar("  e a estrela da pasta favorita ao lado do campo",
           'data-ui-fav="r3_pasta"' in p)
    checar("e NAO reimplementa a busca por RTSTRUCT",
           "_rs_existente" not in fonte and "radai_batch" not in fonte)
    checar("o campo de caminho continua, na aba «Aponte uma pasta»",
           'id="r3_pasta"' in p)
    checar("e «Procurar» abre o explorador de pastas",
           "uiExplorador({" in S.JS_SERIE)
    checar("sem pasta, nada e varrido (o campo treme), e o ROOT nao e lido",
           "uiTremer" in listar and "root_configurado" not in fonte)
    _a_pasta_lista_pela_varredura_da_casca(S)
    abrir = _funcao_js(S.JS_SERIE, "r3Abrir")
    checar("abrir a serie e pedir o estado pelo bilhete, nunca pelo caminho",
           "encodeURIComponent(b)" in abrir and "pasta" not in abrir,
           abrir[:160])
    import radai_config
    checar("`root_configurado` existe e nao levanta",
           isinstance(radai_config.root_configurado(), str))
    v = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    checar("o vigia usa o mesmo dono do caminho",
           "radai_config.caminho_padrao()" in v)
def teste_os_quatro_quadros():
    secao("os quatro quadros, cada um com seu deslizador")
    fonte, _c = _sem_prosa(_componentes.fonte("app/radai_recon3d_screen.py"))
    import radai_recon3d_screen as _S0
    _pag = _S0.pagina()
    for eixo in (0, 1, 2):
        checar("o plano %d tem imagem" % eixo, ('id="r3_img%d"' % eixo) in _pag)
        checar("e deslizador proprio", ('id="r3_pos%d"' % eixo) in _pag)
    checar("a projecao tem imagem propria", 'id="r3_imgp"' in fonte)
    checar("com laje", 'id="r3_laje"' in fonte)
    checar("e com escolha de eixo", 'id="r3_eixop"' in fonte)
    for rot in ("axial", "coronal", "sagital"):
        checar("o quadro `%s` esta rotulado" % rot, rot in fonte)

    import radai_recon3d_screen as _S
    js = _S.JS_SERIE
    checar("o plano usa a MESMA rota da projecao",
           js.count("/api/recon3d/projecao") == 1,
           str(js.count("/api/recon3d/projecao")))
    checar("e as duas imagens passam por `r3Url`",
           js.count("r3Url(") == 3)
    checar("e a laje 0 quer dizer um voxel",
           "r3Url(eixo, 0)" in fonte)
    checar("o servidor apara a laje para pelo menos 1 voxel",
           "max(1, int(round(float(laje) / mm)))" in fonte)

    checar("a tela nao escreve par de janela nenhum",
           "R.JANELAS.get" in fonte and "1500" not in _S.JS_SERIE)


def teste_os_tres_cartoes_navegam():
    secao("os tres cartoes do modulo navegam")
    import radai_modules
    fs = radai_modules.FERRAMENTAS.get("recon3d") or ()
    checar("o modulo tem tres cartoes", len(fs) == 3, str(len(fs)))
    obras = [f for f in fs
             if (len(f) > 5 and radai_modules.nao_navega(f[5]))]
    checar("nenhum deles travado", not obras, str(obras))
    checar("todos com rota", all(f[3] for f in fs), [f[3] for f in fs])
    checar("(isca) com «EM BREVE», a mesma pergunta travaria",
           radai_modules.nao_navega(u"EM BREVE"))
    p = radai_modules.pagina("recon3d")
    checar("e a pagina desenha os tres como link",
           p.count('<a class="md-fer') >= 3, p.count('<a class="md-fer'))


def _fantoma_3d():
    import numpy as np
    v = np.full((60, 80, 80), -1000, dtype=np.int16)
    zz, yy, xx = np.ogrid[:60, :80, :80]
    corpo = ((yy - 40) ** 2 + (xx - 40) ** 2 <= 30 ** 2) & (zz >= 5) & (zz < 55)
    v[np.broadcast_to(corpo, v.shape)] = 40
    faixa = (zz >= 10) & (zz < 50)
    pulmao = ((yy - 40) ** 2 + (xx - 28) ** 2 <= 10 ** 2) & faixa
    v[np.broadcast_to(pulmao, v.shape)] = -800
    osso = ((yy - 40) ** 2 + (xx - 55) ** 2 <= 5 ** 2) & faixa
    v[np.broadcast_to(osso, v.shape)] = 700
    v[10:50, 30:51, 63] = 700
    v[30, 40, 20] = 700
    return v, (2.0, 1.0, 1.0)


def teste_o_3d_de_osso_e_pele():
    secao("o 3D: osso e pele pela densidade")
    import numpy as np
    import radai_recon3d as R
    v, esp = _fantoma_3d()
    d = R.cena_3d(v, esp, ("sup", "post", "esq"))
    camadas = dict((it.get("camada"), it) for it in d.get("itens") or [])
    checar("sai uma camada de osso e uma de pele",
           set(camadas) == {"osso", "pele"}, str(sorted(camadas)))
    checar("a bussola recebe os eixos na ordem do desenho",
           d.get("eixos") == ["esq", "post", "sup"], str(d.get("eixos")))
    if set(camadas) != {"osso", "pele"}:
        return
    pele = np.asarray(camadas["pele"]["pontos"], dtype=float)
    osso = np.asarray(camadas["osso"]["pontos"], dtype=float)
    cx = (pele[:, 0].min() + pele[:, 0].max()) / 2.0
    cy = (pele[:, 1].min() + pele[:, 1].max()) / 2.0
    cz = (pele[:, 2].min() + pele[:, 2].max()) / 2.0
    r = np.hypot(pele[:, 0] - cx, pele[:, 1] - cy)
    lado = np.abs(pele[:, 2] - cz) < 30.0
    dentro = int(((r < 24.0) & lado).sum())
    checar("a pele NAO desenha o pulmao por dentro", dentro == 0,
           "%d ponto(s) de pele a menos de 24 mm do eixo" % dentro)
    checar("e desenha o contorno do corpo (r ~ 30 mm)",
           float(np.median(r[lado])) > 27.0, "%.1f" % float(np.median(r[lado])))
    nrm = np.asarray(camadas["pele"]["normais"], dtype=float)
    radial = np.stack([pele[:, 0] - cx, pele[:, 1] - cy], axis=1)
    radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-9)
    fora = float((np.sum(radial[lado] * nrm[lado][:, :2], axis=1) > 0).mean())
    checar("as normais da pele apontam para fora do corpo", fora > 0.95,
           "%.0f%%" % (100 * fora))
    cilindro = osso[np.abs(osso[:, 0] - cx - 15.0) < 7.0]
    dx = float(np.mean(cilindro[:, 0]) - cx) if len(cilindro) else 0.0
    checar("osso e pele no mesmo referencial (osso a +15 mm do eixo)",
           len(cilindro) > 50 and abs(dx - 15.0) < 3.0,
           "%d pontos, dx = %.1f" % (len(cilindro), dx))
    lamina = int((np.abs(osso[:, 0] - cx - 23.0) < 1.6).sum())
    checar("a lamina de um voxel sobrevive a reducao", lamina > 20,
           "%d ponto(s)" % lamina)
    grao = int((osso[:, 0] - cx < 0).sum())
    checar("o grao de um voxel nao entra na cena", grao == 0,
           "%d ponto(s) a esquerda do eixo" % grao)
    vazio = R.cena_3d(np.full((10, 20, 20), -1000, dtype=np.int16), esp)
    checar("serie sem nada acima do limiar diz isso, sem levantar",
           not vazio["itens"] and bool(vazio["erro"]), str(vazio.get("erro")))


def _nuvem_referencia(mask, grade, max_pontos):
    import numpy as np
    import radai_geom
    import radai_viewer3d as V
    m = np.asarray(mask, dtype=bool)
    idx = np.argwhere(V._superficie(m))
    escolha = V._amostrar(len(idx), max_pontos)
    if escolha is not None:
        idx = idx[escolha]
    dd = radai_geom.distancia_com_sinal(m, grade)
    gz, gy, gx = np.gradient(dd, *grade.spacing)
    n = np.stack([gx[tuple(idx.T)], gy[tuple(idx.T)], gz[tuple(idx.T)]], axis=1)
    nr = np.linalg.norm(n, axis=1)
    nr[nr < 1e-9] = 1.0
    pts = idx.astype(float) * np.asarray(grade.spacing)
    return pts, n / nr[:, None]


def teste_a_nuvem_no_recorte_e_a_mesma():
    secao("a nuvem no recorte e a mesma do volume inteiro")
    import numpy as np
    import radai_geom
    import radai_viewer3d as V
    g = radai_geom.Grade((2.5, 1.0, 1.0))
    zz, yy, xx = np.ogrid[:40, :120, :120]
    casos = {
        "no meio": ((zz - 22) ** 2 * 6.25 + (yy - 70) ** 2 + (xx - 50) ** 2) < 150,
        "na borda": ((zz - 3) ** 2 * 6.25 + (yy - 5) ** 2 + (xx - 60) ** 2) < 200,
    }
    for nome, m in casos.items():
        d = V.nuvem_de_mascara(m, g, max_pontos=1500)
        pts_ref, nrm_ref = _nuvem_referencia(m, g, 1500)
        centro_ref = pts_ref.mean(axis=0)
        esperado = np.round((pts_ref - centro_ref)[:, ::-1], 2)
        checar("[%s] os mesmos pontos, na mesma ordem" % nome,
               np.array_equal(np.asarray(d["pontos"]), esperado),
               "%d contra %d" % (len(d["pontos"]), len(esperado)))
        dif = float(np.abs(np.asarray(d["normais"]) - nrm_ref).max()) \
            if len(d["normais"]) == len(nrm_ref) else 9.0
        checar("[%s] a mesma normal" % nome, dif < 2e-3, "%.4f" % dif)
        checar("[%s] e o centro no lugar certo do volume" % nome,
               np.allclose(d["centro_mm"], centro_ref, atol=2e-3),
               "%s contra %s" % (d["centro_mm"], np.round(centro_ref, 3)))
        loc = V.nuvem_de_mascara(m, g, max_pontos=1500, normal="local")
        nl = np.asarray(loc["normais"], dtype=float)
        checar("[%s] a normal pela vizinhanca: mesmos pontos, unitaria" % nome,
               loc["pontos"] == d["pontos"]
               and np.allclose(np.linalg.norm(nl, axis=1), 1.0, atol=3e-3))
        if nome == "no meio":
            p = np.asarray(loc["pontos"], dtype=float)
            radial = p / np.maximum(np.linalg.norm(p, axis=1, keepdims=True),
                                    1e-9)
            cos_l = float(np.mean(np.sum(nl * radial, axis=1)))
            cos_s = float(np.mean(np.sum(nrm_ref * radial, axis=1)))
            checar("[no meio] a normal pela vizinhanca segue o raio",
                   cos_l > 0.97, "cosseno medio %.3f (a da distancia: %.3f)"
                   % (cos_l, cos_s))


def _colunas_listra(item, esp_x, esp_z):
    import numpy as np
    p = np.asarray(item["pontos"], dtype=float)
    x = np.round(p[:, 0] / esp_x).astype(int)
    z = np.round(p[:, 2] / esp_z).astype(int)
    lateral = (z > z.min()) & (z < z.max())
    x, z = x[lateral], z[lateral]
    xs = np.arange(np.percentile(x, 15), np.percentile(x, 85) + 1).astype(int)
    cortes = {}
    for a, b in zip(x, z):
        cortes.setdefault(int(a), set()).add(int(b))
    n = len(set(z.tolist()))
    vazias = [c for c in xs if len(cortes.get(int(c), ())) < 0.25 * n]
    return len(vazias) / float(max(1, len(xs)))


def teste_a_pele_nao_sai_em_listras():
    secao("a pele nao sai em listras")
    import numpy as np
    sys.path.insert(0, AQUI)
    import make_test_series as M
    import radai_recon3d as R
    import radai_viewer3d as V
    n = 60
    vol = np.stack([M.fatia(z, n) for z in range(n)]).astype(np.int16)
    cena = R.cena_3d(vol, (M.THICK_MM, M.PIXEL_MM, M.PIXEL_MM))
    pele = [it for it in cena["itens"] if it.get("camada") == "pele"]
    checar("o fantoma tem pele, e ela e amostrada (a cobaia vale)",
           len(pele) == 1 and pele[0]["n_total"] > len(pele[0]["pontos"]),
           str([(it.get("camada"), it.get("n_total")) for it in cena["itens"]]))
    if len(pele) != 1:
        return
    fr = _colunas_listra(pele[0], M.PIXEL_MM, M.THICK_MM)
    checar("menos de 20% das colunas da face lateral viram listra (era 78,7%)",
           fr < 0.20, "%.3f" % fr)
    a = V._amostrar(33194, 4000)
    b = V._amostrar(33194, 4000)
    checar("a amostragem e deterministica e crescente, com teto",
           np.array_equal(a, b) and len(a) <= 4000
           and bool(np.all(np.diff(a) > 0)) and a[-1] < 33194,
           "%d pontos" % len(a))
    checar("abaixo do teto, desenha todos", V._amostrar(100, 4000) is None)


def teste_varias_estruturas_num_referencial_so():
    secao("varias estruturas: um referencial so")
    import numpy as np
    import radai_geom
    import radai_viewer3d as V
    g = radai_geom.Grade((2.0, 1.0, 1.0))
    zz, yy, xx = np.ogrid[:30, :100, :100]
    a = ((zz - 15) ** 2 * 4 + (yy - 50) ** 2 + (xx - 25) ** 2) < 100
    b = ((zz - 15) ** 2 * 4 + (yy - 50) ** 2 + (xx - 75) ** 2) < 100

    def distancia(itens):
        p = [np.asarray(it["pontos"], dtype=float).mean(axis=0) for it in itens]
        return float(np.linalg.norm(p[0] - p[1]))

    itens = [V.nuvem_de_mascara(a, g), V.nuvem_de_mascara(b, g)]
    antes = distancia(itens)
    V.recentrar(itens)
    depois = distancia(itens)
    checar("sem recentrar, as duas caem no mesmo lugar (o defeito)",
           antes < 1.0, "%.1f mm" % antes)
    checar("recentradas, a distancia entre elas e a do volume (50 mm)",
           abs(depois - 50.0) < 1.0, "%.1f mm" % depois)

    import radai_rt

    class _Sessao(object):
        grade = g

        def mascara_de(self, nome, sufixo=""):
            return {"Kidney_L_ai": a, "Kidney_R_ai": b}.get(nome)

        def fechar(self):
            pass
    original = radai_rt.abrir
    try:
        radai_rt.abrir = lambda *x, **k: _Sessao()
        d = V.nuvem_da_serie("fantoma", "RS_fantoma.dcm",
                             ["Kidney_L_ai", "Kidney_R_ai"])
    finally:
        radai_rt.abrir = original
    checar("a cena do Ver segmentacao traz as duas",
           len(d.get("itens") or []) == 2, str(d.get("erro")))
    if len(d.get("itens") or []) == 2:
        checar("e as poe a 50 mm uma da outra, como no volume",
               abs(distancia(d["itens"]) - 50.0) < 1.0,
               "%.1f mm" % distancia(d["itens"]))


def teste_a_serie_e_lida_uma_vez():
    secao("a serie e lida uma vez")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import numpy as np
    import SimpleITK as sitk
    import engine
    import radai_thumbnail
    import radai_recon3d_screen as S
    leituras = []

    def _ler(pasta, uid=None):
        leituras.append((pasta, uid))
        img = sitk.GetImageFromArray(np.full((12, 16, 16), 40, dtype=np.int16))
        img.SetSpacing((1.0, 1.0, 2.0))
        return img
    original = engine.load_sitk
    app = FastAPI()
    S.montar(app)
    cli = TestClient(app)
    b = radai_thumbnail.bilhete("fantoma_r3", "1.2.3.4")
    try:
        engine.load_sitk = _ler
        S._VOL.update({"chave": None, "v": None})
        r1 = cli.get("/api/recon3d/projecao", params={"b": b, "eixo": 0,
                                                      "laje": 0, "pos": 0.5})
        r2 = cli.get("/api/recon3d/projecao", params={"b": b, "eixo": 1,
                                                      "laje": 10, "pos": 0.3})
        cli.get("/api/recon3d/estado", params={"b": b})
        n_mesma = len(leituras)
        b2 = radai_thumbnail.bilhete("fantoma_r3", "1.2.3.5")
        cli.get("/api/recon3d/projecao", params={"b": b2, "eixo": 0})
    finally:
        engine.load_sitk = original
    checar("as duas imagens saem", r1.status_code == 200
           and r2.status_code == 200, "%s %s" % (r1.status_code, r2.status_code))
    checar("tres pedidos da mesma serie, UMA leitura", n_mesma == 1,
           "%d leitura(s)" % n_mesma)
    checar("outra serie, outra leitura", len(leituras) == 2,
           "%d leitura(s)" % len(leituras))
    checar("e a anterior sai da memoria",
           S._VOL["chave"] == ("fantoma_r3", "1.2.3.5"), str(S._VOL["chave"]))
    rel = S._VOL.get("relogio")
    checar("a serie em memoria arma o relogio que a solta (daemon)",
           rel is not None and getattr(rel, "daemon", False), repr(rel))
    if rel is not None:
        rel.cancel()
        S._VOL["relogio"] = None


def teste_a_serie_sai_da_memoria_quando_ninguem_olha():
    secao("a serie sai da memoria quando ninguem olha")
    import time
    import numpy as np
    import radai_recon3d_screen as S
    agora = time.time()
    try:
        S._VOL.update({"chave": ("p", "u"), "v": np.zeros((2, 2, 2)),
                       "esp": (1.0, 1.0, 1.0), "sentido": None,
                       "visto": agora - 30.0, "relogio": None})
        falta = S._soltar_se_parada(agora=agora, rearmar=False)
        checar("olhada ha 30 s: fica, e diz quanto falta",
               S._VOL["v"] is not None
               and abs(falta - (S.SOLTAR_APOS_S - 30.0)) < 1e-6, repr(falta))
        S._VOL["visto"] = agora - S.SOLTAR_APOS_S - 1.0
        falta = S._soltar_se_parada(agora=agora, rearmar=False)
        checar("parada ha mais que SOLTAR_APOS_S: sai da memoria",
               falta is None and S._VOL["v"] is None and S._VOL["chave"] is None,
               "%r %r" % (falta, S._VOL["chave"]))
        checar("e sem serie, nao ha o que vigiar",
               S._soltar_se_parada(agora=agora, rearmar=False) is None)
        checar("o prazo e de minutos, e nao de segundos",
               300 <= S.SOLTAR_APOS_S <= 1800, str(S.SOLTAR_APOS_S))
    finally:
        S._VOL.update({"chave": None, "v": None, "esp": None, "sentido": None,
                       "relogio": None})


def teste_o_erro_do_3d_vai_para_o_log_e_nao_para_a_tela():
    secao("o erro do 3D vai para o log, e nao para a tela")
    import json
    import numpy as np
    import SimpleITK as sitk
    import engine
    import radai_geom
    import radai_recon3d as R
    import radai_thumbnail
    import radai_recon3d_screen as S
    linhas = []
    b = radai_thumbnail.bilhete("fantoma_erro", "9.9.9")
    orig = (R.nuvem_da_camada, radai_thumbnail._log_da_estacao,
            radai_thumbnail.serie_do_bilhete, engine.load_sitk,
            radai_geom.Grade.__dict__["de_sitk"])
    radai_thumbnail._JA_REGISTRADAS.clear()
    try:
        radai_thumbnail._log_da_estacao = lambda: linhas.append
        radai_thumbnail.serie_do_bilhete = lambda _b: {"modalidade": "CT"}

        def _ler(pasta, uid=None):
            img = sitk.GetImageFromArray(np.full((6, 8, 8), 40, dtype=np.int16))
            return img
        engine.load_sitk = _ler

        def _sem_sentido(img):
            raise ValueError("C:\\RADIOTERAPIA_AI\\tmp\\%s\\CT"
                             % PACIENTE_COM_ESPACO)
        radai_geom.Grade.de_sitk = staticmethod(_sem_sentido)

        def _explode(*a, **k):
            raise IOError(u"Sem DICOM em \\\\servidor\\imagens\\Patients"
                          u"\\%s\\CT" % PACIENTE_COM_ESPACO)
        R.nuvem_da_camada = _explode
        S._VOL.update({"chave": None, "v": None, "relogio": None})
        d = S.cena_da_serie(b)
    finally:
        (R.nuvem_da_camada, radai_thumbnail._log_da_estacao,
         radai_thumbnail.serie_do_bilhete, engine.load_sitk) = orig[:4]
        setattr(radai_geom.Grade, "de_sitk", orig[4])
        rel = S._VOL.get("relogio")
        if rel is not None:
            rel.cancel()
        S._VOL.update({"chave": None, "v": None, "esp": None, "sentido": None,
                       "relogio": None})
    checar("a tela recebe a frase FIXA, sem o tipo colado nela",
           d.get("erro") == u"não consegui montar o 3D"
           and d.get("tipo") == "OSError", str(d))
    checar("e nenhum caminho", not _tem_paciente(json.dumps(d)),
           json.dumps(d)[:160])
    texto = u"\n".join(linhas)
    checar("a causa da cena vai para o log da estacao",
           u"reconstrucoes 3D, cena: falhou com OSError" in texto, texto[:300])
    checar("a orientacao que falha tambem vai para o log",
           u"reconstrucoes 3D, orientacao: falhou com ValueError" in texto,
           texto[:300])
    checar("e o log nao leva o caminho do paciente, nem o pedaco depois do "
           "espaco", not _tem_paciente(texto), texto[:300])


def teste_a_serie_que_nao_abre_nao_leva_o_caminho_a_tela():
    secao("a serie que nao abre nao leva o caminho a tela")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import json
    import engine
    import radai_recon3d as R
    import radai_thumbnail
    import radai_recon3d_screen as S
    caminho = u"C:\\RADIOTERAPIA_AI\\tmp\\%s\\CT" % PACIENTE_COM_ESPACO
    b = radai_thumbnail.bilhete(caminho, "9.9.8")
    linhas = []
    orig = (engine.load_sitk, R.estado_da_serie, radai_thumbnail._log_da_estacao)
    radai_thumbnail._JA_REGISTRADAS.clear()
    try:
        def _recusa(pasta, uid=None):
            raise ValueError("Sem DICOM em %s" % pasta)
        engine.load_sitk = _recusa
        R.estado_da_serie = lambda pasta: {"segmentada": False}
        radai_thumbnail._log_da_estacao = lambda: linhas.append
        S._VOL.update({"chave": None, "v": None, "relogio": None})
        app = FastAPI()
        S.montar(app)
        d = TestClient(app).get("/api/recon3d/estado", params={"b": b}).json()
    finally:
        engine.load_sitk, R.estado_da_serie, radai_thumbnail._log_da_estacao = orig
        S._VOL.update({"chave": None, "v": None, "esp": None, "sentido": None,
                       "relogio": None})
    crua = json.dumps(d, ensure_ascii=False)
    checar("a tela sabe que a serie nao abre", bool(d.get("nao_le")), crua[:160])
    checar("com uma frase FIXA, e o tipo num campo a parte",
           d.get("nao_le") == u"a causa foi escrita no log da estação"
           and d.get("tipo") == "ValueError", crua[:200])
    checar("e nenhum caminho na resposta",
           not _tem_paciente(crua) and "TC_TESTE" not in crua, crua[:200])
    texto = u"\n".join(linhas)
    checar("a causa vai para o log da estacao",
           u"reconstrucoes 3D, estado: falhou com ValueError" in texto,
           texto[:300])
    checar("e o log nao leva o caminho do paciente, nem o pedaco depois do "
           "espaco", not _tem_paciente(texto), texto[:300])
    _r3estado_no_node(S.JS_SERIE, d)


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


def _r3estado_no_node(js, resposta):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        checar("node disponivel para executar r3Estado", False,
               "PULADO -- sem node")
        return
    fns = [_funcao_js(js, n) for n in ("r3Esc", "r3Frase", "r3Estado")]
    if not all(fns):
        checar("r3Estado e r3Esc existem na pagina", False, str([bool(f) for f in fns]))
        return
    prog = u"\n".join([
        u"var ALVO = {className: '', innerHTML: ''}, PELO_UI = [];",
        u"var window = {uiHTML: function(e, h){ PELO_UI.push(h); e.innerHTML = h; }};",
        u"function r3El(i){ return i === 'r3_estado' ? ALVO : null; }",
        u"var R3 = {fer: 'geral'};",
    ] + fns + [
        u"r3Estado(%s);" % json.dumps(resposta, ensure_ascii=False),
        u"console.log('JSON:' + JSON.stringify({pelo_ui: PELO_UI, html: ALVO.innerHTML}));",
    ])
    d = tempfile.mkdtemp(prefix="radai_ac_recon3d_js_")
    alvo = os.path.join(d, "r3.js")
    try:
        io.open(alvo, "w", encoding="utf-8").write(prog)
        r = subprocess.run([node, alvo], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    saida = None
    for ln in reversed((r.stdout or "").splitlines()):
        if ln.startswith("JSON:"):
            saida = json.loads(ln[5:])
            break
    if saida is None:
        checar("r3Estado executa no node", False, ((r.stderr or "") + (r.stdout or ""))[-300:])
        return
    h = saida.get("html") or u""
    checar("a tela escreve a serie que nao abre PELO `uiHTML` (a frase se traduz)",
           len(saida.get("pelo_ui") or []) == 1, str(saida)[:200])
    checar("  a frase num no marcado, e o tipo num <code> a parte",
           u"<span data-radai-frase>a causa foi escrita no log da estação</span>" in h
           and u"<code>ValueError</code>" in h, h[:240])


def teste_a_rota_do_3d():
    secao("a rota do 3D")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import json
    from datetime import datetime
    sys.path.insert(0, AQUI)
    import make_test_series
    import radai_thumbnail
    import radai_recon3d_screen as S
    base = tempfile.mkdtemp(prefix="r3d_")
    pasta = os.path.join(base, "PAC_R3", "CT")
    uid = make_test_series.escreve_serie(pasta, "PAC_R3", datetime.now(), 20)
    b = radai_thumbnail.bilhete(pasta, uid)
    app = FastAPI()
    S.montar(app)
    cli = TestClient(app)
    d = cli.get("/api/recon3d/nuvem", params={"b": b}).json()
    camadas = sorted(it.get("camada") for it in d.get("itens") or [])
    checar("a TC sintetica da osso e pele", camadas == ["osso", "pele"],
           "%s %s" % (camadas, d.get("erro")))
    checar("e diz quanto levou para montar",
           isinstance(d.get("segundos"), (int, float)), str(d.get("segundos")))
    crua = json.dumps(d)
    checar("a resposta nao leva o caminho", "PAC_R3" not in crua)
    morto = cli.get("/api/recon3d/nuvem", params={"b": "f" * 32}).json()
    checar("bilhete morto manda recarregar a lista",
           not morto.get("itens") and "recarregue" in (morto.get("erro") or ""),
           str(morto))
    original = radai_thumbnail.serie_do_bilhete
    try:
        radai_thumbnail.serie_do_bilhete = lambda _b: {"modalidade": "MR"}
        rm = cli.get("/api/recon3d/nuvem", params={"b": b}).json()
    finally:
        radai_thumbnail.serie_do_bilhete = original
    checar("RM nao ganha cena de osso por limiar de Hounsfield",
           not rm.get("itens") and "TC" in (rm.get("erro") or ""), str(rm))
    checar("e a frase e fixa, com a modalidade num campo a parte",
           rm.get("erro") == u"o 3D por densidade existe só para TC, e esta "
                             u"série não é TC" and rm.get("modalidade") == "MR",
           str(rm))


_EXPORTA = ("download", "attachment", "content-disposition", "toblob",
            "todataurl", "createobjecturl", "new blob", "to_obj", "to_stl",
            ".mp4", ".webm", "salvar", "showsavefilepicker", "mssaveblob")


def _o_que_exporta(p):
    baixo = (p or u"").lower()
    return [x for x in _EXPORTA if x in baixo]


def _sem_comentario_renderizado(p):
    p = re.sub(r"<!--.*?-->", " ", p, flags=re.S)
    p = re.sub(r"/\*.*?\*/", " ", p, flags=re.S)
    p = re.sub(r"(?m)(^|[\s;{}(),])//[^\n]*", r"\1", p)
    return p


def _paginas_sem_a_gravacao():
    import radai_recon3d_screen as S
    import radai_recon3d_vascular as V
    saida = {}
    for nome, p in (("geral", S.pagina("geral")),
                    ("toracica", S.pagina("toracica")),
                    ("vascular", V.pagina())):
        p = _sem_comentario_renderizado(
            p.replace(S.JS_GRAVAR, u" ").replace(S.AVISO_DA_GRAVACAO, u" "))
        inteira = p.lower()
        p = re.sub(r'(?s)<span class="ui-balao">.*?</span></span>',
                   lambda m: re.sub(r">[^<]*<", u"><", m.group(0)), p)
        # GUARDA: o atributo de baixar e o Blob se procuram ANTES de tirar o texto dos baloes.
        for x in ("download=", "createobjecturl"):
            if x in inteira and x not in p.lower():
                p += u" " + x
        saida[nome] = p
    return saida


def teste_a_tela_renderizada_nao_exporta():
    secao("a pagina renderizada nao exporta")
    import radai_recon3d_screen as S
    paginas = _paginas_sem_a_gravacao()
    for nome in ("geral", "toracica", "vascular"):
        achados = _o_que_exporta(paginas.get(nome, u""))
        checar("[%s] fora da gravacao do visor, a pagina nao tem caminho de "
               "exportar" % nome, nome in paginas and not achados,
               str(achados))
    import radai_recon3d_vascular as V
    js0 = V.JS
    V.JS = js0 + (u"\nfunction vxSalvar(){ var a = document.createElement('a');"
                  u" a.download = 'x.png'; a.click() }\n")
    try:
        isca_v = _o_que_exporta(_paginas_sem_a_gravacao()["vascular"])
    finally:
        V.JS = js0
    checar("(isca) um download no JS da Vascular seria acusado",
           "download" in isca_v, str(isca_v))
    vp0 = V.pagina
    V.pagina = lambda: vp0().replace(
        u'<span class="ui-balao">',
        u'<span class="ui-balao"><a href="#" download="v.png">salvar a imagem</a>', 1)
    try:
        isca_b = _o_que_exporta(_paginas_sem_a_gravacao()["vascular"])
    finally:
        V.pagina = vp0
    checar("(isca) um <a download> dentro de um balao seria acusado",
           "download" in isca_b, str(isca_b))
    for nome, pg in (("geral", S.pagina("geral")), ("toracica", S.pagina("toracica")),
                     ("vascular", V.pagina())):
        checar("[%s] a pagina nao carrega <script src> (todo o JS esta na pagina medida)"
               % nome, not re.search(r"<script[^>]*\ssrc=", pg, flags=re.I))
    p = paginas["geral"]
    for isca in (u'<a href="#" download="malha.stl">STL</a>',
                 u"<script>URL.createObjectURL(new Blob([b]))</script>",
                 u"<script>cvGL.toDataURL('image/png')</script>",
                 u'<button onclick="r3Salvar()">salvar</button>'):
        checar(u"(isca) `%s` seria acusado" % isca[:34],
               bool(_o_que_exporta(p + isca)))
    canvas = re.findall(r"<canvas[^>]*>", p, flags=re.I)
    ids = sorted(re.search(r'id="([^"]+)"', c).group(1) for c in canvas
                 if re.search(r'id="([^"]+)"', c))
    checar("tres canvas, todos do quadro 3D (malha, bussola, nuvem)",
           ids == ["cv3D", "cv3Db", "cvGL"], str(ids))
    import radai_recon3d_screen as S2
    lig = _funcao_js(S2.JS_MALHA, "r3gLigar")
    checar("o menu do botao direito nao abre sobre o 3D",
           "'contextmenu'" in lig and "preventDefault" in lig, lig[:80])


def teste_o_quadro_3d_esta_na_tela():
    secao("o quadro 3D esta na tela")
    import radai_recon3d_screen as S
    p = S.pagina()
    for marca in ('id="cvGL"', 'id="cv3Db"', 'id="cv3D"', 'id="dica3d"',
                  'id="r3_estr"', 'id="r3_rs"', 'id="r3_camadas3d"',
                  'id="r3_aviso3d"', 'id="r3_motivo3d"',
                  "r3Vista('ant')", "r3Vista('esq')", "r3Vista('sup')",
                  "r3Vista('post')", "r3Vista('dir')", "r3Vista('inf')",
                  "r3Vista('inicial')"):
        checar("a tela tem `%s`" % marca, marca in p)
    checar("o renderizador do recuo e o de radai_viewer, costurado",
           "function n3Mostrar(" in p and "function n3Desenhar(" in p)
    checar("e so ele: sem o palco de tres planos nem o visor de um eixo",
           "function RadaiPalco(" not in p and "function RadaiUmEixo(" not in p)
    checar("o renderizador da malha e o desta tela, sem biblioteca",
           "function r3gDesenhar(" in p and "function r3gLerStl(" in p
           and "<script src" not in p.lower())
    checar("a malha vem da rota da malha, por POST",
           "fetch('/api/recon3d/malha', {method: 'POST'" in p)
    checar("a lista vem da rota das estruturas, por POST",
           "fetch('/api/recon3d/estruturas', {method: 'POST'" in p)
    checar("o recuo pede a nuvem por POST, com as estruturas",
           "fetch('/api/recon3d/nuvem', {method: 'POST'" in p)
    checar("a frase da tela anuncia o 3D", "o 3D" in p)
    for fn in ("n3Dir", "n3MatrizInicial", "n3Girar", "n3Bussola"):
        checar("a malha usa `%s` do painel de sempre" % fn,
               (fn + "(") in S.JS_MALHA)
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        checar("node disponivel para parsear o JS da tela", False,
               "PULADO -- sem node")
        return
    js = "\n".join(re.findall(r"(?is)<script[^>]*>(.*?)</script>", p))
    d = tempfile.mkdtemp(prefix="r3d_")
    alvo = os.path.join(d, "t.js")
    io.open(alvo, "w", encoding="utf-8").write(js)
    r = subprocess.run([node, "--check", alvo], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    checar("o JS da tela parseia", r.returncode == 0, (r.stderr or "")[-200:])


def teste_as_telas_que_listam_conjuntos_reconhecem_os_plugins():
    secao("as telas que listam conjuntos reconhecem os plugins")
    import radai_recon3d as R
    d = tempfile.mkdtemp(prefix="r3d_conj_")
    try:
        for nome in (u"RS_RadAI_20260924_12345678.dcm",
                     u"RS_RadAI_ORB_20260924_12345678.dcm",
                     u"RS_RadAI_TX_20260924_12345678.dcm",
                     u"RS_RadAI_ZZZ_20260924_12345678.dcm"):
            io.open(os.path.join(d, nome), "wb").write(b"RT")
        e = R.estado_da_serie(d)
        por = dict((c["arquivo"], c) for c in e.get("conjuntos") or ())
        checar("o entregue e reconhecido pela data (marca positiva)",
               por.get(u"RS_RadAI_20260924_12345678.dcm", {}).get(
                   "conjunto") == "oar", str(por)[:200])
        checar("  o plugin da orbita e o plugin, e nao o entregue",
               por.get(u"RS_RadAI_ORB_20260924_12345678.dcm", {}).get(
                   "conjunto") == "orb", str(por)[:200])
        checar("  o `TX_` do modulo toracico NAO vira o entregue",
               por.get(u"RS_RadAI_TX_20260924_12345678.dcm", {}).get(
                   "conjunto") not in ("oar", None), str(por)[:200])
        checar("  e o infixo desconhecido aparece como desconhecido (e nao "
               "some, e nao e o entregue)",
               por.get(u"RS_RadAI_ZZZ_20260924_12345678.dcm", {}).get(
                   "conjunto") == "", str(por)[:200])
        checar("  e a serie conta como contornada",
               e.get("segmentada") is True and len(por) == 4, str(e)[:160])
        import radai_recon3d_screen as T
        import radai_sets
        for nome in (u"RS_RadAI_FAST_20260924_12345678.dcm",
                     u"RS_RadAI_FULL_20260924_12345678.dcm"):
            io.open(os.path.join(d, nome), "wb").write(b"RT")
        e = R.estado_da_serie(d)
        por = dict((c["arquivo"], c) for c in e.get("conjuntos") or ())
        checar("o OAR_Fast e o conjunto `fast` (do registro)",
               por.get(u"RS_RadAI_FAST_20260924_12345678.dcm", {}).get(
                   "conjunto") == "fast", str(por)[:200])
        ordem = [c["arquivo"] for c in T.arquivos_da_serie(d)]
        checar("  e a lista do 3D abre com OAR, OAR_Fast, FULL",
               ordem[:3] == [u"RS_RadAI_20260924_12345678.dcm",
                             u"RS_RadAI_FAST_20260924_12345678.dcm",
                             u"RS_RadAI_FULL_20260924_12345678.dcm"],
               str(ordem))
        orig = radai_sets.SAIDAS_DE_MODO
        try:
            radai_sets.SAIDAS_DE_MODO = ()
            e0 = R.estado_da_serie(d)
        finally:
            radai_sets.SAIDAS_DE_MODO = orig
        por0 = dict((c["arquivo"], c) for c in e0.get("conjuntos") or ())
        checar("  e sem a entrada do registro ele e desconhecido (a deteccao "
               "e uma so)",
               por0.get(u"RS_RadAI_FAST_20260924_12345678.dcm", {}).get(
                   "conjunto") == "", str(por0)[:200])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    import json
    import subprocess
    import shutil as _sh
    import radai_view as V
    pag = V._pagina()
    m = re.search(r"var VR_CONJ = (\[.*?\]);", pag, re.S)
    checar("a pagina serve a lista de conjuntos", bool(m))
    if not m:
        return
    lista = json.loads(m.group(1))
    checar("  e ela traz os plugins, marcados como plugin",
           any(c.get("plugin") and c["cod"] == "orb" for c in lista)
           and all(not c.get("plugin") for c in lista
                   if c["cod"] in ("oar", "full", "ts")),
           str([c["cod"] for c in lista]))
    node = _sh.which("node")
    if not node:
        checar("node disponivel para executar vrCodDe (PULADO -- sem node)",
               True)
        return
    fn = _funcao_js(pag, "vrCodDe")
    checar("vrCodDe existe na pagina", bool(fn))
    casos = [u"RS_RadAI_20260924_1.dcm", u"RS_RadAI_semdata_1.dcm",
             u"RS_RadAI_ORB_20260924_1.dcm", u"RS_RadAI_FULL_20260924_1.dcm",
             u"RS_RadAI_FAST_20260924_1.dcm",
             u"RS_RadAI_TX_20260924_1.dcm", u"RS_RadAI_ZZZ_20260924_1.dcm"]

    def _rodar(fonte_fn):
        prog = u"\n".join([u"var VR_CONJ = %s;" % json.dumps(lista),
                           fonte_fn,
                           u"console.log('JSON:' + JSON.stringify(%s.map(vrCodDe)));"
                           % json.dumps(casos)])
        tmp = tempfile.mkdtemp(prefix="r3d_vr_")
        try:
            alvo = os.path.join(tmp, "vr.js")
            io.open(alvo, "w", encoding="utf-8").write(prog)
            r = subprocess.run([node, alvo], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        for ln in reversed((r.stdout or u"").splitlines()):
            if ln.startswith(u"JSON:"):
                return json.loads(ln[5:])
        return None
    saida = _rodar(fn)
    checar("vrCodDe executa no node", saida is not None)
    if saida is None:
        return
    esperado = ["oar", "oar", "orb", "full", "fast", "", ""]
    checar("  entregue pela data (e `semdata`), plugin e OAR_Fast pelo "
           "infixo, e o desconhecido NAO e o entregue", saida == esperado,
           "%s | esperado %s" % (saida, esperado))
    velho = re.sub(r"if\(/\^\[0-9\]\{8\}/.*?return '';", u"return 'oar';",
                   fn, flags=re.S)
    s2 = _rodar(velho)
    checar("  (isca) com o recuo de antes, o desconhecido vira o entregue -- "
           "a checagem discrimina", s2 is not None and s2[-1] == "oar",
           str(s2))



def _circulo(cx, cy, r, z, n=48):
    import numpy as np
    a = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(a), cy + r * np.sin(a),
                     np.full(n, float(z))], axis=1)


def _esfera(cx, cy, cz, R, dz=3.0):
    import numpy as np
    fora = []
    for z in np.arange(cz - R, cz + R + 1e-6, dz):
        r2 = R * R - (z - cz) ** 2
        if r2 > 4.0:
            fora.append(_circulo(cx, cy, np.sqrt(r2), z))
    return fora


def _malha_conferida(verts, faces):
    import radai_bolus
    return radai_bolus.conferir_malha(verts, faces)


def teste_a_malha_da_estrutura_fecha():
    secao("a malha de cada estrutura fecha, para fora e no lugar")
    import math
    import numpy as np
    import radai_recon3d as R
    esf = _esfera(10.0, -20.0, 30.0, 24.0)
    v, f, info = R.malha_da_estrutura(esf)
    c = _malha_conferida(v, f)
    alvo = 4.0 / 3.0 * math.pi * 24.0 ** 3
    checar("a esfera fecha (toda aresta com par, nenhuma repetida)",
           c["fechada"], str(c))
    checar("  com a normal para fora (volume assinado positivo)",
           c["volume_mm3"] > 0, "%.0f" % c["volume_mm3"])
    checar("  e o volume da esfera, a 6%",
           abs(c["volume_mm3"] - alvo) / alvo < 0.06,
           "%.0f contra %.0f mm3" % (c["volume_mm3"], alvo))
    centro = (v.min(axis=0) + v.max(axis=0)) / 2.0
    checar("  no lugar dos contornos, em mm LPS (centro a 1,5 mm)",
           float(np.abs(centro - [10.0, -20.0, 30.0]).max()) < 1.5,
           str(np.round(centro, 2)))
    raio = np.linalg.norm(v - [10.0, -20.0, 30.0], axis=1)
    checar("  e na superficie da esfera (raio mediano a 1 mm)",
           abs(float(np.median(raio)) - 24.0) < 1.0,
           "%.2f mm" % float(np.median(raio)))
    checar("  com a grade escolhida e os triangulos contados no info",
           info.get("triangulos") == len(f) and info.get("passo_mm") > 0,
           str(info))

    tubo = []
    for z in np.arange(0.0, 36.1, 3.0):
        tubo += [_circulo(0.0, 0.0, 40.0, z, 96), _circulo(0.0, 0.0, 30.0, z, 96)]
    v2, f2, _i2 = R.malha_da_estrutura(tubo)
    c2 = _malha_conferida(v2, f2)
    anel = math.pi * (40.0 ** 2 - 30.0 ** 2) * 39.0
    checar("o tubo fecha", c2["fechada"], str(c2))
    checar("  e o furo continua furo (volume do anel, e nao do disco)",
           abs(c2["volume_mm3"] - anel) / anel < 0.15,
           "%.0f contra %.0f mm3 (disco: %.0f)" % (
               c2["volume_mm3"], anel, math.pi * 40.0 ** 2 * 39.0))
    perto = np.hypot(v2[:, 0], v2[:, 1])
    meio = (v2[:, 2] > 8) & (v2[:, 2] < 28)
    checar("  sem vertice no meio do furo",
           float(perto[meio].min()) > 26.0, "%.1f mm" % float(perto[meio].min()))

    ilhas = []
    for z in np.arange(0.0, 30.1, 3.0):
        ilhas += [_circulo(-50.0, 0.0, 12.0, z), _circulo(50.0, 0.0, 12.0, z)]
    v3, f3, _i3 = R.malha_da_estrutura(ilhas)
    c3 = _malha_conferida(v3, f3)
    checar("duas ilhas: fecha, e nada entre elas",
           c3["fechada"] and not bool(((np.abs(v3[:, 0]) < 30)).any()),
           "%s, %d vertice(s) entre" % (c3["fechada"],
                                        int((np.abs(v3[:, 0]) < 30).sum())))


def teste_a_grade_cabe_no_teto_e_a_estimativa_vale():
    secao("a grade cabe no teto, e a estimativa vale")
    import numpy as np
    import radai_bolus
    import radai_recon3d as R
    esf = _esfera(0.0, 0.0, 0.0, 60.0)
    v, f, info = R.malha_da_estrutura(esf, teto_triangulos=20000)
    checar("com teto de 20 mil, a malha fica perto dele",
           len(f) <= 20000 * 1.15 and len(f) > 20000 * 0.3,
           "%d triangulos, passo %.2f" % (len(f), info["passo_mm"]))
    F, _o, p, _i = R.campo_da_estrutura(esf, passo_fixo=3.0)
    est = R._triangulos_estimados(F)
    real = len(radai_bolus.superficie(F)[1])
    checar("a estimativa pelo campo erra menos de 25%",
           abs(est - real) / float(real) < 0.25, "%d contra %d" % (est, real))
    area = R._area_lateral(R._niveis(esf)[0], 3.0)
    prev = R.K_TRIANGULOS_POR_AREA * area / (3.0 ** 2)
    checar("a previsao pela area dos contornos nao fica ABAIXO da real "
           "(errar para baixo montaria duas vezes)",
           prev >= real * 0.95, "%.0f contra %d" % (prev, real))


def teste_a_pele_sai_so_pela_face_de_fora():
    secao("a pele sai so pela face de fora, em qualquer grade")
    import math
    import numpy as np
    import radai_recon3d as R
    casca = []
    for z in np.arange(0.0, 60.1, 5.0):
        casca += [_circulo(0.0, 0.0, 100.0, z, 128),
                  _circulo(0.0, 0.0, 95.0, z, 128)]
    solido = math.pi * 100.0 ** 2 * 65.0

    def vol(fe, passo):
        F, origem, p, _i = R.campo_da_estrutura(casca, face_externa=fe,
                                                 passo_fixo=passo)
        import radai_bolus
        vv, ff = radai_bolus.superficie(F)
        return radai_bolus.volume_assinado(vv * p, ff)
    for passo in (2.0, 12.0):
        v = vol(True, passo)
        checar("grade de %.0f mm: a face de fora envolve o corpo inteiro" % passo,
               abs(v - solido) / solido < 0.12,
               "%.0f contra %.0f cm3" % (v / 1000, solido / 1000))
    checar("sem `face_externa`, o anel continua anel (grade de 2 mm)",
           vol(False, 2.0) < solido * 0.2)
    checar("a pele e casca pelo nome, sem o sufixo",
           R.e_casca(u"Skin_ai") and not R.e_casca(u"Lung_L_ai"))
    original = R.so_os_de_fora
    try:
        R.so_os_de_fora = lambda niveis: niveis
        v_isca = vol(True, 12.0)
    finally:
        R.so_os_de_fora = original
    checar("(isca) preenchendo so a mascara, a grade de 12 mm parte a pele",
           v_isca < solido * 0.6,
           "%.0f contra %.0f cm3" % (v_isca / 1000, solido / 1000))


def teste_o_stl_e_valido_e_de_visualizacao():
    secao("o STL e valido, e diz que e de visualizacao")
    import struct
    import numpy as np
    import radai_bolus
    import radai_recon3d as R
    v, f, _i = R.malha_da_estrutura(_esfera(0.0, 0.0, 0.0, 20.0))
    dados = R.stl_da_malha(v, f)
    T = struct.unpack("<I", dados[80:84])[0]
    checar("80 + 4 + 50 bytes por triangulo", len(dados) == 84 + 50 * T
           and T == len(f), "%d bytes, %d triangulos" % (len(dados), T))
    cab = dados[:80]
    checar("o cabecalho nao comeca com «solid» (leitor de STL texto)",
           not cab.lstrip().lower().startswith(b"solid"))
    checar("e diz que e de visualizacao e que o contorno nao foi aprovado",
           b"VIEW ONLY" in cab and b"UNAPPROVED" in cab, repr(cab[:60]))
    _c, tri, nrm = radai_bolus.ler_stl(dados)
    checar("os triangulos do STL sao os da malha (float32)",
           np.allclose(tri, v[f], atol=1e-3))
    calc = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    calc /= np.maximum(np.linalg.norm(calc, axis=1, keepdims=True), 1e-12)
    checar("e a normal de cada um e a da ordem dos vertices (para fora)",
           float(np.mean(np.sum(calc * nrm, axis=1))) > 0.99)
    try:
        radai_bolus.stl_binario(v, f, cabecalho=b"solid bla")
        recusou = False
    except ValueError:
        recusou = True
    checar("(isca) cabecalho que comeca com «solid» e recusado", recusou)


def _rodar_js(prog, prefixo="r3d_js_"):
    import json
    import shutil as _sh
    import subprocess
    node = _sh.which("node")
    if not node:
        return None, "sem node"
    d = tempfile.mkdtemp(prefix=prefixo)
    try:
        alvo = os.path.join(d, "t.js")
        io.open(alvo, "w", encoding="utf-8").write(prog)
        r = subprocess.run([node, alvo], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for ln in reversed((r.stdout or u"").splitlines()):
        if ln.startswith(u"JSON:"):
            return json.loads(ln[5:]), ""
    return None, ((r.stderr or u"") + (r.stdout or u""))[-400:]


def teste_a_tela_le_o_stl():
    secao("a tela le o STL (r3gLerStl, no node)")
    import base64
    import numpy as np
    import radai_recon3d as R
    import radai_recon3d_screen as S
    v, f, _i = R.malha_da_estrutura(_esfera(5.0, 6.0, 7.0, 18.0))
    dados = R.stl_da_malha(v, f)
    fn = _funcao_js(S.JS_MALHA, "r3gLerStl")
    checar("r3gLerStl existe", bool(fn))
    b64 = base64.b64encode(dados).decode("ascii")
    prog = u"\n".join([
        fn,
        u"var bin = Buffer.from('%s', 'base64');" % b64,
        u"var ab = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.length);",
        u"var m = r3gLerStl(ab);",
        u"var fora = 0, max = 0;",
        u"for(var k = 0; k < 3*m.T; k++) if(m.idx[k] > max) max = m.idx[k];",
        u"for(var j = 0; j < m.nv; j++){",
        u" var ex = m.pos[3*j] - 5, ey = m.pos[3*j+1] - 6, ez = m.pos[3*j+2] - 7;",
        u" var dd = Math.sqrt(ex*ex + ey*ey + ez*ez);",
        u" if((ex*m.nrm[3*j] + ey*m.nrm[3*j+1] + ez*m.nrm[3*j+2]) / dd > 0.8) fora++;",
        u"}",
        u"var curto = '';",
        u"try{ r3gLerStl(ab.slice(0, ab.byteLength - 7)) }catch(e){ curto = String(e.message) }",
        u"console.log('JSON:' + JSON.stringify({nv: m.nv, T: m.T, fora: fora,",
        u" max: max, centro: m.centro, curto: curto}));",
    ])
    d, erro = _rodar_js(prog)
    if d is None:
        checar("r3gLerStl executa no node", False, erro)
        return
    checar("os vertices do STL viram os da malha (um por vertice)",
           d["nv"] == len(v) and d["T"] == len(f),
           "%s vertices para %d, %s triangulos" % (d["nv"], len(v), d["T"]))
    checar("  e a normal suave de cada um aponta para fora (> 99%)",
           d["fora"] >= 0.99 * d["nv"], "%s de %s" % (d["fora"], d["nv"]))
    checar("  o indice nunca passa do numero de vertices", d["max"] < d["nv"])
    checar("  e o centro da caixa e o da esfera",
           np.allclose(d["centro"], [5.0, 6.0, 7.0], atol=1.5), str(d["centro"]))
    checar("STL de tamanho errado e recusado, com frase",
           "tamanho" in (d.get("curto") or ""), str(d.get("curto")))


def _rtstruct_sintetico(caminho, estruturas):
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    meta = Dataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.3"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = generate_uid()
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTSTRUCT"
    ds.StructureSetLabel = "RadAI_OAR"
    ss, rc = [], []
    for i, est in enumerate(estruturas, 1):
        nome, cor, conts = est[:3]
        s = Dataset()
        s.ROINumber = i
        s.ROIName = nome
        if len(est) > 3 and est[3]:
            s.ROIDescription = est[3]
        ss.append(s)
        r = Dataset()
        r.ReferencedROINumber = i
        r.ROIDisplayColor = [int(x) for x in cor]
        seq = []
        for c in conts:
            it = Dataset()
            it.ContourGeometricType = "CLOSED_PLANAR"
            it.NumberOfContourPoints = len(c)
            it.ContourData = ["%.2f" % float(x) for x in c.ravel()]
            seq.append(it)
        r.ContourSequence = seq
        rc.append(r)
    ds.StructureSetROISequence = ss
    ds.ROIContourSequence = rc
    try:
        ds.save_as(caminho, enforce_file_format=True)
    except TypeError:
        ds.save_as(caminho, write_like_original=False)


def _esfera_no_plano(centro, R, linha, coluna, passo=3.0, n=64):
    import numpy as np
    linha = np.asarray(linha, dtype=float)
    coluna = np.asarray(coluna, dtype=float)
    normal = np.cross(linha, coluna)
    a = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    fora = []
    for w in np.arange(-R, R + 1e-6, passo):
        r2 = R * R - w * w
        if r2 > 4.0:
            r = np.sqrt(r2)
            fora.append(np.asarray(centro, dtype=float) + w * normal
                        + np.outer(r * np.cos(a), linha)
                        + np.outer(r * np.sin(a), coluna))
    return fora


def teste_o_nome_proprio_decide_pelo_nome_padrao():
    secao("STUDY com nome proprio: osso, vaso, pele e opacidade pelo nome "
          "padrao da descricao da ROI")
    import radai_recon3d as R
    import radai_sets
    esfera = _esfera_no_plano((0.0, 0.0, 0.0), 10.0, (1, 0, 0), (0, 1, 0))
    d = radai_sets.descricao_da_roi
    base = tempfile.mkdtemp(prefix="r3d_proprio_")
    try:
        rs = os.path.join(base, "RS_proprio.dcm")
        _rtstruct_sintetico(rs, [
            (u"CRANIO", (200, 200, 200), esfera, d(u"Skull_ai")),
            (u"ACI_E", (220, 40, 40), esfera, d(u"A_Carotid_L_ai")),
            (u"TEGUMENTO", (240, 200, 180), esfera, d(u"Skin_ai")),
            (u"SEM_DESC", (100, 100, 100), esfera)])
        por = dict((r[u"nome"], r) for r in R.abrir_conjunto(rs)[u"rois"])
        checar("o nome padrao sai da descricao da ROI, e sem descricao fica "
               "o proprio nome",
               por[u"CRANIO"].get(u"padrao") == u"Skull_ai"
               and por[u"ACI_E"].get(u"padrao") == u"A_Carotid_L_ai"
               and por[u"SEM_DESC"].get(u"padrao") == u"SEM_DESC",
               str(dict((k, v.get(u"padrao")) for k, v in por.items())))
        checar("CRANIO e osso; ACI_E e vaso, e nao osso",
               R.e_osso(por[u"CRANIO"][u"padrao"])
               and R.e_vaso(por[u"ACI_E"][u"padrao"])
               and not R.e_osso(por[u"ACI_E"][u"padrao"]))
        checar("TEGUMENTO sai so pela face de fora e com a opacidade da pele",
               por[u"TEGUMENTO"].get(u"casca") is True
               and por[u"TEGUMENTO"][u"opacidade"]
               == R.opacidade_inicial(u"Skin_ai"),
               str(por[u"TEGUMENTO"]))
        checar("isca: so pelo nome proprio, CRANIO nao seria osso, ACI_E nao "
               "seria vaso, e TEGUMENTO seria opaco e cheio",
               not R.e_osso(u"CRANIO") and not R.e_vaso(u"ACI_E")
               and not R.e_casca(u"TEGUMENTO")
               and R.opacidade_inicial(u"TEGUMENTO")
               != R.opacidade_inicial(u"Skin_ai"))
        tela = io.open(_componentes.fonte("app/radai_recon3d_screen.py"),
                       encoding="utf-8").read()
        checar("a lista de estruturas da tela marca osso e vaso pelo nome "
               "padrao", u'R.e_osso(r.get("padrao") or r["nome"])' in tela
               and u'R.e_vaso(r.get("padrao") or r["nome"])' in tela
               and u'R.e_osso(r["nome"])' not in tela)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_rtstruct_fora_do_axial_vira_malha():
    secao("o RTSTRUCT de serie sagital, coronal ou obliqua (a RM) vira malha "
          "no lugar")
    import math
    import numpy as np
    import radai_recon3d as R
    c = math.cos(math.radians(9.0))
    s = math.sin(math.radians(9.0))
    planos = [("axial", (1, 0, 0), (0, 1, 0)),
              ("sagital", (0, 1, 0), (0, 0, -1)),
              ("coronal", (1, 0, 0), (0, 0, -1)),
              ("axial obliqua", (1, 0, 0), (0, c, s)),
              ("sagital obliqua", (s, c, 0), (0, 0, -1))]
    centro, raio = (12.0, -25.0, 40.0), 22.0
    alvo = 4.0 / 3.0 * math.pi * raio ** 3
    base = tempfile.mkdtemp(prefix="r3d_plano_")
    try:
        for rotulo, linha, coluna in planos:
            rs = os.path.join(base, "RS_%s.dcm" % rotulo.replace(" ", "_"))
            _rtstruct_sintetico(rs, [(u"Esfera_ai", (220, 60, 60),
                                      _esfera_no_plano(centro, raio, linha,
                                                       coluna))])
            conj = R.abrir_conjunto(rs)
            v, f, _info = R.malha_do_conjunto(conj, u"Esfera_ai")
            m = _malha_conferida(v, f)
            meio = (v.min(axis=0) + v.max(axis=0)) / 2.0 if len(v) else None
            checar("%s: a malha fecha, com o volume da esfera a 6%%" % rotulo,
                   m["fechada"] and abs(m["volume_mm3"] - alvo) / alvo < 0.06,
                   "%s %.0f contra %.0f" % (m["fechada"], m["volume_mm3"],
                                            alvo))
            checar("%s:   e no lugar dos contornos, em mm LPS (centro a "
                   "1,5 mm)" % rotulo, meio is not None
                   and float(np.abs(meio - centro).max()) < 1.5,
                   str(None if meio is None else np.round(meio, 2)))
            nuvem = R.nuvem_do_conjunto(conj, u"Esfera_ai")
            p = np.asarray(nuvem.get(u"pontos") or [[1e9, 1e9, 1e9]])
            dist = np.linalg.norm(p - centro, axis=1)
            checar("%s:   e a nuvem de pontos na superficie dela (raio "
                   "mediano a 1,5 mm)" % rotulo,
                   abs(float(np.median(dist)) - raio) < 1.5,
                   "%.2f mm" % float(np.median(dist)))
        rng = np.random.RandomState(7)
        tortos = []
        for p in _esfera_no_plano(centro, raio, (0, 1, 0), (0, 0, -1)):
            q = p.copy()
            q[:, 0] += rng.uniform(-1.0, 1.0, len(q))
            tortos.append(q)
        rs_t = os.path.join(base, "RS_sagital_fora_do_plano.dcm")
        _rtstruct_sintetico(rs_t, [(u"Esfera_ai", (220, 60, 60), tortos)])
        v, f, _info = R.malha_do_conjunto(R.abrir_conjunto(rs_t), u"Esfera_ai")
        m = _malha_conferida(v, f)
        checar("o RTSTRUCT de antes (pontos ate 1 mm fora do corte) tambem vira "
               "malha: cada contorno vai ao plano dele (volume a 8%)",
               m["fechada"] and abs(m["volume_mm3"] - alvo) / alvo < 0.08,
               "%s %.0f contra %.0f" % (m["fechada"], m["volume_mm3"], alvo))
        axial = {u"Esfera_ai": _esfera(10.0, -20.0, 30.0, 24.0)}
        checar("contorno axial nao gira (o caminho de sempre)",
               R.plano_dos_contornos(axial) is None)
        rs = os.path.join(base, "RS_sagital.dcm")
        guardado = R.plano_dos_contornos
        R.plano_dos_contornos = lambda *a, **k: None
        try:
            try:
                R.malha_do_conjunto(R.abrir_conjunto(rs), u"Esfera_ai")
                recusou = False
            except ValueError:
                recusou = True
        finally:
            R.plano_dos_contornos = guardado
        checar("ISCA: empilhando pela posicao z do paciente, como antes, a "
               "sagital nao vira malha", recusou)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _serie_com_rtstruct(base):
    from datetime import datetime
    import numpy as np
    sys.path.insert(0, AQUI)
    import make_test_series
    pasta = os.path.join(base, "PAC_MALHA", "CT")
    uid = make_test_series.escreve_serie(pasta, "PAC_MALHA", datetime.now(), 20)
    pele = []
    for z in np.arange(0.0, 57.1, 3.0):
        pele += [_circulo(0.0, 0.0, 100.0, z, 96), _circulo(0.0, 0.0, 95.0, z, 96)]
    tubo = []
    for z in np.arange(9.0, 45.1, 3.0):
        tubo += [_circulo(-40.0, 0.0, 14.0, z), _circulo(-40.0, 0.0, 8.0, z)]
    rs = u"RS_RadAI_20260927_%s.dcm" % uid[-8:]
    _rtstruct_sintetico(os.path.join(pasta, rs), [
        (u"Esfera_ai", (220, 60, 60), _esfera(30.0, 10.0, 27.0, 18.0)),
        (u"Tubo_ai", (60, 120, 220), tubo),
        (u"Skin_ai", (200, 170, 150), pele)])
    return pasta, uid, rs


def teste_a_rota_da_malha():
    secao("a rota da malha")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import json
    import numpy as np
    import radai_bolus
    import radai_recon3d as R
    import radai_thumbnail
    import radai_recon3d_screen as S
    base = tempfile.mkdtemp(prefix="r3d_malha_")
    pasta, uid, rs = _serie_com_rtstruct(base)
    b = radai_thumbnail.bilhete(pasta, uid)
    app = FastAPI()
    S.montar(app)
    cli = TestClient(app)
    try:
        d = cli.post("/api/recon3d/estruturas", json={"b": b}).json()
        nomes = [e["nome"] for e in d.get("estruturas") or []]
        checar("a lista traz as tres estruturas, na ordem do arquivo",
               nomes == ["Esfera_ai", "Tubo_ai", "Skin_ai"], str(d)[:200])
        checar("  e abre o entregue quando nada foi pedido", d.get("rs") == rs)
        checar("  com a cor do arquivo e a opacidade de nascer",
               d["estruturas"][0]["cor"] == [220, 60, 60]
               and d["estruturas"][2]["opacidade"] < 0.5
               and d["estruturas"][2]["casca"] is True, str(d["estruturas"]))
        checar("  os eixos da malha sao LPS", d.get("eixos") == ["esq", "post", "sup"])
        cx = d.get("caixa") or [[0, 0, 0], [0, 0, 0]]
        checar("  e a caixa da cena e a dos contornos",
               abs(cx[0][0] + 100) < 1 and abs(cx[1][0] - 100) < 1
               and abs(cx[0][2]) < 0.5 and abs(cx[1][2] - 57) < 0.5, str(cx))
        checar("  com as camadas da TC oferecidas (serie de TC)",
               [c["camada"] for c in d.get("camadas") or []] == ["osso", "pele"])
        checar("  e sem o caminho da serie na resposta",
               "PAC_MALHA" not in json.dumps(d))

        r = cli.post("/api/recon3d/malha",
                     json={"b": b, "rs": rs, "nome": "Esfera_ai"})
        checar("a malha sai (200)", r.status_code == 200, str(r.status_code))
        h = dict((k.lower(), v) for k, v in r.headers.items())
        checar("  como bytes genericos, e nao como arquivo",
               h.get("content-type", "").startswith("application/octet-stream")
               and "content-disposition" not in h, str(h))
        checar("  sem cache no navegador", "no-store" in h.get("cache-control", ""))
        _c, tri, _n = radai_bolus.ler_stl(r.content)
        pts = tri.reshape(-1, 3)
        uniq, inv = np.unique(pts, axis=0, return_inverse=True)
        cm = radai_bolus.conferir_malha(uniq, inv.reshape(-1, 3))
        checar("  o STL fecha, com a normal para fora", cm["fechada"]
               and cm["volume_mm3"] > 0, str(cm))
        centro = (uniq.min(axis=0) + uniq.max(axis=0)) / 2.0
        checar("  e a esfera esta onde os contornos a puseram (mm LPS)",
               float(np.abs(centro - [30.0, 10.0, 27.0]).max()) < 2.0,
               str(np.round(centro, 1)))

        chamadas = []
        original = R.malha_do_conjunto

        def _contar(c, nome):
            chamadas.append(nome)
            return original(c, nome)
        R.malha_do_conjunto = _contar
        try:
            r2 = cli.post("/api/recon3d/malha",
                          json={"b": b, "rs": rs, "nome": "Esfera_ai"})
            r3 = cli.post("/api/recon3d/malha",
                          json={"b": b, "rs": rs, "nome": "Tubo_ai"})
        finally:
            R.malha_do_conjunto = original
        checar("pedir de novo nao monta de novo (guardada por serie + estrutura)",
               r2.content == r.content and chamadas == ["Tubo_ai"],
               str(chamadas))
        checar("  e a outra estrutura e montada", r3.status_code == 200)

        g = cli.get("/api/recon3d/malha", params={"b": b, "rs": rs,
                                                 "nome": "Esfera_ai"})
        checar("a barra de endereco nao abre a malha (GET nao existe)",
               g.status_code in (404, 405), str(g.status_code))
        for fora in ("../" + rs, "C:\\Windows\\win.ini", "RS_RadAI_outra.dcm"):
            x = cli.post("/api/recon3d/malha",
                         json={"b": b, "rs": fora, "nome": "Esfera_ai"})
            checar("  arquivo que nao esta ao lado da serie e recusado (%s)"
                   % fora[:14], x.status_code == 404
                   and x.headers.get("content-type", "").startswith(
                       "application/json"), str(x.status_code))
        x = cli.post("/api/recon3d/malha",
                     json={"b": b, "rs": rs, "nome": "Nao_Existe_ai"})
        checar("  estrutura que nao esta no arquivo: 404 com frase fixa",
               x.status_code == 404 and x.json().get("erro")
               == u"esta estrutura não está no arquivo", x.text[:120])
        m = cli.post("/api/recon3d/malha",
                     json={"b": "f" * 32, "rs": rs, "nome": "Esfera_ai"})
        checar("  bilhete morto manda recarregar a lista",
               m.status_code == 404 and "recarregue" in m.json().get("erro", ""))

        o = cli.post("/api/recon3d/malha", json={"b": b, "camada": "osso"})
        checar("a camada de osso da TC sai em malha", o.status_code == 200
               and len(o.content) > 84, str(o.status_code))
        if o.status_code == 200:
            _c2, tri2, _n2 = radai_bolus.ler_stl(o.content)
            p2 = tri2.reshape(-1, 3)
            checar("  e cai no insert de osso do fantoma (mm LPS)",
                   abs(float(np.median(p2[:, 1])) - 51.0) < 6.0
                   and abs(float(np.median(p2[:, 0]))) < 6.0,
                   str(np.round(np.median(p2, axis=0), 1)))
        n = cli.post("/api/recon3d/nuvem",
                     json={"b": b, "rs": rs, "nomes": ["Esfera_ai"],
                           "camadas": []}).json()
        its = n.get("itens") or []
        checar("o recuo pede a nuvem da estrutura em mm LPS",
               len(its) == 1 and n.get("lps") is True
               and its[0].get("nome") == "Esfera_ai", str(n)[:200])
        if its:
            pc = np.asarray(its[0]["pontos"], dtype=float).mean(axis=0)
            checar("  no mesmo lugar da malha",
                   float(np.abs(pc - [30.0, 10.0, 27.0]).max()) < 2.5,
                   str(np.round(pc, 1)))
    finally:
        with S._TRAVA_MALHA:
            S._esquecer_malhas()
        shutil.rmtree(base, ignore_errors=True)


def _longo(pasta):
    import radai_watcher as W
    return W.caminho_longo(os.path.abspath(pasta))


def teste_a_serie_do_acervo_abre_com_o_prefixo_do_vigia():
    secao("a serie do acervo abre com o prefixo do vigia (\\\\?\\)")
    if os.name != "nt":
        checar("o prefixo \\\\?\\ so existe no Windows", True, "PULADO")
        return
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import engine
    import radai_archive
    import radai_viewseg
    import radai_recon3d_screen as S
    base = tempfile.mkdtemp(prefix="r3d_acervo_")
    pasta, uid, rs = _serie_com_rtstruct(base)
    longo = _longo(pasta)
    checar("a pasta que o vigia grava tem o prefixo \\\\?\\ (o que a "
           "varredura devolve)", longo.startswith("\\\\?\\"), repr(longo[:6]))
    checar("  e o GDCM, sozinho, nao lista a pasta com ele (a causa)",
           not engine.sitk.ImageSeriesReader.GetGDCMSeriesFileNames(longo, uid)
           and len(engine.sitk.ImageSeriesReader.GetGDCMSeriesFileNames(
               pasta, uid)) == 20)
    radai_archive.registrar_serie(uid=uid, pasta=longo, rs=rs,
                                  date="20260927", pid="PAC_MALHA",
                                  estruturas=3, secs=1, maquina="bateria",
                                  ver="bateria")
    import radai_tabela_acervo
    app = FastAPI()
    radai_tabela_acervo.montar(app)
    S.montar(app)
    cli = TestClient(app)

    def _abrir_pelo_acervo():
        ac = cli.post("/api/recon3d/acervo?ferramenta=geral",
                      json={"limite": 60}).json().get("series") or []
        ent = [s for s in ac if s.get("uid8") == uid[-8:]]
        if not ent:
            return {"erro": "sem entrada no acervo: %s" % ac}, 0
        b = ent[0]["bilhete"]
        e = cli.get("/api/recon3d/estado", params={"b": b}).json()
        p = cli.get("/api/recon3d/projecao",
                    params={"b": b, "modo": "mip", "eixo": 0, "laje": 0,
                            "pos": 0.5, "janela": "mediastino"})
        return e, p.status_code

    try:
        with S._TRAVA_VOL:
            S._esquecer_serie()
        est, cod = _abrir_pelo_acervo()
        checar("a serie do acervo abre: o estado nao diz «nao le»",
               "erro" not in est and not est.get("nao_le"), str(est)[:200])
        checar("  e o plano sai (200), em vez do 404 dos prints",
               cod == 200, str(cod))
        lista, erro = radai_viewseg.series_contornadas(longo)
        checar("o «Ver segmentacao» le a mesma entrada (e nao tinha o "
               "defeito)", not erro and [s for s in lista
                                         if s.get("uid") == uid], str(erro))
        velho = engine._pasta_para_o_gdcm
        engine._pasta_para_o_gdcm = lambda d: str(d)
        try:
            with S._TRAVA_VOL:
                S._esquecer_serie()
            est2, cod2 = _abrir_pelo_acervo()
        finally:
            engine._pasta_para_o_gdcm = velho
            with S._TRAVA_VOL:
                S._esquecer_serie()
        checar("ISCA: com a pasta prefixada indo direto ao GDCM, a serie nao "
               "le e o plano da 404 (as de cima reprovariam)",
               est2.get("nao_le") and est2.get("tipo") == "ValueError"
               and cod2 == 404, "%s %s" % (str(est2)[:120], cod2))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_pasta_com_ponto_no_fim_abre_pelo_prefixo():
    secao("a pasta terminada em ponto abre pelo prefixo, e nao pela vizinha")
    if os.name != "nt":
        checar("o prefixo \\\\?\\ so existe no Windows", True, "PULADO")
        return
    from datetime import datetime
    sys.path.insert(0, AQUI)
    import make_test_series
    import engine
    base = tempfile.mkdtemp(prefix="r3d_ponto_")
    base_longa = _longo(base)
    try:
        com_ponto = base_longa + "\\CT_0."
        vizinha = os.path.join(base, "CT_0")
        uid_p = make_test_series.escreve_serie(com_ponto, "PAC_PONTO",
                                               datetime.now(), 6)
        make_test_series.escreve_serie(vizinha, "PAC_VIZINHA",
                                       datetime.now(), 9)
        checar("  (o fantoma) a pasta com ponto existe pelo prefixo, com 6 "
               "cortes", len(os.listdir(com_ponto)) == 6)
        img = engine.load_sitk(com_ponto, uid_p)
        checar("a serie da pasta com ponto abre pelo prefixo (com o UID)",
               img.GetSize()[2] == 6, str(img.GetSize()))
        img2 = engine.load_sitk(com_ponto)
        checar("  e sem o UID ela le a PROPRIA pasta, e nao a vizinha sem o "
               "ponto (6 cortes, e nao 9)", img2.GetSize()[2] == 6,
               str(img2.GetSize()))
        velho = engine._pasta_para_o_gdcm
        engine._pasta_para_o_gdcm = engine._sem_prefixo_longo
        try:
            img3 = engine.load_sitk(com_ponto)
            n3 = img3.GetSize()[2]
        except Exception as e:
            n3 = type(e).__name__
        finally:
            engine._pasta_para_o_gdcm = velho
        checar("ISCA: tirando o prefixo sem conferir, sem o UID ele le a "
               "vizinha (9 cortes — a de cima reprovaria)", n3 == 9, str(n3))
    finally:
        shutil.rmtree(base_longa, ignore_errors=True)


def teste_as_malhas_saem_com_a_serie():
    secao("as malhas saem da memoria com a serie")
    import time
    import radai_recon3d_screen as S
    try:
        with S._TRAVA_MALHA:
            S._esquecer_malhas()
            S._guardar_malha(("p1", "u1", "rs", 0.0, "A", "1"), b"x" * 10)
            S._guardar_malha(("p2", "u2", "rs", 0.0, "B", "1"), b"y" * 10)
            S._CONJ.update({"chave": ("p1", "u1", "rs", 0.0), "c": {"x": 1}})
            S._esquecer_malhas(fora_da_serie=("p2", "u2"))
            checar("outra serie aberta: a primeira sai, a nova fica",
                   list(S._MALHAS) == [("p2", "u2", "rs", 0.0, "B", "1")]
                   and S._CONJ["c"] is None, str(list(S._MALHAS)))
        agora = time.time()
        S._VOL.update({"v": None, "visto": agora - S.SOLTAR_APOS_S - 5,
                       "relogio": None})
        falta = S._soltar_se_parada(agora=agora, rearmar=False)
        checar("parada ha mais que SOLTAR_APOS_S: as malhas saem tambem",
               falta is None and not S._MALHAS and S._CONJ["c"] is None,
               "%r %d" % (falta, len(S._MALHAS)))
        velho = S.TETO_CACHE_MALHAS_MB
        try:
            S.TETO_CACHE_MALHAS_MB = 1
            with S._TRAVA_MALHA:
                for i in range(4):
                    S._guardar_malha(("p", "u", "rs", 0.0, str(i), "1"),
                                     b"z" * 400000)
                n = len(S._MALHAS)
                ultima = ("p", "u", "rs", 0.0, "3", "1") in S._MALHAS
        finally:
            S.TETO_CACHE_MALHAS_MB = velho
        checar("acima do teto de bytes, as mais antigas saem, e a ultima fica",
               n <= 3 and ultima, "%d guardadas" % n)
    finally:
        with S._TRAVA_MALHA:
            S._esquecer_malhas()
        S._VOL.update({"chave": None, "v": None, "relogio": None})


def _dom_falso():
    return u"""
var LOG = [];
function Canvas(id){ this.id = id; this.hidden = false; this.width = 300;
  this.height = 300; this.ev = {}; }
Canvas.prototype.addEventListener = function(t, f){ this.ev[t] = f };
Canvas.prototype.getBoundingClientRect = function(){ return {width: 400, height: 300} };
Canvas.prototype.getContext = function(t){
  if(t === '2d') return {clearRect: function(){}, save: function(){}, restore: function(){},
    beginPath: function(){}, moveTo: function(){}, lineTo: function(){}, stroke: function(){},
    fillText: function(){}};
  return (typeof CTX === 'function') ? CTX(t) : null;
};
var EL = {cvGL: new Canvas('cvGL'), cv3Db: new Canvas('cv3Db'), cv3D: new Canvas('cv3D'),
  r3_aviso3d: {hidden: true}, r3_motivo3d: {textContent: ''},
  r3_modo3d: {textContent: ''}, dica3d: {innerHTML: ''},
  r3_estr: {addEventListener: function(){}, innerHTML: ''},
  r3_camadas3d: {addEventListener: function(){}, innerHTML: ''},
  r3_cab_camadas: {hidden: true}, r3_conta: {textContent: ''}};
function r3El(i){ return EL[i] || null }
function r3Esc(t){ return String(t) }
var window = {devicePixelRatio: 1, addEventListener: function(){},
              requestAnimationFrame: function(f){ LOG.push('raf') }};
var document = {querySelector: function(){ return null }};
function n3MatrizInicial(){ return [1,0,0, 0,1,0, 0,0,1] }
function n3MatrizDaVista(){ return [1,0,0, 0,1,0, 0,0,1] }
function n3Girar(M){ return M }
function n3Bussola(){ LOG.push('bussola') }
var N3 = {eixos: null};
"""


def _gl_falso(compila=True):
    return u"""
function GLFalso(){
 var g = {VERTEX_SHADER: 1, FRAGMENT_SHADER: 2, COMPILE_STATUS: 3, LINK_STATUS: 4,
  ARRAY_BUFFER: 5, ELEMENT_ARRAY_BUFFER: 6, STATIC_DRAW: 7, FLOAT: 8,
  UNSIGNED_SHORT: 9, UNSIGNED_INT: 10, TRIANGLES: 11, DEPTH_TEST: 12, LEQUAL: 13,
  BLEND: 14, CULL_FACE: 15, SRC_ALPHA: 16, ONE_MINUS_SRC_ALPHA: 17, FRONT: 18,
  BACK: 19, COLOR_BUFFER_BIT: 20, DEPTH_BUFFER_BIT: 21};
 var nomes = {12: 'DEPTH', 14: 'BLEND', 15: 'CULL', 18: 'FRONT', 19: 'BACK'};
 g.createShader = function(){ return {} }; g.shaderSource = function(){};
 g.compileShader = function(){};
 g.getShaderParameter = function(){ return %s };
 g.createProgram = function(){ return {} }; g.attachShader = function(){};
 g.linkProgram = function(){}; g.getProgramParameter = function(){ return true };
 g.getExtension = function(){ return {} };
 g.getAttribLocation = function(){ return 0 }; g.getUniformLocation = function(p, n){ return n };
 g.viewport = g.clearColor = g.clear = g.useProgram = g.enableVertexAttribArray =
  g.uniformMatrix3fv = g.uniformMatrix4fv = g.uniform3f = g.uniform2f = g.bindBuffer =
  g.vertexAttribPointer = g.depthFunc = g.blendFunc = function(){};
 g.uniform1f = function(n, v){ if(n === 'uAlfa') g.alfa = v };
 g.enable = function(x){ LOG.push('on:' + (nomes[x] || x)) };
 g.disable = function(x){ LOG.push('off:' + (nomes[x] || x)) };
 g.depthMask = function(x){ LOG.push('mask:' + x) };
 g.cullFace = function(x){ LOG.push('cull:' + (nomes[x] || x)) };
 g.drawElements = function(){ LOG.push('draw:' + g.alfa) };
 g.drawArrays = function(){ LOG.push('draw:' + g.alfa) };
 return g;
}
""" % ("true" if compila else "false")


def teste_o_recuo_e_detectado_e_nao_presumido():
    secao("o recuo sem WebGL e detectado, e nao presumido")
    import radai_recon3d_screen as S
    js = S.JS_MALHA

    def rodar(ctx, fonte=js):
        prog = u"\n".join([
            _dom_falso(), _gl_falso(compila=(ctx != "nao_compila")),
            u"var CTX = %s;" % {
                "nenhum": u"function(){ return null }",
                "nao_compila": u"function(){ return GLFalso() }",
                "ok": u"function(){ return GLFalso() }"}[ctx],
            fonte,
            u"r3mIniciar();",
            u"console.log('JSON:' + JSON.stringify({modo: R3M.modo,"
            u" aviso: EL.r3_aviso3d.hidden, motivo: EL.r3_motivo3d.textContent,"
            u" gl: EL.cvGL.hidden, nuvem: EL.cv3D.hidden,"
            u" menu: !!EL.cv3D.ev.contextmenu, menuGL: !!EL.cvGL.ev.contextmenu}));",
        ])
        return _rodar_js(prog)
    d, erro = rodar("nenhum")
    if d is None:
        checar("r3mIniciar executa no node", False, erro)
        return
    checar("sem contexto WebGL: a nuvem de pontos", d["modo"] == "nuvem", str(d))
    checar("  e a tela DIZ, com o motivo", d["aviso"] is False
           and "contexto WebGL" in d["motivo"], str(d))
    checar("  o canvas da malha some e o da nuvem aparece",
           d["gl"] is True and d["nuvem"] is False, str(d))
    checar("  e o menu do botao direito nao abre sobre a nuvem", d["menu"])
    d2, _e = rodar("nao_compila")
    checar("contexto que nao compila o sombreador: a nuvem, com o motivo",
           d2 and d2["modo"] == "nuvem" and "compilou" in d2["motivo"], str(d2))
    d3, _e = rodar("ok")
    checar("WebGL que funciona: a malha, sem aviso",
           d3 and d3["modo"] == "gl" and d3["aviso"] is True
           and d3["gl"] is False and d3["nuvem"] is True, str(d3))
    checar("  e o menu do botao direito nao abre sobre a malha",
           d3 and d3["menuGL"])
    presume = js.replace(_funcao_js(js, "r3gDetectar"),
                         u"function r3gDetectar(){ R3G.gl = GLFalso();"
                         u" R3G.canvas = r3El('cvGL'); return '' }")
    d4, _e = rodar("nenhum", presume)
    checar("(isca) o detector que presume declararia WebGL sem contexto",
           d4 is not None and d4["modo"] == "gl", str(d4))


def teste_a_transparencia_desenha_na_ordem():
    secao("a transparencia desenha na ordem certa")
    import radai_recon3d_screen as S
    js = S.JS_MALHA
    cena = u"""
r3mIniciar();
R3M.estr = [{nome: 'A'}, {nome: 'B'}, {nome: 'Frente'}, {nome: 'Fundo'}];
R3M.cam = []; R3M.rs = 'rs';
R3M.lig = {A: true, B: true, Frente: true, Fundo: true};
R3M.alfa = {A: 1.0, B: 1.0, Frente: 0.3, Fundo: 0.4};
function obj(z){ return {vbo: 1, nbo: 1, ibo: 1, tipo: 9, n: 3,
                         cor: [255, 255, 255], centro: [0, 0, z]} }
R3G.objs = {'rs|A': obj(0), 'rs|B': obj(5), 'rs|Frente': obj(50),
            'rs|Fundo': obj(-50)};
R3G.centro = [0, 0, 0]; R3G.raio = 100;
LOG.length = 0;
r3gDesenhar();
console.log('JSON:' + JSON.stringify(LOG));
"""

    def rodar(fonte):
        return _rodar_js(u"\n".join([_dom_falso(), _gl_falso(),
                                     u"var CTX = function(){ return GLFalso() };",
                                     fonte, cena]))
    log, erro = rodar(js)
    if log is None:
        checar("r3gDesenhar executa no node", False, erro)
        return
    desenhos = [x for x in log if x.startswith("draw:")]
    checar("as quatro sao desenhadas, as translucidas duas vezes cada",
           desenhos == ["draw:1", "draw:1", "draw:0.4", "draw:0.4",
                        "draw:0.3", "draw:0.3"], str(desenhos))
    i_trans = log.index("draw:0.4") if "draw:0.4" in log else -1
    antes, depois = log[:i_trans], log[i_trans:]
    checar("  as opacas com profundidade escrita e sem mistura",
           "mask:true" in antes and "off:BLEND" in antes, str(antes))
    checar("  as translucidas com mistura e SEM escrever profundidade",
           "on:BLEND" in antes[antes.index("draw:1"):]
           and "mask:false" in antes[antes.index("draw:1"):], str(log))
    checar("  cada translucida: a face de tras, depois a da frente",
           depois[:4] == ["draw:0.4", "cull:BACK", "draw:0.4", "cull:FRONT"]
           and log[i_trans - 1] == "cull:FRONT", str(log))
    checar("  e a bussola por cima", "bussola" in log)
    invertida = js.replace(u"trans.sort(function(a, b){ return a[2] - b[2] });",
                           u"trans.sort(function(a, b){ return b[2] - a[2] });")
    checar("(isca) a troca foi feita na copia", invertida != js)
    log2, _e = rodar(invertida)
    d2 = [x for x in (log2 or []) if x.startswith("draw:")]
    checar("(isca) com a ordem invertida, a da frente sairia primeiro",
           d2[2:3] == ["draw:0.3"], str(d2))


def teste_o_visor_e_um_so_com_o_nidus():
    secao("o visor WebGL mora num modulo so do RECON_3D, e as duas telas o usam")
    import radai_recon3d_gl as G
    import radai_recon3d_screen as S
    for fn in ("r3gLerStl", "r3gPrograma", "r3gSubirEm", "r3gUmEm", "r3gOrto",
               "r3gCorte", "r3gTranslucidoEm"):
        checar("o modulo do visor tem %s" % fn, ("function %s(" % fn) in G.JS)
    checar("o sombreador recorta pela caixa no espaco da serie (uParaCaixa)",
           "uParaCaixa" in G.JS and "discard" in G.JS)
    checar("a tela das Reconstrucoes usa o modulo, sem copia do leitor de STL",
           S.JS_MALHA.startswith(G.JS)
           and S.JS_MALHA.count("function r3gLerStl(") == 1)
    try:
        import radai_nidus_screen as NS
        checar("o Nidus importa o mesmo modulo", G.JS in NS.pagina())
    except Exception as e:
        checar("o Nidus importa o mesmo modulo", False, str(e)[:80])


def teste_o_visor_3d_herda_do_nidus():
    secao("o visor 3D herda do Nidus: Ver atraves, as barras e as incidencias")
    import radai_nidus as N
    import radai_recon3d_screen as S
    p = S.pagina("geral")
    checar("o botao «Ver atraves» esta no visor", 'id="r3_atraves"' in p
           and ">Ver através</span>" in p)
    checar("as barras LAO/RAO (-180 a 180) e CRA/CAU (-90 a 90)",
           'id="r3_lao" min="-180" max="180"' in p
           and 'id="r3_cra" min="-90" max="90"' in p)
    faltam = [n for n, a, b in N.INCIDENCIAS
              if ('data-lao="%d" data-cra="%d"' % (a, b)) not in p
              or (">%s</small>" % N.rotulo_do_angulo(a, b)) not in p]
    checar("as oito incidencias do Nidus, com o angulo no botao", not faltam,
           str(faltam))
    checar("e a convencao vem do radai_nidus (uma funcao so)",
           "function radaiIncidencia(" in p
           and "function radaiIncidencia(" not in S.JS_MALHA)
    js = (u"document.querySelectorAll = function(){ return [] };\n"
          + N.JS_CONVENCAO + S.JS_MALHA)
    prog = u"\n".join([_dom_falso(), _gl_falso(),
                       u"var CTX = function(){ return GLFalso() };", js, u"""
EL.r3_lao = {value: '0'}; EL.r3_cra = {value: '0'};
EL.r3_lao_v = {textContent: ''}; EL.r3_cra_v = {textContent: ''};
EL.r3_atraves = {setAttribute: function(k, v){ this[k] = v }};
function r3MenosMovimento(){ return true }
r3mIniciar();
var r = {};
r3IncAplicar(90, 0, true);
var b = radaiIncidencia(90, 0), M = R3G.M;
r.linhas = [M[0]-b.r[0], M[1]-b.r[1], M[2]-b.r[2], M[3]-b.u[0], M[4]-b.u[1], M[5]-b.u[2],
            M[6]-b.d[0], M[7]-b.d[1], M[8]-b.d[2]].map(Math.abs).reduce(function(a, x){ return Math.max(a, x) }, 0);
r.rot = [EL.r3_lao_v.textContent, EL.r3_cra_v.textContent];
EL.r3_lao.value = '-35'; EL.r3_cra.value = '20'; r3IncBarra();
r.de = r3IncDe(R3G.M);
R3G.M = n3Girar(R3G.M, 0, 0); R3M.incVisto = ''; r3IncSincronizar();
r.sinc = [EL.r3_lao.value, EL.r3_cra.value];
R3M.estr = [{nome: 'Skull_ai', osso: true, cor: [230, 220, 200]},
            {nome: 'Skin_ai', casca: true, cor: [200, 160, 140]},
            {nome: 'Brain_ai', cor: [200, 120, 120]}];
R3M.cam = [{camada: 'osso', cor: [230, 220, 200]}, {camada: 'pele', cor: [200, 160, 140]}];
R3M.alfa = {Skull_ai: 1, Skin_ai: 0.15, Brain_ai: 1, '@osso': 1, '@pele': 0.15};
r3Atraves();
r.atraves = JSON.parse(JSON.stringify(R3M.alfa));
r.botao = EL.r3_atraves['aria-pressed'];
r3Atraves();
r.volta = JSON.parse(JSON.stringify(R3M.alfa));
console.log('JSON:' + JSON.stringify(r));
"""])

    def rodar(fonte):
        return _rodar_js(fonte)
    d, erro = rodar(prog)
    if d is None:
        checar("as barras e o Ver atraves executam no node", False, erro)
        return
    checar("a incidencia vira a camera: as linhas de M sao r, u e d da convencao",
           d["linhas"] < 1e-9, str(d["linhas"]))
    checar("  e a leitura diz LAO 90° · CRA 0°", d["rot"] == [u"LAO 90°", u"CRA 0°"],
           str(d["rot"]))
    checar("as barras giram o 3D e a leitura volta da camera (RAO 35, CRA 20)",
           d["de"] == [-35, 20] and d["sinc"] == [u"-35", u"20"], str(d))
    a, v = d["atraves"], d["volta"]
    checar("«Ver atraves» poe osso e pele em alfa baixo, e o resto fica",
           a["Skull_ai"] == 0.1 and a["@osso"] == 0.1 and a["Skin_ai"] == 0.03
           and a["@pele"] == 0.03 and a["Brain_ai"] == 1, str(a))
    checar("  e diz que esta ligado", d["botao"] == u"true")
    checar("desligar devolve a opacidade de antes",
           v == {u"Skull_ai": 1, u"Skin_ai": 0.15, u"Brain_ai": 1, u"@osso": 1,
                 u"@pele": 0.15}, str(v))
    isca = prog.replace("R3M.atravesAntes[k] = R3M.alfa[k];", "")
    d2, _e = rodar(isca)
    checar("  isca: sem guardar a opacidade, desligar nao a devolve",
           d2 is not None and d2["volta"].get("Skull_ai") != 1, str(d2))
    isca2 = prog.replace("return [b.r[0], b.r[1], b.r[2], b.u[0], b.u[1], b.u[2], b.d[0], b.d[1], b.d[2]];",
                         "return [b.r[0], b.r[1], b.r[2], b.u[0], b.u[1], b.u[2], b.v[0], b.v[1], b.v[2]];")
    d3, _e = rodar(isca2)
    checar("  isca: a camera olhando do lado do tubo e acusada",
           isca2 != prog and d3 is not None and d3["linhas"] > 0.5, str(d3))


def teste_o_cartao_do_modulo_navega():
    secao("o cartao do modulo navega")
    import radai_modules as M
    est = (M.MODULOS.get("recon3d") or {}).get("estado") or u""
    checar("o modulo nao tem etiqueta que trave o cartao",
           not M.nao_navega(est), repr(est))
    checar("(isca) com «EM BREVE» de volta, a mesma pergunta o travaria",
           M.nao_navega(u"EM BREVE"))
    fs = dict((f[0], f) for f in M.FERRAMENTAS.get("recon3d") or ())
    checar("e a ferramenta que o 3D mora nela continua com rota",
           (fs.get("recon_anatomia") or ("",) * 4)[3] == "/recon3d/anatomia")


def _n3_lados_no_node(js, lang):
    import json as _json
    import subprocess
    node = shutil.which("node")
    if not node:
        return None
    a = js.index(u"var N3_LADO = ")
    b = js.index(u"var N3_OPOSTO")
    prog = (u"var document = {documentElement: {getAttribute: function(){ "
            u"return %s }}, querySelectorAll: function(){ return [] },"
            u" addEventListener: function(){} };\n" % _json.dumps(lang)
            + js[a:b].replace(u"try{ document.addEventListener", u"try{ (0)")
            + u"\nconsole.log(JSON.stringify(n3Lados()));")
    d = tempfile.mkdtemp(prefix="r3d_n3_")
    try:
        alvo = os.path.join(d, "n3.js")
        io.open(alvo, "w", encoding="utf-8").write(prog)
        r = subprocess.run([node, alvo], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        try:
            return _json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return {"erro": (r.stderr or "")[-160:]}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def teste_a_barra_e_a_bussola_falam_a_lingua_da_tela():
    secao("a barra de transparencia, as camadas e a bussola na lingua da tela")
    import radai_recon3d_screen as S
    import radai_viewer as V
    import radai_phrases as F
    js = S.JS_MALHA
    checar("a barra de cada estrutura tem nome proprio: o molde "
           "«opacidade de %s»", "'opacidade de %s'.replace('%s', nome)" in js
           and 'aria-label="opacidade"' not in js)
    checar("  e a de cada camada da TC, uma chave inteira por camada",
           "opacidade da camada de osso" in js
           and "opacidade da camada de pele" in js)
    checar("a camada da TC e FRASE da tela (`data-radai-frase`), e nao nome "
           "de RTSTRUCT (`data-radai-t`)",
           "'<span class=\"r3e-n\" data-radai-frase>' + r3Esc(desenho ? "
           "'desenho do axial' : nome)" in js)
    tab = dict((F.normalizar(t[0]), t) for t in F.TABELA)
    chaves = ("opacidade de %s", "opacidade da camada de osso",
              "opacidade da camada de pele", "osso", "pele",
              "%d conjunto(s) de contorno nesta pasta")
    sem = [k for k in chaves if not (k in tab and all(tab[k][1:]))]
    checar("  e as frases tem chave (a contagem da pasta tambem)", not sem, sem)
    fonte_v = io.open(_componentes.fonte("app/radai_viewer.py"),
                      encoding="utf-8").read()
    for rot, pag, n in (("Reconstrucoes 3D", S.pagina(), 6),
                        ("painel de sempre", fonte_v, 3)):
        bts = re.findall(r"<button[^>]*data-n3-lado=\"[a-z]+\"[^>]*>", pag)
        checar("[%s] os %d botoes de vista tem `aria-label` e a letra por "
               "idioma (`data-n3-lado`)" % (rot, n),
               len(bts) == n and all("aria-label=" in b for b in bts),
               str(bts)[:160])
    checar("a bussola pergunta a letra a `n3Lados()`, e nao a tabela fixa",
           "LADO = n3Lados()" in V.JS_3D
           and "N3_LADO[nome]" not in V.JS_3D)
    en = _n3_lados_no_node(V.JS_3D, "en")
    pt = _n3_lados_no_node(V.JS_3D, "pt-BR")
    sem_lang = _n3_lados_no_node(V.JS_3D, "")
    if en is None:
        checar("node disponivel para rodar `n3Lados` (PULADO)", True)
        return
    checar("em ingles a esquerda e L e a direita e R (a letra do DICOM)",
           en.get("esq") == "L" and en.get("dir") == "R", str(en))
    checar("  em portugues continua E e D", pt.get("esq") == "E"
           and pt.get("dir") == "D", str(pt))
    checar("  e sem `lang` (pt-BR nao passa pelo dicionario) tambem",
           sem_lang.get("esq") == "E", str(sem_lang))
    velho = V.JS_3D.replace("var t = (!lg || lg.indexOf('pt') === 0) ? "
                            "N3_LADO : N3_LADO_DICOM;", "var t = N3_LADO;")
    en_v = _n3_lados_no_node(velho, "en")
    checar("  (isca) com a tabela fixa, o ingles volta a dizer E",
           velho != V.JS_3D and en_v.get("esq") == "E", str(en_v))


def _png_cinza(dados):
    import struct
    import zlib
    import numpy as np
    if not dados or dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("nao e PNG")
    i, larg, alt, idat = 8, 0, 0, b""
    while i < len(dados):
        n = struct.unpack(">I", dados[i:i + 4])[0]
        tipo, corpo = dados[i + 4:i + 8], dados[i + 8:i + 8 + n]
        if tipo == b"IHDR":
            larg, alt, prof, cor = struct.unpack(">IIBB", corpo[:10])
            if (prof, cor) != (8, 0):
                raise ValueError("PNG que para_png nao escreve")
        elif tipo == b"IDAT":
            idat += corpo
        i += 12 + n
    cru = zlib.decompress(idat)
    linhas = np.frombuffer(cru, dtype=np.uint8).reshape(alt, larg + 1)
    if linhas[:, 0].any():
        raise ValueError("filtro diferente de 0")
    return linhas[:, 1:]


def _fantoma_anisotropico():
    import numpy as np
    import SimpleITK as sitk
    v = np.zeros((20, 48, 64), dtype=np.int16)
    v[15] = 1000
    img = sitk.GetImageFromArray(v)
    img.SetSpacing((1.0, 1.0, 5.0))
    return img


def teste_os_planos_saem_na_proporcao_fisica():
    secao(u"os planos na proporcao fisica (mm) e com o cranio em cima (v8.3)")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import numpy as np
    import engine
    import radai_nidus as N
    import radai_recon3d as R
    import radai_thumbnail
    import radai_recon3d_screen as S

    checar(u"o Nidus usa a MESMA grade (os mesmos objetos, e nao uma copia)",
           N.grade_da_tela is R.grade_da_tela
           and N.para_a_tela is R.para_a_tela
           and N.TETO_DA_TELA == R.TETO_DA_TELA,
           "%r %r" % (N.grade_da_tela, R.grade_da_tela))
    checar(u"mm_do_plano: axial (y, x), coronal (z, x), sagital (z, y)",
           [R.mm_do_plano((5.0, 0.8, 0.9), e) for e in (0, 1, 2)]
           == [(0.8, 0.9), (5.0, 0.9), (5.0, 0.8)],
           str([R.mm_do_plano((5.0, 0.8, 0.9), e) for e in (0, 1, 2)]))
    a = np.arange(6).reshape(3, 2)
    checar(u"sem sentido (a orientacao nao foi lida), o plano sai como veio",
           R.cranio_em_cima(a, 1, None) is a)
    checar(u"indice crescendo para os pes («inf»): ja esta certo, nao vira",
           R.cranio_em_cima(a, 1, ("inf", "post", "esq")) is a)
    checar(u"o axial nao tem cranio no plano: nao vira",
           R.cranio_em_cima(a, 0, ("sup", "post", "esq")) is a)

    guarda = engine.load_sitk
    app = FastAPI()
    S.montar(app)
    cli = TestClient(app)
    b = radai_thumbnail.bilhete("fantoma_r3_aniso", "1.2.3.9")

    def _plano(eixo, laje=0, pos=0.5):
        r = cli.get("/api/recon3d/projecao",
                    params={"b": b, "eixo": eixo, "laje": laje, "pos": pos,
                            "janela": "mediastino", "modo": "mip"})
        return _png_cinza(r.content) if r.status_code == 200 else None

    def _faixa(img):
        if img is None:
            return []
        return [int(k) for k in np.where((img == 255).all(axis=1))[0]]

    try:
        engine.load_sitk = lambda pasta, uid=None: _fantoma_anisotropico()
        with S._TRAVA_VOL:
            S._esquecer_serie()
        cor = _plano(1)
        sag = _plano(2)
        ax = _plano(0)
        proj = _plano(1, laje=10)
        ax15 = _plano(0, pos=15 / 19.0)
        velho = R.para_a_tela
        R.para_a_tela = lambda a, ml, mc: np.asarray(a)
        try:
            isca_achata = _plano(1)
        finally:
            R.para_a_tela = velho
        velho = R.cranio_em_cima
        R.cranio_em_cima = lambda a, eixo, sentido: a
        try:
            isca_vira = _plano(1)
        finally:
            R.cranio_em_cima = velho
    finally:
        engine.load_sitk = guarda
        with S._TRAVA_VOL:
            S._esquecer_serie()

    def _proporcao_certa(img, mm_alt, mm_larg):
        return (img is not None
                and abs(img.shape[0] / float(img.shape[1])
                        - mm_alt / float(mm_larg)) < 0.02)

    checar(u"coronal: 100 x 64 mm vira 100 x 64 px (era 20 x 64)",
           cor is not None and cor.shape == (100, 64),
           str(None if cor is None else cor.shape))
    checar(u"sagital: 100 x 48 mm vira 100 x 48 px",
           sag is not None and sag.shape == (100, 48),
           str(None if sag is None else sag.shape))
    checar(u"a projecao (laje de 10 mm) no coronal tambem",
           _proporcao_certa(proj, 100.0, 64.0),
           str(None if proj is None else proj.shape))
    checar(u"o axial (pixel ja quadrado) nao muda: 48 x 64",
           ax is not None and ax.shape == (48, 64),
           str(None if ax is None else ax.shape))
    checar(u"o corte 15 ocupa 5 linhas no coronal: 5 mm, e nao 1 px",
           len(_faixa(cor)) == 5, str(_faixa(cor)))
    checar(u"e cai a 20 mm do TOPO: o cranio esta em cima",
           _faixa(cor) == [20, 21, 22, 23, 24], str(_faixa(cor)))
    checar(u"o mesmo no sagital",
           _faixa(sag) == [20, 21, 22, 23, 24], str(_faixa(sag)))
    checar(u"o deslizador do axial em 15/19 ainda abre o corte 15",
           ax15 is not None and bool((ax15 == 255).all()),
           "" if ax15 is None else "min %d" % int(ax15.min()))
    checar(u"isca: sem ampliar, a proporcao reprova (1 px por corte)",
           not _proporcao_certa(isca_achata, 100.0, 64.0)
           and len(_faixa(isca_achata)) == 1,
           str(None if isca_achata is None else isca_achata.shape))
    checar(u"isca: sem virar, a faixa cai a 75 mm do topo e reprova",
           _faixa(isca_vira) == [75, 76, 77, 78, 79], str(_faixa(isca_vira)))

    checar(u"os quadros dos planos nao convertem clique em coordenada",
           not re.search(r"clientX|offsetX|layerX|pageX", S.JS_SERIE), "")
    m = re.search(r"\.r3-tela img\{([^}]*)\}", S.CSS)
    regra = (m.group(1) if m else "").replace(" ", "")
    checar(u"a folha dos quadros preserva a proporcao do PNG",
           bool(m) and "max-width:100%" in regra
           and "max-height:100%" in regra
           and not ("width:100%" in regra.replace("max-width:100%", "")
                    and "height:100%" in regra.replace("max-height:100%", "")
                    and "object-fit:contain" not in regra),
           regra)


def teste_a_leitura_sem_uid_saiu():
    secao("a serie sem UID nao e adivinhada pela pasta (so servia a demo)")
    from datetime import datetime
    import numpy as np
    sys.path.insert(0, AQUI)
    import make_test_series
    import radai_rotulos
    import radai_thumbnail
    import radai_recon3d_screen as S
    fonte, _c = _sem_prosa(_componentes.fonte("app/radai_recon3d_screen.py"))
    checar("a funcao que varria a pasta atras do UID saiu",
           not hasattr(S, "_uid_da_serie") and "_UID_DA_PASTA" not in fonte)
    checar("  e a tela nao varre mais a pasta inteira para abrir uma serie",
           "radai_dicom.varrer(" not in fonte)
    base = tempfile.mkdtemp(prefix="r3d_")
    pasta = os.path.join(base, "PAC", "CT")
    uid = make_test_series.escreve_serie(pasta, "PAC", datetime.now(), 20)
    m = np.zeros((20, 32, 32), dtype=bool)
    m[5:10, 8:16, 8:16] = True
    radai_rotulos.gravar(pasta, uid, {"total_v3": {"liver": m}},
                         protocolos=["anatomia_toracica"], modalidade="CT")
    nomes = [c["arquivo"] for c in S.arquivos_da_serie(pasta, uid)]
    checar("com o UID do bilhete, o mapa de rotulos entra na lista de conjuntos",
           S.ARQUIVO_ROTULOS in nomes, nomes)
    checar("isca: sem o UID o mapa ficaria de fora",
           S.ARQUIVO_ROTULOS not in [c["arquivo"]
                                     for c in S.arquivos_da_serie(pasta, u"")])
    outra = u"RS_RadAI_20261001_99999999.dcm"
    io.open(os.path.join(pasta, outra), "wb").write(b"RT")
    checar("isca: sem o UID, a pasta oferece o RTSTRUCT de outra serie",
           outra in [c["arquivo"] for c in S.arquivos_da_serie(pasta, u"")])
    try:
        S.conjunto_da_serie(radai_thumbnail.bilhete(pasta, u""))
        sem = "abriu"
    except S.SemSerie as e:
        sem = str(e)
    except Exception as e:
        sem = type(e).__name__
    checar("bilhete sem UID nao abre o conjunto de outra serie da pasta",
           sem == u"sem UID", sem)
    shutil.rmtree(base, ignore_errors=True)


def _cranio_vascular():
    import numpy as np
    import SimpleITK as sitk
    forma = (60, 90, 90)
    z, y, x = np.indices(forma).astype(np.float64)
    r = np.sqrt((y - 45.0) ** 2 + (x - 45.0) ** 2)
    a = np.full(forma, -1000, np.int16)
    a[r < 34] = 40
    casca = (r >= 30) & (r < 34)
    a[casca] = 1200
    junto = (y - 45.0) ** 2 + (x - 72.0) ** 2 <= 1.5 ** 2
    a[junto] = 350
    calcificado = (y - 45.0) ** 2 + (x - 30.0) ** 2 <= 3.5 ** 2
    a[calcificado] = 900
    img = sitk.GetImageFromArray(a)
    img.SetSpacing((1.0, 1.0, 1.0))
    return img, casca, junto, calcificado


def teste_o_vascular_tira_o_osso_pela_segmentacao():
    secao("o Vascular tira o osso pela segmentacao do ContourLab, e o limiar so como recuo")
    import numpy as np
    import SimpleITK as sitk
    import radai_nidus as N
    import radai_nidus_screen as NS
    import radai_rotulos
    import radai_thumbnail
    import radai_recon3d_vascular as V
    img, casca, junto, calcificado = _cranio_vascular()
    uid = u"1.2.826.0.1.3680043.8.498.77665544"
    base = tempfile.mkdtemp(prefix="r3d_vasc_")
    try:
        mapa = os.path.join(base, "mapa")
        os.makedirs(mapa)
        radai_rotulos.gravar(mapa, uid, {"total": {
            "skull": casca, "common_carotid_artery_left": junto}}, ref=img)
        s = N.abrir(img, "CT")
        modo = V.ler_osso(s, mapa, uid)
        vol = sitk.GetArrayFromImage(V.volume_da_projecao(s, com_osso=False))
        fundo = s.escala["min"]
        checar("com a segmentacao, o osso sai por ela e a tela sabe de onde",
               modo == "segmentacao" and V.modo_do_osso(s) == "segmentacao"
               and bool(s.osso_fonte), (modo, s.osso_fonte))
        checar("  a calota sai inteira (vira o fundo da serie)",
               bool((vol[casca] == fundo).all()), int((vol[casca] != fundo).sum()))
        checar("  o vaso calcificado (900 HU, maior que 2 cm3) fica, valor a valor",
               bool((vol[calcificado] == 900).all()),
               int((vol[calcificado] != 900).sum()))
        checar("  o vaso a 1,5 mm do osso fica (a margem e de um voxel, e o vaso "
               "que o mapa nomeia nunca entra no osso)",
               bool((vol[junto] == 350).all()), int((vol[junto] != 350).sum()))
        checar("  «mostrar o osso» devolve a imagem inteira",
               V.volume_da_projecao(s, com_osso=True) is s.img)
        s2 = N.abrir(img, "CT")
        vazio = os.path.join(base, "vazio")
        os.makedirs(vazio)
        modo2 = V.ler_osso(s2, vazio, uid)
        vol2 = sitk.GetArrayFromImage(V.volume_da_projecao(s2, com_osso=False))
        checar("sem segmentacao, o recuo e o limiar, e a tela e avisada (limiar)",
               modo2 == "limiar" and not s2.osso_fonte, modo2)
        checar("  (isca) o limiar apaga o vaso calcificado inteiro",
               bool((vol2[calcificado] != 900).all()),
               int((vol2[calcificado] == 900).sum()))
        checar("  (isca) e leva junto o vaso a menos de 2 mm do osso",
               bool((vol2[junto] != 350).any()), int((vol2[junto] != 350).sum()))
        checar("  o recuo ainda tira a calota",
               bool((vol2[casca] <= -1000).all()))
        rm = N.abrir(img, "MR")
        checar("RM sem segmentacao: o osso fica, e a tela diz por que",
               V.ler_osso(rm, vazio, uid) == "fica"
               and V.volume_da_projecao(rm, com_osso=False) is rm.img)
        rm2 = N.abrir(img, "MR")
        checar("RM com a segmentacao: o osso sai por ela",
               V.ler_osso(rm2, mapa, uid) == "segmentacao"
               and V.volume_da_projecao(rm2, com_osso=False) is not rm2.img)
        orig, linhas = NS.osso_da_segmentacao, []
        log0 = radai_thumbnail._log_da_estacao
        radai_thumbnail._JA_REGISTRADAS.clear()

        def _explode(*a, **k):
            raise IOError(u"Sem DICOM em \\\\servidor\\%s" % PACIENTE_COM_ESPACO)
        try:
            NS.osso_da_segmentacao = _explode
            radai_thumbnail._log_da_estacao = lambda: linhas.append
            s3 = N.abrir(img, "CT")
            modo3 = V.ler_osso(s3, mapa, uid)
        finally:
            NS.osso_da_segmentacao = orig
            radai_thumbnail._log_da_estacao = log0
        texto = u"\n".join(linhas)
        checar("a leitura do osso que falha cai no recuo declarado, e a causa vai ao log",
               modo3 == "limiar" and u"vascular, osso: falhou com OSError" in texto,
               (modo3, texto[:200]))
        checar("  sem o caminho do paciente no log", not _tem_paciente(texto), texto[:200])
        fonte, _c = _sem_prosa(_componentes.fonte("app/radai_recon3d_vascular.py"))
        checar("o osso sai pela mesma funcao do Nidus (sem copiar a regra)",
               "osso_da_segmentacao(" in fonte and "mascaras_da_serie" not in fonte)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _osso_no_tecido():
    import numpy as np
    import SimpleITK as sitk
    forma = (40, 60, 60)
    a = np.full(forma, 40, np.int16)
    a[:3, :3, :3] = -1000
    osso = np.zeros(forma, bool)
    osso[13:27, 23:37, 23:37] = True
    a[osso] = 1200
    img = sitk.GetImageFromArray(a)
    img.SetSpacing((1.0, 1.0, 1.0))
    return img, osso


def teste_o_vascular_so_tira_o_osso_no_mip():
    secao("o Vascular tira o osso so no MIP: no MinIP ele viraria buraco escuro")
    import numpy as np
    import radai_nidus as N
    import radai_recon3d_vascular as V
    img, osso = _osso_no_tecido()

    def _centro_minip(vol, s):
        plano, _i = N.projetar(vol, 0, 0, "minip", "angio", lado=128,
                               escala=s.escala)
        h, w = plano.shape
        return float(plano[h // 2 - 2:h // 2 + 3, w // 2 - 2:w // 2 + 3].min())

    lim = N.abrir(img, "CT")
    seg = N.abrir(img, "CT")
    seg.tirar_osso(osso, {"fonte": "fantoma"})
    checar("os dois modos que tiram osso estao no fantoma (limiar e segmentacao)",
           V.modo_do_osso(lim) == "limiar" and V.modo_do_osso(seg) == "segmentacao",
           (V.modo_do_osso(lim), V.modo_do_osso(seg)))
    for rot, s in (("limiar", lim), ("segmentacao", seg)):
        checar("  %s: no MIP o osso sai" % rot,
               V.volume_da_projecao(s, False, "mip") is not s.img)
        checar("  %s: no MinIP o volume e a imagem inteira, com o osso" % rot,
               V.volume_da_projecao(s, False, "minip") is s.img)
        c = _centro_minip(V.volume_da_projecao(s, False, "minip"), s)
        checar("  %s: o MinIP pelo meio do osso mostra o tecido em volta "
               "(40 HU), e nao um buraco" % rot, abs(c - 40.0) < 1.0, c)
        isca = _centro_minip(V.volume_da_projecao(s, False, "mip"), s)
        checar("  (isca) %s: com o volume do MIP, o MinIP abre o buraco escuro "
               "onde o osso estava (%.0f HU)" % (rot, isca),
               isca < -500.0, isca)
    checar("a chamada sem modo continua sendo a do MIP",
           V.volume_da_projecao(lim, False) is V.volume_da_projecao(lim, False, "mip"))


def _vx_no_node(js, passos, isca=None):
    import json
    nomes = ("vxUrl", "vxErro", "vxOsso", "vxEstado", "vxPintar")
    fns = [_funcao_js(js, n) for n in nomes]
    if not all(fns):
        return None, "faltam funcoes: %s" % [n for n, f in zip(nomes, fns) if not f]
    corpo = u"\n".join(fns)
    if isca:
        corpo = corpo.replace(isca[0], isca[1])
    prog = u"\n".join([
        u"var PASSOS = %s, ATUAL = null, PEDIDOS = [], TEXTOS = [];" % json.dumps(passos, ensure_ascii=False),
        u"function no(){ return {hidden: true, textContent: '', attrs: {},",
        u" setAttribute: function(k, v){ this.attrs[k] = String(v) },",
        u" getAttribute: function(k){ return this.attrs[k] == null ? null : this.attrs[k] },",
        u" removeAttribute: function(k){ delete this.attrs[k]; if(k === 'src') this._src = '' }} }",
        u"var IMG = no(); IMG._src = ''; IMG.style = {};",
        u"Object.defineProperty(IMG, 'src', {get: function(){ return this._src },",
        u" set: function(v){ var eu = this, r = ATUAL.img; eu._src = v;",
        u"  setTimeout(function(){ if(r === 'ok'){ if(eu.onload) eu.onload() } else if(eu.onerror) eu.onerror() }, 0) }});",
        u"var SPANS = ['segmentacao', 'limiar', 'fica'].map(function(m){ var s = no(); s.attrs['data-vx-osso'] = m; return s });",
        u"var OSSO = no(); OSSO.querySelectorAll = function(){ return SPANS };",
        u"var EL = {vx_img: IMG, vx_proj: no(), vx_erro: no(), vx_osso: OSSO, vx_osso_fonte: no(), vx_ang: no()};",
        u"function r3El(i){ return EL[i] || null }",
        u"var R3 = {b: 'b1'};",
        u"var window = {uiCarregando: function(){}, uiTexto: function(e, t){ TEXTOS.push(t); e.textContent = t }};",
        u"function uiCarregando(){}",
        u"function uiTexto(e, t){ window.uiTexto(e, t) }",
        u"function fetch(u){ PEDIDOS.push(u); var r = ATUAL.estado;",
        u" if(r === 'rejeita' || r == null) return Promise.reject(new TypeError('Failed to fetch'));",
        u" return Promise.resolve({json: function(){ return Promise.resolve(r) }}) }",
        u"var VX = {lao: 0, cra: 0, modo: 'mip', jan: 'angio', lado: 512, laje: 0, inv: false,",
        u" osso: false, zoom: 1, ux: 0, uy: 0, t: 0, pedido: 0, erro: false, osso_b: null};",
        u"var VX_NAO_RESPONDEU = 'O app não respondeu.';",
        corpo,
        u"var FOTOS = [];",
        u"function foto(){ return {erro: EL.vx_erro.hidden ? null : EL.vx_erro.textContent,",
        u" src: IMG.src || '', modo: OSSO.getAttribute('data-modo'), pedidos: PEDIDOS.length,",
        u" escondida: IMG.style.visibility === 'hidden',",
        u" vistos: SPANS.filter(function(s){ return !s.hidden }).map(function(s){ return s.attrs['data-vx-osso'] }),",
        u" fonte: EL.vx_osso_fonte.textContent} }",
        u"function passo(){ if(!PASSOS.length){ console.log('JSON:' + JSON.stringify({fotos: FOTOS, textos: TEXTOS})); return }",
        u" ATUAL = PASSOS.shift(); if(ATUAL.b) R3.b = ATUAL.b;",
        u" vxPintar(false); setTimeout(function(){ FOTOS.push(foto()); passo() }, 30) }",
        u"passo();",
    ])
    return _rodar_js(prog, prefixo="r3d_vx_")


def teste_o_vascular_responde_o_motivo():
    secao("o Vascular responde o motivo em JSON, no lugar do 404 seco, e a tela o mostra")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception as e:
        checar("fastapi e o TestClient disponiveis", False,
               "PULADO: %s" % type(e).__name__)
        return
    import json
    from datetime import datetime
    import numpy as np
    sys.path.insert(0, AQUI)
    import make_test_series
    import radai_nidus as N
    import radai_rotulos
    import radai_thumbnail
    import radai_recon3d_vascular as V
    app = FastAPI()
    V.montar(app)
    cli = TestClient(app)
    morto = cli.get("/api/recon3d/vascular/projecao", params={"b": "morto"})
    checar("bilhete morto: 404 com o motivo em JSON, e nao o corpo vazio",
           morto.status_code == 404 and morto.content
           and morto.json() == {"erro": V.FORA_DA_LISTA}, morto.content[:120])
    em = cli.get("/api/recon3d/vascular/estado", params={"b": "morto"})
    checar("  e o estado do bilhete morto diz o mesmo",
           em.status_code == 404 and em.json() == {"erro": V.FORA_DA_LISTA}, em.content[:120])
    base = tempfile.mkdtemp(prefix="r3d_vasc_rota_")
    V._ABERTA.update({"chave": None, "serie": None})
    V._FALHAS.clear()
    try:
        pasta = os.path.join(base, PACIENTE_COM_ESPACO, "CT")
        uid = make_test_series.escreve_serie(pasta, "PAC_VASC", datetime.now(), 24)
        b = radai_thumbnail.bilhete(pasta, uid)
        r = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
        e = cli.get("/api/recon3d/vascular/estado", params={"b": b})
        checar("sem segmentacao: a projecao sai em PNG e o estado diz o recuo (limiar)",
               r.status_code == 200 and r.headers.get("content-type") == "image/png"
               and e.status_code == 200
               and e.json() == {"osso": {"modo": "limiar", "fonte": ""}}, e.content[:160])
        cranio = np.zeros((24, 128, 128), dtype=bool)
        cranio[:, 20:30, 20:108] = True
        radai_rotulos.gravar(pasta, uid, {"total": {"skull": cranio}},
                             ref=V.serie(b).img)
        V._ABERTA.update({"chave": None, "serie": None})
        r2 = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
        e2 = cli.get("/api/recon3d/vascular/estado", params={"b": b}).json()
        checar("com o mapa do ContourLab: o estado diz segmentacao, e de qual conjunto",
               r2.status_code == 200 and (e2.get("osso") or {}).get("modo") == "segmentacao"
               and (e2.get("osso") or {}).get("fonte"), str(e2))
        checar("  e nenhum caminho do paciente no estado", not _tem_paciente(json.dumps(e2)))
        orig, linhas = N.projetar, []
        log0 = radai_thumbnail._log_da_estacao
        radai_thumbnail._JA_REGISTRADAS.clear()

        def _explode(*a, **k):
            raise ValueError(u"Sem DICOM em C:\\%s\\CT" % PACIENTE_COM_ESPACO)

        def _recusa(*a, **k):
            raise N.SerieRecusada(N.RECUSA_POUCOS_CORTES % 1)
        try:
            radai_thumbnail._log_da_estacao = lambda: linhas.append
            N.projetar = _explode
            r3 = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
            e3 = cli.get("/api/recon3d/vascular/estado", params={"b": b})
            N.projetar = _recusa
            r4 = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
        finally:
            N.projetar = orig
            radai_thumbnail._log_da_estacao = log0
        d3 = r3.json() if r3.headers.get("content-type", "").startswith("application/json") else {}
        checar("a projecao que falha: 500 com a frase FIXA e o tipo a parte",
               r3.status_code == 500 and d3.get("erro") == V.PROJECAO_FALHOU
               and d3.get("tipo") == "ValueError", r3.content[:200])
        checar("  e o estado devolve a mesma falha, sem reabrir a serie (a tela a le dali)",
               e3.status_code == 500 and e3.json() == d3, e3.content[:200])
        checar("  sem o caminho do paciente na resposta", not _tem_paciente(r3.text), r3.text[:200])
        checar("  e a causa vai ao log da estacao, sem o caminho",
               u"reconstrucoes 3D, vascular: falhou com ValueError" in u"\n".join(linhas)
               and not _tem_paciente(u"\n".join(linhas)), u"\n".join(linhas)[:200])
        checar("a serie recusada pelo Nidus: 422 com a frase da recusa",
               r4.status_code == 422
               and r4.json().get("erro") == N.RECUSA_POUCOS_CORTES % 1, r4.content[:200])
        r5 = cli.get("/api/recon3d/vascular/projecao", params={"b": b, "lado": 256})
        e5 = cli.get("/api/recon3d/vascular/estado", params={"b": b}).json()
        checar("  e a projecao que volta a sair apaga a falha lembrada",
               r5.status_code == 200 and "osso" in e5, str(e5)[:160])
    finally:
        V._ABERTA.update({"chave": None, "serie": None})
        V._FALHAS.clear()
        shutil.rmtree(base, ignore_errors=True)
    js = V.pagina()
    passos = [
        {"img": "erro", "estado": {"erro": V.PROJECAO_FALHOU, "tipo": "ValueError"}},
        {"img": "ok", "estado": {"osso": {"modo": "limiar", "fonte": ""}}},
        {"b": "b2", "img": "ok", "estado": {"osso": {"modo": "segmentacao", "fonte": "Estudo 3D"}}},
        {"img": "erro", "estado": {"erro": V.FORA_DA_LISTA}},
        {"img": "erro", "estado": "rejeita"},
        {"img": "ok", "estado": {"osso": {"modo": "segmentacao", "fonte": "Estudo 3D"}}},
        {"img": "ok", "estado": None}]
    d, erro = _vx_no_node(js, [dict(x) for x in passos])
    if d is None:
        checar("vxPintar executa no node", False, erro)
        return
    f = d.get("fotos") or []
    if len(f) != 7:
        checar("vxPintar fez os sete passos", False, str(d)[:300])
        return
    checar("a tela mostra o motivo da falha, pelo uiTexto (a frase se traduz)",
           f[0]["erro"] == V.PROJECAO_FALHOU and not f[0]["src"]
           and V.PROJECAO_FALHOU in d.get("textos", []), str(f[:1]))
    checar("  a projecao que volta apaga o motivo e diz o recuo do limiar",
           f[1]["erro"] is None and f[1]["src"] and f[1]["modo"] == "limiar"
           and f[1]["vistos"] == ["limiar"], str(f[1:2]))
    checar("  outra serie: a segmentacao, com o conjunto de onde o osso saiu",
           f[2]["modo"] == "segmentacao" and f[2]["vistos"] == ["segmentacao"]
           and f[2]["fonte"] == "Estudo 3D", str(f[2:3]))
    checar("  o bilhete morto diz para recarregar a lista, sem a imagem quebrada "
           "nem a linha do osso da serie anterior",
           f[3]["erro"] == V.FORA_DA_LISTA and not f[3]["src"] and f[3]["escondida"]
           and f[3]["modo"] is None and f[2]["escondida"] is False, str(f[2:4]))
    checar("  e o servidor que nao responde diz que o app nao respondeu",
           f[4]["erro"] == V.NAO_RESPONDEU, str(f[4:5]))
    checar("  a barra que arrasta nao pergunta o estado a cada projecao (so depois de "
           "falha ou serie nova)", f[6]["pedidos"] == f[5]["pedidos"] and f[6]["erro"] is None,
           str(f[5:]))
    di, _e = _vx_no_node(js, [dict(passos[0])],
                         isca=(u"vxErro((d && d.erro) || VX_NAO_RESPONDEU);", u""))
    checar("  (isca) sem mostrar o motivo, a tela ficaria muda e a checagem reprova",
           di is not None and (di.get("fotos") or [{}])[0].get("erro") is None, str(di)[:160])
    pag = V.pagina()
    checar("a pagina tem as tres frases do osso e o lugar do motivo",
           u'id="vx_erro" role="alert" hidden' in pag
           and all(x in pag for x in (V.OSSO_PELA_SEGMENTACAO, V.OSSO_PELO_LIMIAR, V.OSSO_FICA))
           and u'"O app não respondeu."' in pag)


def teste_os_mpr_trazem_os_contornos_nos_tres_planos():
    secao("os contornos nos tres planos, com furos e geometria da serie")
    import json
    import numpy as np
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import radai_recon3d_screen as S
    import radai_thumbnail
    forma = (5, 9, 11)
    esp = (3.0, 2.0, 1.0)
    origem = (40.0, -30.0, 100.0)
    direcao = (0, 0, 1, 0, 1, 0, -1, 0, 0)
    d = np.asarray(direcao).reshape(3, 3)
    plano = np.asarray(((0, 1, 0), (0, 0, 1), (1, 0, 0)))
    polis = []
    for z in (1, 2, 3):
        for xy in (((1.5, 1.5), (7.5, 1.5), (7.5, 6.5), (1.5, 6.5)),
                   ((3.5, 3.5), (5.5, 3.5), (5.5, 4.5), (3.5, 4.5))):
            idx = np.asarray([[x, y, z] for x, y in xy])
            lps = origem + (idx * esp[::-1]).dot(d.T)
            polis.append(lps.dot(plano.T))
    roi = {"nome": "Teste_ai", "cor": [220, 40, 60]}
    conjunto = {"rois": [roi], "contornos": {"Teste_ai": polis}, "plano": plano}
    cortes = S._cortes_para_mpr(conjunto, esp, origem, direcao)
    checar("a geometria sagital retorna aos indices da imagem",
           sorted(cortes["Teste_ai"]) == [1, 2, 3])
    vol = np.zeros(forma, dtype=bool)
    vol[1:4, 2:7, 2:8] = True
    vol[1:4, 4, 4:6] = False
    for eixo, indice in ((0, 2), (1, 4), (2, 5)):
        esperado = np.take(vol, indice, axis=eixo)
        obtido = S._mascara_do_plano(cortes["Teste_ai"], forma, eixo, indice)
        checar("plano %d preserva a estrutura e o furo" % eixo,
               np.array_equal(obtido, esperado))
    checar("a conversao dos pontos e reutilizada nos proximos planos",
           S._cortes_para_mpr(conjunto, esp, origem, direcao) is cortes)
    mapa = SimpleNamespace(_vol={"a": vol.astype(np.uint8)},
                           tabela=[{"nome": "Teste_ai", "chave": "a", "indice": 1}])
    rotulos = {"tipo": "rotulos", "mapa": mapa, "rois": [roi],
               "esp_zyx": esp, "origem": origem, "direcao": direcao}
    for eixo, indice in ((0, 2), (1, 4), (2, 5)):
        planos = list(S._segmentacoes_do_plano(rotulos, forma, esp, origem,
                                              direcao, eixo, indice, None))
        checar("mapa de rotulos no plano %d, sem criar mascara 3D" % eixo,
               len(planos) == 1 and np.array_equal(planos[0][1],
                                                  np.take(vol, indice, axis=eixo)))
    app = FastAPI()
    S.montar(app)
    b = radai_thumbnail.bilhete("fantoma_mpr", "1.2.3.456")
    anteriores = S._snapshot_do_volume, S.conjunto_da_serie
    try:
        S._snapshot_do_volume = lambda *_: (np.zeros(forma, dtype=np.int16),
                esp, ("sup", "post", "esq"), origem, direcao)
        S.conjunto_da_serie = lambda *_: (conjunto, "teste", [], ())
        cli = TestClient(app)
        for eixo in (0, 1, 2):
            r = cli.get("/api/recon3d/projecao", params={
                "b": b, "eixo": eixo, "laje": 0, "segmentacao": True})
            checar("a imagem do plano %d inclui contorno colorido" % eixo,
                   r.status_code == 200 and "image/svg+xml" in r.headers.get("content-type", "")
                   and '<path d="' in r.text and 'rgb(220,40,60)' in r.text
                   and "data:image/png;base64," in r.text)
        r = cli.get("/api/recon3d/projecao", params={
            "b": b, "laje": 0, "segmentacao": True, "nomes": json.dumps([])})
        checar("desligar todas tambem oculta os contornos nos planos",
               r.status_code == 200 and "<path " not in r.text)
        for modo in ("mip", "minip"):
            r = cli.get("/api/recon3d/projecao", params={
                "b": b, "laje": 10, "modo": modo, "segmentacao": True})
            checar("%s continua sem sobrepor segmentacao" % modo,
                   r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n")
    finally:
        S._snapshot_do_volume, S.conjunto_da_serie = anteriores


def teste_o_volume_e_a_geometria_sao_da_mesma_serie():
    secao("troca concorrente de serie nao mistura imagem e geometria")
    import threading
    import numpy as np
    import SimpleITK as sitk
    import engine
    import radai_recon3d_screen as S
    import radai_thumbnail
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    imagens = {}
    for uid, valor, esp, origem, direcao in (
            ("A", 40, (1, 2, 3), (1, 2, 3), (1, 0, 0, 0, 1, 0, 0, 0, 1)),
            ("B", 900, (2, 3, 4), (101, 202, 303), (0, 0, 1, 0, 1, 0, -1, 0, 0))):
        img = sitk.GetImageFromArray(np.full((3, 7, 9), valor, dtype=np.int16))
        img.SetSpacing(tuple(float(x) for x in esp))
        img.SetOrigin(tuple(float(x) for x in origem))
        img.SetDirection(tuple(float(x) for x in direcao))
        imagens[uid] = img

    def com_troca(operacao, quente=False):
        trocar, terminou, parar = (threading.Event() for _ in range(3))
        dono, erros, trocas = [], [], []
        original = engine.load_sitk, S._TRAVA_VOL, S._armar_relogio
        cache = dict(S._VOL)

        def ler(_pasta, uid):
            if uid == "A":
                dono[:] = [threading.get_ident()]
            return imagens[uid]

        class TravaComTroca:
            def __enter__(self):
                original[1].acquire()
                if not dono and threading.current_thread() is not t:
                    dono[:] = [threading.get_ident()]

            def __exit__(self, *_):
                chave = S._VOL.get("chave") or ()
                agir = (dono == [threading.get_ident()]
                        and len(chave) == 2 and chave[1] == "A")
                original[1].release()
                if agir:
                    terminou.clear()
                    trocar.set()
                    if not terminou.wait(5):
                        raise RuntimeError("a troca sintetica nao terminou")

        def segunda_serie():
            while trocar.wait(5):
                trocar.clear()
                if parar.is_set():
                    return
                try:
                    S._volume("fantoma_concorrente_B", "B")
                    trocas.append(True)
                except Exception as e:
                    erros.append(type(e).__name__)
                finally:
                    terminou.set()

        t = threading.Thread(target=segunda_serie, daemon=True)
        try:
            engine.load_sitk = ler
            S._armar_relogio = lambda *_: None
            S._esquecer_serie()
            if quente:
                S._volume("fantoma_concorrente_A", "A")
                dono[:] = []
            S._TRAVA_VOL = TravaComTroca()
            t.start()
            resultado = operacao()
            return resultado, bool(trocas) and not erros
        finally:
            parar.set()
            trocar.set()
            t.join(5)
            engine.load_sitk, S._TRAVA_VOL, S._armar_relogio = original
            with S._TRAVA_VOL:
                S._VOL.clear()
                S._VOL.update(cache)

    (v, esp, origem, direcao), alternou = com_troca(
        lambda: S._volume_lps("fantoma_concorrente_A", "A"))
    checar("outra thread substituiu o cache antes do retorno de A", alternou)
    checar("o volume LPS retido continua inteiramente da serie A",
           bool((v == 40).all()) and esp == (3, 2, 1)
           and origem == (1, 2, 3) and direcao == imagens["A"].GetDirection())
    (v, esp, origem, direcao), alternou = com_troca(
        lambda: S._volume_lps("fantoma_concorrente_A", "A"), quente=True)
    checar("a leitura do cache tambem retém toda a geometria de A",
           alternou and bool((v == 40).all()) and esp == (3, 2, 1)
           and origem == (1, 2, 3) and direcao == imagens["A"].GetDirection())
    tripla, alternou = com_troca(lambda: S._volume("fantoma_concorrente_A", "A"))
    checar("a API _volume mantem tres valores da mesma serie",
           alternou and len(tripla) == 3 and bool((tripla[0] == 40).all())
           and tripla[1] == (3, 2, 1) and tripla[2] == ("sup", "post", "esq"))
    app = FastAPI()
    S.montar(app)
    b = radai_thumbnail.bilhete("fantoma_concorrente_A", "A")
    pontos = np.asarray([[2, 2, 1], [5, 2, 1], [5, 5, 1], [2, 5, 1]])
    lps = pontos * (1, 2, 3) + (1, 2, 3)
    conjunto = {"rois": [{"nome": "Teste_ai", "cor": [20, 80, 180]}],
                "contornos": {"Teste_ai": [lps]}, "plano": None}
    anteriores = S.conjunto_da_serie, S._png_com_contornos
    geometrias = []

    def sobrepor(png, c, forma, esp, origem, direcao, sentido, eixo, indice, nomes):
        geometrias.append((esp, origem, direcao, sentido))
        return anteriores[1](png, c, forma, esp, origem, direcao,
                             sentido, eixo, indice, nomes)
    try:
        S.conjunto_da_serie = lambda *_: (conjunto, "teste", [], ())
        S._png_com_contornos = sobrepor
        with TestClient(app) as cli:
            r, alternou = com_troca(lambda: cli.get(
                "/api/recon3d/projecao", params={"b": b, "eixo": 0,
                                               "pos": 0.5, "laje": 0,
                                               "segmentacao": True}))
        checar("a rota MPR conserva a geometria do PNG apesar da troca",
               alternou and geometrias == [((3, 2, 1), (1, 2, 3),
                    imagens["A"].GetDirection(), ("sup", "post", "esq"))])
        checar("o contorno de A continua no plano de A depois da troca",
               r.status_code == 200 and "<path " in r.text
               and "rgb(20,80,180)" in r.text)
    finally:
        S.conjunto_da_serie, S._png_com_contornos = anteriores


def main():
    print("test_recon3d | projecao, janela, e a fronteira")
    try:
        import numpy
    except Exception:
        print("  numpy ausente — a bateria nao roda aqui")
        print("\n" + "=" * 64)
        print("OK: 0 checagens (runtime sem numpy)")
        print("=" * 64)
        return 0
    testes = [teste_mip_e_minip_sao_max_e_min,
              teste_o_vascular_so_tira_o_osso_no_mip,
              teste_a_laje_nao_estoura_o_volume,
              teste_png_sem_pil,
              teste_serie_sem_contorno_manda_para_o_auto_contorno,
              teste_o_modulo_nao_exporta,
              teste_a_tela_tambem_nao_exporta,
              teste_a_serie_vem_de_uma_lista,
              teste_a_escolha_da_serie_e_o_popup_da_casca,
              teste_os_quatro_quadros,
              teste_os_tres_cartoes_navegam,
              teste_nao_ha_deteccao,
              teste_o_3d_de_osso_e_pele,
              teste_a_nuvem_no_recorte_e_a_mesma,
              teste_a_pele_nao_sai_em_listras,
              teste_varias_estruturas_num_referencial_so,
              teste_a_serie_e_lida_uma_vez,
              teste_a_serie_sai_da_memoria_quando_ninguem_olha,
              teste_o_erro_do_3d_vai_para_o_log_e_nao_para_a_tela,
              teste_a_serie_que_nao_abre_nao_leva_o_caminho_a_tela,
              teste_a_rota_do_3d,
              teste_a_tela_renderizada_nao_exporta,
              teste_o_quadro_3d_esta_na_tela,
              teste_as_telas_que_listam_conjuntos_reconhecem_os_plugins,
              teste_a_malha_da_estrutura_fecha,
              teste_a_grade_cabe_no_teto_e_a_estimativa_vale,
              teste_a_pele_sai_so_pela_face_de_fora,
              teste_o_stl_e_valido_e_de_visualizacao,
              teste_a_tela_le_o_stl,
              teste_a_rota_da_malha,
              teste_a_serie_do_acervo_abre_com_o_prefixo_do_vigia,
              teste_a_pasta_com_ponto_no_fim_abre_pelo_prefixo,
              teste_as_malhas_saem_com_a_serie,
              teste_o_recuo_e_detectado_e_nao_presumido,
              teste_a_transparencia_desenha_na_ordem,
              teste_o_visor_e_um_so_com_o_nidus,
              teste_o_visor_3d_herda_do_nidus,
              teste_o_cartao_do_modulo_navega,
              teste_a_barra_e_a_bussola_falam_a_lingua_da_tela,
              teste_os_planos_saem_na_proporcao_fisica,
              teste_a_leitura_sem_uid_saiu,
              teste_o_rtstruct_fora_do_axial_vira_malha,
              teste_o_nome_proprio_decide_pelo_nome_padrao,
              teste_o_vascular_tira_o_osso_pela_segmentacao,
              teste_o_vascular_responde_o_motivo,
              teste_os_mpr_trazem_os_contornos_nos_tres_planos,
              teste_o_volume_e_a_geometria_sao_da_mesma_serie]
    todos = set(k for k, v in globals().items()
                if k.startswith("teste_") and callable(v))
    fora = sorted(todos - set(f.__name__ for f in testes))
    checar("todo teste do arquivo esta na lista do main()", not fora,
           ", ".join(fora))
    for t in testes:
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [(n, d) for n, ok, d in _RESULTADOS if not ok]
    print("\n" + "=" * 64)
    if falhas:
        print("FALHOU: %d de %d checagens" % (len(falhas), len(_RESULTADOS)))
        for n, d in falhas:
            print("  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print("OK: %d checagens, todas passaram" % len(_RESULTADOS))
    print("=" * 64)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
