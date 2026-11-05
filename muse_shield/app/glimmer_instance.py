"""Bring up the fine-tuned Glimmer for masking when the app starts, and take it down when it stops.

`python -m muse_shield.app` calls `up()` before serving: it creates a live-merge deployment of the
masking LoRA (default: muse-shield-glimmer-er-v3a-s250, the best entity-resolution model) on one H200, waits
until it really answers, and returns the '<model>#<deployment>' route the masker uses. `down()` deletes
it again, so nothing bills after you stop the app. A deployment this app left running (a crash, a killed
terminal) is reused instead of starting a second one.

Plain REST against api.fireworks.ai, so it runs in the project venv. Settings:
    FIREWORKS_API_KEY                  required
    MUSE_SHIELD_GLIMMER_LORA           model id or full path (default muse-shield-glimmer-er-v3a-s250)
    MUSE_SHIELD_FIREWORKS_ACCOUNT      account id (default: the API key's first account)
    MUSE_SHIELD_GLIMMER_SHAPE          deployment shape (default: the H200 BF16 live-merge shape)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

API = "https://api.fireworks.ai/v1"
INFERENCE = "https://api.fireworks.ai/inference/v1"
DEFAULT_LORA = "muse-shield-glimmer-er-v3a-s250"
DEFAULT_SHAPE = "accounts/fireworks/deploymentShapes/dkuwotf7"  # 1x H200, BF16: what Glimmer live-merge uses
PREFIX = "ms-app-"  # deployments this app owns
GONE = {"DELETING", "DELETED", "FAILED"}


class InstanceError(RuntimeError):
    pass


@dataclass
class Instance:
    deployment_id: str
    route: str
    reused: bool = False


class GlimmerInstance:
    def __init__(self, api_key: str | None = None, lora: str | None = None, account: str | None = None,
                 shape: str | None = None, client: httpx.Client | None = None, log=print):
        self.key = api_key or os.environ.get("FIREWORKS_API_KEY", "")
        if not self.key:
            raise InstanceError("FIREWORKS_API_KEY is needed to bring up the Glimmer masking model")
        self.http = client or httpx.Client(timeout=60, headers={"Authorization": f"Bearer {self.key}"})
        self.account = account or os.environ.get("MUSE_SHIELD_FIREWORKS_ACCOUNT") or self._first_account()
        lora = lora or os.environ.get("MUSE_SHIELD_GLIMMER_LORA", DEFAULT_LORA)
        self.model = lora if "/" in lora else f"accounts/{self.account}/models/{lora}"
        self.shape = shape or os.environ.get("MUSE_SHIELD_GLIMMER_SHAPE", DEFAULT_SHAPE)
        self.log = log

    def _first_account(self) -> str:
        r = self.http.get(f"{API}/accounts")
        r.raise_for_status()
        accounts = r.json().get("accounts") or []
        if not accounts:
            raise InstanceError("this Fireworks key has no account")
        return accounts[0]["name"].split("/")[-1]

    def _url(self, dep_id: str = "") -> str:
        return f"{API}/accounts/{self.account}/deployments" + (f"/{dep_id}" if dep_id else "")

    def _route(self, dep_id: str) -> str:
        return f"{self.model}#accounts/{self.account}/deployments/{dep_id}"

    def _ours(self) -> list[dict]:
        """Deployments of this model that this app created and that are still alive."""
        r = self.http.get(self._url(), params={"pageSize": 200})
        r.raise_for_status()
        return [d for d in r.json().get("deployments", []) if d["name"].split("/")[-1].startswith(PREFIX)
                and d.get("baseModel") == self.model and d.get("state") not in GONE]

    def up(self, wait_s: int = 1800) -> Instance:
        existing = self._ours()
        if existing:
            dep_id, reused = existing[0]["name"].split("/")[-1], True
            self.log(f"Glimmer: reusing {dep_id} ({existing[0].get('state')})")
        else:
            # deleted deployments keep their id reserved for a while, so every start gets a new one
            dep_id, reused = f"{PREFIX}{self.model.split('/')[-1][-24:]}-{time.strftime('%m%d-%H%M%S')}".replace("_", "-")[:63], False
            body = {"baseModel": self.model, "deploymentShape": self.shape, "minReplicaCount": 1, "maxReplicaCount": 1,
                    "displayName": "Muse Shield masking (deleted when the app stops)"}
            r = self.http.post(self._url(), params={"deploymentId": dep_id}, json=body)
            if r.status_code >= 400:
                raise InstanceError(f"couldn't create the Glimmer deployment: {r.status_code} {r.text[:300]}")
            self.log(f"Glimmer: creating {dep_id} for {self.model.split('/')[-1]} (a few minutes; billed per hour while up)")
        inst = Instance(dep_id, self._route(dep_id), reused)
        try:
            self._wait_ready(dep_id, wait_s)
            self._probe(inst.route)
        except BaseException:  # never leave a half-started GPU billing (errors, Ctrl-C)
            self.down(inst)
            raise
        self.log(f"Glimmer: serving at {inst.route}")
        return inst

    def _wait_ready(self, dep_id: str, wait_s: int) -> None:
        t0, last = time.monotonic(), ""
        while True:
            d = self.http.get(self._url(dep_id)).json()
            state = d.get("state", "")
            if state == "READY":
                return
            if state in GONE:
                raise InstanceError(f"Glimmer deployment {dep_id} is {state}: {d.get('status')}")
            if time.monotonic() - t0 > wait_s:
                raise InstanceError(f"Glimmer deployment {dep_id} not ready after {wait_s}s (state {state})")
            if state != last:
                self.log(f"Glimmer: {state.lower().replace('_', ' ') or 'starting'}…")
                last = state
            time.sleep(10)

    def _probe(self, route: str, tries: int = 40) -> None:
        """READY doesn't prove it serves: wait for a real answer."""
        for _ in range(tries):
            r = self.http.post(f"{INFERENCE}/chat/completions", timeout=120,
                               json={"model": route, "max_tokens": 4, "messages": [{"role": "user", "content": "Say ok."}]})
            if r.status_code == 200:
                return
            time.sleep(10)
        raise InstanceError(f"Glimmer is READY but doesn't answer: {r.status_code} {r.text[:200]}")

    def down(self, inst: Instance) -> None:
        r = self.http.delete(self._url(inst.deployment_id), params={"ignoreChecks": "true"})
        if r.status_code >= 400 and r.status_code != 404:
            raise InstanceError(f"couldn't delete {inst.deployment_id} ({r.status_code}); delete it in the Fireworks "
                                "console, it bills while it runs")
        self.log(f"Glimmer: deleted {inst.deployment_id}")
