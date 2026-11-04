"""A fake Muse Spark analyzer driven by known values, for document tests (no network)."""

import json

import httpx

from muse_shield.backends import GlimmerBackend


def fake_values(values: dict[str, str], contexts: dict[str, str] | None = None, roles: dict[str, str] | None = None,
                skip: set[str] = frozenset()):
    """An analyzer that flags every listed value present in a unit (value -> type), and a context for each
    sentence containing a trigger (trigger -> kind). `skip` values are never flagged (to test propagation).
    `.calls` counts analysis requests and `.units` records the unit texts it saw."""
    contexts, roles = contexts or {}, roles or {}
    calls: list[str] = []

    def handler(request):
        msgs = json.loads(request.content)["messages"]
        numbered = [m["content"] for m in msgs if m["content"].startswith("Known contexts")][-1].split("\n", 1)[1]
        sentences = [part.split("] ", 1)[1] for part in numbered.split(" [") if "] " in part]
        unit = " ".join(sentences)
        calls.append(unit)
        ents = [{"text": v, "type": t, **({"role": roles[v]} if v in roles else {})}
                for v, t in values.items() if v in unit and v not in skip]
        ctxs = [{"sentences": [i], "kind": kind, "subtype": None, "summary": f"a {kind.lower()} passage"}
                for i, s in enumerate(sentences, 1) for trig, kind in contexts.items() if trig in s]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"entities": ents, "contexts": ctxs})}}],
                                         "usage": {"prompt_tokens": 600, "completion_tokens": 80}})

    backend = GlimmerBackend("https://spark.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    backend.calls = calls
    return backend
