# -*- coding: utf-8 -*-
import json
import threading
import time
from collections import OrderedDict

import radai_menu
import radai_web

SOLTAR_APOS_S = 600.0
LADOS = (256, 512, 768, 1024)
EPONIMOS = (u"AP", u"Towne", u"Caldwell")
JANELAS = ((u"angio", u"angio"), (u"vaso_fino", u"vaso fino"),
           (u"osso", u"osso"), (u"parenquima", u"parênquima"))
# GUARDA: abaixo de 700 HU o limiar leva junto o vaso contrastado.
OSSO_HU = 700.0
OSSO_MIN_CM3 = 2.0
OSSO_MARGEM_MM = 2.0
OSSO_E_O_VASO = (u"Pela segmentação do ContourLab sai só o osso, com um voxel de "
                 u"margem. Sem ela, o limiar de 700 HU leva junto o vaso "
                 u"calcificado e o vaso a menos de 2 mm do osso — no canal "
                 u"carotídeo, no forame transverso; «mostrar o osso» devolve "
                 u"tudo.")
OSSO_PELA_SEGMENTACAO = (u"O osso sai pela segmentação do ContourLab desta "
                         u"série, com um voxel de margem: o vaso calcificado "
                         u"fica na projeção.")
OSSO_PELO_LIMIAR = (u"Esta série não tem segmentação do ContourLab com osso: "
                    u"o osso sai pelo limiar de 700 HU, que leva junto o vaso "
                    u"calcificado e o vaso a menos de 2 mm do osso. Segmente "
                    u"a série pelo «Rodar agora» para o osso sair pela "
                    u"segmentação.")
OSSO_FICA = (u"Esta série não tem segmentação do ContourLab com osso, e sem "
             u"HU não há limiar que o separe: o osso fica na projeção.")
FORA_DA_LISTA = u"recarregue a lista de séries"
PROJECAO_FALHOU = (u"não consegui projetar esta série: a causa foi escrita no "
                   u"log da estação")
NAO_RESPONDEU = u"O app não respondeu."
MODOS_DO_OSSO = (u"segmentacao", u"limiar", u"fica")

_ABERTA = {"chave": None, "serie": None, "visto": 0.0, "relogio": None}
_TRAVA = threading.Lock()
_FALHAS = OrderedDict()
_TRAVA_FALHAS = threading.Lock()


def _soltar_se_ociosa():
    with _TRAVA:
        _ABERTA["relogio"] = None
        if _ABERTA["serie"] is None:
            return
        ocioso = time.time() - _ABERTA["visto"]
        if ocioso >= SOLTAR_APOS_S:
            _ABERTA.update({"chave": None, "serie": None})
            return
        _armar(SOLTAR_APOS_S - ocioso)


def _armar(s):
    if _ABERTA["relogio"] is not None:
        return
    r = threading.Timer(max(1.0, float(s)), _soltar_se_ociosa)
    r.daemon = True
    _ABERTA["relogio"] = r
    r.start()


def serie(b):
    import radai_thumbnail
    pasta, uid = radai_thumbnail.resolver(b)
    if not pasta:
        return None
    chave = (pasta, uid or u"")
    with _TRAVA:
        if _ABERTA["chave"] == chave and _ABERTA["serie"] is not None:
            _ABERTA["visto"] = time.time()
            return _ABERTA["serie"]
        _ABERTA.update({"chave": None, "serie": None})
        import engine
        import radai_projection as N
        img = engine.load_sitk(pasta, uid or None)
        mod = u""
        try:
            mod = str((radai_thumbnail.serie_do_bilhete(b) or {})
                      .get("modalidade") or u"").upper()
        except Exception:
            mod = u""
        s = N.abrir(img, mod or None)
        s.sem_osso = None
        ler_osso(s, pasta, uid or u"", bilhete=b)
        _ABERTA.update({"chave": chave, "serie": s, "visto": time.time()})
        _armar(SOLTAR_APOS_S)
        return s


def ler_osso(s, pasta, uid, bilhete=u""):
    s.osso_fonte = u""
    try:
        import radai_projection_bone as NS
        m, info = NS.osso_da_segmentacao(s, pasta, uid)
        if m is not None and s.tirar_osso(m, info):
            s.osso_fonte = str((info or {}).get("fonte") or u"")
    except Exception as e:
        s.osso = None
        try:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"reconstrucoes 3D, vascular, osso",
                                            e, bilhete=bilhete)
        except Exception:
            pass
    return modo_do_osso(s)


def modo_do_osso(s):
    if getattr(s, "osso", None) is not None:
        return MODOS_DO_OSSO[0]
    if s.escala.get("hu", True):
        return MODOS_DO_OSSO[1]
    return MODOS_DO_OSSO[2]


def retirar_osso(img, fundo=None):
    import SimpleITK as sitk
    esp = img.GetSpacing()
    vox_mm3 = float(esp[0] * esp[1] * esp[2]) or 1.0
    m = sitk.Cast(img >= OSSO_HU, sitk.sitkUInt8)
    m = sitk.RelabelComponent(sitk.ConnectedComponent(m),
                              minimumObjectSize=int(OSSO_MIN_CM3 * 1000.0
                                                    / vox_mm3)) > 0
    m = sitk.BinaryDilate(m, [max(1, int(round(OSSO_MARGEM_MM / e)))
                              for e in esp])
    if fundo is None:
        f = sitk.MinimumMaximumImageFilter()
        f.Execute(img)
        fundo = f.GetMinimum()
    return sitk.Mask(img, m == 0, outsideValue=fundo)


def volume_da_projecao(s, com_osso=False, modo="mip"):
    # GUARDA: o osso so sai no MIP; no MinIP o valor que o apaga viraria buraco escuro.
    if com_osso or modo != u"mip":
        return s.img
    if modo_do_osso(s) == MODOS_DO_OSSO[0]:
        return s.base(u"mip", True)
    if modo_do_osso(s) == MODOS_DO_OSSO[2]:
        return s.img
    if getattr(s, "sem_osso", None) is None:
        s.sem_osso = retirar_osso(s.img, s.escala.get("min"))
    return s.sem_osso


def projecao_png(b, lao=0.0, cra=0.0, modo="mip", janela="angio", lado=512,
                 laje=0.0, inverter=False, com_osso=False):
    import radai_projection as N
    import radai_recon3d as R
    s = serie(b)
    if s is None:
        return None
    lado = int(lado or N.LADO_PADRAO)
    if lado not in LADOS:
        lado = N.LADO_PADRAO
    modo = u"minip" if str(modo) == u"minip" else u"mip"
    janela = janela if janela in dict(JANELAS) else u"angio"
    plano, info = N.projetar(volume_da_projecao(s, com_osso, modo), float(lao), float(cra), modo, janela,
                             lado=lado, laje_mm=(float(laje) or None),
                             escala=s.escala)
    c, l = info["centro"], info["largura"]
    if inverter:
        return R.para_png(-plano, -c, l)
    return R.para_png(plano, c, l)


def _ajuda():
    import radai_projection as N
    return (u"A angiografia sintética projeta a própria imagem e não precisa "
            u"de segmentação; quando a série tem a do ContourLab, o osso sai "
            u"por ela.",
            N.LIMITACAO_CLINICA, N.LIMITACAO_RM)


AJUDA = _ajuda()

ALERTA = (u"Projeção sintética por tratamento de imagem &mdash; <b>não "
          u"substitui a angiografia digital</b>")

CSS = u"""
.vx-palco{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}
@media (max-width:980px){.vx-palco{grid-template-columns:minmax(0,1fr)}}
.vx-proj{position:relative;background:#000;border-radius:8px;overflow:hidden;
 height:min(72vh,680px);min-height:320px;display:flex;align-items:center;
 justify-content:center;cursor:grab;touch-action:none}
.vx-proj:active{cursor:grabbing}
.vx-proj img{width:100%;height:100%;object-fit:contain;user-select:none;transform-origin:center;
 transition:transform .12s ease-out}
.vx-cmd{display:flex;flex-direction:column;gap:14px;font-size:12px;color:var(--text-muted)}
.vx-g{display:flex;flex-direction:column;gap:7px}
.vx-g .r3-ferr-cab b{font-family:var(--mono);color:var(--text);letter-spacing:.02em}
.vx-g input[type=range]{width:100%;accent-color:var(--mod-recon)}
.vx-bts{display:flex;gap:5px;flex-wrap:wrap}
.vx-zoom{position:absolute;top:8px;right:8px;display:flex;gap:4px}
.vx-zoom button{width:26px;height:26px;padding:0;border-radius:6px;border:1px solid var(--line);
 background:var(--panel);color:var(--text-muted);cursor:pointer;font-family:var(--mono)}
.vx-zoom button:hover,.vx-zoom button:focus-visible{color:var(--text);border-color:var(--mod-recon);outline:none}
.vx-info{font-family:var(--mono);font-size:10.5px;color:var(--text-dim);margin:0}
.vx-osso{display:flex;gap:8px;align-items:flex-start;margin:0;font-size:11.5px;
 line-height:1.5;color:var(--text-muted)}
.vx-osso:not([data-modo]){display:none}
.vx-osso::before{content:"";width:7px;height:7px;border-radius:50%;flex:0 0 auto;
 margin-top:5px;background:var(--aviso)}
.vx-osso[data-modo="segmentacao"]::before{background:var(--ok)}
.vx-osso code{font-family:var(--mono);font-size:10.5px;color:var(--text)}
.vx-erro{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
 width:max-content;max-width:min(80%,440px);margin:0;padding:10px 14px;border-radius:8px;
 background:rgba(0,0,0,.6);color:var(--img-texto);font-size:12.5px;line-height:1.5;
 text-align:center}
.vx-erro[hidden]{display:none}
"""

JS = u"""
var VX = {lao: 0, cra: 0, modo: 'mip', jan: 'angio', lado: 512, laje: 0, inv: false, osso: false,
          zoom: 1, ux: 0, uy: 0, t: 0, pedido: 0, erro: false, osso_b: null};
var VX_NAO_RESPONDEU = @NAO_RESPONDEU@;
function vxErro(frase){
 var e = r3El('vx_erro'); if(!e) return;
 VX.erro = !!frase;
 if(!frase){ e.hidden = true; e.textContent = ''; return }
 if(window.uiTexto) uiTexto(e, frase); else e.textContent = frase;
 e.hidden = false;
}
function vxOsso(modo, fonte){
 var p = r3El('vx_osso'); if(!p) return;
 if(!modo){ p.removeAttribute('data-modo'); return }
 p.setAttribute('data-modo', modo);
 Array.prototype.forEach.call(p.querySelectorAll('[data-vx-osso]'), function(s){
  s.hidden = s.getAttribute('data-vx-osso') !== modo });
 var f = r3El('vx_osso_fonte'); if(f) f.textContent = fonte || '';
}
function vxEstado(meu){
 var b = R3.b;
 fetch('/api/recon3d/vascular/estado?b=' + encodeURIComponent(b))
  .then(function(r){ return r.json().catch(function(){ return {} }) })
  .then(function(d){
   if(meu !== VX.pedido || b !== R3.b) return;
   if(d && d.osso){ vxErro(''); vxOsso(d.osso.modo, d.osso.fonte); VX.osso_b = b; return }
   vxOsso(''); VX.osso_b = null;
   vxErro((d && d.erro) || VX_NAO_RESPONDEU);
  })
  .catch(function(){
   if(meu !== VX.pedido) return;
   vxOsso(''); VX.osso_b = null; vxErro(VX_NAO_RESPONDEU) });
}
function vxUrl(lado){
 return '/api/recon3d/vascular/projecao?b=' + encodeURIComponent(R3.b)
  + '&lao=' + VX.lao + '&cra=' + VX.cra + '&modo=' + VX.modo + '&janela=' + VX.jan
  + '&lado=' + lado + '&laje=' + VX.laje + '&inverter=' + (VX.inv ? 1 : 0)
  + '&osso=' + (VX.osso ? 1 : 0);
}
function vxPintar(rapido){
 if(!R3.b) return;
 var img = r3El('vx_img'), cx = r3El('vx_proj'); if(!img) return;
 clearTimeout(VX.t);
 var meu = ++VX.pedido;
 if(VX.osso_b !== R3.b) vxOsso('');
 function apaga(){ if(window.uiCarregando) uiCarregando(cx, false) }
 function carrega(lado){
  if(window.uiCarregando && !rapido) uiCarregando(cx, true, 'projetando');
  img.onload = function(){
   if(meu !== VX.pedido) return;
   img.style.visibility = '';
   apaga();
   if(VX.erro || VX.osso_b !== R3.b) vxEstado(meu);
  };
  img.onerror = function(){
   img.removeAttribute('src'); img.style.visibility = 'hidden'; apaga();
   if(meu === VX.pedido) vxEstado(meu);
  };
  img.src = vxUrl(lado);
 }
 if(rapido){ carrega(256); VX.t = setTimeout(function(){ rapido = false; carrega(VX.lado) }, 450) }
 else carrega(VX.lado);
 var i = r3El('vx_ang');
 if(i) i.textContent = 'LAO/RAO ' + VX.lao + '° · CRA/CAU ' + VX.cra + '°';
}
function vxMarcar(){
 Array.prototype.forEach.call(document.querySelectorAll('[data-vx]'), function(b){
  var k = b.getAttribute('data-vx'), v = b.getAttribute('data-v'), on = false;
  if(k === 'modo') on = VX.modo === v;
  else if(k === 'jan') on = VX.jan === v;
  else if(k === 'lado') on = String(VX.lado) === v;
  else if(k === 'inv') on = VX.inv;
  else if(k === 'osso') on = VX.osso;
  b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false');
 });
 var l = r3El('vx_lao'), c = r3El('vx_cra');
 if(l) l.value = VX.lao; if(c) c.value = VX.cra;
 var lv = r3El('vx_lajev');
 if(lv){ if(window.uiTexto) uiTexto(lv, VX.laje ? VX.laje + ' mm' : 'todo o volume');
         else lv.textContent = VX.laje ? VX.laje + ' mm' : 'todo o volume' }
}
function vxAcao(b){
 var k = b.getAttribute('data-vx'), v = b.getAttribute('data-v');
 if(k === 'modo') VX.modo = v;
 else if(k === 'jan') VX.jan = v;
 else if(k === 'lado') VX.lado = +v;
 else if(k === 'inv') VX.inv = !VX.inv;
 else if(k === 'osso') VX.osso = !VX.osso;
 else if(k === 'inc'){ var p = v.split(','); VX.lao = +p[0]; VX.cra = +p[1] }
 vxMarcar(); vxPintar(false);
}
function vxZoom(f){
 VX.zoom = f ? Math.max(1, Math.min(8, VX.zoom * f)) : 1;
 if(!f){ VX.ux = 0; VX.uy = 0 }
 if(VX.zoom === 1){ VX.ux = 0; VX.uy = 0 }
 var img = r3El('vx_img');
 if(img) img.style.transform = 'translate(' + VX.ux + 'px,' + VX.uy + 'px) scale(' + VX.zoom + ')';
}
function r3AoAbrir(d){ vxPintar(false) }
window.addEventListener('DOMContentLoaded', function(){
 var cmd = r3El('vx_cmd');
 if(cmd) cmd.addEventListener('click', function(e){
  var b = e.target.closest ? e.target.closest('[data-vx]') : null; if(b) vxAcao(b) });
 ['lao', 'cra'].forEach(function(k){
  var s = r3El('vx_' + k); if(!s) return;
  s.addEventListener('input', function(){ VX[k] = +s.value; vxPintar(true) });
 });
 var lj = r3El('vx_laje');
 if(lj) lj.addEventListener('input', function(){ VX.laje = +lj.value; vxMarcar(); vxPintar(true) });
 var cx = r3El('vx_proj');
 if(cx){
  cx.addEventListener('wheel', function(e){ e.preventDefault(); vxZoom(e.deltaY < 0 ? 1.15 : 0.87) }, {passive: false});
  var arr = false, ax = 0, ay = 0;
  cx.addEventListener('pointerdown', function(e){ if(VX.zoom <= 1) return; arr = true; ax = e.clientX; ay = e.clientY;
   try{ cx.setPointerCapture(e.pointerId) }catch(_){} });
  cx.addEventListener('pointermove', function(e){ if(!arr) return;
   VX.ux += e.clientX - ax; VX.uy += e.clientY - ay; ax = e.clientX; ay = e.clientY; vxZoom(1) });
  cx.addEventListener('pointerup', function(){ arr = false });
  cx.addEventListener('contextmenu', function(e){ e.preventDefault() });
 }
 vxMarcar();
});
"""


def _html_projecao():
    import radai_projection as N
    inc = u"".join(
        u'<button type="button" class="jan" data-vx="inc" data-v="%g,%g">'
        u'<span %s>%s</span></button>'
        % (lao, cra, u'data-radai-t="1" translate="no"'
           if nome in EPONIMOS else u"data-radai-frase", nome)
        for nome, lao, cra in N.INCIDENCIAS)
    jan = u"".join(
        u'<button type="button" class="jan" data-vx="jan" data-v="%s" '
        u'aria-pressed="false"><span data-radai-frase>%s</span></button>'
        % (k, rot) for k, rot in JANELAS)
    res = u"".join(
        u'<button type="button" class="jan" data-vx="lado" data-v="%d" '
        u'aria-pressed="false">%d</button>' % (n, n) for n in LADOS)
    return (
        u'<div class="vx-palco"><div class="vx-proj" id="vx_proj">'
        u'<img id="vx_img" alt="" draggable="false">'
        u'<p class="vx-erro" id="vx_erro" role="alert" hidden></p>'
        u'<span class="vx-zoom"><button type="button" onclick="vxZoom(1.25)" '
        u'aria-label="aproximar" title="aproximar">+</button>'
        u'<button type="button" onclick="vxZoom(0.8)" aria-label="afastar" '
        u'title="afastar">&minus;</button>'
        u'<button type="button" onclick="vxZoom(0)" aria-label="voltar ao '
        u'início" title="voltar ao início">&#8635;</button></span></div>'
        u'<div class="vx-cmd" id="vx_cmd">'
        u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
        u'incidência</span><b id="vx_ang"></b></div>'
        u'<div class="vx-bts">%s</div>'
        u'<label class="sub" for="vx_lao">LAO/RAO</label>'
        u'<input type="range" id="vx_lao" min="-90" max="90" value="0">'
        u'<label class="sub" for="vx_cra">CRA/CAU</label>'
        u'<input type="range" id="vx_cra" min="-90" max="90" value="0"></div>'
        u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
        u'projeção</span></div><div class="vx-bts">'
        u'<button type="button" class="jan" data-vx="modo" data-v="mip">MIP'
        u'</button><button type="button" class="jan" data-vx="modo" '
        u'data-v="minip">MinIP</button>'
        u'<button type="button" class="jan" data-vx="inv" data-v="1">'
        u'<span data-radai-frase>inverter cores</span></button>'
        u'<button type="button" class="jan" data-vx="osso" data-v="1" '
        u'aria-pressed="false"><span data-radai-frase>mostrar o osso</span>'
        u'</button><span class="ui-ajuda dir" id="vx_osso_aj" tabindex="0" '
        u'aria-label="ajuda">?<span class="ui-balao"><p data-radai-frase>%s</p>'
        u'</span></span></div>'
        u'<p class="vx-osso" id="vx_osso" aria-live="polite">'
        u'<span data-vx-osso="segmentacao" hidden><span data-radai-frase>%s'
        u'</span> <code id="vx_osso_fonte" translate="no"></code></span>'
        u'<span data-vx-osso="limiar" hidden data-radai-frase>%s</span>'
        u'<span data-vx-osso="fica" hidden data-radai-frase>%s</span></p>'
        u'<label class="sub" for="vx_laje"><span data-radai-frase>laje</span> '
        u'· <span id="vx_lajev" data-radai-frase>todo o volume</span></label>'
        u'<input type="range" id="vx_laje" min="0" max="120" value="0"></div>'
        u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
        u'janela</span></div><div class="vx-bts">%s</div></div>'
        u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
        u'resolução</span></div><div class="vx-bts">%s</div></div>'
        u'</div></div>' % (inc, OSSO_E_O_VASO, OSSO_PELA_SEGMENTACAO,
                           OSSO_PELO_LIMIAR, OSSO_FICA, jan, res))


def pagina():
    import radai_recon3d_screen as S
    import radai_ui
    import radai_viewer
    f = S.FERRAMENTAS_3D["vascular"]
    cab = radai_ui.cabeca_de_funcao(
        f["icone"], f["nome"], f["frase"],
        radai_ui.ajuda(*(AJUDA + S.AJUDA_EXPORTA)), u"recon3d")
    corpo = (cab + S._html_passo_serie()
             + radai_ui.passo(u"2", u"Angiografia sintética", _html_projecao(),
                              ident=u"vx_p2")
             + radai_ui.passo(u"3", u"Superfície dos vasos",
                              S.html_palco("vascular"), ident=u"vx_p3")
             + radai_ui.alerta(ALERTA))
    js = (radai_viewer.JS_3D + S.JS_MALHA + S.JS_GRAVAR + S.JS_SERIE
          + JS.replace(u"@NAO_RESPONDEU@",
                       json.dumps(NAO_RESPONDEU, ensure_ascii=False)))
    return (u'<!doctype html><html><head><meta charset="utf-8">'
            u'<title>Vascular &middot; Reconstru&ccedil;&otilde;es 3D</title>'
            u'<meta name="viewport" content="width=device-width,initial-scale=1">'
            u'<style>%s%s</style></head><body>'
            u'<div class="r3-wrap" data-ferramenta="vascular">%s</div>'
            u'<script>%s</script></body></html>' % (S.CSS, CSS, corpo, js))


def resposta_de_falha(e):
    import radai_projection as N
    if isinstance(e, N.SerieRecusada):
        return 422, {"erro": str(e)}
    return 500, {"erro": PROJECAO_FALHOU, "tipo": type(e).__name__}


def _lembrar_falha(b, falha):
    with _TRAVA_FALHAS:
        _FALHAS.pop(str(b or u""), None)
        if falha is not None:
            _FALHAS[str(b or u"")] = falha
            while len(_FALHAS) > 16:
                _FALHAS.popitem(last=False)


def estado_da_projecao(b):
    with _TRAVA_FALHAS:
        falha = _FALHAS.get(str(b or u""))
    if falha is not None:
        return falha
    try:
        s = serie(b)
    except Exception as e:
        import radai_thumbnail
        radai_thumbnail.registrar_falha(u"reconstrucoes 3D, vascular", e,
                                        bilhete=b)
        return resposta_de_falha(e)
    if s is None:
        return 404, {"erro": FORA_DA_LISTA}
    return 200, {"osso": {"modo": modo_do_osso(s),
                          "fonte": getattr(s, "osso_fonte", u"") or u""}}


def montar(app):
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    @app.get("/recon3d/vascular", response_class=HTMLResponse)
    def _tela():
        return radai_menu.aplicar(pagina(), "recon_vascular")

    @app.get("/api/recon3d/vascular/projecao")
    def _projecao(b: str = "", lao: float = 0.0, cra: float = 0.0,
                  modo: str = "mip", janela: str = "angio", lado: int = 512,
                  laje: float = 0.0, inverter: int = 0, osso: int = 0):
        try:
            png = projecao_png(b, lao, cra, modo, janela, lado, laje,
                               bool(inverter), bool(osso))
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"reconstrucoes 3D, vascular", e,
                                            bilhete=b)
            st, corpo = resposta_de_falha(e)
            _lembrar_falha(b, (st, corpo))
            return JSONResponse(status_code=st, content=corpo,
                                headers={"Cache-Control": "no-store"})
        if png is None:
            return JSONResponse(status_code=404, content={"erro": FORA_DA_LISTA},
                                headers={"Cache-Control": "no-store"})
        _lembrar_falha(b, None)
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/recon3d/vascular/estado")
    def _estado(b: str = ""):
        st, corpo = estado_da_projecao(b)
        return JSONResponse(status_code=st, content=corpo,
                            headers={"Cache-Control": "no-store"})

    return app
