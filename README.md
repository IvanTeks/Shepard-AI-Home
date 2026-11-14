# Shepard

> **Start here:** See [SHEPARD-FILE-MAP.md](SHEPARD-FILE-MAP.md) for a plain-English map of every part of the project. To install Shepard on another machine, follow [MOVE-SHEPARD-TO-ANOTHER-COMPUTER.md](MOVE-SHEPARD-TO-ANOTHER-COMPUTER.md).

Shepard is a local-first AI ecosystem powered by Ollama. Shepard coordinates a
group of specialized, customizable agents called **Sheep**. Their shared task,
message, and audit system is the **Labyrinth**.

This first version is deliberately local and narrow: it proves that agents can
plan, delegate, collaborate, persist their work, and stop at permission gates.
Account connectors and device control come after this foundation is tested.

## What works now

- Shepard plans a goal with `shepard:latest` by default, using your local Ollama service.
- Tasks are delegated to configurable Sheep using `qwen3:8b` by default.
- Shepard or any individual Sheep can instead use a connected Claude API model.
- Sheep see relevant work from earlier Sheep and return recorded results.
- Jobs, tasks, messages, approvals, and audit events persist in SQLite.
- External capabilities stop at an approval gate.
- Agent names, roles, personalities, models, and capabilities live in JSON.
- The web dashboard has a direct Shepard chat mode and a 3D circular Labyrinth mode.
- The Greek-inspired Labyrinth uses one projected world coordinate system for the maze, domains, houses, Sheep, routes, and Shepard. It can be orbited, tilted, and zoomed without characters drifting away from their homes.
- The living-world renderer adds dimensional maze walls, atmospheric particles, depth lighting, subtle idle motion, active travel routes, responsive labels, and a reduced-motion fallback without adding a web framework or external rendering dependency.
- Tap Shepard at the central tree to zoom into the roots and open an in-world chat.
- Shepard can safely extract text from public webpage URLs pasted into chat; private and local network addresses are blocked.
- Multi-step chat requests can become real jobs. Assigned Sheep visibly travel to the roots, then their result returns to the conversation.
- The Labyrinth sky follows local time and, with browser location permission, current local weather. Coordinates are rounded before the weather request and are not stored.
- Day skies include drifting clouds and birds; night skies bring out the owls.
- A weekly council gives every registered Sheep a review task and asks Shepard to synthesize process improvements.
- New Sheep can be created from the dashboard and receive their own domain automatically.
- Shepard's Bell provides persistent one-time, daily, weekday, and weekly alarms with a full-screen ring, sound, dismiss, and ten-minute snooze. Overdue alarms ring on the next launch.
- The Connections menu reports honest per-service setup state and includes Claude, Wayfinder's approval-gated Chrome bridge, Google Calendar OAuth, and owner-controlled Outlook Web sharing for mail and calendar pages.
- Wayfinder is a dedicated Browser Sheep with separate `browser.read`, `browser.navigate`, and `browser.submit` capabilities.
- The Career Garden separates opportunity triage, Active Scout, résumé work, and Chrome imports into four focused, responsive stations.
- Résumé Studio accepts local DOCX, TXT, and Markdown uploads, produces a Scout + Reviewer critique, and derives grounded role and keyword suggestions.
- Active Scout checks Remotive's public remote-job API and the public SimplifyJobs/Pitt CSC internship registry on a schedule while Shepard is open. Its local evidence score weighs requested-role alignment, grounded résumé signals, and comma-separated location preferences before saving discoveries for owner review.
- Research Trails links to official NSF REU, USAJOBS Early Careers, NASA internship, and ORISE undergraduate portals for owner-led research without claiming automated access those services do not provide.
- Shepard's Voice Station provides push-to-talk dictation, review-before-send transcripts, optional spoken replies, and barge-in that stops speech when the microphone starts. Dictation never bypasses the Gatekeeper or submits a message automatically.
- Hen is a market-research Sheep with an evidence-locked two-day watchlist briefing, a configurable $50 price ceiling, IPO-calendar signals that require SEC verification, and an independent Reviewer pass. Hen cannot place trades or promise returns.
- No third-party Python packages are required.

The tiny domain-building sprites are adapted from Shade's CC0 MiniWorld Sprites;
the local attribution copy is in `web/assets/MiniWorldSprites-LICENSE.txt`.

## Run it

From this directory:

```bash
python3 -m shepard init
python3 -m shepard doctor
python3 -m shepard agents
python3 -m shepard run "Find three software internships that fit my background and prepare an application plan"
```

Launch the local web control center:

```bash
python3 -m shepard web
```

On macOS, you can also double-click `Start Shepard.command`. It reopens the
working page if Shepard is already running, or starts the server first if it is
not. The address is always `http://127.0.0.1:8765/` and only works while the
local Shepard server is running.

To run Shepard from a private GitHub Codespace instead of leaving a computer
on, follow [SHEPARD-CLOUD-HOME.md](SHEPARD-CLOUD-HOME.md). The repository now
contains a ready-to-use browser VS Code environment that starts Shepard and
privately forwards port 8765. This route uses GitHub's included Codespaces quota
and stops when idle; it is a free workshop/home-on-demand, not a 24/7 server.

For a new computer, read `TRANSFER-GUIDE.md` and run `Setup Shepard.command` on
macOS or `Setup-Shepard.bat` on Windows. The transfer package includes Shepard's
model recipe and current local memory, but never includes the `secrets/` folder.

Drag the Labyrinth to orbit it, scroll to zoom, or double-click to reset the view.
Every farmhouse and Sheep is projected from a fixed location inside the maze;
only Sheep assigned to active work leave their domain and travel to the roots.
Tap the central Shepard tree for the in-world chat, or use the mode switch for
the full chat room. Paste a public `http://` or `https://` URL into either chat
when you want Shepard to read that page.

## Use Shepard's voice

Open the roots chat or full chat room and press **Speak**. Shepard places the
raw transcript in the message box so you can correct it before choosing
**Send**; dictation never auto-submits a request or skips an approval. Turn on
**Read replies** in the Voice Station when you want Shepard to speak completed
answers aloud. Starting the microphone while Shepard is speaking stops the
current voice so you can interrupt naturally.

This first voice bridge is free and needs no API key. Read-aloud uses the
device's installed system voice. Dictation uses the browser speech-recognition
service and, depending on the browser, audio may be processed by the browser
provider. It is therefore not the same as an offline Whisper installation.

## Connect Claude

Create an Anthropic API key, then open **Connections → Claude API → Connect**
and paste the key. Shepard validates it before saving it locally in the
git-ignored `secrets/anthropic.json` file. Anthropic API billing is separate
from a Claude web subscription.

After connecting, click Shepard or a Sheep, enter a returned model name such as
`claude:claude-sonnet-5` in its **Model** field, and save. Other characters can
remain on local Ollama, so a single job may use both local and Claude models.

## Connect Gemini

Open **Connections → Gemini API → Connect** and paste a Gemini API key from
Google AI Studio. Shepard tests the key and stores it only in the git-ignored
`secrets/gemini.json` file. The key provides Gemini models; it does not grant
Google Calendar, Gmail, Drive, or other Google account access.

After connecting, choose a returned `gemini:...` model in any Shepard or Sheep
character profile. Characters that are not changed continue using Ollama or
their separately selected provider.

## Connect Chrome

Open **Connections → Chrome Bridge → Install**, generate a pairing code, and
follow the displayed path. In Chrome:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select Shepard's `chrome-extension` folder.
4. Pin **Shepard Chrome Bridge**, open its popup, paste the pairing code, and
   choose **Save & test**.

When you want Shepard to read the current webpage, click the extension and then
**Share this page**. The extension uses Chrome's temporary active-tab permission:
it does not request browsing history, cookies, passwords, or permanent access to
every website. Shared page text is kept only in server memory, with at most five
pages retained and each discarded after one hour. Ask
Shepard “summarize this page” or “use the current Chrome tab” after sharing it.

Wayfinder can also prepare two browser actions from Shepard chat:

- “Open `https://example.com` in Chrome” proposes an active-tab navigation.
- “Submit this application form” proposes submission of the most recently shared page.

Neither action runs immediately. Approve the specific action in Shepard's
**Gatekeeper**, open the extension, choose **Refresh** under **Approved actions**,
and run it there. Form submission has an additional review step: the extension
shows the destination and field names without reading their values, blocks
password/payment/banking/identity fields, requires exactly one visible non-search
form, and requires a final checkbox before submission.

## Use the Career Garden

Start with **Résumé Studio** in **05 / Internships**. Upload a DOCX, TXT, or
Markdown résumé and let Scout and Reviewer finish the critique. The original
upload and normalized text remain in `data/owner/`; the résumé is not sent to a
job board.

Use **Active Scout** to choose a focused query, optional location preference,
schedule, and minimum preliminary match score. It uses the public Remotive and
SimplifyJobs/Pitt CSC feeds, never sends résumé text, and runs while the Shepard server is open. The shortest schedule makes one Remotive request every six hours, respecting its public API guidance. New matches
arrive as **discovered** opportunities. Open a discovery and choose **Run full
five-Sheep review** before preparing an application. Each discovery links back
to its source listing; Remotive listings keep the required attribution.

Use **Research Trails** for programs that require a human visit, including NSF
REU sites, federal Pathways roles, NASA programs, and ORISE research placements.
Choose a live posting there, then bring it back through the Chrome Bridge for
the same evidence route and owner-controlled tracking.

For a page you already found manually:

1. Open one internship page in Chrome.
2. Use **Shepard Chrome Bridge → Share current page**.
3. Open **05 / Internships** in Shepard and confirm the shared-page card.
4. Add an optional deadline or owner note, then choose **Analyze shared job**.

Wayfinder extracts the posting, Scout compares it with the private résumé in
`data/owner/resume.txt`, Scribe prepares truthful materials, Reviewer audits the
claims, and Steward produces the application checklist. The tracker saves the
match score, brief, deadline, next action, and application stage.

**Request application approval** creates one specific Gatekeeper decision. That
approval authorizes preparation only: it never means the application was
submitted. Mark **Applied**, **Interview**, or **Offer** yourself after the real
event occurs. Any future form submission still requires a separate
`browser.submit` approval and final confirmation in the Chrome Bridge.

Run the all-Sheep improvement council manually:

```bash
python3 -m shepard council
```

The dashboard's **Gather council** button starts the same process. While it is
active, every Sheep travels to the center of the Labyrinth.

## Run Hen's market watch

Hen scans the configured watchlist, filters securities whose latest collected
closing price is at or below the owner's price cap, adds descriptive price,
volatility, drawdown, and volume measurements, and records Nasdaq IPO-calendar
signals for follow-up. Change the cap and symbols in
`config/market-watchlist.json`, then run:

```bash
python3 -m shepard market-briefing
```

The current price feed is an unofficial, no-key Yahoo Finance chart endpoint
that can change or be delayed. The IPO feed is Nasdaq's public calendar. An IPO
calendar entry is never treated as confirmation: Hen requires the related SEC
S-1/F-1, amendments, and final prospectus to be checked. The watchlist is not
the whole market, a share price under $50 does not make a company inexpensive,
and fractional shares may make higher-priced securities accessible. Hen's
briefing is research, not personalized financial advice; it never places an
order and no result is guaranteed.

## Connect Google Calendar

Shepard starts with no account access. To enable the first, read-only calendar
bridge, create a Google OAuth client, configure this redirect URI:

```text
http://127.0.0.1:8765/oauth/google-calendar/callback
```

Then start Shepard with the credentials in the process environment:

```bash
GOOGLE_CLIENT_ID="your-client-id" GOOGLE_CLIENT_SECRET="your-client-secret" python3 -m shepard web
```

Open **Connections** and choose **Connect**. The resulting token is stored only
in `secrets/google-calendar.json`, which is git-ignored and restricted to the
current operating-system user. The initial scope is calendar read-only.

## Use Outlook and its calendar without Azure

Open **Connections → Outlook + Calendar** in Shepard. Use the provided links to
open Outlook Mail or Outlook Calendar in Chrome, sign in normally, then open the
**Shepard Chrome Bridge** extension and choose **Share current page**. Ask Shepard
about your inbox or calendar after sharing it.

New Outlook for Mac does not expose its cloud mailbox through its legacy local
automation interface, so Shepard does not pretend that the desktop app is linked.
This browser workflow needs no Azure portal, Microsoft Entra app registration,
API key, or school administrator approval. Only the page you deliberately share
is read; passwords, cookies, browsing history, and other tabs are not accessed.
Shared text remains in server memory for at most one hour, and this bridge cannot
send, delete, move, or edit mail or calendar events.

Launch the native desktop control room:

```bash
python3 -m shepard desktop
```

On macOS, `dist/Shepard.app` is also a clickable desktop launcher.

Inspect saved work:

```bash
python3 -m shepard jobs
python3 -m shepard show JOB_ID
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Customize the characters

```bash
python3 -m shepard persona scout --name "Mara" --persona "Bold, curious, and evidence-driven"
```

The full configuration is in `config/default.json`. Personality settings never
change permissions; capabilities remain a separate policy field.

## Safety boundary

The current runtime includes a Google Calendar authorization bridge but does not
yet read Google events into agent jobs. Outlook Mail and Calendar work through
explicit, temporary Outlook Web page sharing in the Chrome Bridge; Shepard has no
background mailbox access and cannot send messages or change events. Gmail,
application portals, and device control are represented as planned connections
and are not active. Website
reading is limited to public HTML or text pages, two URLs per message, one MB per
page; local/private network addresses and nonstandard ports are blocked. Future
connectors will use narrow OAuth scopes and the owner approval queue. Sending,
submitting, deleting, purchasing, publishing, calendar changes, browser
navigation, browser form submission, and device control require approval by
default. The Chrome Bridge still cannot read history, cookies, passwords, other
tabs, `chrome://` pages, or operate continuously in the background.
