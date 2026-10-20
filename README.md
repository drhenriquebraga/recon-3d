# 3D Reconstructions

**Part of the Radioterapia.AI Local Suite. 3D Reconstructions: three-dimensional study of the cases segmented in ContourLab — teaching and research material, not a medical device.**

`License: Apache-2.0` · `Component of: Radioterapia.AI Local Suite` · `Platform: Windows 10 and 11, 64-bit`

> **Teaching and research material. This is not a medical device.**
> It is **not** validated for clinical use, and it has no ANVISA registration,
> no CE mark and no FDA clearance. It is a study view, used inside the app: it
> exports no mesh and no structure. Every structure it shows was drawn by a
> third‑party model and is an **unapproved suggestion**; reviewing and
> approving structures is a physician's act, in the planning system. Its
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
shows bone and skin by CT density.

Three tools, inside the suite:

- **General anatomy** — each organ as a 3D mesh with its own transparency,
  the segmentation in the three planes (axial, sagittal and coronal), and MIP
  and MinIP with an adjustable slab (1–100 mm).
- **Thoracic anatomy** — the series that ran the *Thoracic anatomy* study
  protocol in ContourLab's CUSTOM mode: lobes, mediastinum, vessels and the
  rest of that protocol, in 3D. A drawing on the axial slices is interpolated
  between slices and shown in 3D; it is yours, and it is not saved.
- **Vascular** — surfaces, the course of the vessels, and synthetic
  two‑dimensional projections in a free incidence (with the AP, Towne and
  Caldwell views at hand). The bone can be taken out of the projection by a
  density threshold, and a vessel closer than 2 mm to bone (in the carotid
  canal, in the transverse foramen) goes with it; showing the bone gives it
  back.

The 3D view is drawn in WebGL, written for this module; where WebGL is
missing, it falls back to a point cloud on a 2D canvas.

**The only export is a video of the viewer** (MP4 or WebM). Each recording is
a declared act — the person ticks a statement that the video is patient data
before it starts —, and the act is written to `radai_recon3d_atos.log` before
the file leaves. The video may show the patient's face, and it goes to the
browser's downloads folder, which may be in a folder synced to the cloud; the
screen says so beside the statement.

## What it does not do

- It does not segment: it consumes what ContourLab has already produced.
- **It does not export** a mesh or a structure. A reconstruction exported as
  a mesh leaves the planning environment and can be taken elsewhere, and an
  export button is a statement of intended use — and intended use defines a
  regulatory class. Inside the app, it is a study view. ContourLab's RTSTRUCT
  goes to the planning system as usual.
- Its synthetic angiography is a projection of the image itself, with no
  segmentation and no beams, and it shows no flow dynamics.

## What is ours, and what is not

No model runs here and no weight is used: the structures are those that
ContourLab's third‑party models drew (TotalSegmentator, Apache‑2.0, for the
anatomy). MIP and MinIP are computed with NumPy. Each 3D mesh is built in this
program over a distance field from `scipy.ndimage` (BSD‑3), and drawn in WebGL
written for it, with no third‑party graphics library. These libraries are
installed by the Suite's preparer and do not travel in this repository.

## Privacy

Everything runs locally. No image, mesh or measurement leaves the workstation
through this module; the one exception is the video above, by a declared act
each time, recorded before it leaves.

## Part of the Local Suite

3D Reconstructions does not run on its own. The shared shell — the entrance
page, the menus, the twelve languages, the Terms and the Privacy Policy, the
configuration, the case archive, DICOM reading, the viewers and the queue —
lives in the [Suite][suite], and on the workstation the suite is one program:
one process, one port, one `app` folder, assembled by the Suite's installer
from the seven repositories. Its core module, `radai_recon3d` (the display
windows, the MIP and MinIP projection and the PNG writer), is also used by the
Suite's thumbnails and by the Nidus RT, Elastic RT and DicomBridge modules;
the surface of each mesh is built by the 3D Printed Bolus module's code, the
same surface as the bolus.

To use it, install the Suite with its light installer, from the
[releases of radioterapia-ai/local-suite][rel] (the permanent link to the
newest one is [`RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip`][latest]);
requirements and installation are in the Suite README.

This repository has no build of its own. The Suite's packager
(`build/empacotar_instalador.py --dos-repositorios`) downloads each component
at the tag pinned in `build/componentes.lock.json`, checks its SHA‑256 and
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

[suite]: https://github.com/radioterapia-ai/local-suite
[rel]: https://github.com/radioterapia-ai/local-suite/releases
[latest]: https://github.com/radioterapia-ai/local-suite/releases/latest/download/RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip
