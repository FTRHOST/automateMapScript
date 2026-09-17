"""
Tool CLI & Library untuk Inspeksi dan Patching GameObject / AssetBundle Unity.

Cara Pakai:
1. List semua GameObject dalam file bundle:
   python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --list

2. Cari GameObject dengan nama spesifik (misal: MPL_ID):
   python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --search MPL_ID

3. Edit boolean m_IsActive GameObject MPL_ID menjadi True:
   python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --set-active MPL_ID True --output output/bundles/PVP_MChampionPBR_modified.unity3d

 4. Kombinasi Edit GameObject + Spoof Identitas 049 sekaligus (Siap Pakai di Game):
    python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --set-active MPL_ID True --spoof-as input/maps/PVP_049_add.unity3d --output output/bundles/PVP_049_add_SPOOFED.unity3d

 5. Copy GameObject + atur posisi penempatan (LocalPosition absolut, bisa diulang):
    python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --copy-object MPL_ID_G1_1 MPL_ID_G1_1_COPY 5 0 0 --output output/bundles/PVP_MChampionPBR_copied.unity3d

 6. Copy + rotasi Euler (derajat) + skala, berlaku untuk semua --copy-object dalam command:
    python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --copy-object MPL_ID_G1_1 MPL_ID_G1_1_COPY 5 0 0 --copy-rotation 0 90 0 --copy-scale 2 2 2 --output output/bundles/PVP_MChampionPBR_copied.unity3d

 7. Copy lalu kasih material + albedo sendiri (jalan dalam satu command, urutan otomatis):
    python3 tools/inspect_and_patch.py --input input/maps/PVP_MChampionPBR_ob_add.unity3d --copy-object MPL_ID_G1_1 MPL_COPY 5 0 0 --copy-material MPL_COPY ML_COPY_MAT --replace-albedo ML_COPY_MAT img.png --output output/bundles/hasil.unity3d
"""

import argparse
from pathlib import Path
import UnityPy

ROOT = Path(__file__).resolve().parent.parent

def list_gameobjects(env, search=None, limit=0):
    """Melihat semua GameObject beserta nilai m_IsActive dan PathID."""
    game_objects = []
    for obj in env.objects:
        if obj.type.name == "GameObject":
            try:
                data = obj.read()
                name = data.m_Name
                active = getattr(data, "m_IsActive", None)
                if search:
                    if search.lower() in name.lower():
                        game_objects.append((obj.path_id, name, active, data))
                else:
                    game_objects.append((obj.path_id, name, active, data))
            except Exception as e:
                pass
    return game_objects

def set_gameobject_active(env, target_name, active_status):
    """Mengubah boolean m_IsActive dari GameObject berdasarkan nama persis atau partial match."""
    modified_count = 0
    for obj in env.objects:
        if obj.type.name == "GameObject":
            try:
                data = obj.read()
                if data.m_Name == target_name or target_name.lower() in data.m_Name.lower():
                    old_status = getattr(data, "m_IsActive", None)
                    data.m_IsActive = active_status
                    data.save()  # Simpan perubahan struktur data ke objek serialized
                    obj.assets_file.mark_changed()
                    modified_count += 1
                    print(f"[PATCH] GameObject '{data.m_Name}' (PathID: {obj.path_id}): m_IsActive {old_status} -> {active_status}")
            except Exception as e:
                print(f"[ERR] Gagal merubah GameObject {obj.path_id}: {e}")
    return modified_count

_CLONE_DATA = {}


def _remember(reader, data):
    """Ingat status terakhir objek clone/editan agar terbaca dalam sesi yang sama.

    (UnityPy `read()` selalu parse ulang dari bytes file asli, sehingga hasil
    `save()` dalam sesi sama tidak terlihat tanpa cache ini.)
    """
    try:
        _CLONE_DATA[(id(reader.assets_file), reader.path_id)] = data
    except Exception:
        pass


def _read_fresh(obj):
    """Baca objek, dahulukan status terakhir dari cache sesi bila ada."""
    try:
        key = (id(obj.assets_file), obj.path_id)
        if key in _CLONE_DATA:
            return _CLONE_DATA[key]
    except Exception:
        pass
    return obj.read()


def _euler_to_quaternion(rx_deg, ry_deg, rz_deg):
    """Konversi Euler (derajat, sumbu X/Y/Z) ke quaternion (x, y, z, w) ala Unity (urutan Z, X, Y)."""
    import math
    hx, hy, hz = math.radians(rx_deg) / 2, math.radians(ry_deg) / 2, math.radians(rz_deg) / 2
    sx, cx = math.sin(hx), math.cos(hx)
    sy, cy = math.sin(hy), math.cos(hy)
    sz, cz = math.sin(hz), math.cos(hz)
    # qx, qy, qz lalu q = qy * qx * qz (urutan Unity)
    qx = (sx, 0.0, 0.0, cx)
    qy = (0.0, sy, 0.0, cy)
    qz = (0.0, 0.0, sz, cz)

    def _mul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return (
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        )

    return _mul(qy, _mul(qx, qz))


def _apply_transform(td, position=None, rotation_euler=None, scale=None):
    """Set posisi/rotasi/skala pada Transform yang sudah di-read. Return True bila ada yang diubah."""
    changed = False
    if position is not None:
        td.m_LocalPosition.x, td.m_LocalPosition.y, td.m_LocalPosition.z = position
        changed = True
    if rotation_euler is not None:
        qx, qy, qz, qw = _euler_to_quaternion(*rotation_euler)
        td.m_LocalRotation.x, td.m_LocalRotation.y, td.m_LocalRotation.z, td.m_LocalRotation.w = qx, qy, qz, qw
        changed = True
    if scale is not None:
        td.m_LocalScale.x, td.m_LocalScale.y, td.m_LocalScale.z = scale
        changed = True
    if changed:
        td.save()
    return changed


def _fmt_tr(position=None, rotation_euler=None, scale=None):
    parts = []
    if position is not None:
        parts.append(f"pos=({position[0]}, {position[1]}, {position[2]})")
    if rotation_euler is not None:
        parts.append(f"rot=({rotation_euler[0]}, {rotation_euler[1]}, {rotation_euler[2]})")
    if scale is not None:
        parts.append(f"scale=({scale[0]}, {scale[1]}, {scale[2]})")
    return " ".join(parts) if parts else "tanpa perubahan transform"


def copy_gameobject(env, src_name, new_name, position, rotation_euler=None, scale=None):
    """Clone GameObject beserta komponennya (Transform/MeshFilter/MeshRenderer) + atur transform.

    - Mesh & Material dipakai ulang (pointer sama), jadi tidak menambah ukuran texture.
    - Transform baru didaftarkan sebagai anak dari parent yang sama dengan source.
    - Anak-anak Transform source (misal border `ML_049_ob_*_M`) ikut dicopy rekursif
      dengan nama sama, posisi/rotasi/skala maupun mesh/material diwarisi.
    - Idempoten: kalau `new_name` sudah ada, hanya transformnya yang diupdate.
    - `position` = (x, y, z) LocalPosition absolut.
    - `rotation_euler` = (rx, ry, rz) derajat Euler; `scale` = (sx, sy, sz). Keduanya opsional.
    """
    import copy
    from UnityPy.classes import PPtr

    src_go = None
    for obj in env.objects:
        if obj.type.name == "GameObject":
            try:
                if _read_fresh(obj).m_Name == src_name:
                    src_go = obj
                    break
            except Exception:
                continue
    if src_go is None:
        print(f"[ERR] GameObject '{src_name}' tidak ditemukan!")
        return 0
    sf = src_go.assets_file

    # Idempoten: update transform bila nama baru sudah ada
    for obj in env.objects:
        if obj.type.name == "GameObject" and obj.assets_file is sf:
            try:
                obj_data = _read_fresh(obj)
                if obj_data.m_Name == new_name:
                    for c in obj_data.m_Components:
                        co = sf.objects.get(c.path_id)
                        if co is not None and co.type.name in ("Transform", "RectTransform"):
                            td = _read_fresh(co)
                            _apply_transform(td, position, rotation_euler, scale)
                            _remember(co, td)
                            sf.mark_changed()
                            print(f"[COPY] '{new_name}' sudah ada (PathID: {obj.path_id}), transform diupdate: {_fmt_tr(position, rotation_euler, scale)}")
                            return 1
            except Exception:
                continue

    gd = src_go.read()
    comp_readers = []
    src_t = None
    for c in gd.m_Components:
        co = sf.objects.get(c.path_id)
        if co is None:
            for o in env.objects:
                if o.path_id == c.path_id and o.type.name in ("Transform", "RectTransform", "MeshFilter", "MeshRenderer"):
                    co = o
                    break
        if co is None:
            print(f"[ERR] Komponen PathID {c.path_id} milik '{src_name}' tidak ditemukan, copy dibatalkan.")
            return 0
        comp_readers.append(co)
        if co.type.name in ("Transform", "RectTransform"):
            src_t = co
    if src_t is None:
        print(f"[ERR] GameObject '{src_name}' tidak punya Transform, copy dibatalkan.")
        return 0

    father_pid = src_t.read().m_Father.m_PathID

    def _clone_reader(template):
        nid = max(sf.objects.keys()) + 1
        nr = copy.copy(template)
        nr.path_id = nid
        nr.assets_file = sf
        nr.data = None
        if hasattr(nr, "_read_until"):
            try:
                nr._read_until = None
            except Exception:
                pass
        sf.objects[nid] = nr
        return nr

    clones = {src_go.path_id: _clone_reader(src_go)}
    for co in comp_readers:
        clones[co.path_id] = _clone_reader(co)
    new_go = clones[src_go.path_id]
    new_t = clones[src_t.path_id]

    # Wiring GameObject: nama baru + pointer komponen baru (urutan dipertahankan)
    ngd = new_go.read()
    ngd.m_Name = new_name
    ngd.m_IsActive = True
    for pptr in ngd.m_Components:
        if pptr.m_PathID in clones:
            pptr.m_PathID = clones[pptr.m_PathID].path_id
    ngd.save()
    _remember(new_go, ngd)

    # Wiring Transform: milik GO baru, parent sama, transform baru, tanpa anak
    ntd = new_t.read()
    ntd.m_GameObject.m_PathID = new_go.path_id
    ntd.m_Father.m_PathID = father_pid
    ntd.m_Children = []
    _apply_transform(ntd, position, rotation_euler, scale)
    ntd.save()

    # Daftarkan Transform baru ke children parent
    if father_pid != 0:
        father_reader = sf.objects.get(father_pid)
        if father_reader is not None:
            fd = _read_fresh(father_reader)
            new_ptr = PPtr(m_FileID=0, m_PathID=new_t.path_id, assetsfile=sf)
            fd.m_Children.append(new_ptr)
            fd.save()
            _remember(father_reader, fd)

    # Wiring komponen lain: arahkan m_GameObject ke GO baru (mesh/material dipakai ulang)
    for co in comp_readers:
        if co.path_id in (src_go.path_id, src_t.path_id):
            continue
        nd = clones[co.path_id].read()
        try:
            if hasattr(nd, "m_GameObject"):
                nd.m_GameObject.m_PathID = new_go.path_id
                nd.save()
                _remember(clones[co.path_id], nd)
        except Exception as e:
            print(f"[WARN] Gagal wiring {co.type.name} {clones[co.path_id].path_id}: {e}")
    _remember(new_t, ntd)

    # Rekursif: clone anak-anak (misal border ML_049_ob_*_M) di bawah Transform baru
    child_count = 0
    try:
        for child_ptr in list(_read_fresh(src_t).m_Children):
            child_count += _clone_child_subtree(env, sf, child_ptr, new_t)
    except Exception as e:
        print(f"[WARN] Gagal meng-copy anak '{src_name}': {e}")

    sf.mark_changed()
    print(f"[SUCCESS] Copy '{src_name}' (PathID: {src_go.path_id}) -> '{new_name}' (PathID: {new_go.path_id}): {_fmt_tr(position, rotation_euler, scale)} (+{child_count} anak)")
    return 1


def _clone_child_subtree(env, sf, src_child_t_ptr, new_parent_t_reader):
    """Clone satu anak Transform + GameObject + komponennya di bawah parent baru. Rekursif."""
    import copy
    from UnityPy.classes import PPtr

    src_ct = sf.objects.get(src_child_t_ptr.m_PathID)
    if src_ct is None or src_ct.type.name not in ("Transform", "RectTransform"):
        return 0
    ctd = _read_fresh(src_ct)
    try:
        src_cgo = sf.objects.get(ctd.m_GameObject.m_PathID)
    except Exception:
        src_cgo = None
    if src_cgo is None or src_cgo.type.name != "GameObject":
        return 0

    def _cr(template):
        nid = max(sf.objects.keys()) + 1
        nr = copy.copy(template)
        nr.path_id = nid
        nr.assets_file = sf
        nr.data = None
        if hasattr(nr, "_read_until"):
            try:
                nr._read_until = None
            except Exception:
                pass
        sf.objects[nid] = nr
        return nr

    cgd = _read_fresh(src_cgo)
    clones = {src_cgo.path_id: _cr(src_cgo), src_ct.path_id: _cr(src_ct)}
    for c in cgd.m_Components:
        if c.m_PathID in clones:
            continue
        co = sf.objects.get(c.m_PathID)
        if co is None:
            continue
        clones[c.m_PathID] = _cr(co)
    new_cgo = clones[src_cgo.path_id]
    new_ct = clones[src_ct.path_id]

    # Wiring GO anak (nama dipertahankan, duplikat diizinkan Unity)
    ngd = new_cgo.read()
    for pptr in ngd.m_Components:
        if pptr.m_PathID in clones:
            pptr.m_PathID = clones[pptr.m_PathID].path_id
    try:
        child_name = cgd.m_Name
    except Exception:
        child_name = "?"
    ngd.save()
    _remember(new_cgo, ngd)

    # Wiring Transform anak (posisi/rotasi/skala diwarisi apa adanya)
    ntd = new_ct.read()
    ntd.m_GameObject.m_PathID = new_cgo.path_id
    ntd.m_Father.m_PathID = new_parent_t_reader.path_id
    ntd.m_Children = []
    ntd.save()
    _remember(new_ct, ntd)

    for old_pid, nr in clones.items():
        if old_pid in (src_cgo.path_id, src_ct.path_id):
            continue
        nd = nr.read()
        try:
            if hasattr(nd, "m_GameObject"):
                nd.m_GameObject.m_PathID = new_cgo.path_id
                nd.save()
                _remember(nr, nd)
        except Exception:
            pass

    ptd = _read_fresh(new_parent_t_reader)
    ptd.m_Children.append(PPtr(m_FileID=0, m_PathID=new_ct.path_id, assetsfile=sf))
    ptd.save()
    _remember(new_parent_t_reader, ptd)
    print(f"    [CHILD] '{child_name}' ikut tercopy (PathID: {new_cgo.path_id})")

    count = 1
    for grandchild in list(ctd.m_Children):
        count += _clone_child_subtree(env, sf, grandchild, new_ct)
    return count


def copy_material(env, go_name, new_mat_name):
    """Clone Material milik renderer GameObject agar copy-an punya material sendiri.

    - Material asli tidak disentuh; renderer GO di-point ke clone bernama `new_mat_name`.
    - Idempoten: kalau material `new_mat_name` sudah ada, dipakai ulang (tidak duplikat).
    - Kalau renderer punya >1 material, clone diberi nama `new_mat_name_1`, `_2`, dst.
    - Return jumlah material yang di-point ulang.
    """
    import copy

    target_go = None
    for obj in env.objects:
        if obj.type.name == "GameObject":
            try:
                if _read_fresh(obj).m_Name == go_name:
                    target_go = obj
                    break
            except Exception:
                continue
    if target_go is None:
        print(f"[ERR] GameObject '{go_name}' tidak ditemukan!")
        return 0

    def _resolve_reader(mptr):
        try:
            return mptr.deref()
        except Exception:
            pass
        for o in env.objects:
            if o.path_id == mptr.m_PathID and o.type.name == "Material":
                return o
        return None

    def _find_material_by_name(mat_sf, name):
        for o in mat_sf.objects.values():
            if o.type.name == "Material":
                try:
                    if _read_fresh(o).m_Name == name:
                        return o
                except Exception:
                    continue
        return None

    def _clone_in_file(template_reader, name):
        mat_sf = template_reader.assets_file
        existing = _find_material_by_name(mat_sf, name)
        if existing is not None:
            return existing, False
        nid = max(mat_sf.objects.keys()) + 1
        nr = copy.copy(template_reader)
        nr.path_id = nid
        nr.assets_file = mat_sf
        nr.data = None
        if hasattr(nr, "_read_until"):
            try:
                nr._read_until = None
            except Exception:
                pass
        mat_sf.objects[nid] = nr
        nd = nr.read()
        nd.m_Name = name
        nd.save()
        _remember(nr, nd)
        mat_sf.mark_changed()
        return nr, True

    gd = _read_fresh(target_go)
    remapped = 0
    for c in gd.m_Components:
        rend = None
        for o in env.objects:
            if o.path_id == c.path_id and o.type.name in ("MeshRenderer", "SkinnedMeshRenderer"):
                rend = o
                break
        if rend is None:
            continue
        rd = _read_fresh(rend)
        mats = list(rd.m_Materials)
        if not mats:
            continue
        multi = len(mats) > 1
        for i, mptr in enumerate(mats):
            want = f"{new_mat_name}_{i + 1}" if multi else new_mat_name
            mat_reader = _resolve_reader(mptr)
            if mat_reader is None:
                print(f"[ERR] Material renderer '{go_name}' (slot {i}) tidak bisa di-resolve.")
                continue
            try:
                old_name = mat_reader.read().m_Name
            except Exception:
                old_name = "?"
            new_reader, created = _clone_in_file(mat_reader, want)
            mptr.m_PathID = new_reader.path_id  # m_FileID tetap (file material sama)
            remapped += 1
            print(f"[{'SUCCESS' if created else 'COPY'}] Material '{old_name}' -> '{want}' (PathID: {new_reader.path_id}) untuk '{go_name}'")
        rd.save()
        _remember(rend, rd)
        rend.assets_file.mark_changed()
    if remapped == 0:
        print(f"[WARN] '{go_name}' tidak punya renderer/material untuk di-clone.")
    return remapped


def apply_spoof(bundle, env, donor_name, identity_name):
    """Mengubah identitas internal AssetBundle agar bisa diterima game sebagai target identity."""
    old_lower = donor_name.lower()
    new_lower = identity_name.lower()

    old_build = f"BuildPlayer-{donor_name}"
    new_build = f"BuildPlayer-{identity_name}"

    old_container = f"Assets/Scenes/{donor_name}.unity"
    new_container = f"Assets/Scenes/{identity_name}.unity"

    new_abname = f"assets/res_version/android/scenes/android/{new_lower}.unity3d"

    bundle.name = f"{identity_name}.unity3d"

    # 1. Container
    for k in list(bundle.container.keys()):
        if donor_name in k or old_lower in k.lower():
            nk = k.replace(donor_name, identity_name).replace(old_lower, new_lower)
            bundle.container[nk] = bundle.container.pop(k)

    # 2. Files & Externals
    new_files = {}
    for old_key, sf in list(bundle.files.items()):
        new_key = old_key.replace(old_build, new_build)
        sf.name = sf.name.replace(old_build, new_build)
        for ext in sf.externals:
            if hasattr(ext, "path") and isinstance(ext.path, str):
                if old_lower in ext.path.lower() or old_build.lower() in ext.path.lower():
                    ext.path = ext.path.replace(old_lower, new_lower).replace(old_build.lower(), new_build.lower())
        new_files[new_key] = sf
    bundle.files.clear()
    bundle.files.update(new_files)

    # 3. AssetBundle Struct
    for obj in env.objects:
        if obj.type.name == "AssetBundle":
            data = obj.read()
            data.m_Name = new_abname
            new_cont = []
            for cpath, ainfo in data.m_Container:
                ncpath = cpath.replace(donor_name, identity_name).replace(old_lower, new_lower)
                new_cont.append((ncpath if ncpath else new_container, ainfo))
            data.m_Container = new_cont
            data.save()

    bundle.mark_changed()
    for sf in bundle.files.values():
        sf.mark_changed()

def _clone_texture2d(template_reader, new_name, image):
    """Clone ObjectReader Texture2D menjadi objek baru dengan PathID unik dalam file yang sama.

    Meniru template (import settings/format) tanpa merusak texture asli.
    Return: (new_reader, new_data)
    """
    import copy

    assets_file = template_reader.assets_file
    new_path_id = max(assets_file.objects.keys()) + 1
    new_reader = copy.copy(template_reader)
    new_reader.path_id = new_path_id
    new_reader.assets_file = assets_file
    new_reader.data = None
    if hasattr(new_reader, "_read_until"):
        try:
            new_reader._read_until = None
        except Exception:
            pass
    assets_file.objects[new_path_id] = new_reader

    new_data = new_reader.read()
    new_data.m_Name = new_name
    new_data.image = image
    try:
        new_data.m_Width, new_data.m_Height = image.size
    except Exception:
        pass
    new_data.save()
    _remember(new_reader, new_data)
    assets_file.mark_changed()
    return new_reader, new_data


def _find_texture_template(assets_file, prefer_path_id=478):
    """Cari template Texture2D terbaik untuk di-clone (default ML_049_ob_D)."""
    if prefer_path_id in assets_file.objects:
        cand = assets_file.objects[prefer_path_id]
        if cand.type.name == "Texture2D":
            return cand
    for o in assets_file.objects.values():
        if o.type.name == "Texture2D":
            return o
    return None


def replace_albedo_texture(env, mat_name, img_path, used_tex_path_ids=None):
    """Mengganti/menyuntikkan albedo texture (_MainTex) khusus untuk Material tertentu.

    Setiap material mendapat Texture2D BARU hasil clone (tidak mencuri Normal/PBR),
    sehingga bisa patch 40+ material tanpa kehabisan slot.
    """
    from PIL import Image
    if used_tex_path_ids is None:
        used_tex_path_ids = set()

    img_file = Path(img_path).resolve()
    if not img_file.exists():
        print(f"[ERR] File gambar {img_file} tidak ditemukan!")
        return 0

    image = Image.open(img_file)
    print(f"[*] Membuka gambar custom: {img_file.name} ({image.size[0]}x{image.size[1]})")

    all_objects = list(env.objects)
    modified = 0
    for obj in all_objects:
        if obj.type.name == "Material":
            mdata = _read_fresh(obj)
            if mdata.m_Name == mat_name:
                print(f"[*] Menemukan Material Target: {mdata.m_Name} (PathID: {obj.path_id})")

                # Cari PPtr _MainTex
                main_tenv = None
                for tname, tenv in mdata.m_SavedProperties.m_TexEnvs:
                    if tname == "_MainTex":
                        main_tenv = tenv
                        break

                if not main_tenv:
                    print(f"[ERR] Material '{mat_name}' tidak memiliki property _MainTex")
                    continue

                new_tex_name = f"{mat_name}_D"

                # 1. Idempoten: kalau _MainTex sudah menunjuk ke {mat_name}_D milik sendiri, tinggal timpa image
                try:
                    if main_tenv.m_Texture.path_id != 0:
                        pointed = main_tenv.m_Texture.read()
                        if pointed is not None and getattr(pointed, "m_Name", "") == new_tex_name:
                            pointed_reader = getattr(pointed, "object_reader", None)
                            if pointed_reader is None:
                                # fallback: cari reader via path_id di file yang sama
                                pointed_reader = obj.assets_file.objects.get(main_tenv.m_Texture.path_id)
                            pointed.image = image
                            pointed.m_Width, pointed.m_Height = image.size
                            pointed.save()
                            if pointed_reader is not None:
                                _remember(pointed_reader, pointed)
                                pointed_reader.assets_file.mark_changed()
                                used_tex_path_ids.add(pointed_reader.path_id)
                                print(f"[SUCCESS] Texture2D '{new_tex_name}' (PathID: {pointed_reader.path_id}) berhasil diganti dengan gambar {img_file.name}")
                            else:
                                obj.assets_file.mark_changed()
                                print(f"[SUCCESS] Texture2D '{new_tex_name}' berhasil diganti dengan gambar {img_file.name}")
                            modified += 1
                            continue
                except Exception:
                    pass

                # 2. Kalau ada Texture2D orphan bernama {mat_name}_D (dari run sebelumnya), pakai ulang
                reused = False
                for t_obj in all_objects:
                    if t_obj.type.name == "Texture2D":
                        try:
                            if t_obj.assets_file is not obj.assets_file:
                                continue
                            tdata_probe = _read_fresh(t_obj)
                        except Exception:
                            continue
                        if getattr(tdata_probe, "m_Name", "") == new_tex_name:
                            tdata_probe.image = image
                            tdata_probe.m_Width, tdata_probe.m_Height = image.size
                            tdata_probe.save()
                            _remember(t_obj, tdata_probe)
                            t_obj.assets_file.mark_changed()
                            main_tenv.m_Texture.m_PathID = t_obj.path_id
                            main_tenv.m_Texture.m_FileID = 0
                            mdata.save()
                            obj.assets_file.mark_changed()
                            used_tex_path_ids.add(t_obj.path_id)
                            modified += 1
                            print(f"[SUCCESS] Material '{mat_name}' memakai ulang Texture2D '{new_tex_name}' (PathID: {t_obj.path_id}) dengan {img_file.name}!")
                            reused = True
                            break
                if reused:
                    continue

                # 3. Jalur utama: CLONE Texture2D baru, tidak mencuri slot Normal/PBR
                try:
                    template = _find_texture_template(obj.assets_file, prefer_path_id=478)
                    if template is None:
                        print(f"[ERR] Tidak ada template Texture2D di file material {mat_name}.")
                        continue
                    new_reader, _ = _clone_texture2d(template, new_tex_name, image)
                    # refresh daftar objek agar max(path_id) berikutnya benar
                    all_objects.append(new_reader)
                    main_tenv.m_Texture.m_PathID = new_reader.path_id
                    main_tenv.m_Texture.m_FileID = 0
                    mdata.save()
                    obj.assets_file.mark_changed()
                    used_tex_path_ids.add(new_reader.path_id)
                    modified += 1
                    print(f"[SUCCESS] Material '{mat_name}' kini menggunakan Texture2D Albedo terisolasi '{new_tex_name}' (PathID: {new_reader.path_id}) dengan {img_file.name}!")
                except Exception as e:
                    print(f"[ERR] Gagal mengalokasikan Texture2D khusus untuk {mat_name}: {e}")

    return modified

def main():
    parser = argparse.ArgumentParser(description="Unity AssetBundle Inspector & Patching Tool")
    parser.add_argument("--input", required=True, help="Path ke file AssetBundle (.unity3d)")
    parser.add_argument("--list", action="store_true", help="Tampilkan semua GameObject di bundle")
    parser.add_argument("--search", help="Cari GameObject berdasarkan nama")
    parser.add_argument("--set-active", nargs=2, metavar=('NAME', 'STATUS'), help="Set m_IsActive GameObject (contoh: MPL_ID True)")
    parser.add_argument("--replace-albedo", nargs=2, action="append", metavar=('MATERIAL', 'IMAGE'), help="Ganti texture Albedo (_MainTex) Material (contoh: --replace-albedo ML_049_ob_G4_1 MPL_ID_G4_1_1.png)")
    parser.add_argument("--copy-object", nargs=5, action="append", metavar=('SRC', 'NEW', 'X', 'Y', 'Z'), help="Copy GameObject + atur LocalPosition absolut (contoh: --copy-object MPL_ID_G1_1 MPL_ID_G1_1_COPY 5 0 0)")
    parser.add_argument("--copy-rotation", nargs=3, metavar=('RX', 'RY', 'RZ'), help="Rotasi Euler derajat untuk semua --copy-object (contoh: --copy-rotation 0 90 0)")
    parser.add_argument("--copy-scale", nargs=3, metavar=('SX', 'SY', 'SZ'), help="Skala untuk semua --copy-object (contoh: --copy-scale 2 2 2)")
    parser.add_argument("--copy-material", nargs=2, action="append", metavar=('GAMEOBJECT', 'NEWMAT'), help="Clone material renderer GO agar punya material sendiri (contoh: --copy-material MPL_COPY ML_COPY_MAT)")
    parser.add_argument("--spoof-as", help="Path ke target identity file (contoh: input/maps/PVP_049_add.unity3d)")
    parser.add_argument("--output", help="Path output file .unity3d hasil editan")

    args = parser.parse_args()

    input_path = str(Path(args.input).resolve())
    print(f"[*] Membuka AssetBundle: {input_path}")
    env = UnityPy.load(input_path)

    # Mode 1: List / Search
    if args.list or args.search:
        print(f"\n--- Daftar GameObject ---")
        gos = list_gameobjects(env, search=args.search)
        print(f"Total GameObject ditemukan: {len(gos)}")
        for pid, name, active, _ in gos[:100]:
            print(f"  [PathID: {pid:6}] Name: {name:35} | m_IsActive: {active}")
        if len(gos) > 100:
            print(f"  ... dan {len(gos) - 100} lagi.")
        return

    # Mode 2: Patch Active / Edit Objek
    modified = 0
    if args.set_active:
        target_name, status_str = args.set_active
        is_active = status_str.lower() in ("true", "1", "yes")
        modified += set_gameobject_active(env, target_name, is_active)

    # Mode 3b: Copy GameObject + atur posisi/rotasi/skala (jalan dulu agar
    # --copy-material / --replace-albedo bisa menargetkan hasil copy dalam 1 command)
    if args.copy_object:
        rot = scl = None
        if args.copy_rotation:
            try:
                rot = tuple(float(v) for v in args.copy_rotation)
            except ValueError:
                print(f"[ERR] Rotasi harus angka: {args.copy_rotation}")
                rot = None
        if args.copy_scale:
            try:
                scl = tuple(float(v) for v in args.copy_scale)
            except ValueError:
                print(f"[ERR] Skala harus angka: {args.copy_scale}")
                scl = None
        for src_name, new_name, xs, ys, zs in args.copy_object:
            try:
                pos = (float(xs), float(ys), float(zs))
            except ValueError:
                print(f"[ERR] Posisi harus angka: {xs} {ys} {zs}")
                continue
            modified += copy_gameobject(env, src_name, new_name, pos, rot, scl)

    # Mode 3c: Clone material milik GO (agar copy-an bisa punya albedo sendiri)
    if args.copy_material:
        for go_name, new_mat_name in args.copy_material:
            modified += copy_material(env, go_name, new_mat_name)

    # Mode 3: Custom Albedo Texture
    if args.replace_albedo:
        used_tex_path_ids = set()
        for mat_name, img_path in args.replace_albedo:
            modified += replace_albedo_texture(env, mat_name, img_path, used_tex_path_ids)

    # Mode 4: Spoof Identity (opsional)
    if args.spoof_as:
        identity_path = Path(args.spoof_as)
        donor_name = Path(input_path).stem
        identity_name = identity_path.stem
        print(f"[*] Melakukan spoofing identitas: {donor_name} -> {identity_name}")
        bundle = list(env.files.values())[0]
        apply_spoof(bundle, env, donor_name, identity_name)
        modified += 1

    # Save jika ada perubahan atau dipaksa save
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        bundle = list(env.files.values())[0]
        bundle.mark_changed()
        for sf in bundle.files.values():
            sf.mark_changed()
        raw = bundle.save(packer="lz4")
        with open(out_path, "wb") as f:
            f.write(raw)
        print(f"\n[SUCCESS] File tersimpan ke: {out_path} ({len(raw)/1024/1024:.2f} MB)")
        print(f"File ini siap digunakan oleh game!")
    elif modified > 0:
        print("\n[WARNING] Perubahan dilakukan tetapi --output tidak ditentukan. File tidak disimpan.")

if __name__ == "__main__":
    main()
