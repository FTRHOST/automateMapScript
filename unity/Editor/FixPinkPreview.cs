using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEditor;

public class FixPinkPreview : AssetPostprocessor
{
    private static Dictionary<string, string> materialShaderMap = null;

    private static void LoadMap()
    {
        if (materialShaderMap != null) return;
        
        string jsonPath = "Assets/preview_remap.json";
        if (!File.Exists(jsonPath))
        {
            string[] guids = AssetDatabase.FindAssets("preview_remap");
            if (guids.Length > 0)
            {
                jsonPath = AssetDatabase.GUIDToAssetPath(guids[0]);
            }
        }

        if (File.Exists(jsonPath))
        {
            try
            {
                string jsonText = File.ReadAllText(jsonPath);
                // Parse JSON manual sederhana untuk dictionary string -> string
                materialShaderMap = ParseJson(jsonText);
                Debug.Log($"[FixPinkPreview] Loaded {materialShaderMap.Count} material mappings.");
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[FixPinkPreview] Failed to parse preview_remap.json: {e.Message}");
            }
        }
        else
        {
            Debug.LogWarning("[FixPinkPreview] preview_remap.json tidak ditemukan di Assets.");
        }
    }

    [MenuItem("Tools/Fix Pink Materials (Remap Shaders)")]
    public static void FixAllMaterialsInProject()
    {
        LoadMap();
        if (materialShaderMap == null || materialShaderMap.Count == 0)
        {
            Debug.LogError("[FixPinkPreview] Dictionary remapping kosong atau preview_remap.json tidak ditemukan!");
            return;
        }

        string[] guids = AssetDatabase.FindAssets("t:Material");
        int fixedCount = 0;

        foreach (string guid in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) continue;

            if (materialShaderMap.TryGetValue(mat.name, out string targetShaderName))
            {
                Shader targetShader = Shader.Find(targetShaderName);
                if (targetShader != null)
                {
                    mat.shader = targetShader;
                    EditorUtility.SetDirty(mat);
                    fixedCount++;
                }
                else
                {
                    // Fallback jika shader spesifik tidak ada di project Editor (opsional)
                    Shader standardShader = Shader.Find("Standard");
                    if (standardShader != null && mat.shader.name.Contains("Error"))
                    {
                        mat.shader = standardShader;
                        EditorUtility.SetDirty(mat);
                        fixedCount++;
                    }
                }
            }
        }

        AssetDatabase.SaveAssets();
        Debug.Log($"[FixPinkPreview] Selesai remapping. {fixedCount} material diperbaiki.");
    }

    private static Dictionary<string, string> ParseJson(string json)
    {
        var result = new Dictionary<string, string>();
        json = json.Trim('{', '}', '\r', '\n', ' ');
        string[] pairs = json.Split(new[] { ",\n", ",\r\n", "," }, System.StringSplitOptions.RemoveEmptyEntries);
        foreach (var pair in pairs)
        {
            string[] kv = pair.Split(new[] { ':' }, 2);
            if (kv.Length == 2)
            {
                string key = kv[0].Trim(' ', '"', '\t', '\r', '\n');
                string val = kv[1].Trim(' ', '"', '\t', '\r', '\n');
                if (!string.IsNullOrEmpty(key) && !string.IsNullOrEmpty(val))
                {
                    result[key] = val;
                }
            }
        }
        return result;
    }
}
