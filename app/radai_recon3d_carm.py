# -*- coding: utf-8 -*-
"""Geometria ilustrativa compartilhada do arco em C, sem dados do paciente."""

JS = r"""
function radaiSalaArcoC(V){
function construtor(){ return {p:[], n:[], i:[]} }
function v(C, p, n){ C.p.push(p[0],p[1],p[2]); C.n.push(n[0],n[1],n[2]); return C.p.length/3-1 }
function t(C, a, b, c){ C.i.push(a,b,c) }
function subir(C, linhas){
 return r3gSubirEm(V, r3gMalhaDe(C.p, C.n, C.i, linhas), [200,200,200]);
}
function norm(a){ var l=Math.sqrt(a[0]*a[0]+a[1]*a[1]+a[2]*a[2])||1; return [a[0]/l,a[1]/l,a[2]/l] }
function cruz(a,b){ return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]] }
function somar(a,b){ return [a[0]+b[0],a[1]+b[1],a[2]+b[2]] }
function menos(a,b){ return [a[0]-b[0],a[1]-b[1],a[2]-b[2]] }
function escalar(a,s){ return [a[0]*s,a[1]*s,a[2]*s] }
function elipsoide(C, c, r, nu, nv){
 var ids=[], i, j;
 for(j=0;j<=nv;j++){ var ct=1-2*j/nv, st=Math.sqrt(Math.max(0,1-ct*ct)), linha=[];
  for(i=0;i<=nu;i++){ var ph=i/nu*2*Math.PI, e=[st*Math.cos(ph), st*Math.sin(ph), ct];
   linha.push(v(C, [c[0]+r[0]*e[0], c[1]+r[1]*e[1], c[2]+r[2]*e[2]], norm([e[0]/r[0],e[1]/r[1],e[2]/r[2]]))) }
  ids.push(linha) }
 for(j=0;j<nv;j++) for(i=0;i<nu;i++){ var a=ids[j][i], b=ids[j][i+1], c2=ids[j+1][i], d=ids[j+1][i+1];
  t(C,a,c2,b); t(C,b,c2,d) }
}
function cilindro(C, c, rx, ry, z0, z1, n, tampas){
 var a0=[], a1=[], i, k;
 for(i=0;i<=n;i++){ var ph=i/n*2*Math.PI, e=[Math.cos(ph),Math.sin(ph)], nn=norm([e[0]/rx,e[1]/ry,0]);
  a0.push(v(C,[c[0]+rx*e[0], c[1]+ry*e[1], z0], nn)); a1.push(v(C,[c[0]+rx*e[0], c[1]+ry*e[1], z1], nn)) }
 for(k=0;k<n;k++){ t(C,a0[k],a0[k+1],a1[k]); t(C,a0[k+1],a1[k+1],a1[k]) }
 if(tampas){ [[z0,-1],[z1,1]].forEach(function(tampa){ var cc=v(C,[c[0],c[1],tampa[0]],[0,0,tampa[1]]), aro=[];
  for(var q=0;q<=n;q++){ var ph=q/n*2*Math.PI; aro.push(v(C,[c[0]+rx*Math.cos(ph), c[1]+ry*Math.sin(ph), tampa[0]],[0,0,tampa[1]])) }
  for(var w=0;w<n;w++) t(C,cc,aro[w],aro[w+1]) }) }
}
function bloco(C, c, h){
 var fs=[[[1,0,0],[0,1,0],[0,0,1]],[[-1,0,0],[0,0,1],[0,1,0]],[[0,1,0],[0,0,1],[1,0,0]],
         [[0,-1,0],[1,0,0],[0,0,1]],[[0,0,1],[1,0,0],[0,1,0]],[[0,0,-1],[0,1,0],[1,0,0]]];
 fs.forEach(function(F){ var n=F[0], a=F[1], b=F[2], ids=[];
  [[-1,-1],[1,-1],[1,1],[-1,1]].forEach(function(s){
   ids.push(v(C, [c[0]+(n[0]+a[0]*s[0]+b[0]*s[1])*h[0], c[1]+(n[1]+a[1]*s[0]+b[1]*s[1])*h[1],
                     c[2]+(n[2]+a[2]*s[0]+b[2]*s[1])*h[2]], n)) });
  t(C,ids[0],ids[1],ids[2]); t(C,ids[0],ids[2],ids[3]) });
}
 var S={}, n=[0,-1,0], k=0, x, z;
 var G=construtor();
 for(x=-2200;x<=2200;x+=250){ v(G,[x,1050,-2700],n); v(G,[x,1050,1900],n); G.i.push(k,k+1); k+=2 }
 for(z=-2700;z<=1900;z+=250){ v(G,[-2200,1050,z],n); v(G,[2200,1050,z],n); G.i.push(k,k+1); k+=2 }
 S.piso=subir(G, true);
 var M=construtor(); bloco(M,[0,129,-950],[260,25,1250]); bloco(M,[0,600,-1500],[150,446,250]);
 bloco(M,[0,1035,-1500],[330,15,420]); S.mesa=subir(M, false);
 var P=construtor();
 elipsoide(P,[0,4,18],[76,96,86],40,24); cilindro(P,[0,10],50,48,-120,-30,24,false);
 elipsoide(P,[0,10,-400],[190,105,300],40,24); elipsoide(P,[0,15,-760],[170,96,140],40,24);
 [-1,1].forEach(function(s){ cilindro(P,[s*92,30],66,60,-1680,-840,20,true);
  elipsoide(P,[s*92,30,-1690],[60,55,60],16,10); cilindro(P,[s*232,20],46,44,-740,-160,16,true) });
 S.paciente=subir(P, false);
 var A=construtor(), Rc=760, sec=[[-45,-70],[45,-70],[45,70],[-45,70]], segs=48, aneis=[], i, f;
 for(i=0;i<=segs;i++){ var ph=i/segs*Math.PI, e1=[Math.cos(ph),0,Math.sin(ph)], anel=[];
  sec.forEach(function(s){ anel.push(somar(escalar(e1,Rc+s[0]),[0,s[1],0])) }); aneis.push(anel) }
 for(i=0;i<segs;i++) for(f=0;f<4;f++){ var p0=aneis[i][f], p1=aneis[i][(f+1)%4], q0=aneis[i+1][f], q1=aneis[i+1][(f+1)%4];
  var nn=norm(cruz(menos(p1,p0),menos(q0,p0)));
  var ia=v(A,p0,nn), ib=v(A,p1,nn), ic=v(A,q0,nn), id=v(A,q1,nn); t(A,ia,ib,ic); t(A,ib,id,ic) }
 S.arco=subir(A, false);
 var D=construtor(); bloco(D,[470,0,0],[34,160,160]); bloco(D,[(470+34+Rc)/2,0,0],[(Rc-470-34)/2,46,62]);
 S.detector=subir(D, false);
 var DF=construtor(); bloco(DF,[470,0,0],[30,150,150]); S.detectorF=subir(DF, false);
 var U=construtor(); bloco(U,[-640,0,0],[64,80,90]); bloco(U,[-(Rc+640+64)/2,0,0],[(Rc-640-64)/2,46,62]);
 S.tubo=subir(U, false);
 var B=construtor(); bloco(B,[-60,0,0],[516,78,78]); S.feixe=subir(B, false);
 var R=construtor(); bloco(R,[0,0,Rc],[80,110,70]); S.carro=subir(R, false);
 var Cl=construtor(); cilindro(Cl,[0,0],72,72,Rc+60,Rc+330,24,true);
 bloco(Cl,[0,525,Rc+330],[110,525,110]); bloco(Cl,[0,1035,Rc+330],[380,15,380]);
 S.coluna=subir(Cl, false);
 return S;
}
function radaiPoseArcoC(lao, cra){
 function somar(a,b){ return a.map(function(v,i){ return v+b[i] }) }
 function escalar(a,s){ return a.map(function(v){ return v*s }) }
 var a=lao*Math.PI/180, b=cra*Math.PI/180, e1=[Math.sin(a),-Math.cos(a),0], nn=[Math.cos(a),Math.sin(a),0], e2=[0,0,1];
 var X=somar(escalar(e1,Math.cos(b)), escalar(e2,Math.sin(b))), Z=somar(escalar(e1,-Math.sin(b)), escalar(e2,Math.cos(b)));
 return {M:r3gM4base(X,nn,Z,[0,0,0]), Mc:r3gM4base(e1,nn,e2,[0,0,0])};
}
"""
