# LoRA personalization of the local detector

Goal: make the on-device Llama-3.2-1B better at *your* sensitive vocabulary (codenames,
clients, people) without anything leaving the laptop. Teach in the dashboard feeds this.

## 1. Export data (personalized from Teach)

```bash
.venv/bin/privacy-engine lora-data --n 600 --out runs/lora
```

Examples use the exact runtime prompt (`detector/llm.py: SYSTEM_PROMPT`) and the same span
normalization as the runtime parser. Mix: generic typed-slot sentences with wide name and org
pools, about 20% public-only negatives, your taught terms injected into realistic templates,
and your taught example sentences verbatim.

## 2. Train (Apple Silicon / CUDA / CPU)

```bash
.venv/bin/pip install -e '.[lora]'
huggingface-cli login     # accept the Llama 3.2 license on Hugging Face first
.venv/bin/python scripts/lora_train.py --data runs/lora --out adapters/detector-lora
```

r=16 on all attention + MLP projections, loss on the assistant JSON only, 2 epochs.

## 3. Evaluate base vs adapter

```bash
.venv/bin/python scripts/lora_eval.py --data runs/lora --adapter adapters/detector-lora
```

Reports span precision / recall / F1, confidential-context accuracy and latency.

## 4. Serve it through Ollama

```bash
git clone https://github.com/ggml-org/llama.cpp
python llama.cpp/convert_lora_to_gguf.py adapters/detector-lora --outfile adapters/detector-lora.gguf
printf 'FROM llama3.2:1b\nADAPTER ./adapters/detector-lora.gguf\n' > Modelfile
ollama create privacy-detector -f Modelfile
echo LOCAL_LLM_MODEL=privacy-detector >> .env
```

The adapter must be trained on the same base as the Ollama model (Llama-3.2-1B-Instruct).
Then `privacy-engine bench --llm` shows the before/after on leak rate.

## Status

The dataset builder is unit-tested. The train and eval scripts compile, but they have **not been
run in this repo yet** because they need the gated model download and torch.
