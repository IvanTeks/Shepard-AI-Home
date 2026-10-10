# Move Shepard to Another Computer

The portable ZIP contains the complete Shepard application, the current flock,
the Labyrinth database, saved jobs, alarms, internship tracker, and local résumé
data. It deliberately excludes the `secrets/` folder: API keys, OAuth tokens, and
the Chrome pairing secret should never travel inside an ordinary ZIP file.

## On the old laptop

1. Install [Ollama](https://ollama.com/download).
2. Install Python 3.11 or newer if the computer does not already have it.
3. Unzip the Shepard folder somewhere permanent.
4. On macOS, double-click **Setup Shepard.command**. If macOS blocks the first
   launch, Control-click it, choose **Open**, and confirm once.
5. On Windows, double-click **Setup-Shepard.bat**.

Setup downloads `qwen3:8b`, rebuilds the personalized `shepard:latest` model,
prepares the database, and opens `http://127.0.0.1:8765/`. The model download is
the large part; leave Ollama running until it finishes.

After the first setup, use **Start Shepard.command** on macOS. On Windows, run:

```text
python -m shepard web
```

## Reconnect private bridges

Open **Connections** inside Shepard and reconnect Gemini, Claude, or the Chrome
Bridge on the new computer. Those credentials are intentionally not inside the
ZIP. The Chrome extension is included in `chrome-extension/`; load that folder
again from `chrome://extensions` and generate a new pairing code.

## Make the laptop Shepard's always-on home

Keep Ollama and Shepard running and prevent the laptop from sleeping when you
need alarms or Active Scout to run continuously. Alarms and searches persist in
the database, but a sleeping or powered-off computer cannot ring or search. An
overdue alarm rings when Shepard wakes again.

The web address is local to the computer by default. Do not expose port 8765 to
the public internet. Remote access should be added later through an authenticated
private network rather than router port-forwarding.
