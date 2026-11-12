"""Shared domain lexicons for deterministic extraction.

Kept in one place so claim scope detection and quantitative extraction agree on
which dataset names exist; two copies would drift.
"""

from __future__ import annotations

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
