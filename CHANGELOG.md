# Changelog

All notable changes for this MoneyPrinterMax customization are documented here.

## 2026-06-13

### Project Direction

- Added `AGENTS.md` to define the working goals for this project.
- Documented that future work should focus on improving productivity, increasing useful automation, and fixing app quirks as they are identified.
- Added guidance that newly reported quirks should be treated as actionable improvement items, with focused fixes and verification before moving on.

### WebUI: Custom Background Music Upload

- Replaced the custom background music path text input with a file uploader in `webui/Main.py`.
- The custom background music control now behaves like the custom narration audio uploader above it.
- Users can upload an MP3 file directly from the browser instead of manually typing or pasting a local file path.
- Added an in-page audio preview for the uploaded background music so users can confirm they selected the intended track before generating a video.
- Saved uploaded background music into the existing `resource/songs` directory using a generated safe filename based on the task ID.
- Continued using the existing secure background music lookup behavior by passing only the saved filename through `params.bgm_file`.
- Kept support aligned with the current background music service restrictions, which only accept MP3 files from the approved songs directory.
- Avoided allowing arbitrary filesystem paths for background music, preserving the existing protection against unsafe local file reads.

### WebUI Text And Localization

- Updated the English custom background music label from a path-based instruction to an upload-based instruction:
  - Old: `Please enter the file path for custom background music:`
  - New: `Upload custom background music:`
- Updated the Russian custom background music label to match the new upload workflow.
- Added missing Russian translations for the material-order matching controls so the WebUI i18n coverage test passes:
  - `Match Materials to Script Order`
  - `Match Materials to Script Order Help`

### README

- Replaced the root `README.md` Chinese content with the English README content from `README-en.md`.
- Updated the root README language selector so it no longer links to `README.md` as the Chinese version after the root README became English.
- Kept the Arabic README link available from the root README.

### Dependency And Script State

- The current local project state includes a `requirements.txt` change that removes `litellm==1.86.2`.
- The current local project state includes an executable-bit change for `webui.sh`, making the script directly runnable on Unix-like systems.
- These local changes were preserved and included rather than reverted.

### Verification

- Confirmed `webui/Main.py` compiles with `python3 -m py_compile webui/Main.py`.
- Confirmed English and Russian i18n JSON files are valid JSON with `python3 -m json.tool`.
- Ran `python3 -m unittest test.services.test_webui_i18n`; all 4 tests passed.
- Attempted to run pytest-based checks, but this shell does not have a `python` command, the available `python3` environment does not include `pytest`, and `uv` is not installed.

### Files Changed

- `AGENTS.md`
- `CHANGELOG.md`
- `README.md`
- `requirements.txt`
- `webui.sh`
- `webui/Main.py`
- `webui/i18n/en.json`
- `webui/i18n/ru.json`
