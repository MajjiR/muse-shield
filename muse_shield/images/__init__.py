"""Image masking: SAM 3.1 finds faces, plates and cards (or SAM 3 on this machine via MUSE_SHIELD_SAM_URL); our
Glimmer deployment checks for private text, which isn't sent in a picture. MUSE_SHIELD_IMAGE_READER=spark brings back
Muse Spark reading the raw image."""

import os

import httpx

from ..backends import BackendError
from ..config import load_env
from .masker import ImageMasked, ImageMasker, ImageRefused
from .meta import Box, GlimmerTextCheck, Sam, SparkVision

META_URL = "https://api.meta.ai/v1"


def image_models_from_env(client: httpx.Client | None = None) -> tuple[SparkVision | None, Sam | None, str]:
    """(vision, sam, reason it's off). Off unless raw analysis is allowed: the raw image goes to Meta's SAM 3.1.

    SAM 3.1 alone finds and covers what's sensitive (vision is None). MUSE_SHIELD_IMAGE_READER=spark adds Muse
    Spark reading the raw image (text values, other objects), which sends the unmasked picture to a chat model."""
    load_env()
    if os.environ.get("MUSE_SHIELD_DEV_RAW_ANALYSIS") != "1":
        return None, None, ("image masking is off: it sends the raw image to Meta. Set MUSE_SHIELD_DEV_RAW_ANALYSIS=1 "
                            "to enable it for made-up images while prototyping")
    base, key = os.environ.get("META_BASE_URL", META_URL), os.environ.get("MODEL_API_KEY", "")
    try:
        vision = (SparkVision(base, os.environ.get("MUSE_SHIELD_IMAGE_MODEL", "muse-spark-1.3"), key, client=client,
                              reasoning_effort=os.environ.get("MUSE_SHIELD_IMAGE_EFFORT", "minimal"))
                  if os.environ.get("MUSE_SHIELD_IMAGE_READER", "").lower() == "spark" else None)
        # MUSE_SHIELD_SAM_URL points SAM at the local SAM 3 server (images/sam_local.py) instead of the cloud.
        sam_url = os.environ.get("MUSE_SHIELD_SAM_URL", "").strip()
        sam = (Sam(sam_url, "local", model=os.environ.get("MUSE_SHIELD_SAM_MODEL", "sam3-local"), client=client)
               if sam_url else Sam(base, key, client=client))
        return vision, sam, ""
    except BackendError as exc:
        return None, None, str(exc)


__all__ = ["Box", "GlimmerTextCheck", "ImageMasked", "ImageMasker", "ImageRefused", "Sam", "SparkVision",
           "image_models_from_env"]
