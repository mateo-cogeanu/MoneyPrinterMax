from datetime import datetime, timedelta


TARGET_DURATION_WORD_RANGES = {
    15: (35, 45),
    30: (70, 85),
    45: (105, 125),
    60: (140, 165),
}


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
