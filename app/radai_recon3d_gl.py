# -*- coding: utf-8 -*-

JS = u"""
var R3G_VS = ['attribute vec3 aPos;', 'attribute vec3 aNrm;',
 'uniform mat4 uMVP;', 'uniform mat3 uNrm;', 'uniform mat4 uParaCaixa;',
 'varying vec3 vN;', 'varying vec3 vF;',
 'void main(){', ' vN = uNrm * aNrm;',
 ' vF = (uParaCaixa * vec4(aPos, 1.0)).xyz;',
 ' gl_Position = uMVP * vec4(aPos, 1.0);', '}'].join(' ');
var R3G_FS = ['precision mediump float;', 'uniform vec3 uCor;',
 'uniform float uAlfa;', 'uniform float uCorte;', 'uniform vec3 uMin;',
 'uniform vec3 uMax;', 'uniform float uLiso;',
 'varying vec3 vN;', 'varying vec3 vF;', 'void main(){',
 ' if(uCorte > 0.5){ if(any(lessThan(vF, uMin)) || any(greaterThan(vF, uMax))) discard; }',
 ' if(uLiso > 0.5){ gl_FragColor = vec4(uCor, uAlfa); return; }',
 ' vec3 n = normalize(vN);', ' if(n.z < 0.0) n = -n;',
 ' vec3 L = normalize(vec3(-0.35, 0.5, 1.0));',
 ' vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));',
 ' float d = max(dot(n, L), 0.0);',
 ' float s = pow(max(dot(n, H), 0.0), 40.0);',
 ' vec3 c = uCor * (0.26 + 0.74 * d) + vec3(0.36) * s;',
 ' gl_FragColor = vec4(min(c, vec3(1.0)), uAlfa);', '}'].join(' ');
var R3G_IDENTIDADE = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

function r3gLerStl(buf){
 if(!buf || buf.byteLength < 84) throw new Error('STL curto');
 var dv = new DataView(buf);
 var T = dv.getUint32(80, true);
 if(84 + 50 * T !== buf.byteLength) throw new Error('STL de tamanho errado');
 var cap = 1024; while(cap < T * 6) cap *= 2;
 var mask = cap - 1, tab = new Int32Array(cap);
 for(var q = 0; q < cap; q++) tab[q] = -1;
 var bits = new Uint32Array(T * 9), pos = new Float32Array(T * 9);
 var idx = new Uint32Array(T * 3), nv = 0;
 var lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
 for(var t = 0; t < T; t++){
  for(var k = 0; k < 3; k++){
   var o = 84 + 50 * t + 12 + 12 * k;
   var a = dv.getUint32(o, true), b = dv.getUint32(o + 4, true),
       c = dv.getUint32(o + 8, true);
   var h = (Math.imul(a, 73856093) ^ Math.imul(b, 19349663)
            ^ Math.imul(c, 83492791)) & mask;
   var j = tab[h];
   while(j >= 0 && !(bits[3*j] === a && bits[3*j+1] === b && bits[3*j+2] === c)){
    h = (h + 1) & mask; j = tab[h];
   }
   if(j < 0){
    j = nv++; tab[h] = j;
    bits[3*j] = a; bits[3*j+1] = b; bits[3*j+2] = c;
    for(var e = 0; e < 3; e++){
     var x = dv.getFloat32(o + 4 * e, true);
     pos[3*j+e] = x;
     if(x < lo[e]) lo[e] = x;
     if(x > hi[e]) hi[e] = x;
    }
   }
   idx[3*t+k] = j;
  }
 }
 pos = pos.slice(0, nv * 3);
 var nrm = new Float32Array(nv * 3);
 for(var f = 0; f < T; f++){
  var i0 = 3*idx[3*f], i1 = 3*idx[3*f+1], i2 = 3*idx[3*f+2];
  var ux = pos[i1] - pos[i0], uy = pos[i1+1] - pos[i0+1], uz = pos[i1+2] - pos[i0+2];
  var vx = pos[i2] - pos[i0], vy = pos[i2+1] - pos[i0+1], vz = pos[i2+2] - pos[i0+2];
  var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  nrm[i0] += nx; nrm[i0+1] += ny; nrm[i0+2] += nz;
  nrm[i1] += nx; nrm[i1+1] += ny; nrm[i1+2] += nz;
  nrm[i2] += nx; nrm[i2+1] += ny; nrm[i2+2] += nz;
 }
 for(var v = 0; v < nv; v++){
  var l = Math.sqrt(nrm[3*v]*nrm[3*v] + nrm[3*v+1]*nrm[3*v+1] + nrm[3*v+2]*nrm[3*v+2]);
  if(l > 1e-12){ nrm[3*v] /= l; nrm[3*v+1] /= l; nrm[3*v+2] /= l }
  else { nrm[3*v] = 0; nrm[3*v+1] = 0; nrm[3*v+2] = 1 }
 }
 var centro = T ? [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2] : [0, 0, 0];
 return {pos: pos, nrm: nrm, idx: idx, nv: nv, T: T, lo: lo, hi: hi,
         centro: centro};
}

function r3gMalhaDe(pos, nrm, idx, linhas){
 var p = new Float32Array(pos), n = new Float32Array(nrm), i = new Uint32Array(idx);
 return {pos: p, nrm: n, idx: i, nv: p.length / 3, T: linhas ? 0 : i.length / 3,
         linhas: !!linhas, centro: [0, 0, 0]};
}

function r3gCompilar(gl, tipo, fonte){
 var s = gl.createShader(tipo);
 gl.shaderSource(s, fonte); gl.compileShader(s);
 if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) return null;
 return s;
}
function r3gPrograma(V, gl){
 var vs = r3gCompilar(gl, gl.VERTEX_SHADER, R3G_VS);
 var fs = r3gCompilar(gl, gl.FRAGMENT_SHADER, R3G_FS);
 if(!vs || !fs) return 'o WebGL deste navegador não compilou o sombreador';
 var p = gl.createProgram();
 gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p);
 if(!gl.getProgramParameter(p, gl.LINK_STATUS))
  return 'o WebGL deste navegador não ligou o sombreador';
 V.gl = gl; V.prog = p; V.loc = {};
 V.u32 = gl.getExtension('OES_element_index_uint');
 ['aPos', 'aNrm'].forEach(function(n){ V.loc[n] = gl.getAttribLocation(p, n) });
 ['uMVP', 'uNrm', 'uParaCaixa', 'uCor', 'uAlfa', 'uCorte', 'uMin', 'uMax',
  'uLiso'].forEach(function(n){ V.loc[n] = gl.getUniformLocation(p, n) });
 return '';
}

function r3gAjustar(c){
 var r = c.getBoundingClientRect(), d = window.devicePixelRatio || 1;
 var w = Math.max(80, Math.round(r.width * d)), h = Math.max(80, Math.round(r.height * d));
 if(c.width !== w || c.height !== h){ c.width = w; c.height = h }
}

function r3gSubirEm(V, m, cor){
 var gl = V.gl; if(!gl) return null;
 var o = {n: 0, tipo: null, cor: cor || [170, 170, 170], centro: m.centro,
          linhas: !!m.linhas};
 var pos = m.pos, nrm = m.nrm, n = m.linhas ? m.idx.length : m.T * 3;
 if(m.nv > 65535 && !V.u32){
  pos = new Float32Array(n * 3); nrm = new Float32Array(n * 3);
  for(var i = 0; i < n; i++){
   var v = m.idx[i];
   for(var e = 0; e < 3; e++){ pos[3*i+e] = m.pos[3*v+e]; nrm[3*i+e] = m.nrm[3*v+e] }
  }
  o.n = n;
 } else {
  o.ibo = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, o.ibo);
  if(m.nv <= 65535){
   gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(m.idx), gl.STATIC_DRAW);
   o.tipo = gl.UNSIGNED_SHORT;
  } else {
   gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, m.idx, gl.STATIC_DRAW);
   o.tipo = gl.UNSIGNED_INT;
  }
  o.n = n;
 }
 o.vbo = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, o.vbo);
 gl.bufferData(gl.ARRAY_BUFFER, pos, gl.STATIC_DRAW);
 o.nbo = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, o.nbo);
 gl.bufferData(gl.ARRAY_BUFFER, nrm, gl.STATIC_DRAW);
 return o;
}
function r3gSoltarObj(V, o){
 var gl = V.gl; if(!o || !gl) return;
 [o.vbo, o.nbo, o.ibo].forEach(function(b){ if(b) gl.deleteBuffer(b) });
}

function r3gUmEm(V, o, alfa){
 var gl = V.gl, L = V.loc;
 gl.bindBuffer(gl.ARRAY_BUFFER, o.vbo);
 gl.vertexAttribPointer(L.aPos, 3, gl.FLOAT, false, 0, 0);
 gl.bindBuffer(gl.ARRAY_BUFFER, o.nbo);
 gl.vertexAttribPointer(L.aNrm, 3, gl.FLOAT, false, 0, 0);
 gl.uniform3f(L.uCor, o.cor[0] / 255, o.cor[1] / 255, o.cor[2] / 255);
 gl.uniform1f(L.uAlfa, alfa);
 var modo = o.linhas ? gl.LINES : gl.TRIANGLES;
 if(o.tipo){
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, o.ibo);
  gl.drawElements(modo, o.n, o.tipo, 0);
 } else {
  gl.drawArrays(modo, 0, o.n);
 }
}
// GUARDA: translúcido sem escrever profundidade, a face de trás antes da da frente.
function r3gTranslucidoEm(V, o, alfa){
 var gl = V.gl;
 if(alfa <= 0.005) return;
 gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
 gl.depthMask(false); gl.enable(gl.CULL_FACE);
 gl.cullFace(gl.FRONT); r3gUmEm(V, o, alfa);
 gl.cullFace(gl.BACK); r3gUmEm(V, o, alfa);
 gl.depthMask(true); gl.disable(gl.CULL_FACE);
}

function r3gCamera(V, mvp, nrm){
 var gl = V.gl, L = V.loc;
 gl.uniformMatrix4fv(L.uMVP, false, mvp);
 gl.uniformMatrix3fv(L.uNrm, false, nrm);
}
function r3gCorte(V, paraCaixa, lo, hi){
 var gl = V.gl, L = V.loc;
 gl.uniform1f(L.uCorte, paraCaixa ? 1 : 0);
 gl.uniformMatrix4fv(L.uParaCaixa, false, paraCaixa || R3G_IDENTIDADE);
 lo = lo || [0, 0, 0]; hi = hi || [1, 1, 1];
 gl.uniform3f(L.uMin, lo[0], lo[1], lo[2]);
 gl.uniform3f(L.uMax, hi[0], hi[1], hi[2]);
}
function r3gLiso(V, liso){ V.gl.uniform1f(V.loc.uLiso, liso ? 1 : 0) }

function r3gColunas(linhas){
 return [linhas[0], linhas[4], linhas[8], linhas[12],
         linhas[1], linhas[5], linhas[9], linhas[13],
         linhas[2], linhas[6], linhas[10], linhas[14],
         linhas[3], linhas[7], linhas[11], linhas[15]];
}
// GUARDA: câmera ortográfica; as linhas de M são a direita, o alto e a frente da tela no LPS.
function r3gOrto(M, centro, ex, ey, dx, dy, prof){
 var c = centro, l = [];
 var t0 = M[0]*c[0] + M[1]*c[1] + M[2]*c[2];
 var t1 = M[3]*c[0] + M[4]*c[1] + M[5]*c[2];
 var t2 = M[6]*c[0] + M[7]*c[1] + M[8]*c[2];
 l = [ex*M[0], ex*M[1], ex*M[2], dx - ex*t0,
      ey*M[3], ey*M[4], ey*M[5], dy - ey*t1,
      -prof*M[6], -prof*M[7], -prof*M[8], prof*t2,
      0, 0, 0, 1];
 return r3gColunas(l);
}
function r3gNrmDe(M){ return [M[0], M[3], M[6], M[1], M[4], M[7], M[2], M[5], M[8]] }
function r3gM4mul(a, b){
 var o = [];
 for(var c = 0; c < 4; c++) for(var r = 0; r < 4; r++){
  var s = 0; for(var k = 0; k < 4; k++) s += a[k*4 + r] * b[c*4 + k]; o[c*4 + r] = s }
 return o;
}
function r3gM4base(X, Y, Z, T){
 return [X[0], X[1], X[2], 0, Y[0], Y[1], Y[2], 0, Z[0], Z[1], Z[2], 0, T[0], T[1], T[2], 1];
}
function r3gVista(r, u, f, olho){
 var z = [-f[0], -f[1], -f[2]];
 function pe(a, b){ return a[0]*b[0] + a[1]*b[1] + a[2]*b[2] }
 return [r[0], u[0], z[0], 0, r[1], u[1], z[1], 0, r[2], u[2], z[2], 0,
         -pe(r, olho), -pe(u, olho), -pe(z, olho), 1];
}
function r3gPersp(fov, asp, perto, longe){
 var f = 1 / Math.tan(fov / 2);
 return [f / asp, 0, 0, 0, 0, f, 0, 0, 0, 0, (longe + perto) / (perto - longe), -1,
         0, 0, 2 * longe * perto / (perto - longe), 0];
}
function r3gNrmV(A){ return [A[0], A[1], A[2], A[4], A[5], A[6], A[8], A[9], A[10]] }
"""
