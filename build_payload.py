import zipfile
import os

zip_path = r"C:\Users\MrKayes\.gemini\antigravity\scratch\personal-download-manager\payload.zip"
if os.path.exists(zip_path):
    os.remove(zip_path)

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    # 1. Add dist/PDM as app/
    app_root = r"C:\Users\MrKayes\.gemini\antigravity\scratch\personal-download-manager\dist\PDM"
    for root, dirs, files in os.walk(app_root):
        for f in files:
            full_p = os.path.join(root, f)
            rel_p = os.path.relpath(full_p, app_root)
            arc = "app/" + rel_p.replace("\\", "/")
            z.write(full_p, arcname=arc)

    # 2. Add extension as extension/
    ext_root = r"C:\Users\MrKayes\.gemini\antigravity\scratch\personal-download-manager\extension"
    for root, dirs, files in os.walk(ext_root):
        for f in files:
            full_p = os.path.join(root, f)
            rel_p = os.path.relpath(full_p, ext_root)
            arc = "extension/" + rel_p.replace("\\", "/")
            z.write(full_p, arcname=arc)

    # 3. Add pdm_host.exe
    host_exe = r"C:\Users\MrKayes\.gemini\antigravity\scratch\personal-download-manager\pdm_host.exe"
    if os.path.exists(host_exe):
        z.write(host_exe, arcname="pdm_host.exe")

print("Created payload.zip with size:", os.path.getsize(zip_path))
