# Livestock

Herd register and breeding planner for cows and sheep in Rust. The aim is a "god bull": a male that is Good/Good on every gene.
See [MECHANICS.md](MECHANICS.md) for what we know about the game rules.

## Layout

```
Livestock\
  Github\          this repo
    backend\       Python (FastAPI + SQLModel). Genetics and planning live here, not in the browser.
    frontend\      JavaScript UI (Vite, vanilla JS, same View pattern as Sentinel)
  data\            runtime data: livestock.db, settings.json, captures\, cards\, names\
  build\frontend\  built UI, served by the backend
  venv\            Python environment
```

Nothing under `data\`, `build\` or `venv\` is in git.

## Running

Backend (serves the API and the built UI on port 8100):

```
run_backend.bat
```

Frontend, first time:

```
cd frontend
npm install
npm run build        # writes ..\..\build\frontend; restart the backend to serve it
```

For UI development, `npm run dev` serves on http://localhost:5173 and proxies to the backend.

## Capturing animal cards

Rust runs on a different PC from the backend. The screen is normally shared through **Perception**, the capture page
on the Pi that serves all the Rust tools (http://raspberrypi:8300, see the Perception project). Livestock is one of its
modules: it sends the card strip every 2 seconds, so just looking at the herd keeps it up to date, and **Capture**
from any device takes a whole picture through it. The header shows "Gaming PC screen shared" while it is.

Without Perception, a browser on the gaming PC can share the screen itself:

1. On the **gaming PC**, open `http://<backend-pc>:8100` in Chrome. Go to **Capture** and click **Share screen**.
   Screen sharing needs a secure origin. Add `http://<backend-pc>:8100` to
   `chrome://flags/#unsafely-treat-insecure-origin-as-secure` on the gaming PC, as was done for Sentinel.
2. In game, look at an animal so its card is showing.
3. Press **Capture** on any other device (phone, this PC). The gaming-PC browser grabs a frame and uploads it.
   On the gaming PC itself, **Capture in 5s** gives you time to switch back to the game.
4. Review the capture: draw the card and name boxes (once; **Save as default** reuses them), fill in genes,
   herd numbers and sex, then save as a new animal or update the matching one.

Names can be in any script, so they are kept as images. Each animal also gets a short app ID such as `C-01` or `S-03`.
