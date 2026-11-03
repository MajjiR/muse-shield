import httpx

from muse_shield.app.inspector import Inspector, user_text


def test_records_purpose_chat_tag_and_body():
    ins = Inspector()
    client = ins.client("chat", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"usage": {"prompt_tokens": 3}})))
    ins.for_chat("c_1")
    client.post("https://api.test/v1/chat/completions", json={"messages": [{"role": "system", "content": "sys"},
                                                                           {"role": "user", "content": "hi <PERSON_1>"}]})
    (rec,) = ins.list()
    assert rec["purpose"] == "chat" and rec["chat_id"] == "c_1" and rec["status"] == 200 and rec["usage"] == {"prompt_tokens": 3}
    assert user_text(rec["request_body"]) == "hi <PERSON_1>"
    assert ins.summary() == {"requests": 1, "analysis_requests": 0, "chat_requests": 1, "bytes_sent": rec["bytes"]}
