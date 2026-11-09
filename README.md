# 3D Reconstructions

**3D Reconstructions is part of the Radioterapia.AI Local Suite and supports three-dimensional anatomy and cranial vascular studies.**

`License: Apache-2.0` · `Component of: Radioterapia.AI Local Suite` · `Platform: Windows 10 and 11, 64-bit`

> **Teaching and research material. This is not a medical device.**
> It is **not** validated for clinical use, and it has no ANVISA registration,
> no CE mark and no FDA clearance. The views display existing segmentation and research annotations.
> Vascular can export one user-drawn consensus contour as an **UNAPPROVED**
> RTSTRUCT referenced to the original DICOM series. Its
> synthetic angiography is image processing and does not replace digital
> subtraction angiography.

## What it does

It opens, in three dimensions, the series that ContourLab segmented. The case
is picked in the Suite's series pop‑up, which opens by itself when the screen
arrives without a case, from the archive table (exam date, patient, modality,
slices, thickness, structures, mode, tasks, when it was contoured), or arrives
from ContourLab's *View segmentation* by a ticket — never by a path in the
URL. The mesh of each structure comes from the RTSTRUCT of that series, or
from the label map of a 3D study; with no segmentation at all, the 3D view
shows bone and skin by CT density. An RTSTRUCT drawn on sagittal, coronal or
oblique slices (an MR, for example) becomes a mesh in place, each contour on
its own slice plane. When the delivered set carries the workstation's own
structure names, bone, vessel, skin and opacity are still decided by the
standard name each structure keeps in its description.

Three tools, inside the suite:

- **General anatomy** — each organ as a 3D mesh with its own transparency,
  the segmentation in the three planes (axial, sagittal and coronal), and MIP
  and MinIP with an adjustable slab (1–100 mm).
- **Thoracic anatomy** — the series that ran the *Thoracic anatomy* study
  protocol in ContourLab's CUSTOM mode: lobes, mediastinum, vessels and the
  rest of that protocol, in 3D. A drawing on the axial slices is interpolated
  between slices and shown in 3D. **Segment new case** opens the Thoracic
  anatomy protocol in ContourLab.
- **Vascular** — MIP and MinIP from cranial CTA or MRA, a tubular
  enhancement computed on the original voxel grid, and an illustrative C-arm
  whose position follows the projection angle. The pencil stores a contour per
  projection. The temperature adjusts the manual consensus between the union
  and intersection of the contours. In the default CT view, bone is taken out of the MIP (the MinIP keeps the whole
  image) through the segmentation ContourLab already wrote for the series
  (its RTSTRUCT or label map, read in memory, with a one‑voxel margin), so a
  calcified vessel stays; without a segmentation that has bone, on a series with Hounsfield
  units, a 700 HU density threshold is the fallback, and a calcified vessel
  or one closer than 2 mm to bone (in the carotid canal, in the transverse
  foramen) goes with it. The screen says which of the two was used, and a
  projection that fails says why; showing the bone gives it back.

The 3D view is drawn in WebGL, written for this module and shared with
Nidus RT (`radai_recon3d_gl`). Without WebGL, General anatomy and Thoracic
anatomy use a point cloud, and Vascular keeps its 2D projections and pencil. It has *See‑through* (bone and skin turn nearly
transparent, and back), LAO/RAO and CRA/CAU bars and eight projections by
button, in the C‑arm convention of Nidus RT: LAO puts the detector on the
patient's left.

**Viewer recordings** are available in MP4 or WebM. Each recording is
a declared act — the person ticks a statement that the video is patient data
before it starts —, and the act is written to `radai_recon3d_atos.log` before
the file leaves. The video may show the patient's face, and it goes to the
browser's downloads folder, which may be in a folder synced to the cloud; the
screen says so beside the statement.

## Research output

Vascular can save a single manual-consensus ROI after verifying the original
DICOM references and comparing the saved contour with the consensus voxel by
voxel. This export requires a separate DICOM image object for each source
slice. The automatic tubular surface stays in the viewer. MIP and MinIP are
static projections of the source image.

## What is ours, and what is not

Anatomy views use existing contours from ContourLab (TotalSegmentator,
Apache‑2.0, for the anatomy). Vascular computes tubular enhancement with
physical-scale image filters. MIP and MinIP are computed with NumPy. Each 3D mesh is built in this
program over a distance field from `scipy.ndimage` (BSD‑3), and drawn in WebGL
written for it, with no third‑party graphics library. These libraries are
installed by the Suite's preparer and do not travel in this repository.

## Privacy

Processing runs locally. When requested, the browser saves the viewer video
or the manual-consensus RTSTRUCT to its downloads folder. Both files may
contain patient data.

## Part of the Local Suite

3D Reconstructions does not run on its own. The shared shell — the entrance
page, the menus, the twelve languages, the Terms and the Privacy Policy, the
configuration, the case archive, DICOM reading, the viewers and the queue —
lives in the [Suite][suite], and on the workstation the suite is one program:
one process, one port, one `app` folder, assembled by the Suite's installer
from the seven repositories. Its core module, `radai_recon3d` (the display
windows, the MIP and MinIP projection and the PNG writer), is also used by the
Suite's thumbnails and by the Nidus RT, Elastic RT and DicomBridge modules,
and the WebGL viewer, `radai_recon3d_gl`, also draws the 3D view of Nidus RT;
the surface of each mesh is built by the 3D Printed Bolus module's code, the
same surface as the bolus.

To use it, install the Suite with its light installer, from the
[releases of drhenriquebraga/local-suite][rel] (the permanent link to the
newest one is [`RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip`][latest]);
requirements and installation are in the Suite README.

This repository has no build of its own. The Suite's packager
(`build/empacotar_instalador.py --dos-repositorios`) downloads each component
at the tag pinned in `build/componentes.lock.json`, checks the SHA‑256 of its
extracted tree against the lock and
assembles the installer — see *Build from source* in the Suite README.

## Running the batteries

The batteries (`tools/test_*.py`, listed in `componente.json`) run over
synthetic phantoms. **No patient data is used anywhere in this repository, and
none may be committed to it.**

1. Put the [Suite][suite] and the six component repositories side by side in
   one folder. Folder names do not matter: the Suite is the folder with
   `tools/_componentes.py`, and each component is found by its
   `componente.json` (or set `RADAI_COMPONENTES_DIR` to the folder that holds
   the components). The batteries import modules of the Suite and of the
   other components, so all seven are needed.
2. Create the Suite's development environment: a Python virtual environment
   in `.venv` at the Suite root, as its README describes.
3. Run every battery of this component:

   ```
   <suite>\.venv\Scripts\python.exe <suite>\tools\_componentes.py --verificar <this folder>
   ```

   or a single one, with `--rodar test_<name>.py`. Each battery ends with an
   `OK:` or a `FALHOU:` footer, and `--verificar` ends with how many failed.
   `verify.cmd`, in this folder, does the same in two clicks once
   `_python.txt` (ignored by Git) holds the path of that `python.exe`.

4. **Turn on the pre‑commit hook** (once per clone):
   `git config core.hooksPath .githooks`. It runs the Suite's
   patient‑data scan over what is staged and refuses the commit that
   carries DICOM (with or without extension), a medical volume or a run
   log — and refuses it too when the scan cannot run, without the Suite
   beside this folder or without Python.

## Reporting a problem

A problem that is not a vulnerability goes through
**[radioterapia.ai](https://radioterapia.ai)**. Include the Local Suite
version, the Windows version, the screen language and the step that
failed — and **never patient data**: no DICOM series, no screenshot of a
patient image, no log with a patient ID, a UID or a series path. A problem
reproduced with the synthetic phantoms of the batteries is the quickest to
fix.

## Security

Found something that exposes patient data or lets the program act where it
should not? **Do not report it in public.** Use GitHub's private
vulnerability reporting on this repository, described in
[SECURITY.md](SECURITY.md).

## Licence and name

The code is licensed under the [Apache License 2.0](LICENSE). As section 6
says, the licence grants no permission to use the trade names of the
Licensor — "Radioterapia.AI" and "Local Suite" included — except as required
to describe the origin of the work. A build you adapt is yours: name it as
yours.

| | Published code | A service's own build |
|---|---|---|
| What it is | Teaching and research material | An in‑house tool the service adapts, validates and registers in its own jurisdiction |
| Medical device? | **No.** Not validated for clinical use | Whatever that service's validation and registration make it |
| Who answers for it | Whoever downloads, modifies and deploys it answers for their own build, made with the Suite's build path | The service that deploys it |

Built by Dr. Henrique Braga, radiation oncologist —
**[radioterapia.ai](https://radioterapia.ai)**.

[suite]: https://github.com/drhenriquebraga/local-suite
[rel]: https://github.com/drhenriquebraga/local-suite/releases
[latest]: https://github.com/drhenriquebraga/local-suite/releases/latest/download/RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip
