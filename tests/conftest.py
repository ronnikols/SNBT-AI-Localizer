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
