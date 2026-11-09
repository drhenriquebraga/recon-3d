# -*- coding: utf-8 -*-
import json
import math
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path

import radai_menu
import radai_web
import radai_recon3d_vascular_core as V

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
_CANDIDATOS = OrderedDict()
_TRAVA_CANDIDATOS = threading.Lock()
_PROCESSANDO = threading.Lock()
_CACHE = {"Cache-Control": "no-store"}
_CANDIDATO_VENCEU = u"O consenso expirou. Gere a prévia novamente."
_OCUPADO = u"O processamento Vascular já está em andamento."
_PEDIDO_INVALIDO = u"Pedido Vascular inválido."
_FALHA_3D = u"O processamento Vascular não pôde ser concluído."


def _carimbo(arquivos):
    return tuple((stat.st_size, stat.st_mtime_ns)
                 for stat in (Path(path).stat() for path in arquivos))


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
        dados = radai_thumbnail.serie_do_bilhete(b) or {}
        mod = str(dados.get("modalidade") or "").upper()
        arquivos = tuple(item["caminho"] for item in dados.get("arquivos", []))
        import pydicom
        cab = (pydicom.dcmread(str(arquivos[0]), stop_before_pixels=True,
                             specific_tags=["BodyPartExamined"], force=True) if arquivos else {})
        V.conferir_modalidade(mod, cab.get("BodyPartExamined", ""))
        carimbo = _carimbo(arquivos)
        img = engine.load_sitk(pasta, uid or None)
        if carimbo != _carimbo(arquivos):
            raise V.VascularRecusada(V.REF_MUDOU)
        s = N.abrir(img, mod)
        s.origem_vascular = (arquivos, uid, mod, carimbo)
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
    return (u"Abra uma angio-TC ou uma angio-RM de crânio em 3D. MIP e MinIP "
            u"projetam a imagem da série selecionada.",
            u"O realce 3D procura padrões tubulares na grade original. O detalhe "
            u"fino examina mais escalas físicas.",
            u"Guarde o desenho de cada incidência com o lápis. A temperatura "
            u"ajusta o consenso entre a união e a interseção dos desenhos.",
            u"Somente o consenso manual gera um RTSTRUCT de pesquisa, marcado "
            u"como não aprovado e vinculado à série original.",
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
.vx-lapis{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.vx-lapis polygon{fill:#40dfc52d;stroke:#53e4cc;stroke-width:1.6;vector-effect:non-scaling-stroke}
.vx-proj[data-lapis]{cursor:crosshair}
.vx-proj[data-lapis] img{transition:none}
.vx-sala{position:relative;background:#071018;border-radius:8px;overflow:hidden;min-height:320px;height:min(60vh,540px)}
.vx-sala canvas{display:block;width:100%;height:100%;cursor:grab;touch-action:none}
.vx-sala canvas:active{cursor:grabbing}
.vx-sala .r3-rec{position:absolute}
.vx-cmd .ui-bt{width:max-content;max-width:100%}
.vx-cmd p{margin:0}
.vx-cmd .vx-status{min-height:1.4em;color:var(--text)}
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
 VX.imagem = false;
 vxLapisBotoes(); vxLapisPintar(); r3gDesenhar();
 if(VX.osso_b !== R3.b) vxOsso('');
 function apaga(){ if(window.uiCarregando) uiCarregando(cx, false) }
 function carrega(lado){
  if(window.uiCarregando && !rapido) uiCarregando(cx, true, 'projetando');
  img.onload = function(){
   if(meu !== VX.pedido) return;
   img.style.visibility = '';
   VX.imagem = true; vxLapisBotoes();
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
 if(VX.lapis && f) return;
 VX.zoom = f ? Math.max(1, Math.min(8, VX.zoom * f)) : 1;
 if(!f){ VX.ux = 0; VX.uy = 0 }
 if(VX.zoom === 1){ VX.ux = 0; VX.uy = 0 }
 var img = r3El('vx_img');
 if(img) img.style.transform = 'translate(' + VX.ux + 'px,' + VX.uy + 'px) scale(' + VX.zoom + ')';
 vxLapisPintar();
}
function r3AoAbrir(d){
 if(VX.b !== R3.b){
  VX.b = R3.b; VX.guardadas = []; VX.rascunho = null; VX.traco = null;
  VX.lapis = false; VX.token = ''; VX.ocupado = false; ++VX.calculo; ++VX.revisao;
  R3M.b = VXG.gl && !(d && d.nao_le) ? VX.b : null;
  vxSoltar('arvore'); vxSoltar('consenso'); vxZoom(0);
  vxMensagem(''); vxCena('sala');
 }
 r3Carregando(false);
 vxPintar(false);
}
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
  cx.addEventListener('pointerdown', function(e){ if(VX.lapis || VX.zoom <= 1) return; arr = true; ax = e.clientX; ay = e.clientY;
   try{ cx.setPointerCapture(e.pointerId) }catch(_){} });
  cx.addEventListener('pointermove', function(e){ if(!arr) return;
   VX.ux += e.clientX - ax; VX.uy += e.clientY - ay; ax = e.clientX; ay = e.clientY; vxZoom(1) });
  cx.addEventListener('pointerup', function(){ arr = false });
  cx.addEventListener('contextmenu', function(e){ e.preventDefault() });
 }
 vxMarcar();
});
"""


JS_VISORES = r"""
Object.assign(VX, {b:null, imagem:false, lapis:false, guardadas:[], rascunho:null,
 traco:null, token:'', calculo:0, revisao:0, ocupado:false, tela:'sala'});
var VXG = {gl:null, sala:null, arvore:null, consenso:null, yaw:120, pitch:16, escala:1};
var R3M = {modo:'gl', b:null};
var VX_API = '/api/recon3d/vascular/';
function vxMensagem(frase){
 var e = r3El('vx_status');
 if(window.uiTexto) uiTexto(e, frase); else e.textContent = frase;
}
function vxNoAngulo(g){ return g && g.lao === VX.lao && g.cra === VX.cra }
function vxLapisPintar(){
 var cx = r3El('vx_proj'), svg = r3El('vx_lapis');
 cx.toggleAttribute('data-lapis', VX.lapis);
 var g = VX.traco || (vxNoAngulo(VX.rascunho) && VX.rascunho)
  || VX.guardadas.find(vxNoAngulo);
 svg.hidden = !g || VX.zoom !== 1;
 svg.style.display = svg.hidden ? 'none' : '';
 if(!svg.hidden) svg.firstElementChild.setAttribute('points',
  g.pontos.map(function(p){ return p.join(',') }).join(' '));
}
function vxLapisBotoes(){
 var b = r3El('vx_lapis_bt');
 b.disabled = !VX.imagem;
 b.classList.toggle('on', VX.lapis);
 b.setAttribute('aria-pressed', String(VX.lapis));
 r3El('vx_guardar').disabled = !VX.imagem || !vxNoAngulo(VX.rascunho);
 r3El('vx_apagar').disabled = !VX.guardadas.some(vxNoAngulo) && !vxNoAngulo(VX.rascunho);
 r3El('vx_qtd').textContent = VX.guardadas.length + ' / 12';
 r3El('vx_calcular').disabled = !VX.b || !VX.guardadas.length || VX.ocupado;
 r3El('vx_exportar').disabled = !VX.token || VX.ocupado;
 r3El('vx_arvore').disabled = !VX.b || !VXG.gl || VX.ocupado;
 r3El('vx_ver_arvore').disabled = !VXG.arvore;
 r3El('vx_ver_consenso').disabled = !VXG.consenso;
}
function vxLapis(){
 VX.lapis = !VX.lapis;
 if(VX.lapis) vxZoom(0);
 vxLapisBotoes(); vxLapisPintar();
}
function vxPonto(e, cx, limitar){
 var r = cx.getBoundingClientRect(), lado = Math.min(r.width, r.height);
 var x = (e.clientX-r.left-(r.width-lado)/2)/lado;
 var y = (e.clientY-r.top-(r.height-lado)/2)/lado;
 if(!limitar && (x<0 || x>1 || y<0 || y>1)) return null;
 return [x,y].map(function(v){ return Math.round(Math.max(0,Math.min(1,v))*100000)/100000 });
}
function vxLapisLigar(){
 var cx = r3El('vx_proj');
 cx.addEventListener('pointerdown', function(e){
  if(!VX.lapis || !VX.imagem || VX.traco || e.button !== 0 || e.target.closest('button')) return;
  var p = vxPonto(e, cx, false); if(!p) return;
  VX.traco = {id:e.pointerId, lao:VX.lao, cra:VX.cra, pontos:[p]};
  cx.setPointerCapture(e.pointerId); vxLapisPintar(); e.preventDefault();
 });
 cx.addEventListener('pointermove', function(e){
  var g = VX.traco;
  if(!g || g.id !== e.pointerId || !vxNoAngulo(g)) return;
  var p = vxPonto(e, cx, true), u = g.pontos[g.pontos.length-1];
  if(g.pontos.length<512 && Math.hypot(p[0]-u[0],p[1]-u[1]) >= 0.002){
   g.pontos.push(p); vxLapisPintar();
  }
 });
 function terminar(e){
  var g = VX.traco;
  if(!g || g.id !== e.pointerId) return;
  VX.traco = null;
  if(e.type === 'pointerup' && g.pontos.length >= 3 && vxNoAngulo(g)){
   VX.rascunho = {lao:g.lao, cra:g.cra, pontos:g.pontos};
   vxInvalidarConsenso();
  }
  vxLapisPintar(); vxLapisBotoes();
 }
 cx.addEventListener('pointerup', terminar); cx.addEventListener('pointercancel', terminar);
}
function vxInvalidarConsenso(){
 VX.token = ''; ++VX.revisao;
 vxSoltar('consenso');
 if(VX.tela === 'consenso') vxCena('sala');
 vxMensagem('');
}
function vxGuardar(){
 if(!vxNoAngulo(VX.rascunho)) return;
 var i = VX.guardadas.findIndex(vxNoAngulo);
 if(i < 0 && VX.guardadas.length >= 12){ vxMensagem('Limite de 12 incidências guardadas.'); return }
 if(i < 0) VX.guardadas.push(VX.rascunho); else VX.guardadas[i] = VX.rascunho;
 VX.rascunho = null; VX.lapis = false;
 vxInvalidarConsenso(); vxLapisBotoes(); vxLapisPintar(); r3gDesenhar();
}
function vxApagar(){
 if(vxNoAngulo(VX.rascunho)) VX.rascunho = null;
 else VX.guardadas = VX.guardadas.filter(function(g){ return !vxNoAngulo(g) });
 vxInvalidarConsenso(); vxLapisBotoes(); vxLapisPintar(); r3gDesenhar();
}
function vxSoltar(qual){
 var m = VXG[qual];
 if(m && m.obj && VXG.gl) r3gSoltarObj(VXG,m.obj);
 VXG[qual] = null;
}
function vxCena(qual){
 VX.tela = qual; VXG.yaw = 120; VXG.pitch = 16; VXG.escala = 1;
 document.querySelectorAll('[data-vx-cena]').forEach(function(b){
  var ativa = b.getAttribute('data-vx-cena') === qual;
  b.classList.toggle('on', ativa); b.setAttribute('aria-pressed', String(ativa));
 });
 r3gDesenhar();
}
function r3gDesenhar(){
 var c = r3El('cvGL'), g = VXG.gl;
 if(!g || !c) return;
 r3gAjustar(c); g.viewport(0,0,c.width,c.height);
 g.clearColor(0.027,0.051,0.078,1); g.clear(g.COLOR_BUFFER_BIT|g.DEPTH_BUFFER_BIT);
 var sala = VX.tela === 'sala', m = VXG[VX.tela], S = VXG.sala;
 if(!sala && !m) return;
 var alvo = sala ? [0,80,260] : m.centro, dist = sala ? 4750 : m.raio*3.9;
 dist *= VXG.escala;
 var yaw = VXG.yaw*Math.PI/180, pit = VXG.pitch*Math.PI/180;
 var up = sala ? [0,-1,0] : [0,0,1];
 var d = sala ? [Math.cos(pit)*Math.sin(yaw),-Math.sin(pit),Math.cos(pit)*Math.cos(yaw)]
              : [Math.cos(pit)*Math.sin(yaw),Math.cos(pit)*Math.cos(yaw),Math.sin(pit)];
 var olho = alvo.map(function(v,i){ return v + dist*d[i] }), f = d.map(function(v){ return -v });
 function cruz(a,b){ return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]] }
 var r = cruz(f,up), n = Math.hypot.apply(null,r); r = r.map(function(v){ return v/n });
 var u = cruz(r,f), vista = r3gVista(r,u,f,olho);
 var p = r3gPersp(34*Math.PI/180,c.width/c.height,Math.max(0.1,dist/500),dist*10);
 var vp = r3gM4mul(p,vista), I = r3gM4base([1,0,0],[0,1,0],[0,0,1],[0,0,0]);
 r3gCorte(VXG,null);
 function pintar(o,M,cor,alfa,liso){
  if(!o) return;
  o.cor = cor;
  r3gCamera(VXG,r3gM4mul(vp,M),r3gNrmV(r3gM4mul(vista,M)));
  r3gLiso(VXG,liso);
  if(alfa<1) r3gTranslucidoEm(VXG,o,alfa); else r3gUmEm(VXG,o,alfa);
 }
 if(sala){
  var pose = radaiPoseArcoC(VX.lao,VX.cra);
  var metal = [117,145,171], placa = [82,198,227], base = [72,102,124];
  pintar(S.piso,I,[42,57,73],1,true); pintar(S.mesa,I,base,1,false);
  pintar(S.paciente,I,[143,128,113],1,false);
  pintar(S.coluna,I,base,1,false); pintar(S.carro,pose.Mc,metal,1,false);
  pintar(S.arco,pose.M,metal,1,false); pintar(S.detector,pose.M,placa,1,false);
  pintar(S.tubo,pose.M,metal,1,false);
  VX.guardadas.forEach(function(g){
   pintar(S.detectorF,radaiPoseArcoC(g.lao,g.cra).M,[83,228,204],0.42,false);
  });
  pintar(S.feixe,pose.M,placa,0.12,false);
 }else pintar(m.obj,I,VX.tela === 'arvore' ? [240,113,102] : [83,228,204],1,false);
 if(window.r3vQuadro) r3vQuadro();
}
function vxGl(){
 var c = r3El('cvGL');
 try{
  var g = c.getContext('webgl',{antialias:true, alpha:false});
  if(!g || r3gPrograma(VXG,g)) throw new Error();
  g.enable(g.DEPTH_TEST); g.clearDepth(1);
  VXG.sala = radaiSalaArcoC(VXG);
 }catch(_){
  VXG.gl = null; r3El('vx_webgl').hidden = false; return;
 }
 c.addEventListener('webglcontextlost',function(e){
  e.preventDefault(); VXG.gl = null; R3M.b = null;
  r3El('vx_webgl').hidden = false; vxLapisBotoes();
 });
 var arr = null;
 c.addEventListener('pointerdown',function(e){
  if(e.button !== 0) return;
  arr = e; c.setPointerCapture(e.pointerId);
 });
 c.addEventListener('pointermove',function(e){
  if(!arr || arr.pointerId !== e.pointerId) return;
  VXG.yaw -= (e.clientX-arr.clientX)*0.4;
  VXG.pitch = Math.max(-82,Math.min(82,VXG.pitch+(e.clientY-arr.clientY)*0.35));
  arr = e; r3gDesenhar();
 });
 ['pointerup','pointercancel','lostpointercapture'].forEach(function(ev){
  c.addEventListener(ev,function(){ arr = null });
 });
 c.addEventListener('wheel',function(e){
  e.preventDefault(); VXG.escala = Math.max(0.35,Math.min(4,VXG.escala*(e.deltaY>0 ? 1.1 : 0.9)));
  r3gDesenhar();
 },{passive:false});
 c.addEventListener('dblclick',function(){ vxCena(VX.tela) });
 if(window.ResizeObserver) new ResizeObserver(r3gDesenhar).observe(c);
 else window.addEventListener('resize',r3gDesenhar);
 vxCena('sala');
}
function vxOperar(acao){
 if(VX.ocupado || !VX.b || VX.b !== R3.b) return;
 var b = VX.b, calculo = ++VX.calculo, revisao = VX.revisao, pedido = {b:b};
 if(acao === 'arvore'){
  pedido.detalhe = r3El('vx_detalhe').value;
  pedido.sensibilidade = +r3El('vx_sens').value;
 }else if(acao === 'consenso'){
  pedido.incidencias = VX.guardadas;
  pedido.temperatura = +r3El('vx_temperatura').value;
  VX.token = '';
 }else pedido.candidato = VX.token;
 VX.ocupado = true; vxLapisBotoes();
 vxMensagem(acao === 'arvore' ? 'Realçando os vasos na série…' :
  acao === 'consenso' ? 'Calculando o consenso dos desenhos…' : 'Verificando o RTSTRUCT…');
 function mesmoPedido(){ return calculo === VX.calculo && b === R3.b }
 function atual(){ return mesmoPedido() && (acao === 'arvore' || revisao === VX.revisao) }
 fetch(VX_API + acao,{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(pedido)}).then(async function(res){
  if(!res.ok){
   var erro = await res.json().catch(function(){ return {} });
   if(atual() && acao === 'exportar' && res.status === 404) VX.token = '';
   throw new Error(erro.erro || VX_NAO_RESPONDEU);
  }
  if(acao === 'exportar'){
   await vxBaixarRTSTRUCT(res, atual);
   return;
  }
  var buf = await res.arrayBuffer(); if(!atual()) return;
  if(VXG.gl){
   var m = r3gLerStl(buf); if(!m) throw new Error(VX_NAO_RESPONDEU);
   vxSoltar(acao);
   VXG[acao] = {obj:r3gSubirEm(VXG,m), centro:m.centro,
    raio:Math.max(1,Math.hypot(m.hi[0]-m.lo[0],m.hi[1]-m.lo[1],m.hi[2]-m.lo[2])/2)};
   vxCena(acao);
  }
  if(acao === 'consenso') VX.token = res.headers.get('X-Vascular-Candidate') || '';
  vxMensagem(acao === 'arvore' ? 'Realce tubular pronto para inspeção.' : 'Consenso manual pronto para revisão.');
 }).catch(function(e){
  if(atual()) vxMensagem(e.message || VX_NAO_RESPONDEU);
 }).finally(function(){
  if(mesmoPedido()){ VX.ocupado = false; vxLapisBotoes() }
 });
}
window.addEventListener('DOMContentLoaded',function(){
 vxGl(); vxLapisLigar(); vxLapisBotoes(); vxLapisPintar();
 r3El('vx_temperatura').addEventListener('input',function(){
  r3El('vx_temperatura_v').textContent = this.value + '%';
  vxInvalidarConsenso(); vxLapisBotoes();
 });
 r3El('vx_sens').addEventListener('input',function(){
  r3El('vx_sens_v').textContent = this.value + '%';
 });
});
"""


JS_EXPORTAR = r"""
async function vxBaixarRTSTRUCT(res, atual){
 var blob = await res.blob(); if(!atual()) return;
 var a = document.createElement('a'), url = URL.createObjectURL(blob);
 a.href = url; a.download = 'RS_Vascular_Manual.dcm'; a.click();
 setTimeout(function(){ URL.revokeObjectURL(url) },5000);
 vxMensagem('RTSTRUCT manual salvo.');
}
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
        u'<svg class="vx-lapis" id="vx_lapis" viewBox="0 0 1 1" '
        u'preserveAspectRatio="xMidYMid meet" aria-hidden="true" style="display:none">'
        u'<polygon></polygon></svg>'
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
        u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
        u'Desenho por incidência</span><b id="vx_qtd"></b></div><div class="vx-bts">'
        u'<button type="button" class="jan" id="vx_lapis_bt" onclick="vxLapis()" '
        u'aria-pressed="false" disabled><span data-radai-frase>Lápis</span></button>'
        u'<button type="button" class="jan" id="vx_guardar" onclick="vxGuardar()" '
        u'disabled><span data-radai-frase>Guardar incidência</span></button>'
        u'<button type="button" class="jan" id="vx_apagar" onclick="vxApagar()" '
        u'disabled><span data-radai-frase>Apagar desenho</span></button></div></div>'
        u'</div></div>' % (inc, OSSO_E_O_VASO, OSSO_PELA_SEGMENTACAO,
                           OSSO_PELO_LIMIAR, OSSO_FICA, jan, res))


def _html_visor(S):
    import radai_ui
    ajuda = radai_ui.ajuda(
        u"O arco em C é ilustrativo. A posição acompanha a incidência da projeção.",
        u"O realce tubular usa os voxels da própria imagem. A sensibilidade "
        u"controla quanto do sinal aparece na superfície.",
        u"A temperatura de 100% mostra a interseção dos desenhos. Em 0%, o "
        u"contorno reúne os desenhos de todas as incidências.")
    return (u'<div class="vx-palco"><div><div class="vx-sala" id="r3_tela3d">'
            u'<canvas id="cvGL" aria-label="Visor 3D Vascular"></canvas>'
            u'<span class="r3-rec" id="r3_rec" hidden><i></i>REC '
            u'<b id="r3_rec_t">00:00</b></span></div>'
            u'<p id="vx_webgl" class="sub" data-radai-frase hidden>'
            u'O visor 3D precisa de WebGL. As projeções e o lápis continuam disponíveis.</p>'
            + S.html_gravacao() +
            u'</div><div class="vx-cmd"><div class="vx-g"><div class="r3-ferr-cab">'
            u'<span data-radai-frase>Vista</span>' + ajuda + u'</div><div class="vx-bts">'
            u'<button type="button" class="jan on" data-vx-cena="sala" aria-pressed="true" '
            u'onclick="vxCena(\'sala\')"><span data-radai-frase>Sala</span></button>'
            u'<button type="button" class="jan" id="vx_ver_arvore" data-vx-cena="arvore" '
            u'aria-pressed="false" onclick="vxCena(\'arvore\')" disabled>'
            u'<span data-radai-frase>Realce tubular</span></button>'
            u'<button type="button" class="jan" id="vx_ver_consenso" data-vx-cena="consenso" '
            u'aria-pressed="false" onclick="vxCena(\'consenso\')" disabled>'
            u'<span data-radai-frase>Consenso manual</span></button></div></div>'
            u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
            u'Realce tubular</span></div><label class="sub" for="vx_detalhe" '
            u'data-radai-frase>Detalhe do realce</label><select id="vx_detalhe">'
            u'<option value="equilibrado" data-radai-frase>Equilibrado</option>'
            u'<option value="fino" data-radai-frase>Fino</option></select>'
            u'<label class="sub" for="vx_sens"><span data-radai-frase>Sensibilidade</span> '
            u'<b id="vx_sens_v">50%</b></label>'
            u'<input id="vx_sens" type="range" min="0" max="100" value="50">'
            u'<button type="button" class="ui-bt" id="vx_arvore" onclick="vxOperar(\'arvore\')" '
            u'disabled><span data-radai-frase>Processar realce</span></button></div>'
            u'<div class="vx-g"><div class="r3-ferr-cab"><span data-radai-frase>'
            u'Consenso manual</span></div><label class="sub" for="vx_temperatura">'
            u'<span data-radai-frase>Temperatura do consenso</span> '
            u'<b id="vx_temperatura_v">100%</b></label>'
            u'<input id="vx_temperatura" type="range" min="0" max="100" value="100">'
            u'<div class="vx-bts"><button type="button" class="ui-bt" id="vx_calcular" '
            u'onclick="vxOperar(\'consenso\')" disabled>'
            u'<span data-radai-frase>Gerar prévia</span></button>'
            u'<button type="button" class="ui-bt" id="vx_exportar" onclick="vxOperar(\'exportar\')" '
            u'disabled><span data-radai-frase>Salvar RTSTRUCT manual</span></button></div></div>'
            u'<p id="vx_status" class="vx-status" role="status"></p></div></div>')


def pagina():
    import radai_recon3d_carm
    import radai_recon3d_gl
    import radai_recon3d_screen as S
    import radai_ui
    import radai_viewer
    f = S.FERRAMENTAS_3D["vascular"]
    cab = radai_ui.cabeca_de_funcao(
        f["icone"], f["nome"], f["frase"],
        radai_ui.ajuda(*(AJUDA + S.AJUDA_EXPORTA[1:])), u"recon3d")
    corpo = (cab + S._html_passo_serie()
             + radai_ui.passo(u"2", u"Projeções MIP e MinIP", _html_projecao(),
                              ident=u"vx_p2")
             + radai_ui.passo(u"3", u"Sala e reconstrução 3D",
                              _html_visor(S), ident=u"vx_p3")
             + radai_ui.alerta(ALERTA))
    js = (radai_viewer.JS_3D + radai_recon3d_gl.JS + radai_recon3d_carm.JS
          + S.JS_GRAVAR + S.JS_SERIE
          + JS.replace(u"@NAO_RESPONDEU@",
                       json.dumps(NAO_RESPONDEU, ensure_ascii=False))
          + JS_VISORES + JS_EXPORTAR)
    return (u'<!doctype html><html><head><meta charset="utf-8">'
            u'<title>Vascular &middot; Reconstru&ccedil;&otilde;es 3D</title>'
            u'<meta name="viewport" content="width=device-width,initial-scale=1">'
            u'<style>%s%s</style></head><body>'
            u'<div class="r3-wrap" data-ferramenta="vascular">%s</div>'
            u'<script>%s</script></body></html>' % (S.CSS, CSS, corpo, js))


def resposta_de_falha(e):
    import radai_projection as N
    if isinstance(e, (N.SerieRecusada, V.VascularRecusada)):
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
                          "fonte": getattr(s, "osso_fonte", u"") or u""},
                 "modalidade": s.origem_vascular[2]}


def _referencia_atual(s):
    arquivos, uid, modalidade, carimbo = s.origem_vascular
    if _carimbo(arquivos) != carimbo:
        with _TRAVA:
            if _ABERTA["serie"] is s:
                _ABERTA.update({"chave": None, "serie": None})
        raise V.VascularRecusada(V.REF_MUDOU)
    ref = V.capturar_referencia(arquivos, uid, s.img.GetSize())
    if ref.modalidade != modalidade:
        raise V.VascularRecusada(V.REF_MUDOU)
    return ref


def _candidato(token, b, candidato=None):
    with _TRAVA_CANDIDATOS:
        agora = time.monotonic()
        while _CANDIDATOS and (
                agora - next(iter(_CANDIDATOS.values()))[0] >= SOLTAR_APOS_S
                or (candidato is not None and len(_CANDIDATOS) >= 4)):
            _CANDIDATOS.popitem(last=False)
        if candidato is not None:
            _CANDIDATOS[token] = (agora, b, candidato)
            return None
        item = _CANDIDATOS.get(token)
        return item[2] if item and secrets.compare_digest(item[1], b) else None


def _operar(acao, pedido):
    from fastapi.responses import JSONResponse, Response
    campos = {"arvore": {"b", "detalhe", "sensibilidade"},
              "consenso": {"b", "incidencias", "temperatura"}, "exportar": {"b", "candidato"}}
    b = pedido.get("b")
    if set(pedido) != campos[acao] or not isinstance(b, str) or not b.isascii() or len(b) > 128:
        return JSONResponse({"erro": _PEDIDO_INVALIDO}, status_code=400, headers=_CACHE)
    if not _PROCESSANDO.acquire(blocking=False):
        return JSONResponse({"erro": _OCUPADO}, status_code=409, headers=_CACHE)
    try:
        if acao == "exportar":
            import numpy as np
            token = pedido["candidato"]
            item = _candidato(token, b) if isinstance(token, str) and len(token) <= 64 else None
            if item is None:
                return JSONResponse({"erro": _CANDIDATO_VENCEU}, status_code=404, headers=_CACHE)
            ref, geo, bits, temperatura, digest, n = item
            mask = np.unpackbits(bits, axis=-1, count=geo[0][0]).astype(bool)
            if serie(b) is None:
                return JSONResponse({"erro": FORA_DA_LISTA}, status_code=404, headers=_CACHE)
            dados = V.exportar(ref, geo, mask, temperatura, digest, n)
            return Response(dados, media_type="application/dicom", headers={
                **_CACHE, "Content-Disposition": 'attachment; filename="RS_Vascular_Manual.dcm"'})
        s = serie(b)
        if s is None:
            return JSONResponse({"erro": FORA_DA_LISTA}, status_code=404, headers=_CACHE)
        if acao == "arvore":
            mask = V.realcar(s.img, s.origem_vascular[2], pedido["detalhe"], pedido["sensibilidade"])
            return Response(V.malha_do_visor(s.img, mask),
                            media_type="application/octet-stream", headers=_CACHE)
        import numpy as np
        temperatura, incidencias = pedido["temperatura"], pedido["incidencias"]
        if (isinstance(temperatura, bool) or not isinstance(temperatura, (int, float))
                or not math.isfinite(temperatura) or not 0 <= temperatura <= 100):
            raise V.VascularRecusada(_PEDIDO_INVALIDO)
        ref = _referencia_atual(s)
        mask, digest = V.consenso(s.img, incidencias, temperatura)
        malha = V.malha_do_visor(s.img, mask)
        token = secrets.token_urlsafe(32)
        _candidato(token, b, (ref, V.geometria(s.img), np.packbits(mask, axis=-1),
                              temperatura, digest, len(incidencias)))
        return Response(malha, media_type="application/octet-stream",
                        headers={**_CACHE, "X-Vascular-Candidate": token})
    except V.VascularRecusada as exc:
        return JSONResponse({"erro": str(exc)}, status_code=422, headers=_CACHE)
    except Exception as exc:
        import radai_thumbnail
        radai_thumbnail.registrar_falha(u"reconstrucoes 3D, vascular", exc, bilhete=b)
        return JSONResponse({"erro": _FALHA_3D}, status_code=500, headers=_CACHE)
    finally:
        _PROCESSANDO.release()


def montar(app):
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from starlette.concurrency import run_in_threadpool

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

    async def _processar(acao, request):
        origem = request.headers.get("origin")
        if (request.headers.get("sec-fetch-site") == "cross-site"
                or (origem and origem != str(request.base_url).rstrip("/"))
                or request.headers.get("content-type", "").split(";")[0] != "application/json"):
            return JSONResponse({"erro": _PEDIDO_INVALIDO}, status_code=403, headers=_CACHE)
        corpo = bytearray()
        async for pedaco in request.stream():
            corpo.extend(pedaco)
            if len(corpo) > 256 * 1024:
                return JSONResponse({"erro": _PEDIDO_INVALIDO}, status_code=413, headers=_CACHE)
        try:
            pedido = json.loads(corpo)
        except (UnicodeError, ValueError, RecursionError):
            pedido = None
        if not isinstance(pedido, dict):
            return JSONResponse({"erro": _PEDIDO_INVALIDO}, status_code=400, headers=_CACHE)
        return await run_in_threadpool(_operar, acao, pedido)

    @app.post("/api/recon3d/vascular/arvore")
    async def _arvore(request: Request):
        return await _processar("arvore", request)

    @app.post("/api/recon3d/vascular/consenso")
    async def _consenso(request: Request):
        return await _processar("consenso", request)

    @app.post("/api/recon3d/vascular/exportar")
    async def _exportar(request: Request):
        return await _processar("exportar", request)

    return app
