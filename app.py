"""
Storyboard App — local Flask web app for organizing comic/screenplay storyboards.

Features (v1):
  - Create storyboards (projects) with a title + description
  - Add frames: title, dialogue/caption, shot type, visual notes, ordering
  - Click through boards in a grid layout (browser UI)
  - Data persisted as JSON under STORYBOARD_DATA (default: ./data, gitignored)

No image generation in v1. A clean hook is left for ComfyUI/FAL later
(see render_frame_stub()).

Run:  python app.py   ->   http://localhost:5000
"""
import os
import json
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

DATA_DIR = Path(os.environ.get("STORYBOARD_DATA", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

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
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", shot_types=SHOT_TYPES)


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
    for k in ("title", "caption", "shot", "notes", "order"):
        if k in data:
            f[k] = data[k]
    _save_boards(boards)
    return jsonify(f)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
