"""Local-first privacy layer for cloud LLMs.

Raw prompt -> local detector (Llama ~1B + rules) -> policy -> semantic masking
-> encrypted vault -> cloud LLM (masked only) -> local reconstruction.
"""

__version__ = "0.1.0"
