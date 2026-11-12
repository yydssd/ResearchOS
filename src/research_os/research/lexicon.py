"""Shared domain lexicons for deterministic extraction.

Kept in one place so claim scope detection and quantitative extraction agree on
which dataset names exist; two copies would drift.
"""

from __future__ import annotations

import re

# Benchmarks commonly used in image restoration / low-level vision papers.
DATASETS: tuple[str, ...] = (
    "Rain100H",
    "Rain100L",
    "Rain13K",
    "SIDD",
    "DND",
    "GoPro",
    "HIDE",
    "REDS",
    "Set5",
    "Set14",
    "BSD100",
    "Urban100",
    "Manga109",
    "DIV2K",
    "Flickr2K",
    "ImageNet",
    "COCO",
    "CIFAR-10",
    "CIFAR-100",
    "Cityscapes",
    "LOL",
    "RESIDE",
)

# Metrics whose values are comparable only within the same dataset + protocol.
METRICS: tuple[str, ...] = ("PSNR", "SSIM", "LPIPS", "FID", "MAE", "MSE")

# Heading phrase -> canonical task. Papers name the task in subsection headings
# ("Classical image SR.", "RGB Image Denoising") and then stop repeating it, so
# reading it from the sentence alone covers only 17% of result claims (P4 probe).
TASKS: tuple[tuple[str, str], ...] = (
    ("jpeg compression artifact reduction", "jpeg artifact reduction"),
    ("super-resolution", "super-resolution"),
    ("super resolution", "super-resolution"),
    ("image sr", "super-resolution"),
    ("denoising", "denoising"),
    ("deblurring", "deblurring"),
    ("deraining", "deraining"),
    ("inpainting", "inpainting"),
    ("restoration", "image restoration"),
)

# Sentences about someone else's method must not receive the implicit SELF
# subject, or a baseline's number would be attributed to the paper's own method.
THIRD_PARTY = re.compile(
    r"\b(previous|existing|prior|baselines?|compared methods|state-of-the-art|sota|"
    r"competitors?|recent methods?)\b",
    re.IGNORECASE,
)
