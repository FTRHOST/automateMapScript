// FixPinkPreview.cs — taruh di Assets/Editor/ project Unity 2019.4 kamu.
// Menu: Tools > PVP > Fix Pink Preview
// Fungsi: ganti shader yang missing (pink) dengan shader Built-in agar bisa editing.
// PENTING: ini hanya untuk PREVIEW di Editor. Jangan build bundle game dari project
// yang sudah di-remap — bundle final harus pakai shader asli (lihat catatan di bawah).

#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;
using System.Collections.Generic;
using System.IO;

public static class FixPinkPreview
{
    // Prioritas keyword -> shader pengganti (dicek berurutan)
    static readonly string[] AdditiveKeys = {
        "additive", "add_", "_add", "fresnel", "dissolv", "distort", "disturbance",
        "forcefield", "glass", "fx_", "particlefx_pa_add", "blendeduv_ml", "warp"
    };
    static readonly string[] AlphaBlendKeys = {
        "blend", "river", "crystal", "reflection", "mirror", "water",
        "particlefx_pa_blend", "blended", "effect", "indicator", "warp",
        "transparent", "avpro", "uiclip", "ngui"
    };
    static readonly string[] CutoutKeys = {
        "plant", "grass", "mergealpha", "cutout", "alphatest"
    };

    const string SH_OPAQUE   = "Standard";
    const string SH_ADD      = "Legacy Shaders/Particles/Additive";
    const string SH_BLEND    = "Legacy Shaders/Particles/Alpha Blended";
    const string SH_TRANS    = "Legacy Shaders/Transparent/Diffuse";
    const string SH_CUTOUT   = "Legacy Shaders/Transparent/Cutout/Diffuse";
    const string SH_FALLBACK = "Mobile/Diffuse";

    [MenuItem("Tools/PVP/Fix Pink Preview (Remap)")]
    public static void FixAll()
    {
        string[] guids = AssetDatabase.FindAssets("t:Material");
        int fixedCount = 0, skipped = 0;
        foreach (string g in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(g);
            Material m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null) continue;
            if (!IsPink(m)) { skipped++; continue; }
            string origShader = GetOriginalShaderName(m); // dari userData mapping jika ada
            string target = PickReplacement(m.name, origShader);
            Shader s = Shader.Find(target) ?? Shader.Find(SH_FALLBACK);
            if (s == null) continue;
            Undo.RecordObject(m, "Fix pink");
            // _MainTex, _Color, _MaskTex dipertahankan otomatis karena nama properti sama
            m.shader = s;
            // simpan shader asli di userData agar tidak hilang info (untuk referensi build final)
            if (!string.IsNullOrEmpty(origShader) && !m.name.StartsWith("[PVP]"))
            {
                // tandai sudah di-fix, jangan double-tag
                m.name = m.name; // no-op, info asli ada di preview_remap.json
            }
            EditorUtility.SetDirty(m);
            fixedCount++;
        }
        AssetDatabase.SaveAssets();
        Debug.Log($"[PVP] FixPink selesai: {fixedCount} material di-remap, {skipped} sudah OK.");
    }

    [MenuItem("Tools/PVP/Cek Material Masih Pink")]
    public static void CountPink()
    {
        string[] guids = AssetDatabase.FindAssets("t:Material");
        List<string> pink = new List<string>();
        foreach (string g in guids)
        {
            Material m = AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g));
            if (m != null && IsPink(m)) pink.Add(m.name);
        }
        Debug.Log($"[PVP] Material pink: {pink.Count}/{guids.Length}");
        foreach (var n in pink.GetRange(0, System.Math.Min(20, pink.Count)))
            Debug.Log("  pink: " + n);
    }

    static bool IsPink(Material m)
    {
        if (m.shader == null) return true;
        string n = m.shader.name;
        return n.Contains("InternalError") || n == "Hidden/InternalErrorShader";
    }

    // Baca mapping asli dari Assets/preview_remap.json (dibuat oleh preview_remap.py).
    // Format: { "MaterialName": "Original/Shader/Name", ... }
    // Kalau file tidak ada, return "" dan keputusan remap pakai nama material saja.
    static Dictionary<string, string> _cache;
    static string GetOriginalShaderName(Material m)
    {
        if (_cache == null)
        {
            _cache = new Dictionary<string, string>();
            string p = "Assets/preview_remap.json";
            if (File.Exists(p))
            {
                try
                {
                    string json = File.ReadAllText(p);
                    // parse sederhana tanpa dependensi: "key": "value"
                    var lines = json.Split('\n');
                    foreach (var ln in lines)
                    {
                        int k1 = ln.IndexOf('"'); if (k1 < 0) continue;
                        int k2 = ln.IndexOf('"', k1 + 1); if (k2 < 0) continue;
                        int v1 = ln.IndexOf('"', k2 + 1); if (v1 < 0) continue;
                        int v2 = ln.IndexOf('"', v1 + 1); if (v2 < 0) continue;
                        _cache[ln.Substring(k1 + 1, k2 - k1 - 1)] = ln.Substring(v1 + 1, v2 - v1 - 1);
                    }
                    Debug.Log($"[PVP] preview_remap.json loaded: {_cache.Count} entries.");
                }
                catch (System.Exception e) { Debug.LogWarning("[PVP] gagal baca preview_remap.json: " + e.Message); }
            }
        }
        string v;
        return _cache.TryGetValue(m.name, out v) ? v : "";
    }

    static string PickReplacement(string matName, string origShader)
    {
        string hay = (matName + " " + origShader).ToLowerInvariant();
        foreach (var k in AdditiveKeys)   if (hay.Contains(k)) return SH_ADD;
        foreach (var k in CutoutKeys)     if (hay.Contains(k)) return SH_CUTOUT;
        foreach (var k in AlphaBlendKeys) if (hay.Contains(k)) return SH_BLEND;
        // river/reflection/crystal yang butuh lighting sederhana -> transparent diffuse
        if (hay.Contains("river") || hay.Contains("reflection") || hay.Contains("crystal"))
            return SH_TRANS;
        return SH_OPAQUE;
    }
}
#endif
