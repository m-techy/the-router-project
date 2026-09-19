from pathlib import Path


def test_one_command_installers_exist_and_are_idempotent_in_structure():
    shell = Path("install.sh").read_text(encoding="utf-8")
    powershell = Path("install.ps1").read_text(encoding="utf-8")

    assert "git clone --depth 1" in shell
    assert "git -C" in shell
    assert "ROUTER_INSTALL_NO_START" in shell
    assert 'exec "$INSTALL_DIR/start.sh"' in shell

    assert "git clone --depth 1" in powershell
    assert "git -C $InstallDir pull --ff-only" in powershell
    assert "ROUTER_INSTALL_NO_START" in powershell
    assert 'Join-Path $InstallDir "start.bat"' in powershell
