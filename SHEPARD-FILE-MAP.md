# Shepard File Map

This is the human-readable map of Shepard's repository. Standard technical filenames are preserved where development tools require them, but every file and folder is explained here.

## Files You Use Directly

| File | What it is for |
| --- | --- |
| `README.md` | Main overview and operating instructions shown by GitHub. |
| `MOVE-SHEPARD-TO-ANOTHER-COMPUTER.md` | Step-by-step guide for moving Shepard to her permanent computer. |
| `Setup Shepard.command` | First-time setup launcher for macOS. |
| `Start Shepard.command` | Everyday Shepard launcher for macOS. |
| `Setup-Shepard.bat` | First-time setup and launcher for Windows. |
| `SHEPARD-FILE-MAP.md` | This guide. |

## Required Project Files

| File | What it controls |
| --- | --- |
| `.gitignore` | Prevents private data, secrets, logs, ZIPs, and generated files from reaching GitHub. |
| `pyproject.toml` | Python project name, version, supported Python version, and command-line entry point. |
| `Modelfile.shepard` | Instructions Ollama uses to build the personalized `shepard:latest` model. |
| `config/default.json` | Safe default Sheep roster, personalities, models, and capabilities. |

## Shepard's Python Brain (`shepard/`)

| File | What it controls |
| --- | --- |
| `shepard/__init__.py` | Marks the folder as the Shepard Python package. |
| `shepard/__main__.py` | Makes `python -m shepard` work. |
| `shepard/cli.py` | Commands such as `web`, `run`, `doctor`, `council`, and `init`. |
| `shepard/config.py` | Loads and validates Shepard and Sheep configuration. |
| `shepard/database.py` | Stores jobs, messages, approvals, alarms, internships, and results. |
| `shepard/desktop.py` | Optional native desktop control-center window. |
| `shepard/internship_tools.py` | Résumé reading, internship scoring, and job-matching helpers. |
| `shepard/models.py` | Shared data models used by the Labyrinth. |
| `shepard/ollama.py` | Connects Shepard and local Sheep to Ollama. |
| `shepard/providers.py` | Connects selected Sheep to Gemini or Claude APIs. |
| `shepard/runtime.py` | Routes goals through Shepard and the appropriate Sheep. |
| `shepard/webapp.py` | Runs the private local website and its API at `127.0.0.1:8765`. |

## Labyrinth Website (`web/`)

| File | What it controls |
| --- | --- |
| `web/index.html` | Structure of the Labyrinth, menus, panels, chat, and controls. |
| `web/styles.css` | All visual styling, layout, responsiveness, and animation. |
| `web/app.js` | Main browser logic, API calls, UI interactions, and state. |
| `web/labyrinth-scene.js` | Circular maze projection and three-dimensional scene behavior. |
| `web/hand-controls.js` | Camera-based five-finger hand tracking and gesture controls. |
| `web/file-redirect.js` | Redirects accidental raw-file launches to the local Shepard server. |
| `web/sw.js` | Browser cache and offline-shell behavior. |
| `web/manifest.webmanifest` | Installable web-app name, colors, and icon settings. |
| `web/favicon.svg` | Shepard browser-tab icon. |

## Labyrinth Artwork (`web/assets/`)

| File | What it contains |
| --- | --- |
| `web/assets/shepard-tree.png` | Shepard sitting at the roots of the central tree. |
| `web/assets/sheep-sprites.png` | Animated pixel Sheep character sheet. |
| `web/assets/domain-houses.png` | Farmhouse domain artwork. |
| `web/assets/domain-chapels.png` | Chapel domain artwork. |
| `web/assets/domain-workshops.png` | Workshop and forge domain artwork. |
| `web/assets/domain-towers.png` | Tower domain artwork. |
| `web/assets/domain-keeps.png` | Keep and stronghold domain artwork. |
| `web/assets/MiniWorldSprites-LICENSE.txt` | Required license and attribution for included artwork. |

## Chrome Bridge (`chrome-extension/`)

| File | What it controls |
| --- | --- |
| `chrome-extension/README.md` | Chrome Bridge installation and pairing instructions. |
| `chrome-extension/manifest.json` | Chrome extension identity and narrowly scoped permissions. |
| `chrome-extension/popup.html` | Extension popup structure. |
| `chrome-extension/popup.css` | Extension popup appearance. |
| `chrome-extension/popup.js` | Explicit page sharing and approved browser-action behavior. |

## Automated Checks (`tests/`)

| File | What it verifies |
| --- | --- |
| `tests/test_config.py` | Configuration and Sheep customization safety. |
| `tests/test_database.py` | Persistence of jobs, approvals, alarms, and internships. |
| `tests/test_internship_tools.py` | Résumé extraction and internship scoring. |
| `tests/test_providers.py` | Gemini and Claude provider behavior. |
| `tests/test_runtime.py` | Multi-Sheep delegation and private-data boundaries. |
| `tests/test_webapp.py` | Website APIs, connections, approvals, browser bridge, and uploads. |

## Never Upload to GitHub

These paths are intentionally excluded by `.gitignore`:

- `secrets/` — API keys, OAuth tokens, and Chrome pairing information.
- `data/` — the private Labyrinth database, résumé data, jobs, and alarms.
- `artifacts/` — locally generated private work products.
- `.env` — environment credentials.
- `*.zip` — portable archives that may contain personal data.
- `.venv/`, `__pycache__/`, and `*.pyc` — generated Python files.
