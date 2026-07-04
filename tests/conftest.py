import os
import platform
if platform.system() == "Linux":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["DISPLAY"] = ""
    os.environ["WAYLAND_DISPLAY"] = ""

import pytest

@pytest.fixture(scope="session", autouse=True)
def config_app_settings(qapp):
    qapp.setOrganizationName("MineAI-Test")
    qapp.setApplicationName("SNBT-Localizer-Test")

    from PyQt6.QtCore import QSettings
    original_init = QSettings.__init__

    def patched_init(self, *args, **kwargs):
        if args and len(args) >= 2 and args[0] == "MineAI" and args[1] == "SNBT-Localizer":
            args = ("MineAI-Test", "SNBT-Localizer-Test") + args[2:]
        original_init(self, *args, **kwargs)

    QSettings.__init__ = patched_init

@pytest.fixture(scope="session", autouse=True)
def cleanup_qthreads():
    yield
    try:
        from PyQt6.QtCore import QThread
        import time
        time.sleep(0.1)
        threads = list(QThread.allThreads())
        for thread in threads:
            if thread is not None and thread != QThread.currentThread():
                if thread.isRunning():
                    thread.quit()
                    if not thread.wait(5000):
                        thread.terminate()
                        thread.wait()
    except Exception:
        pass
