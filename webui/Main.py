import base64
import html
import importlib
import json
import os
import sys
from datetime import datetime, timedelta
from uuid import uuid4

import requests
import streamlit as st
from loguru import logger

# Add the root directory of the project to the system path to allow importing modules from the project
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
    print("******** sys.path ********")
    print(sys.path)
    print("")

from app.config import config
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services import full_auto, llm, voice
from app.services import task as tm
from app.services import youtube_upload
from app.utils import utils

full_auto = importlib.reload(full_auto)

st.set_page_config(
    page_title="MoneyPrinterMax",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/harry0703/MoneyPrinterTurbo/issues",
        "About": "# MoneyPrinterMax\nSimply provide a topic or keyword for a video, and it will "
        "automatically generate the video copy, video materials, video subtitles, "
        "and video background music before synthesizing a high-definition short "
        "video.\n\nhttps://github.com/harry0703/MoneyPrinterTurbo",
    },
)


streamlit_style = """
<style>
h1 {
    padding-top: 0 !important;
}

div[data-testid="stProgress"] > div > div > div {
    background: linear-gradient(90deg, #13c8a6 0%, #2f80ed 55%, #f2b705 100%);
}

.mpt-progress-shell {
    border: 1px solid rgba(49, 130, 206, 0.22);
    border-radius: 8px;
    padding: 1rem 1rem 0.8rem;
    background: rgba(19, 200, 166, 0.08);
}

.mpt-progress-title {
    font-weight: 700;
    margin-bottom: 0.2rem;
}

.mpt-progress-copy {
    color: rgba(49, 51, 63, 0.72);
    font-size: 0.92rem;
    margin-bottom: 0.75rem;
}

.mpt-font-preview {
    border: 1px solid rgba(49, 130, 206, 0.22);
    border-radius: 8px;
    padding: 0.85rem 1rem;
    margin: 0.35rem 0 1rem;
    background: rgba(19, 200, 166, 0.08);
    font-size: 1.35rem;
    line-height: 1.35;
}
</style>
"""
st.markdown(streamlit_style, unsafe_allow_html=True)

# 定义资源目录
font_dir = os.path.join(root_dir, "resource", "fonts")
song_dir = os.path.join(root_dir, "resource", "songs")
i18n_dir = os.path.join(root_dir, "webui", "i18n")
config_file = os.path.join(root_dir, "webui", ".streamlit", "webui.toml")
system_locale = utils.get_system_locale()

STOCK_SOURCE_CONFIG_KEYS = {
    "pexels": "pexels_api_keys",
    "pixabay": "pixabay_api_keys",
    "coverr": "coverr_api_keys",
}
STOCK_SOURCE_LABEL_KEYS = {
    "pexels": "Pexels",
    "pixabay": "Pixabay",
    "coverr": "Coverr",
}


def normalize_stock_sources(source: str) -> list[str]:
    sources = []
    for raw_source in str(source or "").split(","):
        source_name = raw_source.strip().lower()
        if (
            source_name in STOCK_SOURCE_CONFIG_KEYS
            and source_name not in sources
        ):
            sources.append(source_name)
    return sources


def configured_stock_sources() -> list[str]:
    return [
        source_name
        for source_name, config_key in STOCK_SOURCE_CONFIG_KEYS.items()
        if config.app.get(config_key, "")
    ]


def missing_stock_source_keys(source: str) -> list[str]:
    return [
        source_name
        for source_name in normalize_stock_sources(source)
        if not config.app.get(STOCK_SOURCE_CONFIG_KEYS[source_name], "")
    ]


if "video_subject" not in st.session_state:
    st.session_state["video_subject"] = ""
if "video_script" not in st.session_state:
    st.session_state["video_script"] = ""
if "video_terms" not in st.session_state:
    st.session_state["video_terms"] = ""
if "video_title" not in st.session_state:
    st.session_state["video_title"] = ""
if "video_description" not in st.session_state:
    st.session_state["video_description"] = ""
if "video_script_prompt" not in st.session_state:
    st.session_state["video_script_prompt"] = ""
if "custom_system_prompt" not in st.session_state:
    st.session_state["custom_system_prompt"] = llm.DEFAULT_SCRIPT_SYSTEM_PROMPT
if "use_custom_system_prompt" not in st.session_state:
    st.session_state["use_custom_system_prompt"] = False
if "match_materials_to_script" not in st.session_state:
    st.session_state["match_materials_to_script"] = bool(
        config.app.get("match_materials_to_script", False)
    )
if "ui_language" not in st.session_state:
    st.session_state["ui_language"] = config.ui.get("language", system_locale)
if "local_video_materials" not in st.session_state:
    # 记住用户最近一次已经落盘的本地素材，避免仅修改文案后二次生成时丢失素材列表。
    st.session_state["local_video_materials"] = []

# 加载语言文件
locales = utils.load_locales(i18n_dir)


def tr(key):
    language = st.session_state["ui_language"]
    loc = (
        locales.get(language)
        or locales.get(language.split("-")[0])
        or locales.get("en", {})
    )
    return loc.get("Translation", {}).get(key, key)


# 创建一个顶部栏，包含标题、配置工具和语言选择
title_col, tools_col, lang_col = st.columns([3, 0.35, 1])

with title_col:
    st.title(f"MoneyPrinterMax v{config.project_version}")


def build_config_export(include_youtube_auth: bool = True) -> dict:
    config.save_config()
    export_data = {
        "format": "MoneyPrinterMaxConfigExport",
        "version": 1,
        "exported_at": datetime.now().astimezone().isoformat(),
        "config": config._cfg,
    }

    if include_youtube_auth:
        token_file = youtube_upload.default_token_file()
        if os.path.isfile(token_file):
            with open(token_file, "r", encoding="utf-8") as fp:
                export_data["youtube_oauth_token"] = json.load(fp)

        client_secret_file = config.app.get("youtube_client_secret_file", "")
        client_secret_file = os.path.abspath(os.path.expanduser(client_secret_file))
        if client_secret_file and os.path.isfile(client_secret_file):
            with open(client_secret_file, "r", encoding="utf-8") as fp:
                export_data["youtube_client_secret_json"] = json.load(fp)

    return export_data


def apply_config_import(import_data: dict):
    if import_data.get("format") != "MoneyPrinterMaxConfigExport":
        raise ValueError(tr("Invalid Config Import File"))

    imported_config = import_data.get("config")
    if not isinstance(imported_config, dict):
        raise ValueError(tr("Invalid Config Import File"))

    config._cfg.clear()
    config._cfg.update(imported_config)
    config.app.clear()
    config.app.update(imported_config.get("app", {}))
    config.azure.clear()
    config.azure.update(imported_config.get("azure", {}))
    config.siliconflow.clear()
    config.siliconflow.update(imported_config.get("siliconflow", {}))
    config.ui.clear()
    config.ui.update(imported_config.get("ui", {"hide_log": False}))

    youtube_token = import_data.get("youtube_oauth_token")
    if isinstance(youtube_token, dict):
        token_file = youtube_upload.default_token_file()
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as fp:
            json.dump(youtube_token, fp, indent=2)

    youtube_client_secret = import_data.get("youtube_client_secret_json")
    if isinstance(youtube_client_secret, dict):
        youtube_dir = utils.storage_dir("youtube", create=True)
        client_secret_file = os.path.join(youtube_dir, "client_secret_imported.json")
        with open(client_secret_file, "w", encoding="utf-8") as fp:
            json.dump(youtube_client_secret, fp, indent=2)
        config.app["youtube_client_secret_file"] = client_secret_file
        config._cfg.setdefault("app", {})["youtube_client_secret_file"] = (
            client_secret_file
        )

    config.save_config()


def render_config_tools_menu():
    with st.popover("⋮", use_container_width=True):
        st.write(tr("Config Tools"))
        st.warning(tr("Config Export Warning"))
        include_youtube_auth = st.checkbox(
            tr("Include YouTube OAuth Login"),
            value=True,
            help=tr("Include YouTube OAuth Login Help"),
            key="config_export_include_youtube_auth",
        )
        export_data = build_config_export(include_youtube_auth)
        st.download_button(
            tr("Export Config"),
            data=json.dumps(export_data, indent=2).encode("utf-8"),
            file_name="moneyprintermax-config-export.json",
            mime="application/json",
            use_container_width=True,
        )

        import_file = st.file_uploader(
            tr("Import Config"),
            type=["json"],
            accept_multiple_files=False,
            key="config_import_file",
        )
        if import_file and st.button(
            tr("Apply Imported Config"), type="primary", use_container_width=True
        ):
            try:
                import_data = json.loads(import_file.getvalue().decode("utf-8"))
                apply_config_import(import_data)
                st.success(tr("Config Import Complete"))
                st.rerun()
            except Exception as exc:
                st.error(f"{tr('Config Import Failed')}: {exc}")


with tools_col:
    render_config_tools_menu()

with lang_col:
    display_languages = []
    selected_index = 0
    for i, code in enumerate(locales.keys()):
        display_languages.append(f"{code} - {locales[code].get('Language')}")
        selected_ui_language = st.session_state.get("ui_language", "")
        selected_ui_language_base = selected_ui_language.split("-")[0]
        if code in (selected_ui_language, selected_ui_language_base):
            selected_index = i

    selected_language = st.selectbox(
        "Language / 语言",
        options=display_languages,
        index=selected_index,
        key="top_language_selector",
        label_visibility="collapsed",
    )
    if selected_language:
        code = selected_language.split(" - ")[0].strip()
        st.session_state["ui_language"] = code
        config.ui["language"] = code

support_locales = [
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "de-DE",
    "en-US",
    "fr-FR",
    "ru-RU",
    "vi-VN",
    "th-TH",
    "tr-TR",
]


def get_all_fonts():
    fonts = []
    for root, dirs, files in os.walk(font_dir):
        for file in files:
            if file.endswith(".ttf") or file.endswith(".ttc"):
                fonts.append(file)
    fonts.sort()
    return fonts


def render_font_preview(font_name: str):
    if not font_name:
        return

    font_path = os.path.abspath(os.path.join(font_dir, font_name))
    fonts_root = os.path.abspath(font_dir)
    if not font_path.startswith(fonts_root + os.sep) or not os.path.exists(font_path):
        return

    with open(font_path, "rb") as font_file:
        encoded_font = base64.b64encode(font_file.read()).decode("utf-8")

    family = os.path.splitext(os.path.basename(font_name))[0].replace(" ", "-")
    preview_text = "This is how your subtitles will look."
    st.markdown(
        f"""
        <style>
        @font-face {{
            font-family: "{family}";
            src: url(data:font/ttf;base64,{encoded_font}) format("truetype");
        }}
        </style>
        <div class="mpt-font-preview" style="font-family: '{family}', sans-serif;">
            {html.escape(preview_text)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_all_songs():
    songs = []
    for root, dirs, files in os.walk(song_dir):
        for file in files:
            if file.endswith(".mp3"):
                songs.append(file)
    return songs


def scroll_to_bottom():
    js = """
    <script>
        console.log("scroll_to_bottom");
        function scroll(dummy_var_to_force_repeat_execution){
            var sections = parent.document.querySelectorAll('section.main');
            console.log(sections);
            for(let index = 0; index<sections.length; index++) {
                sections[index].scrollTop = sections[index].scrollHeight;
            }
        }
        scroll(1);
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def render_generated_videos(video_files):
    if not video_files:
        return

    player_cols = st.columns(len(video_files) * 2 + 1)
    for i, video_path in enumerate(video_files):
        with player_cols[i * 2 + 1]:
            st.video(video_path)
            try:
                with open(video_path, "rb") as video_file:
                    st.download_button(
                        tr("Download"),
                        data=video_file,
                        file_name=os.path.basename(video_path),
                        mime="video/mp4",
                        icon=":material/download:",
                        use_container_width=True,
                        key=f"download_generated_video_{i}_{os.path.basename(video_path)}",
                    )
            except Exception as e:
                logger.warning(f"failed to render download button for {video_path}: {e}")


def get_generated_video_files():
    tasks_dir = utils.task_dir()
    video_files = []
    for root, _, files in os.walk(tasks_dir):
        for file in files:
            if file.startswith("final-") and file.lower().endswith(".mp4"):
                file_path = os.path.join(root, file)
                video_files.append(file_path)
    video_files.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return video_files


def format_video_choice(video_path: str) -> str:
    relative_path = os.path.relpath(video_path, utils.task_dir())
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    modified_at = datetime.fromtimestamp(os.path.getmtime(video_path)).strftime(
        "%Y-%m-%d %H:%M"
    )
    return f"{relative_path} · {size_mb:.1f} MB · {modified_at}"


def render_youtube_automation_mode():
    st.subheader(tr("YouTube Automation"))
    st.caption(tr("YouTube Automation Help"))

    default_client_secret_file = youtube_upload.find_default_client_secret_file()
    saved_client_secret_file = config.app.get(
        "youtube_client_secret_file", default_client_secret_file
    )
    client_secret_file = st.text_input(
        tr("YouTube OAuth Client JSON"),
        value=saved_client_secret_file,
        help=tr("YouTube OAuth Client JSON Help"),
    ).strip()
    config.app["youtube_client_secret_file"] = client_secret_file

    with st.expander(tr("YouTube OAuth Troubleshooting")):
        st.markdown(tr("YouTube OAuth Troubleshooting Help"))

    auth_cols = st.columns([1, 1, 2])
    with auth_cols[0]:
        if st.button(tr("Connect YouTube"), use_container_width=True):
            try:
                youtube_upload.get_authenticated_service(
                    client_secret_file=client_secret_file,
                    force_reauth=True,
                )
                st.success(tr("YouTube Connected"))
            except Exception as exc:
                st.error(f"{tr('YouTube Connection Failed')}: {exc}")
    with auth_cols[1]:
        if st.button(tr("Forget YouTube Login"), use_container_width=True):
            youtube_upload.revoke_saved_token()
            st.success(tr("YouTube Login Removed"))
    with auth_cols[2]:
        if youtube_upload.token_exists():
            st.info(tr("YouTube Token Ready"))
        else:
            st.warning(tr("YouTube Token Missing"))

    video_files = get_generated_video_files()
    if not video_files:
        st.warning(tr("No Generated Videos Found"))
        return

    selected_video_index = st.selectbox(
        tr("Generated Video"),
        options=range(len(video_files)),
        format_func=lambda index: format_video_choice(video_files[index]),
    )
    selected_video = video_files[selected_video_index]
    preview_cols = st.columns([1, 1.15, 1])
    with preview_cols[1]:
        st.video(selected_video)

    title = st.text_input(
        tr("YouTube Title"),
        value=st.session_state.get("video_title", "")
        or os.path.splitext(os.path.basename(selected_video))[0],
        max_chars=100,
    )
    description = st.text_area(
        tr("YouTube Description"),
        value=st.session_state.get("video_description", ""),
        height=180,
        max_chars=5000,
    )
    tags = st.text_input(
        tr("YouTube Tags"),
        help=tr("YouTube Tags Help"),
    )

    publish_cols = st.columns(3)
    with publish_cols[0]:
        privacy_status = st.selectbox(
            tr("YouTube Privacy"),
            options=["private", "unlisted", "public"],
            index=0,
            format_func=lambda value: tr(value.title()),
        )
    with publish_cols[1]:
        schedule_enabled = st.checkbox(tr("Schedule Upload"))
    with publish_cols[2]:
        made_for_kids = st.checkbox(tr("Made For Kids"), value=False)

    publish_at = None
    if schedule_enabled:
        date_cols = st.columns(2)
        default_publish_at = datetime.now().astimezone() + timedelta(days=1)
        with date_cols[0]:
            publish_date = st.date_input(
                tr("Publish Date"), value=default_publish_at.date()
            )
        with date_cols[1]:
            publish_time = st.time_input(
                tr("Publish Time"),
                value=default_publish_at.time().replace(second=0, microsecond=0),
            )
        publish_at = datetime.combine(publish_date, publish_time).astimezone()
        st.info(tr("Scheduled YouTube Upload Help"))

    upload_label = (
        tr("Schedule on YouTube")
        if schedule_enabled
        else tr("Upload to YouTube Now")
    )
    if st.button(upload_label, type="primary", use_container_width=True):
        if publish_at and publish_at <= datetime.now().astimezone() + timedelta(
            minutes=15
        ):
            st.error(tr("Publish Time Must Be Future"))
            st.stop()

        try:
            with st.spinner(tr("Uploading to YouTube")):
                result = youtube_upload.upload_video(
                    video_path=selected_video,
                    title=title,
                    description=description,
                    tags=youtube_upload.parse_tags(tags),
                    privacy_status=privacy_status,
                    publish_at=publish_at,
                    client_secret_file=client_secret_file,
                    made_for_kids=made_for_kids,
                )
            if result.get("url"):
                st.success(tr("YouTube Upload Complete"))
                st.link_button(tr("Open YouTube Video"), result["url"])
            else:
                st.success(tr("YouTube Upload Complete"))
                st.json(result)
        except Exception as exc:
            st.error(f"{tr('YouTube Upload Failed')}: {exc}")


def render_youtube_auth_controls(client_secret_key: str = "youtube_client_secret_file"):
    default_client_secret_file = youtube_upload.find_default_client_secret_file()
    saved_client_secret_file = config.app.get(client_secret_key, default_client_secret_file)
    client_secret_file = st.text_input(
        tr("YouTube OAuth Client JSON"),
        value=saved_client_secret_file,
        help=tr("YouTube OAuth Client JSON Help"),
        key=f"{client_secret_key}_input",
    ).strip()
    config.app[client_secret_key] = client_secret_file

    with st.expander(tr("YouTube OAuth Troubleshooting")):
        st.markdown(tr("YouTube OAuth Troubleshooting Help"))

    auth_cols = st.columns([1, 1, 2])
    with auth_cols[0]:
        if st.button(
            tr("Connect YouTube"),
            use_container_width=True,
            key=f"{client_secret_key}_connect",
        ):
            try:
                youtube_upload.get_authenticated_service(
                    client_secret_file=client_secret_file,
                    force_reauth=True,
                )
                st.success(tr("YouTube Connected"))
            except Exception as exc:
                st.error(f"{tr('YouTube Connection Failed')}: {exc}")
    with auth_cols[1]:
        if st.button(
            tr("Forget YouTube Login"),
            use_container_width=True,
            key=f"{client_secret_key}_forget",
        ):
            youtube_upload.revoke_saved_token()
            st.success(tr("YouTube Login Removed"))
    with auth_cols[2]:
        if youtube_upload.token_exists():
            st.info(tr("YouTube Token Ready"))
        else:
            st.warning(tr("YouTube Token Missing"))

    return client_secret_file


def render_full_auto_mode():
    st.subheader(tr("Full Auto Mode"))
    st.caption(tr("Full Auto Help"))

    client_secret_file = render_youtube_auth_controls("youtube_client_secret_file")
    topics_file = full_auto.ensure_topics_file(os.path.join(root_dir, "topics.txt"))

    schedule_col, topic_col = st.columns([0.85, 1.15])
    with schedule_col:
        st.write(tr("Publishing Schedule"))
        start_date = st.date_input(
            tr("Start Date"),
            value=(datetime.now().astimezone() + timedelta(days=1)).date(),
            key="full_auto_start_date",
        )
        if "full_auto_upload_times" not in st.session_state:
            st.session_state["full_auto_upload_times"] = [
                datetime.strptime("08:00", "%H:%M").time(),
                datetime.strptime("20:00", "%H:%M").time(),
            ]

        upload_times = []
        for time_index, saved_time in enumerate(
            st.session_state["full_auto_upload_times"]
        ):
            time_cols = st.columns([0.78, 0.22])
            with time_cols[0]:
                upload_times.append(
                    st.time_input(
                        tr("Upload Time").format(number=time_index + 1),
                        value=saved_time,
                        key=f"full_auto_upload_time_{time_index}",
                    )
                )
            with time_cols[1]:
                if st.button(
                    tr("Remove"),
                    key=f"full_auto_remove_time_{time_index}",
                    disabled=len(st.session_state["full_auto_upload_times"]) <= 1,
                    use_container_width=True,
                ):
                    st.session_state["full_auto_upload_times"].pop(time_index)
                    st.rerun()

        st.session_state["full_auto_upload_times"] = upload_times
        if st.button(tr("Add Upload Time"), use_container_width=True):
            st.session_state["full_auto_upload_times"].append(
                datetime.strptime("12:00", "%H:%M").time()
            )
            st.rerun()
        made_for_kids = st.checkbox(
            tr("Made For Kids"), value=False, key="full_auto_made_for_kids"
        )

    with topic_col:
        st.write(tr("Topics File"))
        st.code(os.path.relpath(topics_file, root_dir))
        topic_entries = full_auto.read_pending_topic_entries(topics_file)
        topics = [entry["topic"] for entry in topic_entries]
        st.caption(
            tr("Topics File Help").format(
                path=os.path.relpath(topics_file, root_dir)
            )
        )
        schedule = full_auto.build_schedule(
            topics, start_date, upload_times
        )
        if schedule:
            st.info(
                tr("Full Auto Schedule Summary").format(
                    count=len(topics),
                    per_day=len(
                        {
                            time.replace(second=0, microsecond=0)
                            for time in upload_times
                        }
                    ),
                    start=schedule[0]["publish_label"],
                    end=schedule[-1]["publish_label"],
                )
            )
            st.dataframe(
                [
                    {
                        tr("Video #"): item["number"],
                        tr("Topic"): item["topic"],
                        tr("Publish At"): item["publish_label"],
                    }
                    for item in schedule
                ],
                hide_index=True,
                use_container_width=True,
            )

    settings_cols = st.columns(3)
    auto_params = VideoParams(video_subject="")

    with settings_cols[0]:
        st.write(tr("AI Video Settings"))
        video_languages = [(tr("Auto Detect"), "")]
        for code in support_locales:
            video_languages.append((code, code))
        selected_language_index = st.selectbox(
            tr("Script Language"),
            options=range(len(video_languages)),
            format_func=lambda index: video_languages[index][0],
            key="full_auto_script_language",
        )
        auto_params.video_language = video_languages[selected_language_index][1]
        auto_params.paragraph_number = st.slider(
            tr("Script Paragraph Number"),
            min_value=llm.MIN_SCRIPT_PARAGRAPH_NUMBER,
            max_value=llm.MAX_SCRIPT_PARAGRAPH_NUMBER,
            value=st.session_state.get("paragraph_number_input", 1),
            key="full_auto_paragraph_number",
        )
        target_duration_seconds = st.selectbox(
            tr("Target Video Length"),
            options=[15, 30, 45, 60],
            index=1,
            format_func=lambda seconds: tr("Seconds Format").format(
                seconds=seconds
            ),
            help=tr("Target Video Length Help"),
            key="full_auto_target_duration",
        )
        auto_params.video_script_prompt = st.text_area(
            tr("Custom Script Requirements"),
            height=100,
            max_chars=llm.MAX_SCRIPT_PROMPT_LENGTH,
            key="full_auto_script_prompt",
        ).strip()

        available_stock_sources = configured_stock_sources()
        default_full_auto_sources = normalize_stock_sources(
            st.session_state.get(
                "full_auto_video_sources",
                config.app.get("video_source", "pexels"),
            )
        )
        default_full_auto_sources = [
            source_name
            for source_name in default_full_auto_sources
            if source_name in available_stock_sources
        ]
        if not default_full_auto_sources:
            default_full_auto_sources = available_stock_sources
        selected_stock_sources = st.multiselect(
            tr("Stock Video APIs"),
            options=available_stock_sources,
            default=default_full_auto_sources,
            format_func=lambda source_name: tr(
                STOCK_SOURCE_LABEL_KEYS[source_name]
            ),
            help=tr("Stock Video APIs Help"),
            key="full_auto_video_sources",
        )
        auto_params.video_source = ",".join(selected_stock_sources)
        auto_params.video_concat_mode = VideoConcatMode.random
        auto_params.video_transition_mode = VideoTransitionMode.none
        auto_params.video_clip_duration = st.selectbox(
            tr("Clip Duration"),
            options=[2, 3, 4, 5, 6, 7, 8, 9, 10],
            index=1,
            key="full_auto_clip_duration",
        )
        auto_params.video_count = 1
        auto_params.match_materials_to_script = st.checkbox(
            tr("Match Materials to Script Order"),
            value=bool(st.session_state.get("match_materials_to_script", False)),
            key="full_auto_match_materials",
        )

    with settings_cols[1]:
        st.write(tr("Music and Voice"))
        saved_voice_name = config.ui.get("voice_name", voice.NO_VOICE_NAME)
        available_voices = [voice.NO_VOICE_NAME] + voice.get_all_azure_voices(
            filter_locals=None
        )
        if saved_voice_name not in available_voices:
            saved_voice_name = available_voices[0]
        auto_params.voice_name = st.selectbox(
            tr("Speech Synthesis"),
            options=available_voices,
            index=available_voices.index(saved_voice_name),
            format_func=lambda value: tr("No Voice") if value == voice.NO_VOICE_NAME else value,
            key="full_auto_voice_name",
        )
        auto_params.voice_volume = st.selectbox(
            tr("Speech Volume"),
            options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
            index=2,
            key="full_auto_voice_volume",
        )
        auto_params.voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
            key="full_auto_voice_rate",
        )

        bgm_options = [
            (tr("No Background Music"), ""),
            (tr("Random Background Music"), "random"),
            (tr("Custom Background Music"), "custom"),
        ]
        selected_bgm_index = st.selectbox(
            tr("Background Music"),
            options=range(len(bgm_options)),
            index=1,
            format_func=lambda index: bgm_options[index][0],
            key="full_auto_bgm_type",
        )
        auto_params.bgm_type = bgm_options[selected_bgm_index][1]
        uploaded_bgm_file = None
        selected_bgm_file = ""
        if auto_params.bgm_type == "custom":
            song_options = get_all_songs()
            selected_bgm_file = st.selectbox(
                tr("Existing Background Music"),
                options=[""] + song_options,
                format_func=lambda value: value or tr("Upload New Background Music"),
                key="full_auto_existing_bgm",
            )
            uploaded_bgm_file = st.file_uploader(
                tr("Custom Background Music File"),
                type=["mp3", "MP3"],
                accept_multiple_files=False,
                key="full_auto_custom_bgm_file",
            )
            if uploaded_bgm_file:
                st.audio(uploaded_bgm_file, format="audio/mp3")
                st.info(
                    tr("Full Auto Custom Music Selected").format(
                        filename=uploaded_bgm_file.name
                    )
                )
            elif selected_bgm_file:
                st.info(
                    tr("Full Auto Custom Music Selected").format(
                        filename=selected_bgm_file
                    )
                )
            else:
                st.warning(tr("Full Auto Custom Music Required"))
        auto_params.bgm_volume = st.selectbox(
            tr("Background Music Volume"),
            options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            index=2,
            key="full_auto_bgm_volume",
        )

    with settings_cols[2]:
        st.write(tr("Subtitle Settings"))
        auto_params.subtitle_enabled = st.checkbox(
            tr("Enable Subtitles"), value=True, key="full_auto_subtitles_enabled"
        )
        font_names = get_all_fonts()
        saved_font_name = config.ui.get("font_name", "Roboto.ttf")
        if saved_font_name not in font_names:
            saved_font_name = "Roboto.ttf" if "Roboto.ttf" in font_names else font_names[0]
        auto_params.font_name = st.selectbox(
            tr("Font"),
            font_names,
            index=font_names.index(saved_font_name),
            key="full_auto_font_name",
        )
        render_font_preview(auto_params.font_name)
        subtitle_positions = [
            (tr("Top"), "top"),
            (tr("Center"), "center"),
            (tr("Bottom"), "bottom"),
            (tr("Custom"), "custom"),
        ]
        selected_position_index = st.selectbox(
            tr("Position"),
            options=range(len(subtitle_positions)),
            index=2,
            format_func=lambda index: subtitle_positions[index][0],
            key="full_auto_subtitle_position",
        )
        auto_params.subtitle_position = subtitle_positions[selected_position_index][1]
        if auto_params.subtitle_position == "custom":
            auto_params.custom_position = st.slider(
                tr("Custom Position (% from top)"),
                0.0,
                100.0,
                float(config.ui.get("custom_position", 70.0)),
                key="full_auto_custom_position",
            )
        auto_params.text_fore_color = st.color_picker(
            tr("Font Color"),
            config.ui.get("text_fore_color", "#FFFFFF"),
            key="full_auto_text_color",
        )
        auto_params.font_size = st.slider(
            tr("Font Size"),
            30,
            100,
            int(config.ui.get("font_size", 60)),
            key="full_auto_font_size",
        )
        auto_params.stroke_color = st.color_picker(
            tr("Stroke Color"), "#000000", key="full_auto_stroke_color"
        )
        auto_params.stroke_width = st.slider(
            tr("Stroke Width"), 0.0, 10.0, 1.5, key="full_auto_stroke_width"
        )
        subtitle_background_enabled = st.checkbox(
            tr("Enable Subtitle Background"),
            value=config.ui.get("subtitle_background_enabled", True),
            key="full_auto_subtitle_background_enabled",
        )
        if subtitle_background_enabled:
            auto_params.text_background_color = st.color_picker(
                tr("Subtitle Background Color"),
                config.ui.get("subtitle_background_color", "#000000"),
                key="full_auto_subtitle_background_color",
            )
            auto_params.rounded_subtitle_background = st.checkbox(
                tr("Rounded Subtitle Background"),
                value=config.ui.get("rounded_subtitle_background", False),
                help=tr("Rounded Subtitle Background Help"),
                key="full_auto_rounded_subtitle_background",
            )
        else:
            auto_params.text_background_color = False
            auto_params.rounded_subtitle_background = False

    if st.button(tr("Start Full Auto"), type="primary", use_container_width=True):
        if not topics:
            st.error(tr("Please Enter Video Topics"))
            st.stop()
        normalized_upload_times = [
            time.replace(second=0, microsecond=0) for time in upload_times
        ]
        if not normalized_upload_times:
            st.error(tr("At Least One Upload Time Required"))
            st.stop()
        if len(set(normalized_upload_times)) != len(normalized_upload_times):
            st.error(tr("Upload Times Must Be Different"))
            st.stop()
        if not youtube_upload.token_exists():
            st.error(tr("YouTube Token Missing"))
            st.stop()
        if not normalize_stock_sources(auto_params.video_source):
            st.error(tr("Please Select at Least One Stock Video API"))
            st.stop()
        if schedule[0]["publish_at"] <= datetime.now().astimezone() + timedelta(minutes=15):
            st.error(tr("Publish Time Must Be Future"))
            st.stop()

        batch_id = str(uuid4())
        if auto_params.bgm_type == "custom":
            if uploaded_bgm_file:
                _, bgm_ext = os.path.splitext(os.path.basename(uploaded_bgm_file.name))
                bgm_ext = bgm_ext.lower() or ".mp3"
                bgm_filename = f"full-auto-bgm-{batch_id}{bgm_ext}"
                with open(os.path.join(utils.song_dir(), bgm_filename), "wb") as f:
                    f.write(uploaded_bgm_file.getbuffer())
                auto_params.bgm_file = bgm_filename
            elif selected_bgm_file:
                auto_params.bgm_file = selected_bgm_file
            else:
                st.error(tr("Full Auto Custom Music Required"))
                st.stop()
            auto_params.bgm_type = "custom"
            logger.info(
                f"full auto custom bgm locked: {auto_params.bgm_file}"
            )
        else:
            auto_params.bgm_file = ""

        progress = st.progress(0, text=tr("Starting Full Auto"))
        results = []
        total_steps = len(schedule)
        for index, item in enumerate(schedule):
            topic = item["topic"]
            topic_entry = topic_entries[index]
            progress.progress(
                int(index / total_steps * 100),
                text=tr("Full Auto Working On").format(
                    current=index + 1, total=total_steps, topic=topic
                ),
            )

            script = llm.generate_script(
                video_subject=topic,
                language=auto_params.video_language,
                paragraph_number=auto_params.paragraph_number,
                video_script_prompt="\n".join(
                    part
                    for part in [
                        full_auto.build_duration_script_requirement(
                            target_duration_seconds
                        ),
                        auto_params.video_script_prompt,
                    ]
                    if part
                ),
                custom_system_prompt="",
            )
            if not script or "Error: " in script:
                st.error(f"{tr('Video Script Generation Failed')}: {topic}")
                st.stop()

            terms = llm.generate_terms(
                topic,
                script,
                amount=8 if auto_params.match_materials_to_script else 5,
                match_script_order=auto_params.match_materials_to_script,
            )
            if not terms or "Error: " in terms:
                st.error(f"{tr('Video Keywords Generation Failed')}: {topic}")
                st.stop()

            metadata = llm.generate_social_metadata(
                video_subject=topic,
                video_script=script,
                language=auto_params.video_language or llm.DEFAULT_SOCIAL_LANGUAGE,
                platform=llm.DEFAULT_SOCIAL_PLATFORM,
            )
            description_parts = [metadata.get("caption", "")]
            hashtags = metadata.get("hashtags", [])
            if hashtags:
                description_parts.append(" ".join(hashtags))

            task_params = VideoParams(**auto_params.model_dump())
            task_params.video_subject = topic
            task_params.video_script = script
            task_params.video_terms = terms
            if auto_params.bgm_type == "custom":
                task_params.bgm_type = "custom"
                task_params.bgm_file = auto_params.bgm_file
            task_id = str(uuid4())
            result = tm.start(task_id=task_id, params=task_params)
            video_files = result.get("videos", []) if result else []
            if not video_files:
                st.error(f"{tr('Video Generation Failed')}: {topic}")
                st.stop()

            upload_result = youtube_upload.upload_video(
                video_path=video_files[0],
                title=metadata.get("title") or topic,
                description="\n\n".join(part for part in description_parts if part),
                tags=hashtags,
                privacy_status="private",
                publish_at=item["publish_at"],
                client_secret_file=client_secret_file,
                made_for_kids=made_for_kids,
            )
            video_url = upload_result.get("url", "")
            if video_url:
                full_auto.mark_topic_completed(
                    topics_file,
                    topic_entry["line_number"],
                    video_url,
                )
            results.append(
                {
                    tr("Topic"): topic,
                    tr("Publish At"): item["publish_label"],
                    tr("YouTube URL"): video_url,
                }
            )

        progress.progress(100, text=tr("Full Auto Complete"))
        st.success(tr("Full Auto Complete"))
        st.dataframe(results, hide_index=True, use_container_width=True)


def init_log():
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        # 获取日志记录中的文件全路径
        file_path = record["file"].path
        # 将绝对路径转换为相对于项目根目录的路径
        relative_path = os.path.relpath(file_path, root_dir)
        # 更新记录中的文件路径
        record["file"].path = f"./{relative_path}"
        # 返回修改后的格式字符串
        # 您可以根据需要调整这里的格式
        record["message"] = record["message"].replace(root_dir, ".")

        _format = (
            "<green>{time:%Y-%m-%d %H:%M:%S}</> | "
            + "<level>{level}</> | "
            + '"{file.path}:{line}":<blue> {function}</> '
            + "- <level>{message}</>"
            + "\n"
        )
        return _format

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
    )


init_log()

locales = utils.load_locales(i18n_dir)


mode_options = [
    (tr("Create Video Mode"), "create"),
    (tr("YouTube Automation Mode"), "youtube"),
    (tr("Full Auto Mode"), "full_auto"),
]
selected_mode_index = st.radio(
    tr("App Mode"),
    options=range(len(mode_options)),
    format_func=lambda index: mode_options[index][0],
    horizontal=True,
    label_visibility="collapsed",
)
if mode_options[selected_mode_index][1] == "youtube":
    render_youtube_automation_mode()
    config.save_config()
    st.stop()
if mode_options[selected_mode_index][1] == "full_auto":
    render_full_auto_mode()
    config.save_config()
    st.stop()


@st.cache_data(ttl=300, show_spinner=False)
def get_groq_model_ids(api_key: str, base_url: str) -> list[str]:
    if not api_key:
        return []

    normalized_base_url = (base_url or "https://api.groq.com/openai/v1").strip().rstrip("/")
    models_url = f"{normalized_base_url}/models"

    try:
        response = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])

        model_ids = []
        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    model_ids.append(model_id.strip())

        return sorted(set(model_ids))
    except Exception as e:
        logger.warning(f"failed to fetch groq models: {e}")
        return []

# 创建基础设置折叠框
if not config.app.get("hide_config", False):
    with st.expander(tr("Basic Settings"), expanded=False):
        config_panels = st.columns(3)
        left_config_panel = config_panels[0]
        middle_config_panel = config_panels[1]
        right_config_panel = config_panels[2]

        # 左侧面板 - 日志设置
        with left_config_panel:
            # 是否隐藏配置面板
            hide_config = st.checkbox(
                tr("Hide Basic Settings"), value=config.app.get("hide_config", False)
            )
            config.app["hide_config"] = hide_config

            # 是否禁用日志显示
            hide_log = st.checkbox(
                tr("Hide Log"), value=config.ui.get("hide_log", False)
            )
            config.ui["hide_log"] = hide_log

        # 中间面板 - LLM 设置

        with middle_config_panel:
            st.write(tr("LLM Settings"))
            # 下拉框需要展示“AIHubMix（推荐）”这类面向用户的文案，
            # 但配置文件和后端逻辑必须继续使用稳定的小写 provider id。
            # 因此这里显式维护 display label 和 provider id 的映射，避免
            # UI 文案变化污染 `config.app["llm_provider"]`。
            aihubmix_label = f"AIHubMix ({tr('Recommended')})"
            if config.ui.get("language") == "zh":
                aihubmix_label = "AIHubMix（推荐）"
            llm_provider_options = [
                ("OpenAI", "openai"),
                (aihubmix_label, "aihubmix"),
                ("AIML API", "aimlapi"),
                ("Moonshot", "moonshot"),
                ("Azure", "azure"),
                ("Qwen", "qwen"),
                ("DeepSeek", "deepseek"),
                ("ModelScope", "modelscope"),
                ("Gemini", "gemini"),
                ("Grok", "grok"),
                ("Groq", "groq"),
                ("Ollama", "ollama"),
                ("G4f", "g4f"),
                ("OneAPI", "oneapi"),
                ("Cloudflare", "cloudflare"),
                ("ERNIE", "ernie"),
                ("MiniMax", "minimax"),
                ("MiMo", "mimo"),
                ("Pollinations", "pollinations"),
                ("LiteLLM", "litellm"),
            ]
            llm_provider_labels = [label for label, _ in llm_provider_options]
            llm_provider_values = {
                label: provider_id for label, provider_id in llm_provider_options
            }
            saved_llm_provider = config.app.get("llm_provider", "openai").lower()
            saved_llm_provider_index = 0
            for i, (_, provider_id) in enumerate(llm_provider_options):
                if provider_id == saved_llm_provider:
                    saved_llm_provider_index = i
                    break

            llm_provider_label = st.selectbox(
                tr("LLM Provider"),
                options=llm_provider_labels,
                index=saved_llm_provider_index,
            )
            llm_helper = st.container()
            llm_provider = llm_provider_values[llm_provider_label]
            config.app["llm_provider"] = llm_provider

            llm_api_key = config.app.get(f"{llm_provider}_api_key", "")
            llm_secret_key = config.app.get(
                f"{llm_provider}_secret_key", ""
            )  # only for baidu ernie
            llm_base_url = config.app.get(f"{llm_provider}_base_url", "")
            llm_model_name = config.app.get(f"{llm_provider}_model_name", "")
            llm_account_id = config.app.get(f"{llm_provider}_account_id", "")

            tips = ""
            if llm_provider == "ollama":
                if not llm_model_name:
                    llm_model_name = "qwen:7b"
                if not llm_base_url:
                    llm_base_url = config.get_default_ollama_base_url()

                with llm_helper:
                    docker_hint = ""
                    if config.is_running_in_container():
                        docker_hint = "\n                            > 检测到容器环境，未配置 Base Url 时会默认使用 `http://host.docker.internal:11434/v1`\n"
                    tips = f"""
                            ##### Ollama配置说明
                            - **API Key**: 随便填写，比如 123
                            - **Base Url**: 一般为 http://localhost:11434/v1
                                - 如果 `MoneyPrinterTurbo` 和 `Ollama` **不在同一台机器上**，需要填写 `Ollama` 机器的IP地址
                                - 如果 `MoneyPrinterTurbo` 是 `Docker` 部署，建议填写 `http://host.docker.internal:11434/v1`{docker_hint}
                            - **Model Name**: 使用 `ollama list` 查看，比如 `qwen:7b`
                            """

            if llm_provider == "openai":
                if not llm_model_name:
                    llm_model_name = "gpt-3.5-turbo"
                with llm_helper:
                    tips = """
                            ##### OpenAI 配置说明
                            > 需要VPN开启全局流量模式
                            - **API Key**: [点击到官网申请](https://platform.openai.com/api-keys)
                            - **Base Url**: 官方 OpenAI 可留空；如果使用 OpenAI 兼容供应商（例如 OpenRouter），请填写对应的兼容接口地址
                            - **Model Name**: 填写**有权限**的模型；如果使用兼容供应商，请填写该平台支持的模型 ID
                            """

            if llm_provider == "aihubmix":
                if not llm_model_name:
                    llm_model_name = "gpt-5.4-mini"
                if not llm_base_url:
                    llm_base_url = "https://aihubmix.com/v1"
                with llm_helper:
                    tips = """
                            ##### AIHubMix 配置说明
                            - **注册链接**: [点击注册 AIHubMix](https://aihubmix.com/?aff=CEve)
                            - **Base Url**: 预填 https://aihubmix.com/v1
                            - **推荐模型**: 默认 gpt-5.4-mini，也可以填写 AIHubMix 支持的免费模型或其它模型 ID

                            推荐理由：
                            - **模型全**: Claude、GPT、Gemini、Grok、DeepSeek、通义等 700+ 模型一站覆盖
                            - **稳定**: 无限并发，永远在线，集群部署于谷歌云，长期为众多知名应用提供高并发服务
                            - **能力完整**: 文本、图片生成、视频生成、TTS、STT、向量嵌入、Rerank，多模态场景全搞定
                            - **计费透明**: 按量付费，无会员无包月，免费模型可使用
                            """

            if llm_provider == "aimlapi":
                if not llm_model_name:
                    llm_model_name = "openai/gpt-4o-mini"
                if not llm_base_url:
                    llm_base_url = "https://api.aimlapi.com/v1"
                with llm_helper:
                    tips = """
                            ##### AIML API Configuration
                            - **API Key**: create one at https://aimlapi.com/app/keys
                            - **Base Url**: https://api.aimlapi.com/v1
                            - **Model Name**: for example `openai/gpt-4o-mini`, `openai/gpt-4o`, `anthropic/claude-sonnet-4.5`, or `google/gemini-3-flash-preview`
                            """

            if llm_provider == "moonshot":
                if not llm_model_name:
                    llm_model_name = "moonshot-v1-8k"
                with llm_helper:
                    tips = """
                            ##### Moonshot 配置说明
                            - **API Key**: [点击到官网申请](https://platform.moonshot.cn/console/api-keys)
                            - **Base Url**: 固定为 https://api.moonshot.cn/v1
                            - **Model Name**: 比如 moonshot-v1-8k，[点击查看模型列表](https://platform.moonshot.cn/docs/intro#%E6%A8%A1%E5%9E%8B%E5%88%97%E8%A1%A8)
                            """
            if llm_provider == "oneapi":
                if not llm_model_name:
                    llm_model_name = (
                        "claude-3-5-sonnet-20240620"  # 默认模型，可以根据需要调整
                    )
                with llm_helper:
                    tips = """
                        ##### OneAPI 配置说明
                        - **API Key**: 填写您的 OneAPI 密钥
                        - **Base Url**: 填写 OneAPI 的基础 URL
                        - **Model Name**: 填写您要使用的模型名称，例如 claude-3-5-sonnet-20240620
                        """

            if llm_provider == "qwen":
                if not llm_model_name:
                    llm_model_name = "qwen-max"
                with llm_helper:
                    tips = """
                            ##### 通义千问Qwen 配置说明
                            - **API Key**: [点击到官网申请](https://dashscope.console.aliyun.com/apiKey)
                            - **Base Url**: 留空
                            - **Model Name**: 比如 qwen-max，[点击查看模型列表](https://help.aliyun.com/zh/dashscope/developer-reference/model-introduction#3ef6d0bcf91wy)
                            """

            if llm_provider == "g4f":
                if not llm_model_name:
                    llm_model_name = "gpt-3.5-turbo"
                with llm_helper:
                    tips = """
                            ##### gpt4free 配置说明
                            > [GitHub开源项目](https://github.com/xtekky/gpt4free)，可以免费使用GPT模型，但是**稳定性较差**
                            - **API Key**: 随便填写，比如 123
                            - **Base Url**: 留空
                            - **Model Name**: 比如 gpt-3.5-turbo，[点击查看模型列表](https://github.com/xtekky/gpt4free/blob/main/g4f/models.py#L308)
                            """
            if llm_provider == "azure":
                with llm_helper:
                    tips = """
                            ##### Azure 配置说明
                            > [点击查看如何部署模型](https://learn.microsoft.com/zh-cn/azure/ai-services/openai/how-to/create-resource)
                            - **API Key**: [点击到Azure后台创建](https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/OpenAI)
                            - **Base Url**: 留空
                            - **Model Name**: 填写你实际的部署名
                            """

            if llm_provider == "gemini":
                if not llm_model_name:
                    llm_model_name = "gemini-1.0-pro"

                with llm_helper:
                    tips = """
                            ##### Gemini 配置说明
                            > 需要VPN开启全局流量模式
                            - **API Key**: [点击到官网申请](https://ai.google.dev/)
                            - **Base Url**: 留空
                            - **Model Name**: 比如 gemini-1.0-pro
                            """

            if llm_provider == "grok":
                if not llm_model_name:
                    llm_model_name = "grok-4.3"
                if not llm_base_url:
                    llm_base_url = "https://api.x.ai/v1"

                with llm_helper:
                    tips = """
                            ##### Grok 配置说明
                            - **API Key**: 填写您的 GrokAPI 密钥
                            - **Base Url**: 填写 GrokAPI 的基础 URL
                            - **Model Name**: 比如 grok-4.3
                            """

            if llm_provider == "groq":
                if not llm_model_name:
                    llm_model_name = "llama-3.3-70b-versatile"
                if not llm_base_url:
                    llm_base_url = "https://api.groq.com/openai/v1"

                with llm_helper:
                    tips = """
                            ##### Groq 配置说明
                            - **API Key**: [点击到官网申请](https://console.groq.com/keys)
                            - **Base Url**: 固定为 https://api.groq.com/openai/v1
                            - **Model Name**: 比如 llama-3.3-70b-versatile
                            """

            if llm_provider == "deepseek":
                if not llm_model_name:
                    llm_model_name = "deepseek-chat"
                if not llm_base_url:
                    llm_base_url = "https://api.deepseek.com"
                with llm_helper:
                    tips = """
                            ##### DeepSeek 配置说明
                            - **API Key**: [点击到官网申请](https://platform.deepseek.com/api_keys)
                            - **Base Url**: 固定为 https://api.deepseek.com
                            - **Model Name**: 固定为 deepseek-chat
                            """

            if llm_provider == "mimo":
                if not llm_model_name:
                    llm_model_name = "mimo-v2.5-pro"
                if not llm_base_url:
                    llm_base_url = "https://api.xiaomimimo.com/v1"
                with llm_helper:
                    tips = """
                            ##### Xiaomi MiMo 配置说明
                            - **API Key**: [点击到官网申请](https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call)
                            - **Base Url**: 固定为 https://api.xiaomimimo.com/v1
                            - **Model Name**: 默认 mimo-v2.5-pro，也可以按官方文档填写其它可用模型
                            """

            if llm_provider == "modelscope":
                if not llm_model_name:
                    llm_model_name = "Qwen/Qwen3-32B"
                if not llm_base_url:
                    llm_base_url = "https://api-inference.modelscope.cn/v1/"
                with llm_helper:
                    tips = """
                            ##### ModelScope 配置说明
                            - **API Key**: [点击到官网申请](https://modelscope.cn/docs/model-service/API-Inference/intro)
                            - **Base Url**: 固定为 https://api-inference.modelscope.cn/v1/
                            - **Model Name**: 比如 Qwen/Qwen3-32B，[点击查看模型列表](https://modelscope.cn/models?filter=inference_type&page=1)
                            """

            if llm_provider == "ernie":
                with llm_helper:
                    tips = """
                            ##### 百度文心一言 配置说明
                            - **API Key**: [点击到官网申请](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
                            - **Secret Key**: [点击到官网申请](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
                            - **Base Url**: 填写 **请求地址** [点击查看文档](https://cloud.baidu.com/doc/WENXINWORKSHOP/s/jlil56u11#%E8%AF%B7%E6%B1%82%E8%AF%B4%E6%98%8E)
                            """

            if llm_provider == "pollinations":
                if not llm_model_name:
                    llm_model_name = "default"
                with llm_helper:
                    tips = """
                            ##### Pollinations AI Configuration
                            - **API Key**: Optional - Leave empty for public access
                            - **Base Url**: Default is https://text.pollinations.ai/openai
                            - **Model Name**: Use 'openai-fast' or specify a model name
                            """

            if llm_provider == "litellm":
                if not llm_model_name:
                    llm_model_name = "openai/gpt-4o-mini"
                with llm_helper:
                    tips = """
                            ##### LiteLLM Configuration
                            > [LiteLLM](https://github.com/BerriAI/litellm) routes to 100+ LLM providers via a unified interface.
                            > Set your provider's API key as an env var: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AWS_ACCESS_KEY_ID`, etc.
                            - **Model Name**: LiteLLM format — `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`, `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`, `gemini/gemini-2.5-flash`. See [full provider list](https://docs.litellm.ai/docs/providers)
                            """

            if tips and config.ui["language"] == "zh":
                # AIHubMix 自身就是 OpenAI-compatible 聚合平台；用户主动选择
                # 该 provider 时，再显示 DeepSeek/Moonshot 的通用推荐会造成
                # 信息干扰，也不利于保持合作入口的轻量、清晰。
                if llm_provider != "aihubmix":
                    st.warning(
                        "中国用户建议使用 **DeepSeek** 或 **Moonshot** 作为大模型提供商\n- 国内可直接访问，不需要VPN \n- 注册就送额度，基本够用"
                    )
                st.info(tips)

            st_llm_api_key = st.text_input(
                tr("API Key"), value=llm_api_key, type="password"
            )
            st_llm_base_url = st.text_input(tr("Base Url"), value=llm_base_url)
            st_llm_model_name = ""
            if llm_provider != "ernie":
                if llm_provider == "groq":
                    effective_api_key = st_llm_api_key or llm_api_key
                    effective_base_url = st_llm_base_url or llm_base_url
                    groq_models = get_groq_model_ids(
                        api_key=effective_api_key,
                        base_url=effective_base_url,
                    )

                    if groq_models:
                        selected_index = 0
                        if llm_model_name in groq_models:
                            selected_index = groq_models.index(llm_model_name)

                        st_llm_model_name = st.selectbox(
                            tr("Model Name"),
                            options=groq_models,
                            index=selected_index,
                            key="groq_model_name_select",
                        )
                    else:
                        st_llm_model_name = st.text_input(
                            tr("Model Name"),
                            value=llm_model_name,
                            key="groq_model_name_input",
                        )
                        if effective_api_key:
                            st.caption(
                                "Unable to load Groq model list right now. You can still enter a model name manually — note it won't be validated until generation."
                            )
                        else:
                            st.caption(
                                "Add a Groq API key to load available models automatically."
                            )
                else:
                    st_llm_model_name = st.text_input(
                        tr("Model Name"),
                        value=llm_model_name,
                        key=f"{llm_provider}_model_name_input",
                    )
                if st_llm_model_name:
                    config.app[f"{llm_provider}_model_name"] = st_llm_model_name
            else:
                st_llm_model_name = None

            if st_llm_api_key:
                config.app[f"{llm_provider}_api_key"] = st_llm_api_key
            if st_llm_base_url:
                config.app[f"{llm_provider}_base_url"] = st_llm_base_url
            if st_llm_model_name:
                config.app[f"{llm_provider}_model_name"] = st_llm_model_name
            if llm_provider == "ernie":
                st_llm_secret_key = st.text_input(
                    tr("Secret Key"), value=llm_secret_key, type="password"
                )
                config.app[f"{llm_provider}_secret_key"] = st_llm_secret_key

            if llm_provider == "cloudflare":
                st_llm_account_id = st.text_input(
                    tr("Account ID"), value=llm_account_id
                )
                if st_llm_account_id:
                    config.app[f"{llm_provider}_account_id"] = st_llm_account_id

        # 右侧面板 - API 密钥设置
        with right_config_panel:

            def get_keys_from_config(cfg_key):
                api_keys = config.app.get(cfg_key, [])
                if isinstance(api_keys, str):
                    api_keys = [api_keys]
                api_key = ", ".join(api_keys)
                return api_key

            def save_keys_to_config(cfg_key, value):
                value = value.replace(" ", "")
                if value:
                    config.app[cfg_key] = value.split(",")

            st.write(tr("Video Source Settings"))

            pexels_api_key = get_keys_from_config("pexels_api_keys")
            pexels_api_key = st.text_input(
                tr("Pexels API Key"), value=pexels_api_key, type="password"
            )
            save_keys_to_config("pexels_api_keys", pexels_api_key)

            pixabay_api_key = get_keys_from_config("pixabay_api_keys")
            pixabay_api_key = st.text_input(
                tr("Pixabay API Key"), value=pixabay_api_key, type="password"
            )
            save_keys_to_config("pixabay_api_keys", pixabay_api_key)

            coverr_api_key = get_keys_from_config("coverr_api_keys")
            coverr_api_key = st.text_input(
                tr("Coverr API Key"), value=coverr_api_key, type="password"
            )
            save_keys_to_config("coverr_api_keys", coverr_api_key)

llm_provider = config.app.get("llm_provider", "").lower()
panel = st.columns([1, 1.18, 1])
left_panel = panel[0]
middle_panel = panel[1]
right_panel = panel[2]

params = VideoParams(video_subject="")
params.match_materials_to_script = bool(
    st.session_state.get("match_materials_to_script", False)
)
uploaded_files = []
uploaded_audio_file = None
uploaded_bgm_file = None

with left_panel:
    with st.container(border=True):
        st.write(tr("Video Script Settings"))
        params.video_subject = st.text_input(
            tr("Video Subject"),
            key="video_subject",
        ).strip()

        video_languages = [
            (tr("Auto Detect"), ""),
        ]
        for code in support_locales:
            video_languages.append((code, code))

        selected_index = st.selectbox(
            tr("Script Language"),
            index=0,
            options=range(
                len(video_languages)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_languages[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_language = video_languages[selected_index][1]

        with st.expander(tr("Advanced Script Settings"), expanded=False):
            params.paragraph_number = st.slider(
                tr("Script Paragraph Number"),
                min_value=llm.MIN_SCRIPT_PARAGRAPH_NUMBER,
                max_value=llm.MAX_SCRIPT_PARAGRAPH_NUMBER,
                value=st.session_state.get("paragraph_number_input", 1),
                key="paragraph_number_input",
            )
            target_duration_seconds = st.selectbox(
                tr("Target Video Length"),
                options=[15, 30, 45, 60],
                index=1,
                format_func=lambda seconds: tr("Seconds Format").format(
                    seconds=seconds
                ),
                help=tr("Target Video Length Help"),
                key="target_duration_seconds",
            )
            params.video_script_prompt = st.text_area(
                tr("Custom Script Requirements"),
                height=100,
                max_chars=llm.MAX_SCRIPT_PROMPT_LENGTH,
                placeholder=tr("Custom Script Requirements Placeholder"),
                key="video_script_prompt",
            ).strip()

            use_custom_system_prompt = st.checkbox(
                tr("Use Custom System Prompt"),
                help=tr("Use Custom System Prompt Help"),
                key="use_custom_system_prompt",
            )

            if use_custom_system_prompt:
                custom_system_prompt = st.text_area(
                    tr("Custom System Prompt"),
                    height=240,
                    max_chars=llm.MAX_SCRIPT_SYSTEM_PROMPT_LENGTH,
                    key="custom_system_prompt",
                ).strip()
                params.custom_system_prompt = custom_system_prompt
            else:
                params.custom_system_prompt = ""

        if st.button(
            tr("Generate Video Script and Keywords"), key="auto_generate_script"
        ):
            with st.spinner(tr("Generating Video Script and Keywords")):
                script = llm.generate_script(
                    video_subject=params.video_subject,
                    language=params.video_language,
                    paragraph_number=params.paragraph_number,
                    video_script_prompt="\n".join(
                        part
                        for part in [
                            full_auto.build_duration_script_requirement(
                                target_duration_seconds
                            ),
                            params.video_script_prompt,
                        ]
                        if part
                    ),
                    custom_system_prompt=params.custom_system_prompt,
                )
                terms = llm.generate_terms(
                    params.video_subject,
                    script,
                    amount=8 if params.match_materials_to_script else 5,
                    match_script_order=params.match_materials_to_script,
                )
                if "Error: " in script:
                    st.error(tr(script))
                elif "Error: " in terms:
                    st.error(tr(terms))
                else:
                    st.session_state["video_script"] = script
                    st.session_state["video_terms"] = ", ".join(terms)
        params.video_script = st.text_area(
            tr("Video Script"), value=st.session_state["video_script"], height=280
        )
        if st.button(tr("Generate Video Keywords"), key="auto_generate_terms"):
            if not params.video_script:
                st.error(tr("Please Enter the Video Subject"))
                st.stop()

            with st.spinner(tr("Generating Video Keywords")):
                terms = llm.generate_terms(
                    params.video_subject,
                    params.video_script,
                    amount=8 if params.match_materials_to_script else 5,
                    match_script_order=params.match_materials_to_script,
                )
                if "Error: " in terms:
                    st.error(tr(terms))
                else:
                    st.session_state["video_terms"] = ", ".join(terms)

        params.video_terms = st.text_area(
            tr("Video Keywords"), value=st.session_state["video_terms"]
        )

        if st.button(
            tr("Generate Title and Description"),
            key="auto_generate_title_description",
        ):
            if not params.video_subject and not params.video_script:
                st.error(tr("Video Script and Subject Cannot Both Be Empty"))
                st.stop()

            with st.spinner(tr("Generating Title and Description")):
                metadata = llm.generate_social_metadata(
                    video_subject=params.video_subject,
                    video_script=params.video_script,
                    language=params.video_language or llm.DEFAULT_SOCIAL_LANGUAGE,
                    platform=llm.DEFAULT_SOCIAL_PLATFORM,
                )
                st.session_state["video_title"] = metadata.get("title", "")
                description_parts = [metadata.get("caption", "")]
                hashtags = metadata.get("hashtags", [])
                if hashtags:
                    description_parts.append(" ".join(hashtags))
                st.session_state["video_description"] = "\n\n".join(
                    part for part in description_parts if part
                )

        st.text_input(
            tr("Video Title"),
            key="video_title",
        )
        st.text_area(
            tr("Video Description"),
            key="video_description",
            height=140,
        )

with middle_panel:
    with st.container(border=True):
        st.write(tr("Video Settings"))
        video_concat_modes = [
            (tr("Sequential"), "sequential"),
            (tr("Random"), "random"),
        ]
        video_sources = [
            (tr("Pexels"), "pexels"),
            (tr("Pixabay"), "pixabay"),
            (tr("Coverr"), "coverr"),
            (tr("Multiple Stock APIs"), "stock_multi"),
            (tr("Local file"), "local"),
            (tr("TikTok"), "douyin"),
            (tr("Bilibili"), "bilibili"),
            (tr("Xiaohongshu"), "xiaohongshu"),
        ]

        saved_video_source_name = config.app.get("video_source", "pexels")
        saved_stock_sources = normalize_stock_sources(saved_video_source_name)
        source_option_values = [item[1] for item in video_sources]
        if len(saved_stock_sources) > 1:
            saved_video_source_name = "stock_multi"
        if saved_video_source_name not in source_option_values:
            saved_video_source_name = "pexels"
        saved_video_source_index = source_option_values.index(saved_video_source_name)

        selected_index = st.selectbox(
            tr("Video Source"),
            options=range(len(video_sources)),
            format_func=lambda x: video_sources[x][0],
            index=saved_video_source_index,
        )
        params.video_source = video_sources[selected_index][1]

        if params.video_source == "stock_multi":
            available_stock_sources = configured_stock_sources()
            default_stock_sources = [
                source_name
                for source_name in saved_stock_sources
                if source_name in available_stock_sources
            ]
            if not default_stock_sources:
                default_stock_sources = available_stock_sources
            selected_stock_sources = st.multiselect(
                tr("Stock Video APIs"),
                options=available_stock_sources,
                default=default_stock_sources,
                format_func=lambda source_name: tr(
                    STOCK_SOURCE_LABEL_KEYS[source_name]
                ),
                help=tr("Stock Video APIs Help"),
                key="create_video_stock_sources",
            )
            params.video_source = ",".join(selected_stock_sources)

        config.app["video_source"] = params.video_source

        if params.video_source == "local":
            # Streamlit 的文件类型校验对扩展名大小写敏感，这里同时放行大小写两种形式。
            local_file_types = ["mp4", "mov", "avi", "flv", "mkv", "jpg", "jpeg", "png"]
            uploaded_files = st.file_uploader(
                tr("Upload Local Files"),
                type=local_file_types + [file_type.upper() for file_type in local_file_types],
                accept_multiple_files=True,
            )

        selected_index = st.selectbox(
            tr("Video Concat Mode"),
            index=1,
            options=range(
                len(video_concat_modes)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_concat_modes[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_concat_mode = VideoConcatMode(
            video_concat_modes[selected_index][1]
        )

        # 视频转场模式
        video_transition_modes = [
            (tr("None"), VideoTransitionMode.none.value),
            (tr("Shuffle"), VideoTransitionMode.shuffle.value),
            (tr("FadeIn"), VideoTransitionMode.fade_in.value),
            (tr("FadeOut"), VideoTransitionMode.fade_out.value),
            (tr("SlideIn"), VideoTransitionMode.slide_in.value),
            (tr("SlideOut"), VideoTransitionMode.slide_out.value),
        ]
        selected_index = st.selectbox(
            tr("Video Transition Mode"),
            options=range(len(video_transition_modes)),
            format_func=lambda x: video_transition_modes[x][0],
            index=0,
        )
        params.video_transition_mode = VideoTransitionMode(
            video_transition_modes[selected_index][1]
        )

        video_aspect_ratios = [
            (tr("Portrait"), VideoAspect.portrait.value),
            (tr("Landscape"), VideoAspect.landscape.value),
        ]
        # Coverr 库 99% 是 16:9 横屏,默认竖屏会让画面被大量黑边包围。
        # 用 source-specific widget key 让每个 source 各自记忆 aspect 选择:
        #   - 首次切到 coverr → 默认 Landscape(index=1)
        #   - 其他 source 沿用 Portrait(index=0)
        #   - 用户在某 source 下手动改过 aspect,session_state 会记住,
        #     下次回到同一 source 时尊重用户选择,不会再被强制覆盖。
        default_aspect_index = 1 if params.video_source == "coverr" else 0
        selected_index = st.selectbox(
            tr("Video Ratio"),
            options=range(
                len(video_aspect_ratios)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_aspect_ratios[x][
                0
            ],  # The label is displayed to the user
            index=default_aspect_index,
            key=f"video_aspect_for_{params.video_source}",
        )
        params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])

        params.video_clip_duration = st.selectbox(
            tr("Clip Duration"), options=[2, 3, 4, 5, 6, 7, 8, 9, 10], index=1
        )
        params.video_count = st.selectbox(
            tr("Number of Videos Generated Simultaneously"),
            options=[1, 2, 3, 4, 5],
            index=0,
        )

        with st.expander(tr("Advanced Video Settings"), expanded=False):
            # 默认关闭，避免影响老用户的随机素材体验。开启后只改变关键词和素材
            # 下载/拼接顺序，用于改善画面主题早于或晚于旁白的问题。
            params.match_materials_to_script = st.checkbox(
                tr("Match Materials to Script Order"),
                help=tr("Match Materials to Script Order Help"),
                key="match_materials_to_script",
            )
            config.app["match_materials_to_script"] = params.match_materials_to_script

            video_codec_options = [
                ("libx264 (CPU)", "libx264"),
                ("Apple Metal Accelerated (h264_videotoolbox)", "h264_videotoolbox"),
                ("NVIDIA NVENC (h264_nvenc)", "h264_nvenc"),
                ("AMD AMF (h264_amf)", "h264_amf"),
                ("Intel QSV (h264_qsv)", "h264_qsv"),
                ("Windows MediaFoundation (h264_mf)", "h264_mf"),
            ]
            saved_video_codec = config.app.get("video_codec", "libx264")
            saved_video_codec_values = [item[1] for item in video_codec_options]
            if saved_video_codec not in saved_video_codec_values:
                saved_video_codec = "libx264"
            selected_codec_index = saved_video_codec_values.index(saved_video_codec)
            selected_codec_index = st.selectbox(
                tr("Video Encoder"),
                options=range(len(video_codec_options)),
                index=selected_codec_index,
                format_func=lambda x: video_codec_options[x][0],
                help=tr("Video Encoder Help"),
            )
            config.app["video_codec"] = video_codec_options[selected_codec_index][1]
    with st.container(border=True):
        st.write(tr("Audio Settings"))

        # 添加TTS服务器选择下拉框
        tts_servers = [
            (voice.NO_VOICE_NAME, tr("No Voice")),
            ("azure-tts-v1", "Azure TTS V1"),
            ("azure-tts-v2", "Azure TTS V2"),
            ("siliconflow", "SiliconFlow TTS"),
            ("gemini-tts", "Google Gemini TTS"),
            ("mimo-tts", "Xiaomi MiMo TTS"),
        ]

        # 获取保存的TTS服务器，默认为v1
        saved_tts_server = config.ui.get("tts_server", "azure-tts-v1")
        saved_tts_server_index = 0
        for i, (server_value, _) in enumerate(tts_servers):
            if server_value == saved_tts_server:
                saved_tts_server_index = i
                break

        selected_tts_server_index = st.selectbox(
            tr("TTS Servers"),
            options=range(len(tts_servers)),
            format_func=lambda x: tts_servers[x][1],
            index=saved_tts_server_index,
        )

        selected_tts_server = tts_servers[selected_tts_server_index][0]
        config.ui["tts_server"] = selected_tts_server

        # 根据选择的TTS服务器获取声音列表
        filtered_voices = []

        if selected_tts_server == voice.NO_VOICE_NAME:
            # 无配音是显式模式，只提供一个稳定 sentinel。这样普通 TTS 的空配置
            # 不会被误判为静音，后端也能继续通过同一条音频/字幕流程生成视频。
            filtered_voices = [voice.NO_VOICE_NAME]
        elif selected_tts_server == "siliconflow":
            # 获取硅基流动的声音列表
            filtered_voices = voice.get_siliconflow_voices()
        elif selected_tts_server == "gemini-tts":
            # 获取Gemini TTS的声音列表
            filtered_voices = voice.get_gemini_voices()
        elif selected_tts_server == "mimo-tts":
            # 获取 Xiaomi MiMo TTS 的预置音色列表
            filtered_voices = voice.get_mimo_voices()
        else:
            # 获取Azure的声音列表
            all_voices = voice.get_all_azure_voices(filter_locals=None)

            # 根据选择的TTS服务器筛选声音
            for v in all_voices:
                if selected_tts_server == "azure-tts-v2":
                    # V2版本的声音名称中包含"v2"
                    if "V2" in v:
                        filtered_voices.append(v)
                else:
                    # V1版本的声音名称中不包含"v2"
                    if "V2" not in v:
                        filtered_voices.append(v)

        if selected_tts_server == voice.NO_VOICE_NAME:
            friendly_names = {voice.NO_VOICE_NAME: tr("No Voice")}
        else:
            friendly_names = {
                v: v.replace("Female", tr("Female"))
                .replace("Male", tr("Male"))
                .replace("Neural", "")
                for v in filtered_voices
            }

        saved_voice_name = config.ui.get("voice_name", "")
        saved_voice_name_index = 0

        # 检查保存的声音是否在当前筛选的声音列表中
        if saved_voice_name in friendly_names:
            saved_voice_name_index = list(friendly_names.keys()).index(saved_voice_name)
        else:
            # 如果不在，则根据当前UI语言选择一个默认声音
            for i, v in enumerate(filtered_voices):
                if v.lower().startswith(st.session_state["ui_language"].lower()):
                    saved_voice_name_index = i
                    break

        # 如果没有找到匹配的声音，使用第一个声音
        if saved_voice_name_index >= len(friendly_names) and friendly_names:
            saved_voice_name_index = 0

        # 确保有声音可选
        if friendly_names:
            selected_friendly_name = st.selectbox(
                tr("Speech Synthesis"),
                options=list(friendly_names.values()),
                index=min(saved_voice_name_index, len(friendly_names) - 1)
                if friendly_names
                else 0,
            )

            voice_name = list(friendly_names.keys())[
                list(friendly_names.values()).index(selected_friendly_name)
            ]
            params.voice_name = voice_name
            config.ui["voice_name"] = voice_name
        else:
            # 如果没有声音可选，显示提示信息
            st.warning(
                tr(
                    "No voices available for the selected TTS server. Please select another server."
                )
            )
            params.voice_name = ""
            config.ui["voice_name"] = ""

        # 无配音模式会生成静音占位音频，不展示试听按钮，避免用户误以为需要测试声音。
        if (
            friendly_names
            and selected_tts_server != voice.NO_VOICE_NAME
            and st.button(tr("Play Voice"))
        ):
            play_content = params.video_subject
            if not play_content:
                play_content = params.video_script
            if not play_content:
                play_content = tr("Voice Example")
            with st.spinner(tr("Synthesizing Voice")):
                temp_dir = utils.storage_dir("temp", create=True)
                audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")
                sub_maker = voice.tts(
                    text=play_content,
                    voice_name=voice_name,
                    voice_rate=params.voice_rate,
                    voice_file=audio_file,
                    voice_volume=params.voice_volume,
                )
                # if the voice file generation failed, try again with a default content.
                if not sub_maker:
                    play_content = "This is a example voice. if you hear this, the voice synthesis failed with the original content."
                    sub_maker = voice.tts(
                        text=play_content,
                        voice_name=voice_name,
                        voice_rate=params.voice_rate,
                        voice_file=audio_file,
                        voice_volume=params.voice_volume,
                    )

                if sub_maker and os.path.exists(audio_file):
                    st.audio(audio_file, format="audio/mp3")
                    if os.path.exists(audio_file):
                        os.remove(audio_file)

        # 当选择V2版本或者声音是V2声音时，显示服务区域和API key输入框
        if selected_tts_server == "azure-tts-v2" or (
            voice_name and voice.is_azure_v2_voice(voice_name)
        ):
            saved_azure_speech_region = config.azure.get("speech_region", "")
            saved_azure_speech_key = config.azure.get("speech_key", "")
            azure_speech_region = st.text_input(
                tr("Speech Region"),
                value=saved_azure_speech_region,
                key="azure_speech_region_input",
            )
            azure_speech_key = st.text_input(
                tr("Speech Key"),
                value=saved_azure_speech_key,
                type="password",
                key="azure_speech_key_input",
            )
            config.azure["speech_region"] = azure_speech_region
            config.azure["speech_key"] = azure_speech_key

        # 当选择硅基流动时，显示API key输入框和说明信息
        if selected_tts_server == "siliconflow" or (
            voice_name and voice.is_siliconflow_voice(voice_name)
        ):
            saved_siliconflow_api_key = config.siliconflow.get("api_key", "")

            siliconflow_api_key = st.text_input(
                tr("SiliconFlow API Key"),
                value=saved_siliconflow_api_key,
                type="password",
                key="siliconflow_api_key_input",
            )

            # 显示硅基流动的说明信息
            st.info(
                tr("SiliconFlow TTS Settings")
                + ":\n"
                + "- "
                + tr("Speed: Range [0.25, 4.0], default is 1.0")
                + "\n"
                + "- "
                + tr("Volume: Uses Speech Volume setting, default 1.0 maps to gain 0")
            )

            config.siliconflow["api_key"] = siliconflow_api_key

        # 当选择 Xiaomi MiMo TTS 时，复用 MiMo LLM provider 的 API Key。
        # 这样用户如果同时使用 MiMo 生成文案和语音，只需要维护一份密钥。
        if selected_tts_server == "mimo-tts" or (
            voice_name and voice.is_mimo_voice(voice_name)
        ):
            saved_mimo_api_key = config.app.get("mimo_api_key", "")

            mimo_api_key = st.text_input(
                tr("MiMo API Key"),
                value=saved_mimo_api_key,
                type="password",
                key="mimo_tts_api_key_input",
            )

            st.info(
                tr("MiMo TTS Settings")
                + ":\n"
                + "- "
                + tr("Uses Xiaomi MiMo V2.5 TTS preset voices")
                + "\n"
                + "- "
                + tr("Speed and volume are currently handled by the provider defaults")
            )

            config.app["mimo_api_key"] = mimo_api_key

        params.voice_volume = st.selectbox(
            tr("Speech Volume"),
            options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
            index=2,
        )

        params.voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )

        custom_audio_file_types = ["mp3", "wav", "m4a", "aac", "flac", "ogg"]
        uploaded_audio_file = st.file_uploader(
            tr("Custom Audio File"),
            type=custom_audio_file_types
            + [file_type.upper() for file_type in custom_audio_file_types],
            accept_multiple_files=False,
            key="custom_audio_file_uploader",
        )
        if uploaded_audio_file:
            st.audio(uploaded_audio_file, format="audio/mp3")
            st.info(
                tr(
                    "Custom audio will be used directly. TTS synthesis will be skipped for this task."
                )
            )

        bgm_options = [
            (tr("No Background Music"), ""),
            (tr("Random Background Music"), "random"),
            (tr("Custom Background Music"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Background Music"),
            index=1,
            options=range(
                len(bgm_options)
            ),  # Use the index as the internal option value
            format_func=lambda x: bgm_options[x][
                0
            ],  # The label is displayed to the user
        )
        # Get the selected background music type
        params.bgm_type = bgm_options[selected_index][1]

        # Show or hide components based on the selection
        if params.bgm_type == "custom":
            uploaded_bgm_file = st.file_uploader(
                tr("Custom Background Music File"),
                type=["mp3", "MP3"],
                accept_multiple_files=False,
                key="custom_bgm_file_uploader",
            )
            if uploaded_bgm_file:
                st.audio(uploaded_bgm_file, format="audio/mp3")
        params.bgm_volume = st.selectbox(
            tr("Background Music Volume"),
            options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            index=2,
        )

with right_panel:
    with st.container(border=True):
        st.write(tr("Subtitle Settings"))
        params.subtitle_enabled = st.checkbox(tr("Enable Subtitles"), value=True)
        font_names = get_all_fonts()
        saved_font_name = config.ui.get("font_name", "Roboto.ttf")
        if saved_font_name not in font_names:
            saved_font_name = "Roboto.ttf" if "Roboto.ttf" in font_names else font_names[0]
        saved_font_name_index = font_names.index(saved_font_name)
        params.font_name = st.selectbox(
            tr("Font"), font_names, index=saved_font_name_index
        )
        config.ui["font_name"] = params.font_name
        render_font_preview(params.font_name)

        subtitle_positions = [
            (tr("Top"), "top"),
            (tr("Center"), "center"),
            (tr("Bottom"), "bottom"),
            (tr("Custom"), "custom"),
        ]
        saved_subtitle_position = config.ui.get("subtitle_position", "bottom")
        saved_position_index = 2
        for i, (_, pos_value) in enumerate(subtitle_positions):
            if pos_value == saved_subtitle_position:
                saved_position_index = i
                break
        selected_index = st.selectbox(
            tr("Position"),
            index=saved_position_index,
            options=range(len(subtitle_positions)),
            format_func=lambda x: subtitle_positions[x][0],
        )
        params.subtitle_position = subtitle_positions[selected_index][1]
        config.ui["subtitle_position"] = params.subtitle_position

        if params.subtitle_position == "custom":
            saved_custom_position = config.ui.get("custom_position", 70.0)
            custom_position = st.text_input(
                tr("Custom Position (% from top)"),
                value=str(saved_custom_position),
                key="custom_position_input",
            )
            try:
                params.custom_position = float(custom_position)
                if params.custom_position < 0 or params.custom_position > 100:
                    st.error(tr("Please enter a value between 0 and 100"))
                else:
                    config.ui["custom_position"] = params.custom_position
            except ValueError:
                st.error(tr("Please enter a valid number"))

        font_cols = st.columns([0.3, 0.7])
        with font_cols[0]:
            saved_text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")
            params.text_fore_color = st.color_picker(
                tr("Font Color"), saved_text_fore_color
            )
            config.ui["text_fore_color"] = params.text_fore_color

        with font_cols[1]:
            saved_font_size = config.ui.get("font_size", 60)
            params.font_size = st.slider(tr("Font Size"), 30, 100, saved_font_size)
            config.ui["font_size"] = params.font_size

        stroke_cols = st.columns([0.3, 0.7])
        with stroke_cols[0]:
            params.stroke_color = st.color_picker(tr("Stroke Color"), "#000000")
        with stroke_cols[1]:
            params.stroke_width = st.slider(tr("Stroke Width"), 0.0, 10.0, 1.5)

        subtitle_bg_cols = st.columns([0.4, 0.6])
        saved_subtitle_background_enabled = config.ui.get(
            "subtitle_background_enabled", True
        )
        with subtitle_bg_cols[0]:
            subtitle_background_enabled = st.checkbox(
                tr("Enable Subtitle Background"),
                value=saved_subtitle_background_enabled,
            )
        config.ui["subtitle_background_enabled"] = subtitle_background_enabled
        if subtitle_background_enabled:
            with subtitle_bg_cols[1]:
                saved_subtitle_background_color = config.ui.get(
                    "subtitle_background_color", "#000000"
                )
                params.text_background_color = st.color_picker(
                    tr("Subtitle Background Color"),
                    saved_subtitle_background_color,
                )
                config.ui["subtitle_background_color"] = params.text_background_color
        else:
            params.text_background_color = False

        saved_rounded_subtitle_background = config.ui.get(
            "rounded_subtitle_background", False
        )
        # 背景关闭时，圆角背景没有可渲染的底色。这里禁用控件并保留原配置，
        # 用户下次重新开启字幕背景后，可以继续使用之前保存的圆角偏好。
        params.rounded_subtitle_background = st.checkbox(
            tr("Rounded Subtitle Background"),
            value=(
                saved_rounded_subtitle_background
                if subtitle_background_enabled
                else False
            ),
            help=tr("Rounded Subtitle Background Help"),
            disabled=not subtitle_background_enabled,
        )
        if subtitle_background_enabled:
            config.ui["rounded_subtitle_background"] = (
                params.rounded_subtitle_background
            )
start_button = st.button(tr("Generate Video"), use_container_width=True, type="primary")
if start_button:
    config.save_config()
    task_id = str(uuid4())
    if not params.video_subject and not params.video_script:
        st.error(tr("Video Script and Subject Cannot Both Be Empty"))
        scroll_to_bottom()
        st.stop()

    selected_stock_sources = normalize_stock_sources(params.video_source)
    if params.video_source != "local" and not selected_stock_sources:
        st.error(tr("Please Select a Valid Video Source"))
        scroll_to_bottom()
        st.stop()

    missing_stock_sources = missing_stock_source_keys(params.video_source)
    if missing_stock_sources:
        missing_labels = ", ".join(
            tr(STOCK_SOURCE_LABEL_KEYS[source_name])
            for source_name in missing_stock_sources
        )
        st.error(
            tr("Missing Stock API Keys").format(providers=missing_labels)
        )
        scroll_to_bottom()
        st.stop()

    if uploaded_bgm_file:
        _, bgm_ext = os.path.splitext(os.path.basename(uploaded_bgm_file.name))
        bgm_ext = bgm_ext.lower() or ".mp3"
        bgm_filename = f"custom-bgm-{task_id}{bgm_ext}"
        custom_bgm_path = os.path.join(utils.song_dir(), bgm_filename)
        with open(custom_bgm_path, "wb") as f:
            f.write(uploaded_bgm_file.getbuffer())
        params.bgm_file = bgm_filename

    if uploaded_audio_file:
        task_dir = utils.task_dir(task_id)
        # 上传文件名来自浏览器，不能直接拼到磁盘路径里；这里只保留扩展名，
        # 并使用固定文件名保存到当前任务目录，避免路径穿越或特殊字符问题。
        _, audio_ext = os.path.splitext(os.path.basename(uploaded_audio_file.name))
        audio_ext = audio_ext.lower() or ".mp3"
        custom_audio_path = os.path.join(task_dir, f"custom-audio{audio_ext}")
        with open(custom_audio_path, "wb") as f:
            f.write(uploaded_audio_file.getbuffer())
        params.custom_audio_file = custom_audio_path

    if uploaded_files:
        local_videos_dir = utils.storage_dir("local_videos", create=True)
        # 每次重新上传时都以本次选择的素材为准，避免旧素材不断重复追加。
        params.video_materials = []
        persisted_local_materials = []
        for file in uploaded_files:
            file_path = os.path.join(local_videos_dir, f"{file.file_id}_{file.name}")
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
                m = MaterialInfo()
                m.provider = "local"
                m.url = file_path
                params.video_materials.append(m)
                persisted_local_materials.append(
                    {
                        "provider": m.provider,
                        "url": m.url,
                        "duration": m.duration,
                    }
                )
        # 将已上传并保存到本地的视频素材写入会话，供后续只改文案时直接复用。
        st.session_state["local_video_materials"] = persisted_local_materials
    elif params.video_source == "local" and st.session_state["local_video_materials"]:
        # 当用户没有重新上传文件时，复用最近一次已经保存到磁盘的本地素材列表。
        params.video_materials = []
        for material in st.session_state["local_video_materials"]:
            m = MaterialInfo()
            m.provider = material.get("provider", "local")
            m.url = material.get("url", "")
            m.duration = material.get("duration", 0)
            if m.url:
                params.video_materials.append(m)

    progress_container = st.empty()
    st.toast(tr("Generating Video"))
    with progress_container.container():
        st.markdown(
            f"""
            <div class="mpt-progress-shell">
                <div class="mpt-progress-title">{tr("Generating Video")}</div>
                <div class="mpt-progress-copy">{tr("Preparing your final video. This can take a few minutes.")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        progress_bar = st.progress(12, text=tr("Preparing generation settings"))

    logger.info(tr("Start Generating Video"))
    logger.info(utils.to_json(params))
    scroll_to_bottom()

    progress_bar.progress(38, text=tr("Creating video assets"))
    result = tm.start(task_id=task_id, params=params)
    progress_bar.progress(92, text=tr("Finalizing video output"))
    if not result or "videos" not in result:
        progress_container.empty()
        st.error(tr("Video Generation Failed"))
        logger.error(tr("Video Generation Failed"))
        scroll_to_bottom()
        st.stop()

    video_files = result.get("videos", [])
    progress_bar.progress(100, text=tr("Video Generation Completed"))
    progress_container.empty()
    st.success(tr("Video Generation Completed"))
    try:
        render_generated_videos(video_files)
    except Exception:
        pass

    logger.info(tr("Video Generation Completed"))
    scroll_to_bottom()

config.save_config()
