"""
Storyboard App — local Flask web app for organizing comic/screenplay storyboards.

Data model (v2):
  Project
    └─ Storyboard
         ├─ images[]   (main image + thumbnail slideshow)
         └─ frames[]   (shots: title, caption, shot type, notes, order)

Features:
  - Projects (top-level container) and Storyboards under each project
  - Create a storyboard WITH images inline (multiple images → main + thumbnails)
  - Frames per storyboard (title, dialogue/caption, shot type, notes)
  - Click through projects/storyboards in the browser UI
  - Import: JSON (project/board), CSV or Markdown scene list (text only)
  - Export: download a storyboard as JSON (backup / restore round-trip)
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
# Storage helpers
# ---------------------------------------------------------------------------
def _boards_file() -> Path:
    return DATA_DIR / "boards.json"


def _load() -> dict:
    f = _boards_file()
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return {"projects": []}
    return {"projects": []}


def _save(state: dict) -> None:
    _boards_file().write_text(json.dumps(state, indent=2))


def _find_project(state, pid):
    return next((p for p in state["projects"] if p["id"] == pid), None)


def _find_storyboard(state, pid, sid):
    p = _find_project(state, pid)
    if not p:
        return None, None
    return p, next((s for s in p["storyboards"] if s["id"] == sid), None)


# ---------------------------------------------------------------------------
# Image-gen hook (stub) — wire ComfyUI/FAL in here later.
# ---------------------------------------------------------------------------
def render_frame_stub(frame: dict) -> dict:
    """Placeholder for sketch -> ink line art rendering.
    When image generation is enabled, accept a sketch (path) and call ComfyUI
    (:8188) or FAL, returning the rendered image path/URL. No-op for now."""
    return frame


# ---------------------------------------------------------------------------
# Import helpers (text only: JSON / CSV / Markdown)
# ---------------------------------------------------------------------------
def _frames_from_csv(text: str) -> list:
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
                "title": get("title"), "caption": get("caption"),
                "shot": get("shot"), "notes": get("notes"),
                "order": len(frames), "image": None,
            })
        else:
            v = list(row.values())
            frames.append({
                "title": v[0] if len(v) > 0 else "",
                "caption": v[1] if len(v) > 1 else "",
                "shot": v[2] if len(v) > 2 else "",
                "notes": v[3] if len(v) > 3 else "",
                "order": len(frames), "image": None,
            })
    return frames


def _frames_from_md(text: str) -> list:
    frames = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        elif s and s[0] in "-*+":
            s = s[1:].strip()
        elif len(s) > 2 and s[0].isdigit() and s[1:3] in (". ", ") "):
            s = s[3:].strip()
        if not s:
            continue
        frames.append({
            "title": s, "caption": "", "shot": "", "notes": "",
            "order": len(frames), "image": None,
        })
    return frames


def _new_storyboard(title, description="", frames=None, images=None):
    return {
        "id": uuid.uuid4().hex[:8],
        "title": (title or "Untitled storyboard").strip() or "Untitled storyboard",
        "description": str(description or "").strip(),
        "images": images or [],
        "created": datetime.utcnow().isoformat() + "Z",
        "frames": frames or [],
    }


def _new_project(title, description="", storyboards=None):
    return {
        "id": uuid.uuid4().hex[:8],
        "title": (title or "Untitled project").strip() or "Untitled project",
        "description": str(description or "").strip(),
        "storyboards": storyboards or [],
    }


def _save_images(pid, sid, files) -> list:
    out = []
    dest_dir = UPLOAD_DIR / pid / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i, fh in enumerate(files):
        ext = Path(fh.filename or "").suffix.lower()
        if ext not in ALLOWED_IMG:
            ext = ".img"
        dest = dest_dir / f"{i:02d}{ext}"
        fh.save(str(dest))
        out.append(f"{pid}/{sid}/{dest.name}")
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", shot_types=SHOT_TYPES)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# --- Projects ---
@app.route("/api/projects", methods=["GET"])
def get_projects():
    return jsonify(_load()["projects"])


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True) or {}
    state = _load()
    p = _new_project(data.get("title", "Untitled project"), data.get("description", ""))
    state["projects"].append(p)
    _save(state)
    return jsonify(p), 201


@app.route("/api/projects/<pid>", methods=["GET", "DELETE"])
def project(pid):
    state = _load()
    p = _find_project(state, pid)
    if not p:
        return jsonify({"error": "project not found"}), 404
    if request.method == "DELETE":
        state["projects"] = [x for x in state["projects"] if x["id"] != pid]
        _save(state)
        return jsonify({"ok": True})
    return jsonify(p)


# --- Storyboards (under a project) ---
@app.route("/api/projects/<pid>/storyboards", methods=["POST"])
def create_storyboard(pid):
    state = _load()
    p = _find_project(state, pid)
    if not p:
        return jsonify({"error": "project not found"}), 404
    files = request.files.getlist("image")
    # body may come as JSON or multipart form
    if request.form:
        title = request.form.get("title", "")
        description = request.form.get("description", "")
    else:
        data = request.get_json(silent=True) or {}
        title = data.get("title", "")
        description = data.get("description", "")
    # generate sid first so the image upload path is stable
    sid = uuid.uuid4().hex[:8]
    images = _save_images(pid, sid, files) if files else []
    sb = _new_storyboard(title, description, images=images)
    sb["id"] = sid
    p["storyboards"].append(sb)
    _save(state)
    return jsonify(sb), 201


@app.route("/api/projects/<pid>/storyboards/<sid>", methods=["GET", "DELETE"])
def storyboard(pid, sid):
    state = _load()
    p, sb = _find_storyboard(state, pid, sid)
    if not p or not sb:
        return jsonify({"error": "storyboard not found"}), 404
    if request.method == "DELETE":
        p["storyboards"] = [x for x in p["storyboards"] if x["id"] != sid]
        _save(state)
        return jsonify({"ok": True})
    return jsonify(sb)


# --- Frames (under a storyboard) ---
@app.route("/api/projects/<pid>/storyboards/<sid>/frames", methods=["POST"])
def add_frame(pid, sid):
    state = _load()
    p, sb = _find_storyboard(state, pid, sid)
    if not p or not sb:
        return jsonify({"error": "storyboard not found"}), 404
    data = request.get_json(silent=True) or {}
    frame = {
        "id": uuid.uuid4().hex[:8],
        "title": data.get("title", "").strip(),
        "caption": data.get("caption", "").strip(),
        "shot": data.get("shot", "").strip(),
        "notes": data.get("notes", "").strip(),
        "order": len(sb["frames"]),
    }
    render_frame_stub(frame)
    sb["frames"].append(frame)
    _save(state)
    return jsonify(frame), 201


@app.route("/api/projects/<pid>/storyboards/<sid>/frames/<fid>", methods=["PUT", "DELETE"])
def frame(pid, sid, fid):
    state = _load()
    p, sb = _find_storyboard(state, pid, sid)
    if not p or not sb:
        return jsonify({"error": "storyboard not found"}), 404
    f = next((x for x in sb["frames"] if x["id"] == fid), None)
    if not f:
        return jsonify({"error": "frame not found"}), 404
    if request.method == "DELETE":
        sb["frames"] = [x for x in sb["frames"] if x["id"] != fid]
        _save(state)
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    for k in ("title", "caption", "shot", "notes", "order"):
        if k in data:
            f[k] = data[k]
    _save(state)
    return jsonify(f)


# --- Export ---
@app.route("/api/projects/<pid>/storyboards/<sid>/export", methods=["GET"])
def export_storyboard(pid, sid):
    state = _load()
    p, sb = _find_storyboard(state, pid, sid)
    if not p or not sb:
        return jsonify({"error": "storyboard not found"}), 404
    return jsonify(sb)


# --- Import (text: JSON / CSV / Markdown) ---
@app.route("/api/import", methods=["POST"])
def import_board():
    files = request.files.getlist("file")
    title_override = (request.form.get("title") or "").strip()
    if not files:
        return jsonify({"error": "no file uploaded"}), 400

    state = _load()
    created_projects = []

    for fh in files:
        name = (fh.filename or "").lower()
        ext = Path(name).suffix
        try:
            if ext == ".json":
                raw = json.loads(fh.read().decode("utf-8"))
                # project-shaped?
                if isinstance(raw, dict) and "storyboards" in raw:
                    pr = _new_project(raw.get("title", title_override or "Imported project"),
                                      raw.get("description", ""))
                    for s in raw["storyboards"]:
                        sb = _new_storyboard(s.get("title", ""), s.get("description", ""),
                                             frames=s.get("frames", []), images=s.get("images", []))
                        pr["storyboards"].append(sb)
                    created_projects.append(pr)
                else:
                    # board-shaped or list -> wrap in a project
                    boards = raw if isinstance(raw, list) else [raw]
                    pr = _new_project(title_override or "Imported project")
                    for b in boards:
                        if isinstance(b, dict):
                            sb = _new_storyboard(b.get("title", ""), b.get("description", ""),
                                                 frames=b.get("frames", []), images=b.get("images", []))
                            pr["storyboards"].append(sb)
                    created_projects.append(pr)
            elif ext == ".csv":
                frames = _frames_from_csv(fh.read().decode("utf-8", errors="replace"))
                if frames:
                    pr = _new_project(title_override or Path(name).stem or "Imported CSV")
                    pr["storyboards"].append(_new_storyboard("Scenes", frames=frames))
                    created_projects.append(pr)
            elif ext in (".md", ".txt"):
                frames = _frames_from_md(fh.read().decode("utf-8", errors="replace"))
                if frames:
                    pr = _new_project(title_override or Path(name).stem or "Imported Markdown")
                    pr["storyboards"].append(_new_storyboard("Scenes", frames=frames))
                    created_projects.append(pr)
            else:
                continue
        except Exception as e:
            return jsonify({"error": f"failed to parse {fh.filename}: {e}"}), 400

    if not created_projects:
        return jsonify({"error": "nothing importable found"}), 400

    state["projects"].extend(created_projects)
    _save(state)
    return jsonify({"imported": [p["id"] for p in created_projects], "projects": created_projects}), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
