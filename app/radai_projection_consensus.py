import math
import hashlib
import json


class ProjectionConsensus:
    def __init__(self, img, incidences, lado=1024, chunk_voxels=262144):
        import numpy as np
        from scipy import ndimage
        import radai_projection as N
        if not isinstance(incidences, (list, tuple)) or not 1 <= len(incidences) <= 12:
            raise ValueError('O consenso exige de uma a doze incidências registradas.')
        if type(lado) is not int or not 16 <= lado <= 1024:
            raise ValueError('Grade da incidência inválida.')
        if type(chunk_voxels) is not int or chunk_voxels < 8:
            raise ValueError('Limite de memória do consenso inválido.')
        if img.GetDimension() != 3 or img.GetNumberOfComponentsPerPixel() != 1:
            raise ValueError('O consenso exige uma referência escalar tridimensional.')
        self.geometry = {key: list(value) for key, value in (
            ('size', img.GetSize()), ('spacing', img.GetSpacing()),
            ('origin', img.GetOrigin()), ('direction', img.GetDirection()))}
        if (not all(math.isfinite(float(v)) for key, values in self.geometry.items() for v in values)
                or any(v <= 0 for v in self.geometry['spacing']) or min(self.geometry['size']) < 1):
            raise ValueError('Geometria de referência inválida.')
        direction = np.asarray(self.geometry['direction']).reshape(3, 3)
        if not np.allclose(direction.T @ direction, np.eye(3), atol=1e-5):
            raise ValueError('A referência exige direções ortonormais válidas.')
        self.eixos = N.eixos_lps(img)
        self.lado, self.chunk_voxels, self.max_chunk_voxels = lado, chunk_voxels, 0
        self.diag, self.step, _pf, _f = N._medidas_da_grade(img, lado)
        self.centre = N.centro_da_grade(img)
        self.outside = -max(self.diag * 4., 1.)
        self.fields, self.transforms, self.incidences = [], [], []
        for inc in incidences:
            try:
                lao, cra = float(inc.get('lao', 0)), float(inc.get('cra', 0))
                points = [(float(point[0]), float(point[1])) for point in inc['pontos']]
            except (TypeError, KeyError, IndexError, ValueError):
                raise ValueError('Incidência geométrica inválida.') from None
            if (not math.isfinite(lao) or not math.isfinite(cra) or len(points) > 2000
                    or len(points) < 3 or not all(math.isfinite(v) for point in points for v in point)):
                raise ValueError('Incidência geométrica inválida.')
            mask = N._mascara_poligono(points, lado)
            if not mask.any():
                field = np.full(mask.shape, self.outside, dtype=np.float32)
            elif mask.all():
                field = np.full(mask.shape, -self.outside, dtype=np.float32)
            else:
                field = (ndimage.distance_transform_edt(mask, sampling=(self.step, self.step))
                         - ndimage.distance_transform_edt(~mask, sampling=(self.step, self.step))).astype(np.float32)
            self.fields.append(field)
            self.transforms.append(N._transformada(img, lao, cra))
            self.incidences.append({'lao': lao, 'cra': cra, 'pontos': points})
        self.incidence_digest = hashlib.sha256(json.dumps(self.incidences, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    @staticmethod
    def temperature(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('A temperatura geométrica deve estar entre 0 e 100.')
        return float(value)

    def _blocks(self, size):
        X, Y, Z = (int(v) for v in size)
        bx = min(X, max(8, (min(X, self.chunk_voxels) // 8) * 8))
        by = min(Y, max(1, self.chunk_voxels // bx))
        bz = min(Z, max(1, self.chunk_voxels // (bx * by)))
        for z in range(0, Z, bz):
            for y in range(0, Y, by):
                for x in range(0, X, bx):
                    yield (x, y, z), (min(bx, X-x), min(by, Y-y), min(bz, Z-z))

    def _classify(self, temperature, start, size):
        import numpy as np
        import SimpleITK as sitk
        t = self.temperature(temperature)
        target = sitk.Image(list(size), sitk.sitkUInt8)
        target.SetSpacing(self.geometry['spacing'])
        target.SetDirection(self.geometry['direction'])
        D = np.asarray(self.geometry['direction']).reshape(3, 3)
        origin = np.asarray(self.geometry['origin']) + D @ (np.asarray(self.geometry['spacing']) * start)
        target.SetOrigin(tuple(origin))
        count = math.prod(size)
        self.max_chunk_voxels = max(count, self.max_chunk_voxels)
        values = np.empty((count, len(self.fields)), dtype=np.float32)
        for index, (field, transform) in enumerate(zip(self.fields, self.transforms)):
            image = sitk.GetImageFromArray(np.repeat(field[::-1, None, :], 2, axis=1))
            image.SetSpacing((self.step, self.diag, self.step))
            image.SetOrigin(tuple(v-self.diag/2. for v in self.centre))
            sampled = sitk.Resample(image, target, transform, sitk.sitkNearestNeighbor,
                                   self.outside, sitk.sitkFloat32)
            values[:, index] = sitk.GetArrayViewFromImage(sampled).reshape(-1)
        values.sort(axis=1)
        rank = (1.-t/100.) * (len(self.fields)-1)
        low = int(math.floor(rank))
        high = min(low+1, len(self.fields)-1)
        alpha = rank-low
        field = (1.-alpha)*values[:, low] + alpha*values[:, high]
        return (field >= 0).reshape(tuple(reversed(size)))

    def packed(self, temperature, progress=None):
        import numpy as np
        import radai_projection as N
        t = self.temperature(temperature)
        X, Y, Z = self.geometry['size']
        bits = np.zeros((Z, Y, (X+7)//8), dtype=np.uint8)
        completed, total = 0, X*Y*Z
        for start, size in self._blocks((X, Y, Z)):
            x, y, z = start
            nx, ny, nz = size
            mask = self._classify(t, start, size)
            bits[z:z+nz, y:y+ny, x//8:(x+nx+7)//8] = np.packbits(mask, axis=-1)
            completed += nx*ny*nz
            if progress is not None:
                progress(completed/total)
        return N.Compacto(bits, (Z, Y, X))

    def mask(self, temperature):
        import numpy as np
        packed = self.packed(temperature)
        return np.unpackbits(packed.bits, axis=-1, count=packed.shape[2]).astype(bool)

    def plane(self, temperature, eixo, indice, eixos=None):
        import numpy as np
        import radai_projection as N
        eixos = self.eixos if eixos is None else eixos
        if type(eixo) is not int or eixo not in (0, 1, 2) or type(indice) is not int:
            raise ValueError('Plano do consenso inválido.')
        native_axis = eixos[0][eixo]
        size = list(self.geometry['size'])
        dimension = 2-native_axis
        if not 0 <= indice < size[dimension]:
            raise ValueError('Corte do consenso fora da referência.')
        start = [0, 0, 0]
        start[dimension] = size[dimension]-1-indice if eixos[1][eixo] else indice
        size[dimension] = 1
        plane = np.zeros(tuple(reversed(size)), dtype=bool)
        for local, extent in self._blocks(size):
            x, y, z = local
            nx, ny, nz = extent
            absolute = [start[k]+local[k] for k in range(3)]
            plane[z:z+nz, y:y+ny, x:x+nx] = self._classify(temperature, absolute, extent)
        return N.corte(N.para_lps(plane, eixos), eixo, 0)
