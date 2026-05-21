import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

# Add resolver package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "resolver"))

# We'll test the functions directly (they are async)
# We mock run_command, ensure_container, etc.

@pytest.mark.asyncio
async def test_install_appimage():
    """install_appimage downloads an AppImage, moves it to /opt/appimages, and returns 0."""
    with patch('penta-resolver.run_command', new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [0, 0]  # first call: download; second: move+chmod
        from penta_resolver import install_appimage
        result = await install_appimage("test-container", "http://example.org/MyApp.AppImage", [])
        assert result == 0
        # Check that the move command contained the correct filename
        assert mock_run.call_count == 2
        move_cmd = mock_run.call_args_list[1][0][0]
        assert "mv /tmp/MyApp.AppImage /opt/appimages/" in move_cmd
        assert "chmod +x /opt/appimages/MyApp.AppImage" in move_cmd

@pytest.mark.asyncio
async def test_install_appimage_download_failure():
    """If download fails, function returns non-zero and does not attempt to move."""
    with patch('penta-resolver.run_command', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = 1  # download failed
        from penta_resolver import install_appimage
        result = await install_appimage("test-container", "http://bad.url/app.AppImage", [])
        assert result == 1
        mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_install_github_python():
    """install_github clones a repo, detects setup.py, and runs pip install."""
    with patch('penta-resolver.run_command', new_callable=AsyncMock) as mock_run:
        # First call: git clone (return 0)
        # Second call: build detection script (return 0)
        mock_run.side_effect = [0, 0]
        from penta_resolver import install_github
        result = await install_github("test-container", "user/mylib", [])
        assert result == 0
        assert mock_run.call_count == 2
        detect_cmd = mock_run.call_args_list[1][0][0]
        assert "git clone https://github.com/user/mylib.git" in mock_run.call_args_list[0][0][0]
        assert "pip install ." in detect_cmd  # the detection script chooses pip

@pytest.mark.asyncio
async def test_install_github_makefile():
    """install_github with a repo that contains a Makefile."""
    with patch('penta-resolver.run_command', new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [0, 0]
        from penta_resolver import install_github
        result = await install_github("test-container", "user/makeapp", [])
        assert result == 0
        detect_cmd = mock_run.call_args_list[1][0][0]
        # The detection script checks for Makefile (after pyproject, cargo) -> should use make && make install
        assert "make && make install" in detect_cmd

@pytest.mark.asyncio
async def test_install_github_clone_failure():
    """If clone fails, return non-zero and do not build."""
    with patch('penta-resolver.run_command', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = 1
        from penta_resolver import install_github
        result = await install_github("test-container", "user/nothing", [])
        assert result == 1
        mock_run.assert_called_once()
