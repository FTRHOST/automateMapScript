"""
Buat preview_remap.json + (opsional) export _MainTex untuk Unity Editor.
Cara pakai (dari root repo):
  python3 tools/preview_remap.py
Hasil:
  unity/Assets/preview_remap.json -> copy isi folder unity/Assets/ ke Assets/ project Editor,
                                     dibaca oleh FixPinkPreview.cs
  output/textures/<map>/            -> PNG _MainTex kalau texture hasil ripper rusak (opsional reimport)
"""
import json
import os
from pathlib import Path
import UnityPy

ROOT = Path(__file__).resolve().parent.parent
SV_FILE = str(ROOT / "input" / "shaders" / "ShaderVariants.unity3d")
MAPS = [str(ROOT / "input" / "maps" / "PVP_049_add.unity3d"),
        str(ROOT / "input" / "maps" / "PVP_MChampionPBR_ob_add.unity3d")]
JSON_OUT = ROOT / "unity" / "Assets" / "preview_remap.json"
TEX_OUT = ROOT / "output" / "textures"

JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
combined = {}

for mf in MAPS:
    if not os.path.exists(mf):
        print(f"skip {mf} (tidak ada)")
        continue
    env = UnityPy.load(SV_FILE)
    env.load_file(mf)
    print(f"{Path(mf).name}: {len(list(env.objects))} objects (gabungan SV+map)")
    for obj in env.objects:
        if obj.type.name != "Material":
            continue
        if "BuildPlayer-PVP" not in getattr(obj.assets_file, "name", ""):
            continue
        d = obj.read()
        try:
            sh = d.m_Shader.read().m_ParsedForm.m_Name
        except Exception as e:
            sh = f"<ERR {e}>"
        combined[d.m_Name] = sh

with open(JSON_OUT, "w") as f:
    json.dump(combined, f, indent=1, sort_keys=True)
print(f"-> {JSON_OUT.relative_to(ROOT)} ({len(combined)} material)")

# Export _MainTex utama per material (skip yang null) — untuk jaga-jaga reimport
try:
    for mf in MAPS:
        if not os.path.exists(mf):
            continue
        base = os.path.splitext(os.path.basename(mf))[0]
        outdir = TEX_OUT / base
        os.makedirs(outdir, exist_ok=True)
        env = UnityPy.load(SV_FILE)
        env.load_file(mf)
        n = 0
        for obj in env.objects:
            if obj.type.name != "Material":
                continue
            if "BuildPlayer-PVP" not in getattr(obj.assets_file, "name", ""):
                continue
            d = obj.read()
            for tex_name, tex_env in (d.m_SavedProperties.m_TexEnvs or []):
                if tex_name != "_MainTex":
                    continue
                try:
                    tex = tex_env.m_Texture.read()
                except Exception:
                    continue
                if tex is None or getattr(tex, "m_Width", 0) == 0:
                    continue
                try:
                    tex.image.save(os.path.join(outdir, f"{d.m_Name}_MainTex.png"))
                    n += 1
                except Exception as e:
                    print(f"  gagal export {d.m_Name}: {e}")
                break  # 1 texture per material cukup
        print(f"-> {outdir} ({n} PNG)")
except Exception as e:
    print(f"export texture dilewati: {e}")
