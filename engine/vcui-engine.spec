# PyInstaller spec for the packaged engine: `uv run pyinstaller vcui-engine.spec --noconfirm`.
# One folder (dist/vcui-engine/), not one file: a one-file build would unpack
# several hundred MB to a temp folder on every start.
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

datas, binaries, hiddenimports = [], [], []
for package in ("faster_whisper", "claude_agent_sdk", "openwakeword", "ctranslate2"):
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h
# The SDK's bundled Claude Code CLI (~350 MB) is left out: the engine uses the
# Claude Code installed on the computer, which also holds the person's login.
datas = [entry for entry in datas if "_bundled" not in entry[0].replace("\\", "/")]
binaries = [entry for entry in binaries if "_bundled" not in entry[0].replace("\\", "/")]
datas += collect_data_files("_sounddevice_data", include_py_files=False)
binaries += collect_dynamic_libs("onnxruntime")

a = Analysis(
    ["packaging/entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["vcui_engine.agent_sdk"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="vcui-engine", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="vcui-engine", upx=False)
