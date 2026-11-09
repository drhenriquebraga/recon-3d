import unittest
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import SimpleITK as sitk

import radai_recon3d_vascular_core as V


def tubo():
    z, y, x = np.ogrid[:20, :29, :33]
    return np.where((y - 14)**2 * 0.8**2 + (x - 16)**2 * 0.55**2 < 4.0,
                    np.broadcast_to(410.0, (20, 29, 33)), 30.).astype(np.float32)


class VascularNative(unittest.TestCase):
    def test_cranial_ct_and_mr_tubular_detail(self):
        img = sitk.GetImageFromArray(tubo())
        img.SetSpacing((0.55, 0.8, 1.4))
        img.SetOrigin((12.0, -23.0, 5.0))
        img.SetDirection((0., -1., 0., 1., 0., 0., 0., 0., 1.))
        for modality in ('CT', 'MR'):
            for detail in V.DETALHES:
                with self.subTest(modality=modality, detail=detail):
                    mask = V.realcar(img, modality, detail, 50)
                    self.assertEqual(mask.shape, (20, 29, 33))
                    self.assertTrue(mask[10, 14, 16])
                    self.assertFalse(mask[10, 4, 4])
        with self.assertRaises(V.VascularRecusada):
            V.realcar(img, 'PT', 'equilibrado', 50)
        with self.assertRaises(V.VascularRecusada):
            V.conferir_modalidade('CT', 'CHEST')

    def test_manually_drawn_consensus_has_native_shape(self):
        img = sitk.GetImageFromArray(tubo())
        points = [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]]
        inc = [{'lao': 0, 'cra': 0, 'pontos': points}]
        mask, _ = V.consenso(img, inc, 100)
        self.assertEqual(mask.shape, (20, 29, 33))
        self.assertTrue(mask[10, 14, 16])
        self.assertFalse(mask[10, 14, 1])
        inc[0]['pontos'] = [[0.4, 0.4], [0.6, 0.4], [2, 0.6]]
        with self.assertRaises(V.VascularRecusada):
            V.consenso(img, inc, 100)

    def test_original_ct_and_mr_manual_export_end_to_end(self):
        import pydicom
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pydicom.uid import MRImageStorage
        from make_test_series import escreve_serie
        import radai_recon3d_vascular as screen
        import radai_thumbnail
        app = FastAPI()
        screen.montar(app)
        path = '/api/recon3d/vascular/'
        points = [[0.48, 0.48], [0.53, 0.48], [0.53, 0.53], [0.48, 0.53]]
        with TestClient(app) as client, tempfile.TemporaryDirectory() as tmp:
            for modality in ('CT', 'MR'):
                with self.subTest(modality=modality):
                    folder = Path(tmp) / modality
                    uid = escreve_serie(str(folder), 'SYNTH_VASC_' + modality, datetime.now(), 10)
                    files = sorted(folder.glob('*.dcm'))
                    for file in files:
                        d = pydicom.dcmread(file)
                        d.BodyPartExamined = 'HEAD'
                        if modality == 'MR':
                            d.SOPClassUID = d.file_meta.MediaStorageSOPClassUID = MRImageStorage
                            d.Modality = 'MR'
                            d.PixelSpacing = [1.1, 1.7]
                            d.ImageOrientationPatient = [0.8, 0.6, 0, -0.6, 0.8, 0]
                        y, x = np.ogrid[:d.Rows, :d.Columns]
                        sinal = (y-d.Rows//2)**2 + (x-d.Columns//2)**2 < 9
                        d.PixelData = np.where(sinal, 430, 20).astype('<i2').tobytes()
                        d.save_as(file)
                    b = radai_thumbnail.bilhete(str(folder), uid)
                    for mode in ('mip', 'minip'):
                        response = client.get(path + 'projecao',
                                              params={'b': b, 'modo': mode, 'lado': 256})
                        self.assertEqual(response.status_code, 200, response.content[:120])
                        self.assertEqual(response.headers['content-type'], 'image/png')
                    arvore = client.post(path + 'arvore', json={
                        'b': b, 'detalhe': 'equilibrado', 'sensibilidade': 50})
                    self.assertEqual(arvore.status_code, 200, arvore.content[:120])
                    self.assertNotIn('X-Vascular-Candidate', arvore.headers)
                    self.assertNotIn('Content-Disposition', arvore.headers)
                    invalid = client.post(path + 'exportar', json={'b': b, 'candidato': 'automatica'})
                    self.assertEqual(invalid.status_code, 404)
                    preview = client.post(path + 'consenso', json={
                        'b': b, 'temperatura': 100,
                        'incidencias': [{'lao': 0, 'cra': 0, 'pontos': points},
                                        {'lao': 90, 'cra': 0, 'pontos': points}]})
                    self.assertEqual(preview.status_code, 200, preview.content[:120])
                    data = {'b': b, 'candidato': preview.headers['X-Vascular-Candidate']}
                    cross_site = client.post(path + 'exportar', json=data,
                                             headers={'Origin': 'https://outside.example'})
                    self.assertEqual(cross_site.status_code, 403)
                    wrong_source = client.post(path + 'exportar', json={**data, 'b': 'outro'})
                    self.assertEqual(wrong_source.status_code, 404)
                    exported = client.post(path + 'exportar', json=data)
                    self.assertEqual(exported.status_code, 200, exported.content[:120])
                    self.assertEqual(exported.headers['content-type'], 'application/dicom')
                    rs = pydicom.dcmread(io.BytesIO(exported.content))
                    self.assertEqual(rs.ApprovalStatus, 'UNAPPROVED')
                    self.assertEqual(rs.StructureSetLabel, V.ROTULO)
                    self.assertEqual([roi.ROIName for roi in rs.StructureSetROISequence], [V.ROI_NOME])
                    series = rs.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0]
                    self.assertEqual(series.RTReferencedSeriesSequence[0].SeriesInstanceUID, uid)
                    times = files[0].stat()
                    os.utime(files[0], ns=(times.st_atime_ns, times.st_mtime_ns + 1_000_000_000))
                    self.assertEqual(client.post(path + 'exportar', json=data).status_code, 422)


if __name__ == '__main__':
    unittest.main()
