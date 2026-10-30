# Shepard Cloud Home — Free GitHub Codespaces Route

This is the recommended no-old-laptop, no-card route for Shepard right now.
It gives Shepard a private cloud computer that opens in browser-based VS Code.

## What this route gives you

- The full Python Shepard server and responsive Labyrinth, not just a static copy.
- A private forwarded web address protected by your GitHub login.
- The same GitHub repository on your Mac and in the cloud.
- Automatic startup whenever the Codespace starts.
- No payment method is required while you stay inside GitHub's included quota.

## Important limits

- It is **home-on-demand**, not 24/7 hosting. GitHub stops an idle Codespace.
- Shepard uses Gemini in the cloud because a free Codespace cannot run the local
  Ollama models efficiently. Local Shepard on your Mac still uses Ollama.
- The Codespace's uncommitted database and uploaded résumé persist while that
  Codespace exists, but they are not pushed to GitHub and disappear if you delete it.
- Keep port 8765 **Private**. Public mode would expose Shepard to anyone with the URL.

## One-time setup

1. Push this updated repository to GitHub.
2. Open the repository on GitHub and choose **Code → Codespaces → Create codespace on main**.
3. Add your Gemini key as a Codespaces secret named `GEMINI_API_KEY`:
   **GitHub Settings → Codespaces → Secrets → New secret**.
4. Allow that secret only for the `Shepard-AI-Home` repository.
5. Restart the Codespace after adding the secret.

The included `.devcontainer/devcontainer.json` will:

- initialize Shepard;
- start `Start-Shepard-Cloud.sh`;
- privately forward port 8765; and
- open the Labyrinth in a browser tab.

## Every time after that

Open <https://github.com/codespaces>, start **Shepard Cloud Home**, and use the
forwarded **Shepard Labyrinth** link in the VS Code **Ports** panel.

## Working from your Mac

Make edits on either machine, commit them, and push to GitHub. On the other
machine, pull before continuing. Never commit `secrets/`, `data/`, `.runtime/`,
or `.env`; those paths are ignored intentionally.

## Zero-billing guardrail

Do not attach a payment method for Codespaces. Without one, GitHub blocks usage
when the included quota is exhausted instead of charging you. Stop the Codespace
when you finish using it so the free core-hours last longer.

## Other free homes considered

- **GitHub Pages:** excellent for a static demo of the Labyrinth, but it cannot
  run Shepard's Python API, database, jobs, or approvals.
- **Render Free:** can run Python, but sleeps after inactivity and its free local
  filesystem is ephemeral. Shepard's SQLite memory would be lost after restarts.
- **Hugging Face Spaces:** CPU hardware is listed as free, but creating a Docker
  or Gradio compute Space currently requires a paid plan; static Spaces cannot
  run Shepard's backend.

Codespaces is therefore the safest free first move. A permanent always-on cloud
home would require either a paid persistent service or a larger rewrite around a
free hosted database and an external model API.
