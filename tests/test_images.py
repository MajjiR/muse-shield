import base64
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from muse_shield.images import ImageMasker, Sam, SparkVision
from muse_shield.images.eval import coverage, score
from muse_shield.images.meta import Box, grid_box, parse_sam_boxes
from muse_shield.images.samples import all_samples

W, H = 400, 200
NAME_BOX = (40, 40, 160, 70)   # where the fake image has its "name"
FACE_BOX = (250, 60, 330, 160)
NAME_BOX_AREA = (NAME_BOX[2] - NAME_BOX[0]) * (NAME_BOX[3] - NAME_BOX[1])


def picture() -> bytes:
    img = Image.new("RGB", (W, H), (240, 240, 240))
    d = ImageDraw.Draw(img)
    for x in range(NAME_BOX[0], NAME_BOX[2], 6):  # stripes stand in for text
        d.rectangle([x, NAME_BOX[1], x + 2, NAME_BOX[3]], fill=(10, 10, 10))
    for y in range(FACE_BOX[1], FACE_BOX[3], 4):  # high-contrast "face" so blur is measurable
        d.rectangle([FACE_BOX[0], y, FACE_BOX[2], y + 1], fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def grid(b):  # pixel box -> Muse Spark's 0-1000 grid
    return {"x_min": b[0] / W * 1000, "y_min": b[1] / H * 1000, "x_max": b[2] / W * 1000, "y_max": b[3] / H * 1000}


def fake_meta(find=None, recheck=None, sam_faces=(FACE_BOX,), locate=None, calls=None, sam_plates=()):
    """One MockTransport for both models: chat/completions is Muse Spark, responses is SAM 3.1."""
    calls = calls if calls is not None else []
    finds = iter([find, recheck])

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("/responses"):
            concept = body["input"][0]["content"][1]["text"]
            boxes = sam_faces if concept == "face" else sam_plates if concept == "license plate" else ()
            text = "<0f>" + ",".join(f"{i}<|box;x1={b[0]};y1={b[1]};x2={b[2]};y2={b[3]};w={W};h={H}|><|mask;x=0;y=0;data=1,1,!!|>"
                                     for i, b in enumerate(boxes))
            return httpx.Response(200, json={"output": [{"content": [{"type": "output_text", "text": text}]}]})
        prompt = body["messages"][0]["content"][1]["text"]
        if prompt.startswith("Find the text"):
            content = json.dumps(locate or {"found": False})
        else:
            content = json.dumps(next(finds) or {"text": "", "items": [], "visual": []})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 900, "completion_tokens": 120}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (SparkVision("https://meta.test/v1", "muse-spark-1.3", "k", client=client),
            Sam("https://meta.test/v1", "k", client=client), calls)


FIND = {"text": "NAME Priya Raman\nWelcome", "items": [{"text": "Priya Raman", "type": "PERSON", "bbox": grid(NAME_BOX)}],
        "visual": []}


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "v.db", b"\x44" * 32)


def test_grid_and_sam_boxes_become_pixels():
    assert grid_box({"x_min": 100, "y_min": 0, "x_max": 1012, "y_max": 500}, 400, 200) == Box(40, 0, 400, 100)  # clamped
    assert grid_box({"x_min": 5}, 400, 200) is None
    assert parse_sam_boxes("<0f>0<|box;x1=1;y1=2;x2=30;y2=40;w=50;h=60|><|mask;x=0;y=0;data=1,1,~!|>,1<|box;x1=5;y1=5;x2=5;y2=9;w=50;h=60|>") \
        == [Box(1, 2, 30, 40)]  # zero-width box dropped


def test_mask_blurs_faces_covers_text_and_uses_vault_placeholders(vault):
    vision, sam, calls = fake_meta(find=FIND, recheck={"text": "NAME <PERSON_1>\nWelcome", "items": [], "visual": []})
    chat = vault.create_chat()
    first, _ = vault.entity_placeholder(chat, "PERSON", "Priya Raman")  # already known from a text message
    out = ImageMasker(vault, vision, sam, refine=False).mask(picture(), chat)

    assert out.chat_id == chat
    text = [r for r in out.regions if r["kind"] == "text"]
    assert [r["label"] for r in text] == [first] and "value" not in text[0]  # same label as in chat; value never returned
    assert [r["source"] for r in out.regions if r["kind"] == "face"] == ["sam-3.1"]
    assert out.text == f"NAME {first}\nWelcome"
    assert out.verify == {"ok": True, "leaked": [], "faces_left": 0, "new_finds": []}

    img = Image.open(io.BytesIO(out.image)).convert("L")
    bar = img.crop(NAME_BOX)
    assert sum(1 for v in bar.getdata() if v < 40) > 0.6 * NAME_BOX_AREA  # covered by a dark bar (the label is light)
    face = img.crop((FACE_BOX[0] + 20, FACE_BOX[1] + 30, FACE_BOX[2] - 20, FACE_BOX[3] - 30))
    assert max(face.getdata()) - min(face.getdata()) < 80  # stripes blurred away (they span 0..240 before)
    assert {p for p, _ in calls} == {"/v1/chat/completions", "/v1/responses"}
    assert vault.audit_rows()[-1]["event"] == "image_mask"


def test_recheck_that_can_still_read_a_value_fails_verification(vault):
    vision, sam, _ = fake_meta(find=FIND, recheck={"text": "NAME Priya Raman", "items": [], "visual": []})
    out = ImageMasker(vault, vision, sam, refine=False).mask(picture())
    assert out.verify["ok"] is False and out.verify["leaked"] == ["<PERSON_1>"]


def test_face_spark_sees_but_sam_misses_is_still_blurred(vault):
    find = {**FIND, "visual": [{"kind": "face", "bbox": grid(FACE_BOX)}, {"kind": "qr_code", "bbox": grid((10, 120, 60, 170))}]}
    vision, sam, _ = fake_meta(find=find, sam_faces=())
    out = ImageMasker(vault, vision, sam, refine=False).mask(picture(), verify=False)
    kinds = {r["kind"]: r for r in out.regions}
    assert kinds["face"]["source"] == "muse-spark-1.3" and kinds["qr_code"]["label"] == "<QR_CODE_1>"
    assert out.verify is None


def test_refine_snaps_a_misplaced_box_and_covers_both_when_unsure(vault):
    off = (40, 100, 160, 130)  # Spark's first box is a line too low
    find = {**FIND, "items": [{"text": "Priya Raman", "type": "PERSON", "bbox": grid(off)}]}
    # The crop around the first box spans x 0..240, y 40..190; the name sits at crop pixels (40,0)-(160,30).
    locate = {"found": True, "bbox": {"x_min": 40 / 240 * 1000, "y_min": 0, "x_max": 160 / 240 * 1000, "y_max": 30 / 150 * 1000}}
    vision, sam, _ = fake_meta(find=find, locate=locate)
    out = ImageMasker(vault, vision, sam).mask(picture(), verify=False)
    bars = [Box(*r["box"]) for r in out.regions if r["kind"] == "text"]
    assert len(bars) == 2 and coverage(Box(*NAME_BOX), bars, (W, H)) == 1.0


def test_contributor_models_are_refused():
    with pytest.raises(Exception, match="train on prompts"):
        SparkVision("https://meta.test/v1", "muse-spark-1.3-contributor", "k")


def test_endpoint_off_by_default_and_masks_with_models(vault):
    off = TestClient(create_app(vault, analyzer=None, chat_model=None))
    assert off.get("/health").json()["images"] is False and off.get("/health").json()["image_model"] is None
    assert off.post("/images/mask", json={"image": "x"}).status_code == 503

    vision, sam, _ = fake_meta(find=FIND, recheck={"text": "", "items": [], "visual": []})
    c = TestClient(create_app(vault, image_masker=ImageMasker(vault, vision, sam, refine=False)))
    assert c.get("/health").json()["image_model"] == "muse-spark-1.3 + sam-3.1"
    assert c.post("/images/mask", json={"image": "not base64!"}).status_code == 400
    assert c.post("/images/mask", json={"image": base64.b64encode(b"not an image").decode()}).status_code == 400
    r = c.post("/images/mask", json={"image": "data:image/png;base64," + base64.b64encode(picture()).decode()})
    assert r.status_code == 200
    body = r.json()
    assert body["image"].startswith("data:image/png;base64,") and body["verify"]["ok"]
    assert "Priya" not in json.dumps({k: v for k, v in body.items() if k != "image"})


def test_samples_have_gold_inside_the_image_and_score_perfect_masks():
    for s in all_samples():
        assert s.gold and all(0 <= g["box"].x1 < g["box"].x2 <= s.image.width for g in s.gold)
        perfect = {"regions": [{"kind": "text", "label": "<X_1>", "box": g["box"].as_list()} for g in s.gold]
                   + [{"kind": "photo_id", "label": "<P_1>", "box": p.as_list()} for p in s.photos], "verify": {"ok": True}}
        sc = score(s, perfect)
        assert all(g["masked"] and not g["leaked"] for g in sc["gold"]) and all(p["blurred"] for p in sc["photos"])


def test_sam_alone_finds_and_covers_without_any_reader(vault):
    calls = []
    _, sam, _ = fake_meta(sam_faces=(FACE_BOX,), calls=calls)
    masker = ImageMasker(vault, None, sam)  # SAM 3.1 only: the default now
    out = masker.mask(picture(), verify=True)
    assert all(path.endswith("/responses") for path, _ in calls)  # no chat model ever saw the raw picture
    asked = {body["input"][0]["content"][1]["text"] for _, body in calls}
    assert {"face", "license plate", "id card", "document"} <= asked
    faces = [r for r in out.regions if r["kind"] == "face"]
    assert len(faces) == 1 and faces[0]["source"] == "sam-3.1" and out.text == ""
    assert out.verify["ok"] is True and "Loose text isn't re-scanned" in out.verify["checked"]  # sent as masked
    before, after = Image.open(io.BytesIO(picture())), Image.open(io.BytesIO(out.image))
    face_px = (FACE_BOX[0] + 5, FACE_BOX[1] + 5)
    assert before.getpixel(face_px) != after.getpixel(face_px)  # the face is blurred


def test_sam_alone_fails_closed_when_sam_errors(vault):
    def handler(request):
        return httpx.Response(500, json={"error": "down"})
    sam = Sam("https://meta.test/v1", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Exception):
        ImageMasker(vault, None, sam).mask(picture())  # never "nothing found" when the only finder failed


def test_image_masking_needs_a_finder(vault):
    with pytest.raises(ValueError):
        ImageMasker(vault, None, None)


def test_private_text_in_an_image_is_refused_not_sent(vault):
    from muse_shield.images import ImageRefused
    _, sam, calls = fake_meta()
    seen = []
    masker = ImageMasker(vault, None, sam, text_check=lambda img, mime: (seen.append(img), (True, "an ID card"))[1])
    with pytest.raises(ImageRefused, match="still shows private text \\(an ID card\\)"):
        masker.mask(picture())
    assert len(seen) == 1 and seen[0] != picture()  # Glimmer looked at the masked picture, not the original


def test_a_number_plate_sam_covered_is_not_refused(vault):
    """The plate's number is private text in the original, but SAM covers the plate, so the masked picture passes."""
    _, sam, _ = fake_meta(sam_faces=(), sam_plates=(NAME_BOX,))
    original = picture()
    check = lambda img, mime: (img == original, "vehicle registration number AP32CD7890")  # noqa: E731
    out = ImageMasker(vault, None, sam, text_check=check).mask(original)
    assert [r["kind"] for r in out.regions] == ["license_plate"] and out.regions[0]["label"] == "<LICENSE_PLATE_1>"
    assert out.verify["ok"] is True and "masked image" in out.verify["checked"]


def test_a_photo_without_private_text_is_masked(vault):
    _, sam, _ = fake_meta(sam_faces=(FACE_BOX,))
    out = ImageMasker(vault, None, sam, text_check=lambda img, mime: (False, "a street photo")).mask(picture())
    assert [r["kind"] for r in out.regions] == ["face"]


def test_a_failed_text_check_refuses(vault):
    from muse_shield.backends import BackendError
    from muse_shield.images import ImageRefused
    _, sam, _ = fake_meta()

    def broken(img, mime):
        raise BackendError("deployment down")
    with pytest.raises(ImageRefused, match="couldn't check"):
        ImageMasker(vault, None, sam, text_check=broken).mask(picture())
