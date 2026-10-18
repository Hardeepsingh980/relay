# Demo video

These scripts record the Relay demo video from the running app. The voices come from Gemini text-to-speech, and the captions are burned into the video.

## What you need

- The app runs locally: the API on port 8020 (started with `RELAY_STEP_DELAY=0.5`) and the web app on port 3025.
- `GEMINI_API_KEY` is set in the `.env` file at the repo root.
- `ffmpeg` with libass is installed.

## Make the video

Run these commands in this folder:

```bash
uv run --project ../backend python tts.py
uv run --project ../backend --with playwright python record.py
uv run --project ../backend --with numpy python assemble.py
```

1. `tts.py` makes one clip for each narration line and each line of the recorded call. It caches the clips in `.cache/tts/`, so it calls Gemini again only for text that changed.
2. `record.py` opens a headless Chromium at 1440×810 (1920×1080 pixels) and signs up a new test account. Then it goes through the demo one scene at a time and logs when each line starts. During the call scene, each speaker's voice starts when their line appears on screen.
3. `assemble.py` turns the frames into 30 fps video and mixes the voices at the logged times. Then it adds captions and chapter titles. The output goes to `out/`:
   - `relay-demo.mp4` has the captions burned in.
   - `relay-demo-no-captions.mp4` has no captions.
   - `relay-demo.srt` holds the captions as a separate file.

## Record against the live site

Set `RELAY_DEMO_BASE` to record against a deployed copy instead of `localhost:3025`:

```bash
RELAY_DEMO_BASE=https://relay.34-100-245-68.sslip.io uv run --project ../backend --with playwright python record.py
```

The current video was recorded this way, against the live deployment.

## Re-record one scene

To record again from one scene to the end, run `python record.py --from call`. The scene names are in `script.py`, in `SCENE_ORDER`.

`--from` uses the browser profile and the workspace from the last full run. A full run starts with a new account, which gets its own workspace graph.

## Change what the narrator says

The narration is in `script.py`. It follows the simple-english rules: short sentences, active voice and plain words.

1. Edit the narration in `script.py`.
2. Run `tts.py` again.
3. Record the scenes that use the changed lines.
