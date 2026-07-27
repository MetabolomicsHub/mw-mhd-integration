import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional, Union

LOG_LINE_RE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"\[(?P<logger>[^\]]+)\]\s+"
    r"(?P<message>.*)$"
)
STUDY_ID_RE = re.compile(r"\bST\d{6}\b")
ERROR_CONVERTING_STUDY_RE = re.compile(r"\bError converting study (?P<study_id>ST\d{6})\b")
OFFENDING_LEVELS = {"ERROR", "WARNING"}


def parse_log_line(raw_line: str, line_number: int) -> Optional[dict]:
    line = raw_line.rstrip("\n")
    match = LOG_LINE_RE.match(line)
    if not match:
        return None

    entry = match.groupdict()
    study_ids = STUDY_ID_RE.findall(line)
    error_converting_study = ERROR_CONVERTING_STUDY_RE.search(entry["message"])
    return {
        "line_number": line_number,
        "timestamp": entry["timestamp"],
        "level": entry["level"],
        "logger": entry["logger"],
        "message": entry["message"],
        "study_ids": study_ids,
        "error_converting_study_id": (
            error_converting_study.group("study_id") if error_converting_study else None
        ),
        "raw": line,
    }


def normalize_message(message: str) -> str:
    return STUDY_ID_RE.sub("<STUDY_ID>", message)


def counter_to_ranked_items(
    counter: Counter, key_name: str
) -> list[dict[str, Union[int, str]]]:
    return [{key_name: key, "count": count} for key, count in counter.most_common()]


def analyze_log(log_path: Path, top_n: int) -> dict:
    level_counts: Counter[str] = Counter()
    exact_message_counts = {level: Counter() for level in OFFENDING_LEVELS}
    normalized_message_counts = {level: Counter() for level in OFFENDING_LEVELS}
    error_converting_study_counts: Counter[str] = Counter()
    offending_lines: list[dict] = []
    total_lines = 0
    parsed_lines = 0

    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            total_lines += 1
            entry = parse_log_line(raw_line, line_number)
            if entry is None:
                continue

            parsed_lines += 1
            level = entry["level"]
            if level not in OFFENDING_LEVELS:
                continue

            level_counts[level] += 1
            exact_message_counts[level][entry["message"]] += 1
            normalized_message_counts[level][normalize_message(entry["message"])] += 1

            if entry["error_converting_study_id"]:
                error_converting_study_counts[entry["error_converting_study_id"]] += 1

            offending_lines.append(entry)

    return {
        "log_file": str(log_path),
        "total_lines": total_lines,
        "parsed_lines": parsed_lines,
        "offending_line_count": len(offending_lines),
        "counts_by_level": {level: level_counts.get(level, 0) for level in sorted(OFFENDING_LEVELS)},
        "top_messages_exact": {
            level: counter_to_ranked_items(exact_message_counts[level], "message")[:top_n]
            for level in sorted(OFFENDING_LEVELS)
        },
        "top_messages_normalized": {
            level: counter_to_ranked_items(normalized_message_counts[level], "message")[:top_n]
            for level in sorted(OFFENDING_LEVELS)
        },
        "error_converting_study": {
            "count": sum(error_converting_study_counts.values()),
            "study_id_count": len(error_converting_study_counts),
            "study_ids": sorted(error_converting_study_counts),
            "study_id_counts": counter_to_ranked_items(
                error_converting_study_counts, "study_id"
            ),
        },
        "offending_lines": offending_lines,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a conversion log and emit a JSON summary for ERROR/WARNING lines, "
            "common messages, and 'Error converting study' IDs."
        )
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        default="conversion.log",
        help="Path to the log file to analyze. Defaults to conversion.log.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Where to write the JSON output. Defaults to stdout if omitted.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="How many top exact and normalized messages to include per level.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.exists():
        parser.error(f"Log file does not exist: {log_path}")

    if args.top_n < 1:
        parser.error("--top-n must be >= 1")

    result = analyze_log(log_path, top_n=args.top_n)
    payload = json.dumps(result, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{payload}\n", encoding="utf-8")
        print(output_path)
        return 0

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
