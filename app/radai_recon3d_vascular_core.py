# -*- coding: utf-8 -*-
"""Realce tubular e consenso de lápis são fluxos independentes."""

import hashlib
import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DETALHES = {'equilibrado': (0.8, 1.6), 'fino': (0.45, 0.8, 1.6, 2.5)}
LADO_LAPIS = 1024
MAX_VOXELS = 160_000_000
ROI_CHAVE = 'VascManual'
ROI_NOME = ROI_CHAVE + '_ai'
ROTULO = 'VASC_MANUAL'
SEM_VASOS = 'Nenhum realce tubular nesta configuração.'
MUITA_MALHA = 'A superfície ficou extensa demais para o visor.'
VAZIO = 'Os desenhos não produziram um consenso nesta temperatura.'
INVALIDA = 'Incidência geométrica inválida.'
REF_MUDOU = 'A referência original mudou. Reabra a série e refaça o consenso.'
REF_INCOMPLETA = 'Referências DICOM incompletas.'
PERDA = 'O gravador não conservou o contorno completo.'
MODALIDADE = 'Selecione uma angio-TC ou uma angio-RM de crânio em 3D.'
LIMITE = 'Esta série excede o limite de memória para o processamento 3D.'


class VascularRecusada(ValueError):
    pass


def conferir_modalidade(modalidade, parte=''):
    parte = ''.join(ch for ch in str(parte).upper() if ch.isalnum())
    if (modalidade not in ('CT', 'MR') or parte in {
            'CHEST', 'THORAX', 'ABDOMEN', 'PELVIS', 'ABDOMENPELVIS', 'BREAST',
            'LUNG', 'HEART', 'CARDIAC', 'EXTREMITY', 'UPPEREXTREMITY',
            'LOWEREXTREMITY', 'LSPINE', 'TSPINE', 'KNEE', 'SHOULDER', 'HIP'}):
        raise VascularRecusada(MODALIDADE)


def _tubos_em_bloco(vol, sigma, esp, inicio, fim, piso):
    from scipy import ndimage as ndi
    sig = tuple(sigma / step for step in esp)
    halo = int(4.0 * sig[0] + 0.5) + 1
    lo, hi = max(0, inicio - halo), min(len(vol), fim + halo)
    dados = vol[lo:hi]
    recorte = slice(inicio - lo, fim - lo)
    ativos = (vol[inicio:fim] > piso)
    sinal = np.zeros(ativos.shape, dtype=np.float32)
    if not ativos.any():
        return sinal
    liso = ndi.gaussian_filter(dados, sig, mode='nearest')
    hess = np.empty((np.count_nonzero(ativos), 3, 3), np.float32)
    for i in range(3):
        gradiente = ndi.correlate1d(liso, [-0.5, 0., 0.5], axis=i, mode='nearest')
        for j in range(i, 3):
            deriv = (ndi.correlate1d(liso, [1., -2., 1.], axis=i, mode='nearest') if i == j else
                     ndi.correlate1d(gradiente, [-0.5, 0., 0.5], axis=j, mode='nearest'))
            hess[:, i, j] = deriv[recorte][ativos] * (sig[i] * sig[j])
            hess[:, j, i] = hess[:, i, j]
    vals = np.linalg.eigvalsh(hess)
    vals = np.take_along_axis(vals, np.argsort(np.abs(vals), axis=1), axis=1)
    l1, l2, l3 = vals.T
    eps = np.finfo(np.float32).eps
    tubo = np.square(l2 / np.maximum(np.abs(l3), eps))
    esfera = np.square(l1) / np.maximum(np.abs(l2 * l3), eps)
    forca = np.square(vals).sum(axis=1)
    resposta = -np.expm1(-2 * tubo) * np.exp(-2 * esfera) * -np.expm1(-forca / 0.0032)
    sinal[ativos] = np.where((l2 < 0) & (l3 < 0), resposta, 0)
    return sinal


def realcar(img, modalidade, detalhe, sensibilidade):
    """Resposta tubular bright-on-dark em escalas físicas, na grade original."""
    from scipy import ndimage as ndi
    import SimpleITK as sitk
    conferir_modalidade(modalidade)
    if (not isinstance(detalhe, str) or detalhe not in DETALHES
            or type(sensibilidade) is not int or not 0 <= sensibilidade <= 100):
        raise VascularRecusada('Detalhe ou sensibilidade inválidos.')
    if math.prod(img.GetSize()) > MAX_VOXELS:
        raise VascularRecusada(LIMITE)
    bruto = sitk.GetArrayViewFromImage(img)
    amostra = bruto[::3, ::3, ::3]
    amostra = amostra[np.isfinite(amostra)]
    if not amostra.size:
        raise VascularRecusada(SEM_VASOS)
    if modalidade == 'CT':
        baixo, alto, piso = 0., 600., 100.
    else:
        baixo, alto = np.percentile(amostra, (5, 99.8))
        if alto <= baixo:
            alto = np.max(amostra)
        if alto <= baixo:
            raise VascularRecusada(SEM_VASOS)
        piso = baixo + 0.16 * (alto - baixo)
    vol = np.array(bruto, dtype=np.float32, copy=True)
    np.nan_to_num(vol, copy=False, nan=float(baixo), posinf=float(alto), neginf=float(baixo))
    vol -= baixo
    vol /= alto - baixo
    np.clip(vol, 0., 2., out=vol)
    piso = (piso - baixo) / (alto - baixo)
    esp = img.GetSpacing()[::-1]
    # Halo gaussiano permite processar lotes sem emendas nem reamostragem.
    passo = max(1, 2_100_000 // (vol.shape[1] * vol.shape[2]))
    mask = np.zeros(vol.shape, dtype=bool)
    limiar = 0.34 - 0.0026 * sensibilidade
    for inicio in range(0, len(vol), passo):
        fim = min(inicio + passo, len(vol))
        for sigma in DETALHES[detalhe]:
            mask[inicio:fim] |= _tubos_em_bloco(vol, sigma, esp, inicio, fim, piso) >= limiar
    del vol
    if not mask.any():
        raise VascularRecusada(SEM_VASOS)
    # Remove respostas isoladas sem preencher lacunas ou conectar ramos.
    vizinhos = ndi.convolve(mask.astype(np.uint8), ndi.generate_binary_structure(3, 1),
                             mode='constant', cval=0)
    mask &= vizinhos >= 2
    if not mask.any():
        raise VascularRecusada(SEM_VASOS)
    return mask


def consenso(img, incidencias, temperatura):
    import radai_projection as N
    if math.prod(img.GetSize()) > MAX_VOXELS:
        raise VascularRecusada(LIMITE)
    if not isinstance(incidencias, list) or not 1 <= len(incidencias) <= 12:
        raise VascularRecusada(INVALIDA)
    desenhos = []
    angulos = set()
    for inc in incidencias:
        try:
            lao, cra = (float(inc[chave]) for chave in ('lao', 'cra'))
            pontos = [(float(x), float(y)) for x, y in inc['pontos']]
        except (TypeError, KeyError, ValueError):
            raise VascularRecusada(INVALIDA) from None
        if (not -90 <= lao <= 90 or not -90 <= cra <= 90 or (lao, cra) in angulos
                or not 3 <= len(pontos) <= 512
                or not all(0 <= v <= 1 for ponto in pontos for v in ponto)):
            raise VascularRecusada(INVALIDA)
        angulos.add((lao, cra))
        desenhos.append({'lao': lao, 'cra': cra,
                         'pontos': [(x * LADO_LAPIS, y * LADO_LAPIS) for x, y in pontos]})
    try:
        motor = N.consenso(img, desenhos, lado=LADO_LAPIS)
        mask = motor.mask(temperatura)
    except ValueError as exc:
        raise VascularRecusada(str(exc)) from None
    if not mask.any():
        raise VascularRecusada(VAZIO)
    return mask, motor.incidence_digest


def malha_do_visor(img, mask):
    import radai_recon3d as R
    if np.count_nonzero(mask) > 4_000_000:
        raise VascularRecusada(MUITA_MALHA)
    eixos = tuple(np.flatnonzero(mask.any(axis=tuple(j for j in range(3) if j != i)))
                  for i in range(3))
    if any(not eixo.size for eixo in eixos):
        raise VascularRecusada(SEM_VASOS)
    inicio = tuple(int(eixo[0]) for eixo in eixos)
    caixa = tuple(slice(a, int(eixo[-1]) + 1) for a, eixo in zip(inicio, eixos))
    origem = img.TransformIndexToPhysicalPoint(inicio[::-1])
    verts, faces = R.malha_de_mascara(mask[caixa], img.GetSpacing()[::-1], origem,
                                    img.GetDirection(), suavizar_mm=0.)
    if not len(faces) or len(faces) > 250_000:
        raise VascularRecusada(MUITA_MALHA)
    return R.stl_da_malha(verts, faces)


def geometria(img):
    return img.GetSize(), img.GetSpacing(), img.GetOrigin(), img.GetDirection()


@dataclass(frozen=True)
class Referencia:
    arquivos: tuple
    assinatura: bytes
    serie: str
    estudo: str
    quadro: str
    modalidade: str
    planos: dict


def capturar_referencia(arquivos, uid, tamanho):
    import pydicom
    tags = ['StudyInstanceUID', 'SeriesInstanceUID', 'FrameOfReferenceUID', 'SOPInstanceUID',
            'ImageOrientationPatient', 'ImagePositionPatient', 'PixelSpacing', 'Rows', 'Columns',
            'Modality', 'BodyPartExamined', 'NumberOfFrames', 'PatientID', 'IssuerOfPatientID']
    if not uid or len(arquivos) != tamanho[2]:
        raise VascularRecusada(REF_INCOMPLETA)
    planos, assinatura, identidade = {}, hashlib.sha256(), None
    for arquivo in arquivos:
        arq = Path(arquivo)
        stat = arq.stat()
        d = pydicom.dcmread(str(arq), stop_before_pixels=True, specific_tags=tags, force=True)
        if (not all(tag in d for tag in tags[:10]) or str(d.SeriesInstanceUID) != uid
                or str(d.SOPInstanceUID) in planos or int(d.get('NumberOfFrames', 1)) != 1
                or (int(d.Columns), int(d.Rows)) != tuple(tamanho[:2])):
            raise VascularRecusada(REF_INCOMPLETA)
        conferir_modalidade(str(d.Modality), d.get('BodyPartExamined', ''))
        atual = tuple(str(d.get(tag, '')) for tag in
                      ('StudyInstanceUID', 'FrameOfReferenceUID', 'Modality', 'PatientID', 'IssuerOfPatientID'))
        if identidade is not None and atual != identidade:
            raise VascularRecusada(REF_INCOMPLETA)
        identidade = atual
        pos = np.asarray(d.ImagePositionPatient, dtype=float)
        direcao = np.asarray(d.ImageOrientationPatient, dtype=float)
        if pos.shape != (3,) or direcao.shape != (6,) or not np.isfinite(np.r_[pos, direcao]).all():
            raise VascularRecusada(REF_INCOMPLETA)
        planos[str(d.SOPInstanceUID)] = (pos, np.cross(direcao[:3], direcao[3:]))
        assinatura.update(repr((tuple(str(d.get(tag, '')) for tag in tags),
                                stat.st_size, stat.st_mtime_ns)).encode())
    if identidade is None:
        raise VascularRecusada(REF_INCOMPLETA)
    return Referencia(tuple(arquivos), assinatura.digest(), uid, *identidade[:3], planos)


def _validar_rtstruct(caminho, pasta, ref, mask):
    import pydicom
    from pydicom.uid import RTStructureSetStorage
    from radai_rt import SessaoRT
    from rt_utils import RTStructBuilder
    d = pydicom.dcmread(str(caminho))
    if (str(d.SOPClassUID) != RTStructureSetStorage or str(d.StudyInstanceUID) != ref.estudo
            or d.ApprovalStatus != 'UNAPPROVED' or d.StructureSetLabel != ROTULO):
        raise VascularRecusada(PERDA)
    quadro, = d.ReferencedFrameOfReferenceSequence
    estudo, = quadro.RTReferencedStudySequence
    serie, = estudo.RTReferencedSeriesSequence
    if (str(quadro.FrameOfReferenceUID) != ref.quadro or str(serie.SeriesInstanceUID) != ref.serie
            or {str(i.ReferencedSOPInstanceUID) for i in serie.ContourImageSequence} != set(ref.planos)):
        raise VascularRecusada(PERDA)
    roi, = d.StructureSetROISequence
    contorno, = d.ROIContourSequence
    observacao, = d.RTROIObservationsSequence
    if (roi.ROIName != ROI_NOME or str(roi.ReferencedFrameOfReferenceUID) != ref.quadro
            or roi.ROINumber != contorno.ReferencedROINumber or roi.ROINumber != observacao.ReferencedROINumber
            or 'Consenso geometrico manual' not in observacao.get('ROIObservationDescription', '')
            or not contorno.ContourSequence):
        raise VascularRecusada(PERDA)
    for item in contorno.ContourSequence:
        imagem, = item.ContourImageSequence
        pos, normal = ref.planos[str(imagem.ReferencedSOPInstanceUID)]
        pontos = np.asarray(item.ContourData, dtype=float).reshape(-1, 3)
        if (item.ContourGeometricType != 'CLOSED_PLANAR' or len(pontos) < 3
                or len(pontos) != item.NumberOfContourPoints or not np.isfinite(pontos).all()
                or not np.allclose((pontos - pos) @ normal, 0., atol=1e-3, rtol=0.)):
            raise VascularRecusada(PERDA)
    rt = RTStructBuilder.create_from(dicom_series_path=str(pasta), rt_struct_path=str(caminho))
    leitor = SessaoRT(None, str(caminho), None, mask.shape, [ROI_NOME], rt)
    if not np.array_equal(leitor.mascara(ROI_NOME), mask):
        raise VascularRecusada(PERDA)


def exportar(ref, geo, mask, temperatura, digest, n):
    """Entrega somente o polígono manual validado, na série DICOM original."""
    import engine
    tamanho = geo[0]
    if (mask.shape != tamanho[::-1] or not mask.any()
            or capturar_referencia(ref.arquivos, ref.serie, tamanho).assinatura != ref.assinatura):
        raise VascularRecusada(REF_MUDOU)
    with tempfile.TemporaryDirectory(prefix='radai_vascular_') as tmp:
        for i, arq in enumerate(ref.arquivos):
            shutil.copyfile(arq, Path(tmp) / ('%06d.dcm' % i))
        copia = engine.load_sitk(tmp, ref.serie)
        if not all(np.allclose(a, b, rtol=0., atol=1e-5) for a, b in zip(geo, geometria(copia))):
            raise VascularRecusada(REF_MUDOU)
        del copia
        desc = ('Consenso geometrico manual Vascular. Temperatura %.1f; incidencias %d; SHA256 %s.'
                % (temperatura, n, digest))
        caminho, _ = engine.build_rtstruct(
            tmp, {ROI_CHAVE: mask}, cru=True, descontar=False, suavizar_mm=0., decimar_mm=0.,
            modalidade=ref.modalidade, rotulo=ROTULO,
            origem={ROI_CHAVE: 'recon3d/vascular-manual'}, observacoes={ROI_CHAVE: desc})
        caminho = Path(caminho)
        try:
            try:
                _validar_rtstruct(caminho, tmp, ref, mask)
            except (AttributeError, KeyError, TypeError, ValueError):
                raise VascularRecusada(PERDA) from None
            if capturar_referencia(ref.arquivos, ref.serie, tamanho).assinatura != ref.assinatura:
                raise VascularRecusada(REF_MUDOU)
            return caminho.read_bytes()
        finally:
            caminho.unlink(missing_ok=True)
            if caminho.parent.name.startswith(engine.PREFIXO_TEMP_DO_RS):
                try:
                    caminho.parent.rmdir()
                except OSError:
                    pass
