import pytest
import asyncio
import logging
import gc
import weakref
from PyQt6.QtWidgets import QApplication
import os
import tempfile


@pytest.fixture(scope="session", autouse=True)
def isolate_qsettings_env(tmp_path_factory):
    """Redirect QSettings (NativeFormat) to a sandbox dir for the whole session.

    The production app and tests both use QSettings("MineAI", "SNBT-Localizer"),
    which maps to ~/.config/MineAI/SNBT-Localizer.conf — the user's REAL saved
    settings (API key pools live there). QSettings is a process singleton keyed
    by org/app, so calling .clear() on it in a test run wipes the live config.
    Point XDG_CONFIG_HOME at a throwaway dir instead so tests can never touch
    it. Session scope + autouse: must run before QSettings is first created."""
    sandbox = tmp_path_factory.mktemp("qsettings-sandbox")
    old_xdg = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(sandbox)
    yield
    if old_xdg is None:
        os.environ.pop("XDG_CONFIG_HOME", None)
    else:
        os.environ["XDG_CONFIG_HOME"] = old_xdg


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication once per session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()


@pytest.fixture(autouse=True)
def clean_qsettings():
    """Reset sandboxed QSettings before/after each test (never the live one)."""
    from PyQt6.QtCore import QSettings
    QSettings("MineAI", "SNBT-Localizer").clear()
    QSettings("MineAI-Test", "SNBT-Localizer-Test").clear()
    yield
    QSettings("MineAI", "SNBT-Localizer").clear()
    QSettings("MineAI-Test", "SNBT-Localizer-Test").clear()


@pytest.fixture(autouse=True)
def clean_temp_files():
    """Clean up temp cache files after each test."""
    yield
    import glob
    for f in glob.glob("/tmp/*.sqlite"):
        try:
            os.unlink(f)
        except:
            pass


@pytest.fixture(autouse=True)
def clean_loggers():
    """Remove QtLoggingHandler from loggers and force cleanup after each test."""
    yield
    # Remove and close QtLoggingHandler from snbt_localizer loggers
    for name in ["snbt_localizer", "snbt_localizer.gui"]:
        logger = logging.getLogger(name)
        handlers_to_remove = []
        for h in logger.handlers[:]:
            if type(h).__name__ == "QtLoggingHandler":
                handlers_to_remove.append(h)
        for h in handlers_to_remove:
            try:
                h.close()
            except:
                pass
            logger.removeHandler(h)
    # Force gc to clean up deleted QObjects
    gc.collect()


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Safety net: no test may perform real network I/O.

    ModelLoader/UpdateChecker/KeyVerifierWorker run in QThreads; a real
    request outliving the test leads to destruction of a running QThread
    during GC, which aborts the interpreter ("QThread: Destroyed while
    thread is still running", SIGABRT/exit 134). Tests that exercise the
    real call chain patch it themselves - their monkeypatch applies later
    and therefore wins over this one."""
    import gui

    async def _silent_fetch(self):
        return None

    async def _silent_check(self):
        return None

    async def _silent_key_test(*args, **kwargs):
        return ("Unreachable", "")

    monkeypatch.setattr(gui.ModelLoader, "fetch", _silent_fetch)
    monkeypatch.setattr(gui.UpdateChecker, "_check_updates", _silent_check)
    monkeypatch.setattr(gui, "test_key_with_question", _silent_key_test)
    yield


def pytest_configure(config):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")