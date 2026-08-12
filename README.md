# Storyboard Studio

A small local Flask web app for organizing comic / screenplay storyboards —
boards, frames, dialogue/captions, shot types, and visual notes. Data is saved
as JSON under `./data` (gitignored).

## Run

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

## Features (v1)

- Create storyboards (projects) with title + description
- Add frames: title, dialogue/caption, shot type, visual notes, ordering
- Click through boards in a responsive grid UI
- JSON persistence (no DB required)

## Planned

- Image generation hook (`render_frame_stub` in `app.py`) → wire ComfyUI (:8188)
  or FAL for sketch → ink line art
- Export board to PDF / markdown
- Multi-user / cloud deploy

Created by Drew Gilbert.
