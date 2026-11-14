# Spatial Degradation Conditioning for All-in-One Image Restoration

## Abstract

All-in-one image restoration aims to handle multiple degradation types with a
single model. In this paper we study whether spatial degradation conditioning
provides measurable value beyond ordinary feature conditioning. We propose a
lightweight conditioning module that injects degradation location maps into
the restoration network.

## Method

Our method estimates per-pixel degradation maps from the input and fuses them
with the feature stream using a gated attention block. The gating mechanism
enables the model to adaptively weight degradation-specific cues. We keep the
parameter budget comparable to the baseline by sharing the conditioning
weights across scales.

## Results

On the Rain100H benchmark, our method improves the baseline PSNR by 0.42 dB
and SSIM by 0.013. On the SIDD dataset, the method achieves 39.18 dB PSNR
compared with 39.01 dB for the feature-only baseline. On Rain100L the gain is
smaller, with a 0.11 dB improvement. These results indicate that spatial
conditioning is most valuable under heavy degradation.

## Discussion

We believe that spatial degradation cues help restoration because they
provide location-specific degradation information, although the effect may
diminish on easier benchmarks. Future work will evaluate the method on video
restoration tasks. The implementation details and training protocol are
described in the appendix.

## References

[1] Zhang et al., All-in-One Image Restoration Networks, 2023.
[2] Li et al., Degradation-Aware Feature Conditioning, 2024.
