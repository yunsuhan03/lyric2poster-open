# Lyric2Poster (open-source edition)

Sample Final Term Project code for "Arts and Advanced Big Data". It turns a song from a music chart
into a cover poster: you paste the lyrics, **Claude** writes an art brief (mood, imagery, palette), an
open image model (FLUX) paints the poster, and the title and artist are added as real text.
Lyrics are used once, kept only in your browser session, and never written to disk, logs or a database.

Built only from tools taught in the course, all open or free to start:

| Need | Tool |
| --- | --- |
| Code, history, review | **GitHub** (this repo) |
| Collect charts every day | **GitHub Actions** (scheduled workflow commits JSON and CSV into `data/`) |
| Public web app | **Streamlit Community Cloud** (deploys from the repo; CPU only) |
| GPU work, experiments | **Google Colab** (notebooks 01 to 03; a FLUX image server) |
| Open image model, datasets | **Hugging Face** (a public FLUX Space, optional Dataset for chart history) |
| Art director LLM | **Claude** through the `anthropic` SDK (required). OpenAI is an optional adapter. |

## Layout

```
streamlit_app.py            the whole UI (one script, deploys as is)
lyric2poster/               schemas, safety, prompt_builder, overlay, art_director, image_engines, charts, limits, config
scripts/collect_charts.py   Last.fm -> data/charts/*.json and data/history/*.csv
scripts/push_to_hf.py       optional mirror of data/ to a Hugging Face Dataset
server/image_server.py      FastAPI + FLUX server you run in Colab
notebooks/                  01 art director test, 02 FLUX server + tunnel, 03 chart history analysis
.github/workflows/          ci.yml (tests), collect-charts.yml (daily chart job)
tests/                      36 tests
```

## Run it on your computer (no keys needed)

```bash
pip install -r requirements-dev.txt
python -m pytest -q
streamlit run streamlit_app.py
```

With no keys the app runs in demo mode: a canned art brief and a Pillow-drawn poster.

To use Claude locally, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, fill in
`ANTHROPIC_API_KEY` and `APP_PASSCODE`, and enter the passcode in the sidebar.
(Or paste your own key in the sidebar: it is used for your session only.)

## Deploy

1. **GitHub**: create the repo, push this folder. Add the repository secret `LASTFM_API_KEY`
   (Settings > Secrets and variables > Actions). Optional variable `L2P_CHARTS`
   (default `global;South Korea;United States`; use country names). Run the `collect-charts` workflow once
   from the Actions tab and check that `data/` got a commit.
2. **Streamlit Community Cloud**: New app, pick the repo, main file `streamlit_app.py`.
   Paste the contents of `secrets.toml.example` (with real values) into Advanced settings > Secrets.
3. **Images**: choose one.
   - `L2P_IMAGE_ENGINE = "hf_space"`: calls a public FLUX Space. Simple, but ZeroGPU quotas apply and the
     Space's argument names can change (see `HFSpaceEngine._predict`).
   - `L2P_IMAGE_ENGINE = "remote"`: run `notebooks/02_flux_image_server.ipynb` on a Colab GPU, then put the
     tunnel URL in `L2P_REMOTE_URL` and your token in `L2P_REMOTE_TOKEN`.
   - leave unset: demo posters.
4. Set a monthly **spend limit** for your Anthropic API key in the Anthropic Console.

## Protecting your API key

A public app that calls Claude spends your money. This sample has three layers:
the owner's key is used only after the visitor types `APP_PASSCODE` (no passcode set means the key is not used);
each browser session has a brief and poster limit (`L2P_BRIEF_LIMIT`, `L2P_POSTER_LIMIT`);
visitors may paste their own key. Session limits are speed bumps (a new tab resets them), so the spend limit matters.

## What has and has not been tested

Run and passed in the sandbox where this was written (36 tests):
- Schema rules for Claude structured outputs (no maxItems, minItems at most 1, additionalProperties false).
- The Claude request shape (`output_config.format`, no temperature) against a fake client; retry, copied-lyrics rejection,
  refusal and cut-off handling; errors that never echo lyrics.
- The OpenAI adapter, HF Space engine and remote engine against fake clients; fallback to the demo poster.
- The chart collector against recorded-shape sample data (idempotent history, failed chart keeps old file, API key never in errors).
- The image server with a fake generator (token check, validation).
- The Streamlit script driven end to end with Streamlit's AppTest in demo mode, including a "canary lyric" check that a unique
  sentence never appears in session state, logs or rendered text after the brief is made.

Not run, so treat as unverified until you run them:
- Any real call to the Claude API, OpenAI, Last.fm, or a Hugging Face Space (the sandbox could not reach them).
- The FLUX server on a real GPU (a 16 GB T4 needs CPU offload; fp16 can give black images, so bfloat16 is used).
- The Colab notebooks, the cloudflared tunnel, and the GitHub Actions workflows.
- Deployment on Streamlit Community Cloud.

## Known limits

- Streamlit Community Cloud has no GPU and puts apps to sleep after 12 hours without traffic.
- GitHub may pause scheduled workflows in a repository with no activity for a long time (reported as 60 days; not verified here).
  The daily data commit counts as activity when charts change.
- The Last.fm terms of use were not reviewed. Do that before a public launch.
- Model names change often. `L2P_CLAUDE_MODEL` defaults to `claude-sonnet-5-5`; check the current list.
