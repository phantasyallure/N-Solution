# Nardjis Solutions
*Innovate. Optimize. Scale.* — camera-based restaurant intelligence, for one restaurant or many.

Detects tables that are waiting / empty / not cleaned, measures how long each client waits, alerts the **right** employee, ranks team effort fairly, and lets you ask an AI (Gemini) about your restaurants.

## Two parts, two places

| Part | Where it runs | What it does |
|---|---|---|
| **Engine** (`run.py`, `engine/`) | A computer at the restaurant (your laptop for the phone test) | Reads the camera, detects, alerts on Telegram, pushes numbers to Supabase |
| **Dashboard** (`vercel/`) | Vercel + Supabase (free tiers) | The website you open from any phone. Shows live numbers, team ranking, Gemini assistant |

Only numbers and events are sent to the cloud — never video or images.
You can also run everything on one computer without any cloud (see "Local only").

## Deploy: Supabase + Vercel (about 20 minutes)

**1. Supabase (database)**
1. https://supabase.com → New project.
2. SQL Editor → New query → paste the content of `vercel/supabase.sql` → Run.
3. Project Settings → API: copy the **Project URL** and the **secret key** (`sb_secret_…`, or the legacy `service_role` key). Do not use the publishable/anon key. The tables are locked, so only the secret key can read or write them.

**2. Vercel (dashboard)**
1. Put the `vercel/` folder in a GitHub repository (the folder's content at the repository root, or keep it in a subfolder and set *Root Directory* = `vercel` on Vercel). `.env` files are already git-ignored.
2. Vercel → Add New → Project → import the repository (no build settings needed).
3. Settings → Environment Variables:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — from step 1
   - `ACCESS_CODE` — a long code of your choice. **Required**: without it the dashboard refuses to show data
   - `GEMINI_API_KEY` — optional, free key from https://aistudio.google.com/apikey
4. Deploy. Open the Vercel address, enter your access code. It is empty until the engine sends data.

**3. The engine (restaurant computer)**
1. Copy `.env.example` to `.env` (next to `run.py`) and fill in `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
2. First test with simulated restaurants: `python run.py --demo --headless` → refresh your Vercel page.
3. With a phone camera: `python run.py --headless --only oran-centre --source http://PHONE_IP:8080/video`
4. With real cameras: set each restaurant's `camera.source` in `config.yaml`, then `python run.py --headless`.

The engine must stay running; if it stops, the restaurant shows "Offline" after about 30 seconds.
Add a restaurant: copy a block in `config.yaml`, give it a new `id`, restart the engine — it appears on the dashboard by itself.

**Good to know (free tiers)**
- Supabase pauses free projects after about a week without activity (resume from its dashboard). Free egress is limited, so close dashboard tabs you are not using (background tabs already pause themselves).
- Vercel's free "Hobby" plan is for testing/personal use; for paying customers use a paid plan.
- The blurred live-camera picture is not shown in cloud mode (local only).
- Never put the Supabase secret key in the browser, in GitHub or in a chat. If it leaks, rotate it in Supabase.

**Test the dashboard on your computer before deploying:** `cd vercel`, copy `.env.example` to `.env`, fill it, `npm run dev` → http://localhost:3000

## Local only (no cloud)
```bash
pip install -r requirements.txt
python run.py --demo          # open http://localhost:8000
```
On your phone (same Wi-Fi): `http://<your-computer-ip>:8000`, then "Add to home screen". Set `access_code` in `config.yaml` before sharing the link.

## Gemini AI assistant (free)
Get a key at https://aistudio.google.com/apikey and set `GEMINI_API_KEY` (Vercel variable, or environment variable for the local server). Open the AI tab: ask "Which table waits the longest?", "Compare my restaurants", or tap **Daily briefing**. It answers in French, Arabic or English. Only numbers and employee first names are sent to Gemini. The free tier has rate limits; if Google renames a model, set `GEMINI_MODELS` (Vercel) or `gemini.models` (`config.yaml`).

## Test with a phone camera
Install "IP Webcam" (Android) on the phone, same Wi-Fi:
```bash
pip install ultralytics opencv-python
python tools/zones.py --source http://PHONE_IP:8080/video     # draw tables, press S, paste into config.yaml
python run.py --only oran-centre --source http://PHONE_IP:8080/video
```
For a first test set `staff_uniform.ranges: []` (everyone counts as a client) and lower `patience_limit` to 60.

## What makes it different
- **Smart Dispatch** — only the nearest free employee is alerted; the manager gets escalations.
- **Patience Meter** — alert at 50% of the patience limit, manager at 100%, clients who leave unserved are logged.
- **Fair Effort Score** — visits, tasks, distance, weighted by table difficulty.
- **Privacy-first** — faces always blurred, no face recognition, only the blurred image is saved locally.
- FR / EN / AR (right-to-left), phone-first layout, daily report, Telegram alerts tagged `[Restaurant]`.

## Files
`engine/` detection + decisions (`core.py`, `vision.py`, `cloud.py`, `assistant.py`) · `dashboard/` local server and the web page (`static/index.html` is the single source) · `vercel/` Vercel project + `supabase.sql` · `tests/` (`pytest tests`, and `cd vercel && npm test`)
After editing `dashboard/static/index.html`, run `python tools/sync_vercel.py` to copy it into `vercel/public`.

## Legal note
Tell staff and clients that cameras are in use, and check Algerian data-protection rules (law 18-07) before deploying.
