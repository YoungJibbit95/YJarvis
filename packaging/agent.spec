from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_all("piper")
hiddenimports += collect_submodules("jarvis_agent")
hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    [str(root / "packaging" / "agent_entry.py")],
    pathex=[str(root / "apps" / "agent")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "PyInstaller"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="jarvis-agent", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="jarvis-agent")
