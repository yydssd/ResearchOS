# LangProp: Closing the Loop with Programmatic Policies

## Abstract

We introduce LangProp, a framework that turns a language model's proposals into
executable policies. Our method keeps the policy code under version control and
reuses it across tasks.

## Method

LangProp, our proposed method, stores each policy as code and scores it by
execution feedback. The retrieval buffer keeps the last hundred programs, and a
gating mechanism decides which of them are reused.

## Results

On the CALVIN benchmark the method improves the success rate by 4.2 percent
over the baseline. We train on 8×A100 GPUs and evaluate zero-shot.

## References

[1] Someone et al., A Baseline, 2024.
