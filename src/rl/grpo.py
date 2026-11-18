"""Advantage, log-probabilities in chunks and the clipped token-level loss (design Decision 4). No model code."""

import torch
from torch.utils.checkpoint import checkpoint


def advantages(rewards: list[float | None], groups: list[int]) -> tuple[list[float | None], dict]:
    """Dr. GRPO: reward minus the mean reward of the group, no division by the standard deviation.

    A reward of None marks a rollout that does not go to the loss (for example the context limit).
    A group with equal rewards, or with fewer than two valid rollouts, gets None for all its rollouts.
    """
    by_group: dict[int, list[int]] = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    result: list[float | None] = [None] * len(rewards)
    kept = equal = small = 0
    for members in by_group.values():
        valid = [i for i in members if rewards[i] is not None]
        if len(valid) < 2:
            small += 1
            continue
        values = [rewards[i] for i in valid]
        if max(values) == min(values):
            equal += 1
            continue
        mean = sum(values) / len(values)
        for i in valid:
            result[i] = rewards[i] - mean
        kept += 1
    n = len(by_group) or 1
    return result, {"groups": len(by_group), "groups_kept": kept, "groups_equal": equal, "groups_too_small": small,
                    "mixed_share": round(kept / n, 4)}


def _chunk_logprobs(hidden, weight, targets, softcap: float, temperature: float):
    logits = (hidden @ weight.t()).float()
    if softcap:
        logits = torch.tanh(logits / softcap) * softcap
    if temperature != 1.0:
        logits = logits / temperature
    # The log-probability of one token needs only its logit and the logsumexp, not a full log_softmax tensor.
    return logits.gather(-1, targets[:, None])[:, 0] - torch.logsumexp(logits, -1)


def token_logprobs(hidden, weight, targets, chunk: int = 1024, softcap: float = 0.0, temperature: float = 1.0):
    """Log-probabilities of `targets` from the hidden states before the output layer.

    Only chunks of `chunk` positions have logits at the same time. The backward pass computes each chunk again,
    because the vocabulary of Qwen (248k tokens) needs gigabytes for the logits of a long sample.
    """
    parts = []
    for start in range(0, hidden.shape[0], chunk):
        h, t = hidden[start: start + chunk], targets[start: start + chunk]
        if torch.is_grad_enabled() and h.requires_grad:
            parts.append(checkpoint(_chunk_logprobs, h, weight, t, softcap, temperature, use_reentrant=False))
        else:
            parts.append(_chunk_logprobs(h, weight, t, softcap, temperature))
    return torch.cat(parts) if parts else hidden.new_zeros(0, dtype=torch.float32)


def policy_loss(logp, old_logp, advantage, clip_low: float, clip_high: float) -> tuple[torch.Tensor, dict]:
    """The sum of the clipped policy loss over the tokens. The caller divides by the token count of the step.

    loss(t) = -min(ratio * A, clip(ratio, 1 - clip_low, 1 + clip_high) * A), with ratio = exp(logp - old_logp).
    """
    advantage = torch.as_tensor(advantage, dtype=logp.dtype, device=logp.device).expand_as(logp)
    ratio = torch.exp(logp - old_logp)
    clipped = torch.clamp(ratio, 1 - clip_low, 1 + clip_high)
    loss = -torch.minimum(ratio * advantage, clipped * advantage)
    with torch.no_grad():
        active = ((advantage > 0) & (ratio > 1 + clip_high)) | ((advantage < 0) & (ratio < 1 - clip_low))
        diff = (logp - old_logp).abs()
        stats = {"tokens": int(logp.numel()), "clipped": int(active.sum()),
                 "logprob_diff_sum": float(diff.sum()), "logprob_diff_max": float(diff.max()) if diff.numel() else 0.0}
    return loss.sum(), stats
