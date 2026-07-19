"""Import-level guarantees for the graphical entry point on headless test hosts."""

from __future__ import annotations

import ddt_local.desktop_gui as desktop_gui


def test_gui_module_is_importable_without_initialising_a_display():
    # Tkinter is imported only by main(), so controller/service tests work on CI
    # hosts that intentionally do not provide a display server.
    assert callable(desktop_gui.main)
    assert desktop_gui.OLLAMA_DOWNLOAD_URL == "https://ollama.com/download"
