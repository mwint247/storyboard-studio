"""
Storyboard App — local Flask web app for organizing comic/screenplay storyboards.

Features:
  - Create storyboards (projects) with a title + description
  - Add frames: title, dialogue/caption, shot type, visual notes, ordering
  - Click through boards in a grid layout (browser UI)
  - Import: JSON board, CSV/Markdown scene list, or image files (one frame per
    uploaded sketch) — all via the Upload button in the UI
  - Export: download a board as JSON (backup / restore round-trip)
  - Data persisted as JSON under STORYBOARD_DATA (default: ./data, gitignored)
  - Uploaded images stored under ./data/uploads and served at /uploads/...

No image generation in v1. A clean hook is left for ComfyUI/FAL later
(see render_frame_stub()).

Run:  python app.py   ->   http://localhost:5000
"""
import os
import io
import csv
import json
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB cap on uploads

DATA_DIR = Path(os.environ.get("STORYBOARD_DATA", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# Shot vocabulary used by the "shot type" dropdown in the UI.
SHOT_TYPES = [
    "Wide", "Establishing", "Medium", "Over-the-shoulder", "Close-up",
    "Extreme Close-up", "POV", "Insert", "Aerial", "Tracking",
]


# ---------------------------------------------------------------------------
# Storage helpers (JSON file per app instance — one boards.json)
# ---------------------------------------------------------------------------
def _boards_file() -> Path:
    return DATA_DIR / "boards.json"


def _load_boards() -> list:
    f = _boards_file()
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return []
    return []


def _save_boards(boards: list) -> None:
    _boards_file().write_text(json.dumps(boards, indent=2))


# ---------------------------------------------------------------------------
# Image-gen hook (stub) — wire ComfyUI/FAL in here later.
# ---------------------------------------------------------------------------
def render_frame_stub(frame: dict) -> dict:
    """Placeholder for sketch -> ink line art rendering.

    When image generation is enabled, accept a sketch (base64/file path) and
    call ComfyUI (:8188) or FAL, returning the rendered image path/URL.
    For now it just echoes the frame back unchanged.
    """
    return frame


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------
def _normalize_board(raw: dict, title_override: str = "") -> dict:
    """Coerce an arbitrary dict into a clean board (fresh ids, renumbered)."""
    board = {
        "id": uuid.uuid4().hex[:8],
        "title": (title_override or str(raw.get("title", "Imported board"))).strip()
        or "Imported board",
        "description": str(raw.get("description", "")).strip(),
        "created": datetime.utcnow().isoformat() + "Z",
        "frames": [],
    }
    for f in raw.get("frames", []):
        board["frames"].append({
            "id": uuid.uuid4().hex[:8],
            "title": str(f.get("title", "")).strip(),
            "caption": str(f.get("caption", "")).strip(),
            "shot": str(f.get("shot", "")).strip(),
            "notes": str(f.get("notes", "")).strip(),
            "order": len(board["frames"]),
            "image": f.get("image"),
        })
    for i, f in enumerate(board["frames"]):
        f["order"] = i
    return board


def _csv_to_frames(text: str) -> list:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [f.lower().strip() for f in (reader.fieldnames or [])]
    key_map = {}
    for f in fieldnames:
        for cand in ("title", "caption", "shot", "notes", "order", "image"):
            if cand in f:
                key_map[cand] = f
                break
    frames = []
    for row in reader:
        if key_map:
            get = lambda c: (row.get(key_map.get(c, ""), "") or "")
            frames.append({
                "title": get("title"),
                "caption": get("caption"),
                "shot": get("shot"),
                "notes": get("notes"),
                "order": len(frames),
                "image": None,
            })
        else:
            vals = list(row.values())
            frames.append({
                "title": vals[0] if len(vals) > 0 else "",
                "caption": vals[1] if len(vals) > 1 else "",
                "shot": vals[2] if len(vals) > 2 else "",
                "notes": vals[3] if len(vals) > 3 else "",
                "order": len(frames),
                "image": None,
            })
    return frames


def _md_to_frames(text: str) -> list:
    frames = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # strip common markdown markers
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        elif s[0] in "-*+":
            s = s[1:].strip()
        elif s[0].isdigit() and s[1:3] in (". ", ") "):
            s = s[3:].strip()
        if not s:
            continue
        frames.append({
            "title": s,
            "caption": "",
            "shot": "",
            "notes": "",
            "order": len(frames),
            "image": None,
        })
    return frames


def _save_upload(board_id: str, frame_id: str, file) -> str:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMG:
        ext = ".img"
    dest_dir = UPLOAD_DIR / board_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{frame_id}{ext}"
    file.save(str(dest))
    return f"{board_id}/{dest.name}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", shot_types=SHOT_TYPES)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/boards", methods=["GET"])
def get_boards():
    return jsonify(_load_boards())


@app.route("/api/boards", methods=["POST"])
def create_board():
    data = request.get_json(silent=True) or {}
    boards = _load_boards()
    board = {
        "id": uuid.uuid4().hex[:8],
        "title": data.get("title", "Untitled").strip() or "Untitled",
        "description": data.get("description", "").strip(),
        "created": datetime.utcnow().isoformat() + "Z",
        "frames": [],
    }
    boards.append(board)
    _save_boards(boards)
    return jsonify(board), 201


@app.route("/api/boards/<bid>", methods=["GET", "DELETE"])
def board(bid):
    boards = _load_boards()
    b = next((x for x in boards if x["id"] == bid), None)
    if not b:
        return jsonify({"error": "board not found"}), 404
    if request.method == "DELETE":
        boards = [x for x in boards if x["id"] != bid]
        _save_boards(boards)
        return jsonify({"ok": True})
    return jsonify(b)


@app.route("/api/boards/<bid>/frames", methods=["POST"])
def add_frame(bid):
    boards = _load_boards()
    b = next((x for x in boards if x["id"] == bid), None)
    if not b:
        return jsonify({"error": "board not found"}), 404
    data = request.get_json(silent=True) or {}
    frame = {
        "id": uuid.uuid4().hex[:8],
        "title": data.get("title", "").strip(),
        "caption": data.get("caption", "").strip(),
        "shot": data.get("shot", "").strip(),
        "notes": data.get("notes", "").strip(),
        "order": len(b["frames"]),
        "image": data.get("image"),
    }
    render_frame_stub(frame)  # image-gen hook (no-op for now)
    b["frames"].append(frame)
    _save_boards(boards)
    return jsonify(frame), 201


@app.route("/api/boards/<bid>/frames/<fid>", methods=["PUT", "DELETE"])
def frame(bid, fid):
    boards = _load_boards()
    b = next((x for x in boards if x["id"] == bid), None)
    if not b:
        return jsonify({"error": "board not found"}), 404
    f = next((x for x in b["frames"] if x["id"] == fid), None)
    if not f:
        return jsonify({"error": "frame not found"}), 404
    if request.method == "DELETE":
        b["frames"] = [x for x in b["frames"] if x["id"] != fid]
        _save_boards(boards)
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    for k in ("title", "caption", "shot", "notes", "order", "image"):
        if k in data:
            f[k] = data[k]
    _save_boards(boards)
    return jsonify(f)


@app.route("/api/boards/<bid>/export", methods=["GET"])
def export_board(bid):
    boards = _load_boards()
    b = next((x for x in boards if x["id"] == bid), None)
    if not b:
        return jsonify({"error": "board not found"}), 404
    return jsonify(b)


@app.route("/api/import", methods=["POST"])
def import_board():
    files = request.files.getlist("file")
    title_override = (request.form.get("title") or "").strip()
    if not files:
        return jsonify({"error": "no file uploaded"}), 400

    boards = _load_boards()
    created = []
    image_files = []

    for fh in files:
        name = (fh.filename or "").lower()
        ext = Path(name).suffix
        try:
            if ext == ".json":
                raw = json.loads(fh.read().decode("utf-8"))
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            created.append(_normalize_board(item, title_override))
                elif isinstance(raw, dict):
                    created.append(_normalize_board(raw, title_override))
            elif ext == ".csv":
                text = fh.read().decode("utf-8", errors="replace")
                frames = _csv_to_frames(text)
                if frames:
                    created.append({
                        "id": uuid.uuid4().hex[:8],
                        "title": title_override or Path(name).stem or "Imported CSV",
                        "description": "",
                        "created": datetime.utcnow().isoformat() + "Z",
                        "frames": frames,
                    })
            elif ext in (".md", ".txt"):
                text = fh.read().decode("utf-8", errors="replace")
                frames = _md_to_frames(text)
                if frames:
                    created.append({
                        "id": uuid.uuid4().hex[:8],
                        "title": title_override or Path(name).stem or "Imported Markdown",
                        "description": "",
                        "created": datetime.utcnow().isoformat() + "Z",
                        "frames": frames,
                    })
            elif ext in ALLOWED_IMG:
                image_files.append(fh)
            else:
                # unknown — skip silently
                continue
        except Exception as e:
            return jsonify({"error": f"failed to parse {fh.filename}: {e}"}), 400

    # Build a board from uploaded images (one frame per sketch)
    if image_files:
        image_files.sort(key=lambda f: (f.filename or "").lower())
        img_board = {
            "id": uuid.uuid4().hex[:8],
            "title": title_override or "Uploaded sketches",
            "description": "",
            "created": datetime.utcnow().isoformat() + "Z",
            "frames": [],
        }
        for fh in image_files:
            fid = uuid.uuid4().hex[:8]
            rel = _save_upload(img_board["id"], fid, fh)
            img_board["frames"].append({
                "id": fid,
                "title": Path(fh.filename or fid).stem,
                "caption": "",
                "shot": "",
                "notes": "",
                "order": len(img_board["frames"]),
                "image": rel,
            })
        created.append(img_board)

    if not created:
        return jsonify({"error": "nothing importable found in upload"}), 400

    boards.extend(created)
    _save_boards(boards)
    return jsonify({"imported": [b["id"] for b in created], "boards": created}), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
