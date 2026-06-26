# SNBT-AI-Localizer — Stable Release v1.0

The first stable release of the professional Minecraft quest localizer (FTB Quests). This version introduces strict filtering, stable background workers, and single global progress tracking.

## What's New in v1.0:

1. **Single Global Progress Bar:**
   * Removed the redundant per-file lines progress bar to eliminate visual noise.
   * Integrated a clean, single global progress indicator: `Total Progress: X / Y files`.

2. **Strict Content Filtering:**
   * Checkbox filters (**Translate Titles**, **Translate Subtitles**, **Translate Descriptions**) now strictly govern the parsing logic in `core.py`.
   * Disabled content categories are skipped entirely, saving up to 80% of API token limits (TPM/RPM) and reducing translation time.

3. **Asynchronous Flow Control:**
   * **Pause / Resume** and **Stop** buttons respond instantly without locking the main UI thread.
   * Powered by the **Complement** policy, restarting a cancelled batch resumes exactly where it left off.

4. **Tag Shielding:**
   * Automatic masking of system item tags (e.g., `#forge:ingots`) using untranslatable `__TAG_X__` placeholders to prevent AI translation errors.

5. **Fusion Theme for Wayland:**
   * Disabled global QSS rules that caused rendering glitches in Wayland (Kvantum/Hyprland) environments.
   * Applied a clean dark-toned `QPalette` built on top of the native Fusion style.
