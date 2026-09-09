import pytest
import asyncio
import logging
import gc
import weakref
from PyQt6.QtWidgets import QApplication
import os
import tempfile


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
    """Reset QSettings before each test."""
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


def pytest_configure(config):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")