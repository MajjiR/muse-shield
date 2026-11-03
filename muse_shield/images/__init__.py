"""Image masking with Meta models: Muse Spark finds sensitive text and objects, SAM 3.1 finds faces."""

import os

import httpx

from ..backends import BackendError
from ..config import load_env
from .masker import ImageMasked, ImageMasker
from .meta import Box, Sam, SparkVision

META_URL = "https://api.meta.ai/v1"


def image_models_from_env(client: httpx.Client | None = None) -> tuple[SparkVision | None, Sam | None, str]:
    """(vision, sam, reason it's off). Off unless raw analysis is allowed: the raw image goes to Meta."""
    load_env()
    if os.environ.get("MUSE_SHIELD_DEV_RAW_ANALYSIS") != "1":
        return None, None, ("image masking is off: it sends the raw image to Meta. Set MUSE_SHIELD_DEV_RAW_ANALYSIS=1 "
                            "to enable it for made-up images while prototyping")
    base, key = os.environ.get("META_BASE_URL", META_URL), os.environ.get("MODEL_API_KEY", "")
    try:
        vision = SparkVision(base, os.environ.get("MUSE_SHIELD_IMAGE_MODEL", "muse-spark-1.3"), key, client=client,
                             reasoning_effort=os.environ.get("MUSE_SHIELD_IMAGE_EFFORT", "minimal"))
        return vision, Sam(base, key, client=client), ""
    except BackendError as exc:
        return None, None, str(exc)


__all__ = ["Box", "ImageMasked", "ImageMasker", "Sam", "SparkVision", "image_models_from_env"]
