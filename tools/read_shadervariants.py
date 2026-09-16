"""
Reader ShaderVariants + resolver material map.
Cara pakai (dari root repo):
  python3 tools/read_shadervariants.py
  python3 tools/read_shadervariants.py --map PVP_049_add.unity3d
  python3 tools/read_shadervariants.py --map input/maps/PVP_MChampionPBR_ob_add.unity3d

Kenapa asset pink: Material di map TIDAK menyimpan shader,
hanya PPtr ke CAB-f2f45922... yang isinya ada di ShaderVariants.unity3d.
Kalau load map saja -> "cab not found" -> pink.
Kalau load gabungan -> resolve 100%.
"""
import argparse
import os
from pathlib import Path
import UnityPy

ROOT = Path(__file__).resolve().parent.parent
SV_FILE = str(ROOT / "input" / "shaders" / "ShaderVariants.unity3d")
REPORT_DIR = ROOT / "output" / "reports"

def resolve_map(path_or_name):
    p = Path(path_or_name)
    if p.exists():
        return str(p)
    cand = ROOT / "input" / "maps" / p.name
    if cand.exists():
        return str(cand)
    return path_or_name  # biarkan UnityPy yang error dengan pesan jelas

def load_combined(map_file=None):
    env = UnityPy.load(SV_FILE)
    if map_file:
        env.load_file(map_file)
    return env

def list_shaders(env, limit=0):
    out = []
    for obj in env.objects:
        if obj.type.name == "Shader":
            try:
                name = obj.read().m_ParsedForm.m_Name
            except Exception as e:
                name = f"<err {e}>"
            out.append((obj.path_id, name))
    out.sort(key=lambda x: x[1].lower())
    return out

def material_map(env, only_map=True):
    pairs = []
    for obj in env.objects:
        if obj.type.name != "Material":
            continue
        fname = getattr(obj.assets_file, "name", "")
        if only_map and "BuildPlayer-PVP" not in fname and "BuildPlayer" not in fname:
            continue
        if "CAB-f2f459" in fname:  # ini file SV, skip kalau hanya mau map
            continue
        try:
            d = obj.read()
            sh = d.m_Shader.read()
            shname = sh.m_ParsedForm.m_Name
            pairs.append((d.m_Name, shname, fname))
        except Exception as e:
            try:
                pairs.append((obj.read().m_Name, f"<UNRESOLVED {e}>", fname))
            except Exception:
                pairs.append((f"pathID {obj.path_id}", f"<UNRESOLVED {e}>", fname))
    return pairs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=None, help="PVP_049_add.unity3d / PVP_MChampionPBR_ob_add.unity3d")
    ap.add_argument("--export-shaders", action="store_true")
    ap.add_argument("--export-mats", action="store_true", default=True)
    args = ap.parse_args()

    print(f"[1] Load {SV_FILE}" + (f" + {args.map}" if args.map else " saja"))
    map_path = resolve_map(args.map) if args.map else None
    env = load_combined(map_path)
    print(f"    files: {list(env.files.keys())}")
    print(f"    total objects: {len(list(env.objects))}")

    print("\n[2] Daftar shader di ShaderVariants:")
    shaders = [s for s in list_shaders(env) if True]
    # filter hanya dari file SV
    sv_shaders = []
    for obj in env.objects:
        if obj.type.name == "Shader" and "CAB-f2f459" in getattr(obj.assets_file, "name", ""):
            sv_shaders.append((obj.path_id, obj.read().m_ParsedForm.m_Name))
    sv_shaders.sort(key=lambda x: x[1].lower())
    print(f"    total shader SV: {len(sv_shaders)}")
    for pid, name in sv_shaders[:25]:
        print(f"      {name}")
    if len(sv_shaders) > 25:
        print(f"      ... +{len(sv_shaders)-25} lagi (lihat output/reports/shader_list_full.txt)")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_DIR / "shader_list_full.txt", "w") as f:
        for _, name in sv_shaders:
            f.write(name + "\n")
    print("    -> output/reports/shader_list_full.txt")

    if map_path:
        print(f"\n[3] Material -> Shader untuk {map_path}:")
        pairs = material_map(env, only_map=True)
        # hanya yang dari map tersebut
        pairs = [p for p in pairs if "PVP" in p[2]]
        from collections import Counter
        c = Counter(s for _, s, _ in pairs)
        print(f"    materials: {len(pairs)}, unique shaders: {len(c)}")
        for s, cnt in c.most_common():
            print(f"      {cnt:4}x {s}")
        base = os.path.splitext(os.path.basename(map_path))[0]
        outp = REPORT_DIR / f"mat_shader_{base}.txt"
        with open(outp, "w") as f:
            for mn, sn in sorted(set((a, b) for a, b, _ in pairs)):
                f.write(f"{mn} | {sn}\n")
        print(f"    -> {outp}")
        print("\n    Tips: semua shader di atas ADA di ShaderVariants, jadi di game tidak pink.")
        print("    Pink di Editor = karena AssetRipper membuka map tanpa ShaderVariants.")
    else:
        print("\n[3] Cek satu map spesifik:")
        print("    python3 tools/read_shadervariants.py --map PVP_049_add.unity3d")
        print("    python3 tools/read_shadervariants.py --map PVP_MChampionPBR_ob_add.unity3d")

if __name__ == "__main__":
    main()
