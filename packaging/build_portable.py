from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def build_portable_distribution() -> int:
    """
    Package Amadeus Kurisu into a portable Windows folder (`dist/AmadeusKurisu/`)
    ready to zip and share with a friend. Preserves existing `data/` across rebuilds.
    """
    project_root = Path(__file__).resolve().parent.parent
    entry_script = project_root / "src" / "amadeus" / "main.py"
    dist_dir = project_root / "dist"
    work_dir = project_root / "build"
    bundle_dir = dist_dir / "AmadeusKurisu"
    portable_data = bundle_dir / "data"

    # Backup existing user data (settings.json, USER.md, avatar.vrm) before PyInstaller cleans dist
    backup_dir = Path(tempfile.mkdtemp(prefix="amadeus_data_bak_"))
    has_backup = False
    if portable_data.exists():
        shutil.copytree(portable_data, backup_dir / "data")
        has_backup = True

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name=AmadeusKurisu",
        "--onedir",
        f"--paths={project_root / 'src'}",
        f"--add-data={project_root / 'config'};config",
        f"--add-data={project_root / 'skills'};skills",
        f"--distpath={dist_dir}",
        f"--workpath={work_dir}",
        str(entry_script),
    ]
    print("Construyendo distribución portable de Amadeus Kurisu...")
    res = subprocess.run(cmd, cwd=str(project_root), check=False)
    if res.returncode != 0:
        print("Error durante el empaquetado con PyInstaller.")
        return res.returncode

    if has_backup and (backup_dir / "data").exists():
        if portable_data.exists():
            shutil.rmtree(portable_data)
        shutil.copytree(backup_dir / "data", portable_data)
        shutil.rmtree(backup_dir, ignore_errors=True)
    else:
        portable_data.mkdir(parents=True, exist_ok=True)

    # Create quick-launch batch files for Desktop Overlay (Electron) and Web Mode
    launcher_bat = bundle_dir / "Iniciar_Amadeus_Kurisu.bat"
    launcher_bat.write_text(
        "@echo off\r\n"
        "title Amadeus System // Makise Kurisu\r\n"
        "set ELECTRON_RUN_AS_NODE=\r\n"
        "set AMADEUS_DATA_DIR=%~dp0data\r\n"
        "if exist \"%~dp0..\\..\\desktop\\node_modules\\.bin\\electron.cmd\" (\r\n"
        "    start \"\" \"%~dp0..\\..\\desktop\\node_modules\\.bin\\electron.cmd\" \"%~dp0..\\..\\desktop\"\r\n"
        ") else (\r\n"
        "    \"%~dp0AmadeusKurisu.exe\" --onboarding\r\n"
        ")\r\n",
        encoding="utf-8",
    )
    print(f"Empaquetado completado con éxito en: {bundle_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(build_portable_distribution())
