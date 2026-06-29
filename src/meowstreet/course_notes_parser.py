import hashlib
import re
from pathlib import Path


SECTION_NAMES = [
    "Key Points",
    "Learning Path / Reasoning Chain",
    "Concepts & Definitions",
    "Methodology / Workflow",
    "Examples & Applications",
    "Cautions / Common Mistakes",
    "Transcript Gaps / Incomplete Segments",
    "Actionable Checklist",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SOURCE_RE = re.compile(r"^Source:\s+`?([^`\n]+)`?\s*$", re.MULTILINE)


def _relative(path, root):
    path = Path(path)
    root = Path(root)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _title_from_text(path, text):
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    stem = Path(path).stem
    if stem.endswith("_method_notes"):
        stem = stem[: -len("_method_notes")]
    return stem.replace("_", " ").strip() or Path(path).name


def _source_from_text(text):
    match = SOURCE_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_sections(text):
    lines = text.replace("\r", "").split("\n")
    sections = {}
    section_order = []
    current = None
    buffer = []

    def flush():
        if current is not None:
            content = "\n".join(buffer).strip()
            if current in sections and sections[current] and content:
                sections[current] = f"{sections[current]}\n\n{content}"
            elif current in sections and sections[current]:
                sections[current] = sections[current]
            else:
                sections[current] = content

    for line in lines:
        match = HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 2 and match.group(2).strip() in SECTION_NAMES:
            flush()
            current = match.group(2).strip()
            if current not in section_order:
                section_order.append(current)
            buffer = []
            continue
        if current is not None:
            buffer.append(line)
    flush()

    for name in SECTION_NAMES:
        sections.setdefault(name, "")
    return sections, section_order


def parse_method_note(path, root=None):
    path = Path(path)
    root = Path(root) if root is not None else path.parent
    text = path.read_text(encoding="utf-8")
    sections, section_order = _extract_sections(text)
    return {
        "path": _relative(path, root),
        "title": _title_from_text(path, text),
        "source": _source_from_text(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sections": sections,
        "section_order": section_order,
    }


def parse_method_notes_dir(notes_dir, root=None):
    notes_dir = Path(notes_dir)
    root = Path(root) if root is not None else notes_dir
    if not notes_dir.exists() or not notes_dir.is_dir():
        return []
    return [
        parse_method_note(path, root=root)
        for path in sorted(notes_dir.glob("*.md"))
    ]
