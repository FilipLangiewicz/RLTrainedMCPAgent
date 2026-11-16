"""Turn records and the samples of the trainer (design Decision 2).

The loss uses only the tokens that the model sampled. A family can render a turn again in another form
(for example Bielik writes text after a call, and the parser removes it). Thus the trainer does not render the
conversation again. It uses the exact prompt and output tokens of each turn.
"""

from dataclasses import dataclass, field


@dataclass
class Turn:
    prompt: list[int]
    output: list[int]
    logprobs: list[float]


@dataclass
class Sample:
    ids: list[int] = field(default_factory=list)
    # 1 for a token that the model sampled, 0 for the prompt, tool results and template tokens.
    mask: list[int] = field(default_factory=list)
    # The log-probability of the sampler for each token with mask 1, else 0.
    old_logprobs: list[float] = field(default_factory=list)
    advantage: float = 0.0

    def add(self, ids: list[int], mask: int, logprobs: list[float] | None = None) -> None:
        self.ids += ids
        self.mask += [mask] * len(ids)
        self.old_logprobs += logprobs if logprobs is not None else [0.0] * len(ids)

    @property
    def model_tokens(self) -> int:
        return sum(self.mask)


def _single(turn: Turn) -> Sample:
    sample = Sample()
    sample.add(turn.prompt, 0)
    sample.add(turn.output, 1, turn.logprobs)
    return sample


def chains(turns: list[Turn]) -> list[list[Turn]]:
    """Groups of consecutive turns in which each prompt starts with the prompt and the output of the turn before."""
    groups: list[list[Turn]] = []
    tokens: list[int] = []
    for turn in turns:
        if groups and turn.prompt[: len(tokens)] == tokens and len(turn.prompt) >= len(tokens):
            groups[-1].append(turn)
        else:
            groups.append([turn])
        tokens = turn.prompt + turn.output
    return groups


def build_samples(turns: list[Turn], max_tokens: int, advantage: float = 0.0) -> tuple[list[Sample], int]:
    """Make the samples of one rollout. Return the samples and the number of turns that are too long.

    A merged sample longer than `max_tokens` becomes one sample for each turn. A turn that alone is longer
    than `max_tokens` does not go to the backward pass.
    """
    samples, dropped = [], 0
    for group in chains([t for t in turns if t.output]):
        merged = Sample()
        for turn in group:
            merged.add(turn.prompt[len(merged.ids):], 0)
            merged.add(turn.output, 1, turn.logprobs)
        parts = [merged] if len(merged.ids) <= max_tokens else [_single(t) for t in group]
        for sample in parts:
            if len(sample.ids) > max_tokens:
                dropped += 1
                continue
            sample.advantage = advantage
            samples.append(sample)
    return samples, dropped


def render(family, tokenizer, messages: list[dict], tools: list[dict], thinking: bool, generation_prompt: bool) -> str:
    messages, tools = family.prepare(family._with_mapping_arguments(messages), tools)
    return tokenizer.apply_chat_template(messages, tools=tools, add_generation_prompt=generation_prompt,
                                         tokenize=False, **family.template_args(thinking))


def conversation_tokens(family, tokenizer, messages: list[dict], tools: list[dict],
                        thinking: bool = False) -> tuple[list[int], list[int]]:
    """The token ids of a full conversation and a mask of the tokens of the model. SFT can use this function."""

    def ids(text: str) -> list[int]:
        return tokenizer(text, add_special_tokens=False)["input_ids"]

    full = ids(render(family, tokenizer, messages, tools, thinking, False))
    mask = [0] * len(full)
    for i, m in enumerate(messages):
        if m["role"] != "assistant":
            continue
        start = len(ids(render(family, tokenizer, messages[:i], tools, thinking, True)))
        end = len(ids(render(family, tokenizer, messages[: i + 1], tools, thinking, False)))
        for p in range(start, min(end, len(full))):
            mask[p] = 1
    return full, mask
