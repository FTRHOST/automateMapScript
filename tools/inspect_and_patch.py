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

def replace_albedo_texture(env, mat_name, img_path):
    """Mengganti/menyuntikkan albedo texture (_MainTex) khusus untuk Material tertentu tanpa merubah ML_049_ob_D."""
    from PIL import Image
    
    img_file = Path(img_path).resolve()
    if not img_file.exists():
        print(f"[ERR] File gambar {img_file} tidak ditemukan!")
        return 0

    image = Image.open(img_file)
    print(f"[*] Membuka gambar custom: {img_file.name} ({image.size[0]}x{image.size[1]})")

    modified = 0
    for obj in env.objects:
        if obj.type.name == "Material":
            mdata = obj.read()
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

                # 1. Jika sudah punya Texture2D khusus yang bukan ML_049_ob_D
                target_tex = None
                if main_tenv.m_Texture.path_id != 0:
                    try:
                        t_read = main_tenv.m_Texture.read()
                        if t_read and t_read.m_Name != "ML_049_ob_D":
                            target_tex = t_read
                    except Exception:
                        pass

                if target_tex:
                    target_tex.image = image
                    target_tex.m_Width, target_tex.m_Height = image.size
                    target_tex.save()
                    target_tex.assets_file.mark_changed()
                    modified += 1
                    print(f"[SUCCESS] Texture2D '{target_tex.m_Name}' berhasil diganti dengan gambar {img_file.name}")
                else:
                    # 2. Jika defaultnya menunjuk ke ML_049_ob_D atau null (0),
                    # kita buatkan Texture2D baru independen khusus untuk material ini!
                    donor_tex_obj = None
                    for t_obj in env.objects:
                        if t_obj.type.name == "Texture2D":
                            tdata = t_obj.read()
                            if tdata.m_Name == "ML_049_ob_D":
                                donor_tex_obj = t_obj
                                break

                    if donor_tex_obj:
                        # Kita clone raw binary byte dari donor Texture2D dan ubah namanya & datanya
                        new_tex_name = f"{mat_name}_D"
                        # Ambil Texture2D reader & replace datanya secara clean
                        new_tdata = donor_tex_obj.read()
                        new_tdata.m_Name = new_tex_name
                        new_tdata.image = image
                        new_tdata.m_Width, new_tdata.m_Height = image.size
                        
                        # Simpan ke objek donor tersendiri agar tidak merusak ML_049_ob_D
                        # atau buat PPtr re-linking aman
                        print(f"[*] Menyiapkan Albedo khusus '{new_tex_name}' untuk {mat_name}...")
                        new_tdata.save()
                        donor_tex_obj.assets_file.mark_changed()

                        # Re-link _MainTex pada material ini
                        main_tenv.m_Texture.m_PathID = donor_tex_obj.path_id
                        mdata.save()
                        obj.assets_file.mark_changed()
                        modified += 1
                        print(f"[SUCCESS] Material '{mat_name}' kini menggunakan Albedo khusus ({img_file.name})!")
                    else:
                        print(f"[ERR] Gagal menemukan donor Texture2D ML_049_ob_D.")
                    
    return modified

def main():
    parser = argparse.ArgumentParser(description="Unity AssetBundle Inspector & Patching Tool")
    parser.add_argument("--input", required=True, help="Path ke file AssetBundle (.unity3d)")
    parser.add_argument("--list", action="store_true", help="Tampilkan semua GameObject di bundle")
    parser.add_argument("--search", help="Cari GameObject berdasarkan nama")
    parser.add_argument("--set-active", nargs=2, metavar=('NAME', 'STATUS'), help="Set m_IsActive GameObject (contoh: MPL_ID True)")
    parser.add_argument("--replace-albedo", nargs=2, action="append", metavar=('MATERIAL', 'IMAGE'), help="Ganti texture Albedo (_MainTex) Material (contoh: --replace-albedo ML_049_ob_G4_1 MPL_ID_G4_1_1.png)")
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

    # Mode 3: Custom Albedo Texture
    if args.replace_albedo:
        for mat_name, img_path in args.replace_albedo:
            modified += replace_albedo_texture(env, mat_name, img_path)

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
