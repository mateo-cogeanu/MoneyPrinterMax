from datetime import datetime, timedelta
from pathlib import Path
import re


TARGET_DURATION_WORD_RANGES = {
    15: (35, 45),
    30: (70, 85),
    45: (105, 125),
    60: (140, 165),
}
TOPIC_LINK_SEPARATOR = " | "
YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[^\s|]+",
    re.IGNORECASE,
)


def parse_topics(raw_topics: str) -> list[str]:
    topics = []
    seen = set()
    for line in (raw_topics or "").splitlines():
        topic = line.strip()
        if not topic or topic in seen:
            continue
        topics.append(topic)
        seen.add(topic)
    return topics


def ensure_topics_file(topics_file: str | Path):
    path = Path(topics_file)
    if path.exists():
        return path

    path.write_text(
        "5 baking soda cleaning tricks\n"
        "How AI automates small business tasks\n",
        encoding="utf-8",
    )
    return path


def strip_completed_link(line: str) -> str:
    return YOUTUBE_URL_RE.sub("", line or "").split(TOPIC_LINK_SEPARATOR, 1)[0].strip()


def parse_pending_topic_entries(raw_topics: str) -> list[dict]:
    entries = []
    seen = set()
    for line_number, line in enumerate((raw_topics or "").splitlines(), start=1):
        raw_line = line.rstrip("\n")
        topic = strip_completed_link(raw_line)
        if not topic or YOUTUBE_URL_RE.search(raw_line) or topic in seen:
            continue
        entries.append({"line_number": line_number, "topic": topic})
        seen.add(topic)
    return entries


def read_pending_topic_entries(topics_file: str | Path) -> list[dict]:
    path = ensure_topics_file(topics_file)
    return parse_pending_topic_entries(path.read_text(encoding="utf-8"))


def mark_topic_completed(topics_file: str | Path, line_number: int, video_url: str):
    path = ensure_topics_file(topics_file)
    lines = path.read_text(encoding="utf-8").splitlines()
    if line_number < 1 or line_number > len(lines):
        raise IndexError("topic line number is out of range")

    original_line = lines[line_number - 1].strip()
    topic = strip_completed_link(original_line)
    lines[line_number - 1] = f"{topic}{TOPIC_LINK_SEPARATOR}{video_url}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_schedule(topics: list[str], start_date, publish_times):
    clean_times = sorted({t.replace(second=0, microsecond=0) for t in publish_times})
    schedule = []
    if not clean_times:
        return schedule

    for index, topic in enumerate(topics):
        day_offset = index // len(clean_times)
        slot_time = clean_times[index % len(clean_times)]
        publish_date = start_date + timedelta(days=day_offset)
        publish_at = datetime.combine(publish_date, slot_time).astimezone()
        schedule.append(
            {
                "number": index + 1,
                "topic": topic,
                "publish_at": publish_at,
                "publish_label": publish_at.strftime("%Y-%m-%d %H:%M"),
            }
        )
    return schedule


def build_duration_script_requirement(target_seconds: int) -> str:
    normalized_seconds = (
        target_seconds if target_seconds in TARGET_DURATION_WORD_RANGES else 30
    )
    min_words, max_words = TARGET_DURATION_WORD_RANGES[normalized_seconds]
    return (
        f"Target the voiceover for about {normalized_seconds} seconds. "
        f"Write between {min_words} and {max_words} spoken words. "
        "Keep each video in this batch close to the same length. "
        "Do not make one topic much longer or shorter than the others."
    )
