# For judges: run Muse Shield with our fine-tuned model

Muse Shield masks your private data with **our fine-tuned Muse Glimmer 30B** (the er-v3a LoRA). For the hackathon we
serve it on **Fireworks**, because a 30B model needs a GPU. The weights are a standard LoRA adapter, so they can also be
self-hosted; see [Running it yourself](#running-it-yourself-without-fireworks) at the end.

It takes about 15 minutes, most of it waiting for the model to upload and start.

## What you need

- **Python 3.12** and **Node 20**.
- A **Meta Model API key** (`MODEL_API_KEY`), for Muse Spark (answers) and SAM 3.1 (images).
- A **Fireworks account and API key** (`FIREWORKS_API_KEY`), plus the `firectl` CLI: `brew install fw-ai/firectl/firectl`, then `firectl signin`.
- The Hugging Face CLI: `pip install -U huggingface_hub`.

## 1. Get the LoRA from Hugging Face

```bash
hf download TheEmperor2/muse-shield-glimmer-er-v3a \
  --include "adapter_config.json" "adapter_model*" "*.json" "chat_template.jinja" \
  --exclude "results/*" \
  --local-dir er-v3a
```

That's about 230 MB: the adapter (rank 16, alpha 32, all attention and MLP projections), its config and the tokenizer files.

## 2. Upload it to your Fireworks account as a LoRA on Muse Glimmer 30B

```bash
firectl create model muse-shield-glimmer-er-v3a-s250 ./er-v3a \
  --base-model accounts/fireworks/models/muse-glimmer-30b
```

**Keep `er-v3` in the model id.** The app picks the v3 masking instructions the adapter was trained on from that name.
`firectl get model muse-shield-glimmer-er-v3a-s250` should show it as `READY`.

## 3. Set up the app

```bash
git clone https://github.com/MajjiR/muse-shield && cd muse-shield
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,documents,connectors]'
npm --prefix apps/web install && npm --prefix apps/web run build
cp .env.example .env
```

In `.env`, set:

```
MODEL_API_KEY=...                 # Meta Model API
FIREWORKS_API_KEY=...             # Fireworks
MUSE_SHIELD_GLIMMER_LORA=muse-shield-glimmer-er-v3a-s250
MUSE_SHIELD_DEV_RAW_ANALYSIS=1    # masking sends raw text to YOUR Fireworks deployment: use made-up data
```

## 4. Run it

```bash
.venv/bin/python -m muse_shield.app      # http://127.0.0.1:8765
```

- The app opens straight away.
- In the background it creates a deployment of your uploaded LoRA on one H200. It's billed per hour while it runs, and
  the first start takes a few minutes. The sidebar shows "Starting the masking model…" until the model answers.
- **Ctrl-C deletes the deployment**, so nothing keeps billing.
- If a run crashed and left a deployment behind, the next start reuses it.
- Check with `firectl list deployments` when you're done.

Open <http://127.0.0.1:8765>, start a chat in **Entity resolution** mode and paste something private, for example:

> Draft a short, polite payment reminder email to our customer Sneha Reddy (sneha.reddy82@gmail.com, +91 99085 31746).
> Her account number is CUST-884127 and she owes ₹4,697. Ask her to pay by 15 November. Don't send it, just draft it.

You'll see what was found, what Muse Spark received (placeholders only), and the reply restored on your device.

## Optional: connect your own accounts

Open **Connections** in the sidebar:
- **Folders and files:** pick a folder with the Mac's folder picker. No keys are needed.
- **Gmail, Calendar and Contacts:** sign in with Google's own sign-in.
- **Telegram:** sign in with your phone number and a code.

Google and Telegram each need a one-time app key in `.env` (a Google OAuth client file, and a Telegram `api_id` and
`api_hash`). [docs/connections.md](connections.md) walks through both in a few minutes. Use test accounts: what's read is
masked by your deployment before Muse Spark sees it.

## Running it yourself, without Fireworks

Fireworks is only where we rented the GPU for the hackathon. The adapter is a standard PEFT LoRA for Muse Glimmer 30B,
so any server that can load a LoRA on Muse Glimmer can serve it, for example vLLM with `--enable-lora`. That keeps raw
text entirely on hardware you control, which is the end state Muse Shield is built for. The app currently addresses the
model as a Fireworks route (`GLIMMER_BASE_URL` plus `<model>#<deployment>`); pointing it at a self-hosted
OpenAI-compatible server is the next step on the roadmap.

## Where the numbers come from

- **Model card:** <https://huggingface.co/TheEmperor2/muse-shield-glimmer-er-v3a>
- **Training data:** <https://huggingface.co/datasets/TheEmperor2/muse-shield-er-v3-data>
- **Full release record:** [`results/er-v3-release/`](../results/er-v3-release/README.md). It has the data, training
  logs, every checkpoint score, and the official benchmark runs.
