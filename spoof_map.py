"""
Spoofing grafis Unity AssetBundle:
  Game meminta PVP_049_add.unity3d
  Tapi konten yang dijalankan = PVP_MChampionPBR_ob_add.unity3d

Teknik: ambil ISI dari MChampion (donor), lalu patch IDENTITAS-nya
(nama bundle, container, AssetBundle m_Name, SerializedFile name, externals)
agar sama persis dengan 049 (target). Hasilnya game mengira ini file 049.

Cara pakai:
  python3 spoof_map.py
  -> menghasilkan PVP_049_add_SPOOFED.unity3d
  -> backup asli, lalu rename hasil menjadi PVP_049_add.unity3d di folder game
"""
import os
import UnityPy

DONOR_FILE = "PVP_MChampionPBR_ob_add.unity3d"   # isi grafis yang diinginkan
IDENTITY_FILE = "PVP_049_add.unity3d"            # identitas yang ditiru
OUTPUT_FILE = "PVP_049_add_SPOOFED.unity3d"

OLD_SCENE = "PVP_MChampionPBR_ob_add"
NEW_SCENE = "PVP_049_add"

OLD_LOWER = OLD_SCENE.lower()
NEW_LOWER = NEW_SCENE.lower()

OLD_BUILD = f"BuildPlayer-{OLD_SCENE}"
NEW_BUILD = f"BuildPlayer-{NEW_SCENE}"

OLD_CONTAINER = f"Assets/Scenes/{OLD_SCENE}.unity"
NEW_CONTAINER = f"Assets/Scenes/{NEW_SCENE}.unity"

OLD_ABNAME = f"assets/res_version/android/scenes/android/{OLD_LOWER}.unity3d"
NEW_ABNAME = f"assets/res_version/android/scenes/android/{NEW_LOWER}.unity3d"

OLD_ARCHIVE = f"archive:/{OLD_BUILD.lower()}/{OLD_BUILD.lower()}.sharedassets"
NEW_ARCHIVE = f"archive:/{NEW_BUILD.lower()}/{NEW_BUILD.lower()}.sharedassets"

print(f"[1/5] Load donor (isi): {DONOR_FILE}")
env = UnityPy.load(DONOR_FILE)
bundle = list(env.files.values())[0]
print(f"      bundle.name={bundle.name}")
print(f"      container={list(bundle.container.keys())}")
print(f"      files={list(bundle.files.keys())}")
print(f"      total objects={len(list(env.objects))}")

print(f"[2/5] Patch identitas -> meniru {IDENTITY_FILE} ({NEW_SCENE})")

# 2a. bundle.name & bundle.container
bundle.name = f"{NEW_SCENE}.unity3d"
if OLD_CONTAINER in bundle.container:
    bundle.container[NEW_CONTAINER] = bundle.container.pop(OLD_CONTAINER)
    print(f"      container: {OLD_CONTAINER} -> {NEW_CONTAINER}")
else:
    # fallback: replace any key containing OLD_SCENE
    for k in list(bundle.container.keys()):
        if OLD_SCENE in k or OLD_LOWER in k.lower():
            nk = k.replace(OLD_SCENE, NEW_SCENE).replace(OLD_LOWER, NEW_LOWER)
            bundle.container[nk] = bundle.container.pop(k)
            print(f"      container: {k} -> {nk}")

# 2b. rename SerializedFiles (bundle.files keys + sf.name)
new_files = {}
for old_key, sf in list(bundle.files.items()):
    new_key = old_key.replace(OLD_BUILD, NEW_BUILD)
    old_sf_name = sf.name
    sf.name = sf.name.replace(OLD_BUILD, NEW_BUILD)
    print(f"      SerializedFile: {old_key} -> {new_key} (sf.name: {old_sf_name} -> {sf.name})")
    # 2c. patch externals (archive:/buildplayer-xxx/...)
    for ext in sf.externals:
        if hasattr(ext, "path") and isinstance(ext.path, str):
            if OLD_LOWER in ext.path.lower() or OLD_BUILD.lower() in ext.path.lower():
                old_p = ext.path
                ext.path = ext.path.replace(OLD_LOWER, NEW_LOWER).replace(OLD_BUILD.lower(), NEW_BUILD.lower())
                # pastikan exact archive path benar
                print(f"        external: {old_p} -> {ext.path}")
    new_files[new_key] = sf
bundle.files.clear()
bundle.files.update(new_files)

# 2d. patch AssetBundle object (m_Name + m_Container)
patched_ab = 0
for obj in env.objects:
    if obj.type.name == "AssetBundle":
        data = obj.read()
        print(f"      AssetBundle pathID={obj.path_id} file={obj.assets_file.name}")
        print(f"        m_Name lama: {data.m_Name}")
        print(f"        m_Container lama: {[c for c,_ in data.m_Container]}")
        if OLD_ABNAME.lower() in str(data.m_Name).lower() or OLD_LOWER in str(data.m_Name).lower():
            data.m_Name = NEW_ABNAME
        else:
            # paksa samakan walau format beda
            data.m_Name = NEW_ABNAME
        new_cont = []
        for cpath, ainfo in data.m_Container:
            ncpath = cpath.replace(OLD_SCENE, NEW_SCENE).replace(OLD_LOWER, NEW_LOWER)
            if cpath != ncpath:
                print(f"        m_Container: {cpath} -> {ncpath}")
            new_cont.append((ncpath if ncpath else NEW_CONTAINER, ainfo))
        data.m_Container = new_cont
        print(f"        m_Name baru: {data.m_Name}")
        data.save()
        patched_ab += 1

print(f"      total AssetBundle dipatch: {patched_ab}")

# Tandai bundle berubah agar env.save() mau menulis
bundle.mark_changed()
for sf in bundle.files.values():
    sf.mark_changed()

print("[3/5] Simpan hasil spoof...")
os.makedirs("output", exist_ok=True)
# env.save menulis ke output/<basename>. UnityPy memakai basename dari fname key.
# Agar nama output pasti, kita save manual via bundle.save() lalu tulis file.
raw = bundle.save(packer="lz4")
out_path = os.path.join("output", OUTPUT_FILE)
with open(out_path, "wb") as f:
    f.write(raw)
print(f"      tersimpan: {out_path} ({len(raw)/1024/1024:.2f} MB)")

print("[4/5] Verifikasi ulang hasil...")
env2 = UnityPy.load(out_path)
b2 = list(env2.files.values())[0]
print(f"      bundle.name={b2.name}")
print(f"      container={list(b2.container.keys())}")
print(f"      files={list(b2.files.keys())}")
print(f"      total objects={len(list(env2.objects))} (harus ~15404 = isi MChampion)")
for obj in env2.objects:
    if obj.type.name == "AssetBundle":
        d = obj.read()
        print(f"      AssetBundle m_Name={d.m_Name}")
        print(f"      AssetBundle m_Container={[c for c,_ in d.m_Container]}")
        break
for _, sf in b2.files.items():
    for e in sf.externals:
        print(f"      external {sf.name}: {e.path}")
    break

print("[5/5] Selesai.")
print(f"  Cara pakai di game:")
print(f"   1. Backup {IDENTITY_FILE} asli")
print(f"   2. Copy output/{OUTPUT_FILE} -> {IDENTITY_FILE} (timpa / rename)")
print(f"   3. Game yang load PVP_049_add akan menampilkan map MChampionPBR")
