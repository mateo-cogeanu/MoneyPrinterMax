# Changelog

All notable changes for this MoneyPrinterMax customization are documented here.

## 2026-06-14

### WebUI: Config Portability

- Added a top-right in-app config tools menu with config export and import.
- Config exports include user settings and API key fields from the app config.
- Config exports can optionally include the saved YouTube OAuth token and Google client-secret JSON for moving YouTube upload access to another setup.
- Config import restores app, UI, Azure, SiliconFlow, YouTube OAuth token, and imported Google client-secret settings.

### WebUI: Full Auto Mode

- Added a new `Full Auto` app mode for hands-off topic batching.
- Users can enter one video topic per line and choose two daily upload times.
- The app calculates the full publishing date range from the topic count, start date, and daily upload slots.
- Replaced the fixed two daily upload slots with an editable upload-time list so users can add or remove daily publish times.
- Replaced manual Full Auto topic entry with a repo-local `topics.txt` queue.
- Full Auto now skips `topics.txt` lines that already contain a YouTube link and appends the scheduled video URL to each completed topic line.
- `topics.txt` is now a local ignored queue file; first run creates it empty when missing instead of shipping example topics in the repo.
- Added a schedule preview table showing each topic and its planned publish time.
- Full Auto generates the script, keywords, YouTube title, and YouTube description for each topic.
- Full Auto generates each video sequentially, then schedules it on YouTube through the existing OAuth upload service.
- Added shared subtitle controls so the selected subtitle style is reused for every video in the batch.
- Added shared music controls, including random music, no music, existing custom music, or uploading a new custom MP3 for the whole batch.
- Custom music is now locked before a Full Auto batch starts, and every generated video receives that exact custom file instead of drifting back to random background music.
- Full Auto now stops with a clear message if `Custom Background Music` is selected without choosing or uploading an MP3.
- Added a `Target Video Length` control in Full Auto with 15, 30, 45, and 60 second presets.
- Full Auto now injects a matching spoken-word range into every generated script prompt so batch videos stay closer to the same length.
- Added focused unit tests for topic parsing and schedule generation.

### AI: Shorts Script Quality

- Updated the script-generation prompt so `add a hook` means a short opening hook, not replacing the entire video.
- Added mandatory YouTube Shorts structure rules requiring a hook, main body, and payoff/conclusion.
- The Shorts structure rules are appended even when a custom system prompt is used.
- Added prompt tests to prevent hook-only scripts from returning.

### AI: Stock Material Relevance

- Strengthened stock-video search term generation so terms must be concrete visible phrases tied to the main subject.
- Added a search-term post-processor that keeps the full subject anchor attached to stock searches, reducing broad mismatches like `baking soda` drifting into soda drink clips.
- Added tests for subject anchoring and unrelated brand/drink term cleanup.
- Stock candidates now carry provider metadata such as title/tags/search term, and an LLM relevance judge rejects unrelated candidates before download.
- Added fallback relevance checks to skip obvious mismatches like `laser show` or `ship at sea` when the script is about technical subjects such as Docker.

### WebUI: YouTube Automation Fixes

- Removed the runtime dependency on `google-auth-oauthlib` from the YouTube connect flow.
- Added a built-in local OAuth callback flow so YouTube connection can work in environments where only the core Google auth/client libraries are installed.
- Improved the manual OAuth callback so it uses a local loopback server without requiring `google-auth-oauthlib`.
- Google OAuth error descriptions are now shown in the app when Google redirects back with a connection error.
- Added a YouTube OAuth troubleshooting note for blocked/unverified apps and redirect URI mismatch setup problems.
- The OAuth callback now follows the loopback host in the selected client JSON, so a `localhost` Desktop client keeps using a `localhost` redirect.
- Added a clearer `403: access_denied` message explaining that this is an OAuth consent-screen block, not YouTube API usage.
- Reduced the YouTube Automation video preview width so selected videos no longer dominate the page.

### WebUI: YouTube Automation Mode

- Added a new app mode switch with `Create Video` and `YouTube Automation`.
- Added a YouTube Automation screen for uploading generated videos to YouTube.
- Auto-detects a Google OAuth client-secret JSON in the user's Downloads folder when available.
- Stores the reusable OAuth token locally under `storage/youtube/oauth_token.json`.
- Added controls to connect YouTube, forget the saved login, and see whether a token is ready.
- Lists generated `final-*.mp4` videos from the task storage folder with size and modified time.
- Shows a preview of the selected generated video before upload.
- Added editable YouTube title, description, tags, privacy, and made-for-kids controls.
- Added upload-now support through the YouTube Data API.
- Added scheduled upload support by setting a future publish time.
- Validates scheduled publish times so they are at least 15 minutes in the future.
- Added YouTube OAuth dependency entries for local setup.

## 2026-06-13

### WebUI: Post-Generation Behavior

- Stopped opening the generated task folder in a new `file://` browser tab after video generation completes.
- Generated videos continue to appear directly in the WebUI with the existing download button underneath.

### WebUI: Video Encoder Options

- Added a clearer Apple hardware acceleration option in Advanced Video Settings:
  - `Apple Metal Accelerated (h264_videotoolbox)`
- Kept the existing codec fallback behavior, so unsupported hardware encoders fall back to `libx264`.
- Updated `config.example.toml` comments to call out the macOS hardware acceleration path.

### WebUI: Google Fonts And Preview

- Replaced the bundled subtitle fonts with Google Fonts:
  - `Roboto.ttf`
  - `Montserrat.ttf`
  - `Poppins-Regular.ttf`
  - `Oswald.ttf`
  - `Merriweather.ttf`
  - `PlayfairDisplay.ttf`
- Removed the previous oversized font files from `resource/fonts`.
- Updated subtitle font defaults from the old bundled fonts to `Roboto.ttf`.
- Added a live subtitle font preview under the font selector.
- Updated tests and schema defaults that referenced the old font files.

### WebUI: Simpler Settings Layout

- Removed the duplicate API key management expander from the right-side settings area.
- Kept API key management in the general settings menu at the top.
- Widened the center settings column so Audio Settings has more horizontal room after removing the duplicate panel.

### WebUI: Title And Description Generation

- Added a `Generate Title and Description` button in Video Script Settings after script and keyword generation.
- Reused the existing LLM social metadata helper to generate a short-video title, description, and hashtags.
- Added editable `Video Title` and `Video Description` fields so generated copy can be reviewed and adjusted before use.

### MoneyPrinterMax Branding

- Updated the root README title from `MoneyPrinterTurbo` to `MoneyPrinterMax`.
- Removed the Arabic language link from the root README language selector.
- Updated the Streamlit browser page title and app heading to use `MoneyPrinterMax`.

### WebUI: Cleaner Generation Progress

- Removed the large on-screen log block that appeared after pressing `Generate Video`.
- Added a compact themed progress panel that appears while video generation is running.
- The progress panel uses staged generation text and a custom app-themed progress bar.
- The progress panel is cleared automatically when generation finishes or fails.
- Kept logs going to the normal application logger instead of displaying them as a giant code block in the WebUI.

### WebUI: Video Download Button

- Added a download button below each generated video preview.
- The download button uses a Material download icon instead of an emoji.
- The button text appears to the right of the icon as `Download`.
- The downloaded filename matches the generated video filename.
- The download MIME type is set to `video/mp4`.

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
