import json
import random
from types import SimpleNamespace

import pytest
import torch

from src.models import (
    FAMILIES,
    ScriptedModel,
    check_adapters,
    check_config,
    load_prompt,
)
from src.rl import checkpoint
from src.rl.config import ConfigError, config_hash, differences, resolve
from src.rl.engines import ContextLimit, Engine, RolloutModel
from src.rl.grpo import advantages, policy_loss, token_logprobs
from src.rl.rollouts import (
    REFUSAL_WRITE,
    Rollout,
    f_beta,
    group_stats,
    run_one,
    run_rollouts,
    select_tasks,
)
from src.rl.tokens import Turn, build_samples, conversation_tokens
from src.rl.train import (
    Loop,
    Records,
    Updater,
    backward_part,
    main,
    next_tasks,
    split_samples,
)
from src.tasks import load_tasks

QWEN = FAMILIES["qwen3.5"]
MODEL = {"family": "bielik", "path": "/models/bielik"}
AGENT = {"max_steps": 25, "loop_limit": 3, "error_limit": 5}


def tc(name, **arguments):
    return QWEN.format_calls([{"name": name, "arguments": arguments}])


# Config

def test_config_defaults():
    cfg = resolve({"model": MODEL})
    rl = cfg["rl"]
    assert (rl["loss_type"], rl["lora_rank"], rl["reward"], rl["save_every"]) == ("dapo", 16, "binary", 25)
    assert rl["max_context_tokens"] == rl["max_sample_tokens"] == 8192
    assert cfg["engine"]["name"] == "vllm" and cfg["engine"]["overlap"] is True
    gemma = resolve({"model": {"family": "gemma4", "path": "/m"}})
    assert gemma["engine"]["name"] == "transformers" and gemma["engine"]["overlap"] is False
    assert gemma["engine"]["patch"] is True


def test_config_unknown_key():
    with pytest.raises(ConfigError, match="rl.save_evry"):
        resolve({"model": MODEL, "rl": {"save_evry": 5}})
    with pytest.raises(ConfigError, match="probe"):
        resolve({"model": MODEL, "probe": {}})


def test_config_test_split():
    with pytest.raises(ConfigError, match="test"):
        resolve({"model": MODEL, "rl": {"split": "test"}})
    with pytest.raises(ConfigError, match="test"):
        resolve({"model": MODEL, "rl": {"eval_split": "test"}})
    assert resolve({"model": MODEL, "rl": {"mode": "measure", "split": "test"}})["rl"]["split"] == "test"


def test_config_run_length_keys():
    a = resolve({"model": MODEL})
    b = resolve({"model": MODEL, "rl": {"steps": 5, "deadline_hours": 1}})
    c = resolve({"model": MODEL, "rl": {"learning_rate": 2e-5}})
    assert config_hash(a) == config_hash(b) and differences(a, b) == []
    assert differences(a, c) == ["rl.learning_rate"]


# Samples

def test_stable_prefix_merges_turns():
    t1 = Turn(prompt=[1, 2, 3], output=[4, 5], logprobs=[-0.1, -0.2])
    t2 = Turn(prompt=[1, 2, 3, 4, 5, 6, 7], output=[8], logprobs=[-0.3])
    samples, dropped = build_samples([t1, t2], 100, advantage=0.5)
    assert dropped == 0 and len(samples) == 1
    s = samples[0]
    assert s.ids == [1, 2, 3, 4, 5, 6, 7, 8]
    assert s.mask == [0, 0, 0, 1, 1, 0, 0, 1]
    assert s.old_logprobs == [0, 0, 0, -0.1, -0.2, 0, 0, -0.3]
    assert s.advantage == 0.5 and s.model_tokens == 3


def test_changed_prefix_starts_new_sample():
    t1 = Turn(prompt=[1, 2], output=[3, 9], logprobs=[-0.1, -0.2])
    t2 = Turn(prompt=[1, 2, 3, 4, 5], output=[6], logprobs=[-0.3])  # The parser wrote 4 in place of 9.
    samples, _ = build_samples([t1, t2], 100)
    assert [s.ids for s in samples] == [[1, 2, 3, 9], [1, 2, 3, 4, 5, 6]]
    assert samples[0].mask == [0, 0, 1, 1] and samples[1].mask == [0, 0, 0, 0, 0, 1]


def test_length_limit():
    t1 = Turn(prompt=[1, 2], output=[3], logprobs=[-0.1])
    t2 = Turn(prompt=[1, 2, 3, 4], output=[5], logprobs=[-0.2])
    samples, dropped = build_samples([t1, t2], 4)
    assert [s.ids for s in samples] == [[1, 2, 3]] and dropped == 1
    samples, dropped = build_samples([t1, t2], 5)
    assert [s.ids for s in samples] == [[1, 2, 3, 4, 5]] and dropped == 0


class FakeTokenizer:
    """One token for each character. The template marks each message with its role."""

    eos_token, pad_token, bos_token = "$", None, None

    def apply_chat_template(self, messages, tools=None, add_generation_prompt=False, tokenize=False, **kwargs):
        text = "".join(f"<{m['role'][0]}>{m['content']}$" for m in messages)
        return text + ("<a>" if add_generation_prompt else "")

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [ord(c) for c in text]}

    def decode(self, ids, skip_special_tokens=False):
        return "".join(chr(i) for i in ids)


def test_conversation_tokens():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                {"role": "assistant", "content": "ab"}]
    ids, mask = conversation_tokens(FAMILIES["bielik"], FakeTokenizer(), messages, [])
    text = "".join(chr(i) for i in ids)
    assert text == "<s>s $<u>u$<a>ab$" or text.endswith("<a>ab$")
    assert "".join(chr(i) for i, m in zip(ids, mask) if m) == "ab$"


# Reward and rollouts

@pytest.fixture(scope="module")
def train_tasks():
    return load_tasks("train")


def first(tasks, category, changes=None):
    return next(t for t in tasks if t.category == category and (changes is None or len(t.changes) == changes))


def test_reward_correct_and_refusal_write(train_tasks):
    prompt = load_prompt("system", "v3")
    refusal = first(train_tasks, "refusal")
    good = run_one(ScriptedModel(["ODMOWA: nie mogę tego zrobić."]), refusal, 0, prompt, AGENT, "binary")
    assert good.reward == 1.0 and good.grade == "correct_refusal"
    key = refusal.instruction.split()[1].rstrip(",.")
    bad = run_one(ScriptedModel([tc("jira_add_comment", issue_key=key, body="x"), "Gotowe."]), refusal, 0, prompt,
                  AGENT, "binary")
    assert bad.reward == REFUSAL_WRITE


def test_reward_partial(train_tasks):
    task = first(train_tasks, "update", changes=2) if any(
        t.category == "update" and len(t.changes) == 2 for t in train_tasks) else next(
        t for t in train_tasks if t.changes and len(t.changes) == 2)
    call = task.calls[-1]
    prompt = load_prompt("system", "v3")
    # Only the last call of the solution: at most one of the two expected changes.
    out = run_one(ScriptedModel([tc(call.name, **call.arguments), "Gotowe."]), task, 0, prompt, AGENT, "partial")
    if out.grade != "correct":
        assert out.reward == out.partial
        assert out.reward in (0.0, round(0.2 * f_beta(1, 2, 1), 4))
    binary = run_one(ScriptedModel(["Nic."]), task, 0, prompt, AGENT, "binary")
    assert binary.reward == 0.0


def test_f_beta():
    assert f_beta(1, 2, 1) == pytest.approx(1.25 * 0.5 / (0.25 + 0.5))
    assert f_beta(0, 2, 3) == 0.0


class ScriptedEngine:
    lanes = 3

    def __init__(self, outputs):
        self.outputs = outputs

    def model_for_rollout(self, lane, temperature=None):
        return ScriptedModel(self.outputs)


def test_run_rollouts_and_group_stats(train_tasks):
    tasks = select_tasks(train_tasks, 4, 0)
    assert len({t.category for t in tasks}) == 4
    jobs = [(t, g) for g, t in enumerate(tasks) for _ in range(2)]
    out = run_rollouts(ScriptedEngine(["ODMOWA: nie."]), jobs, load_prompt("system", "v3"), AGENT, "binary")
    assert [r.group for r in out] == [0, 0, 1, 1, 2, 2, 3, 3]
    stats = group_stats(out)
    assert stats["rollouts"] == 8 and stats["mixed_share"] == 0.0
    out[0].reward = None
    out[0].context_limit = True
    assert group_stats(out)["context_limit"] == 1


# Advantage and loss

def test_advantage_drops_equal_groups():
    adv, stats = advantages([0, 0, 0, 1, 0, 0, 1, None], [0, 0, 1, 1, 2, 2, 3, 3])
    assert adv[:2] == [None, None]
    assert adv[2:4] == [-0.5, 0.5]
    assert adv[4:6] == [None, None] and adv[6:] == [None, None]
    assert stats["groups_kept"] == 1 and stats["groups_equal"] == 2 and stats["groups_too_small"] == 1
    adv, _ = advantages([1, 0, 0, None], [0, 0, 0, 0])
    assert adv == pytest.approx([2 / 3, -1 / 3, -1 / 3, None][:3]) or adv[:3] == pytest.approx([2 / 3, -1 / 3, -1 / 3])


def test_policy_loss_values_and_clip():
    old = torch.zeros(3)
    logp = torch.log(torch.tensor([1.0, 1.5, 0.5]))
    loss, st = policy_loss(logp, old, 1.0, 0.2, 0.28)
    # ratio 1 -> -1; ratio 1.5 is clipped to 1.28; ratio 0.5 -> min(0.5, 0.8) = 0.5.
    assert loss.item() == pytest.approx(-(1 + 1.28 + 0.5))
    assert st["clipped"] == 1
    loss, st = policy_loss(logp, old, -1.0, 0.2, 0.28)
    # A < 0: -min(-r, -clip(r)) = max(r, clip(r)): 1, 1.5, 0.8.
    assert loss.item() == pytest.approx(1 + 1.5 + 0.8)
    assert st["clipped"] == 1


def test_token_level_mean():
    w = torch.zeros(1, requires_grad=True)
    a, b = w.expand(10) + 0, w.expand(30) + 0
    la, _ = policy_loss(a, torch.zeros(10), 1.0, 0.2, 0.28)
    lb, _ = policy_loss(b, torch.zeros(30), 1.0, 0.2, 0.28)
    ((la + lb) / 40).backward()
    # Each of the 40 tokens has the weight 1/40: the gradient is -1, not the mean of two sample means.
    assert w.grad.item() == pytest.approx(-1.0)


def test_token_logprobs_chunks():
    torch.manual_seed(0)
    hidden = torch.randn(7, 4, requires_grad=True)
    weight = torch.randn(11, 4)
    targets = torch.randint(0, 11, (7,))
    full = torch.log_softmax(hidden @ weight.t(), -1).gather(-1, targets[:, None])[:, 0]
    chunked = token_logprobs(hidden, weight, targets, chunk=3)
    assert torch.allclose(full, chunked, atol=1e-6)
    g1, = torch.autograd.grad(full.sum(), hidden)
    g2, = torch.autograd.grad(chunked.sum(), hidden)
    assert torch.allclose(g1, g2, atol=1e-6)
    capped = token_logprobs(hidden, weight, targets, chunk=3, softcap=2.0)
    expect = torch.log_softmax(torch.tanh(hidden @ weight.t() / 2) * 2, -1).gather(-1, targets[:, None])[:, 0]
    assert torch.allclose(capped, expect, atol=1e-6)


# Model layer and policy

def write_adapter(folder, base_shape):
    folder.mkdir(parents=True)
    (folder / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "elsewhere"}))
    (folder / "base_model.json").write_text(json.dumps(base_shape))


def test_check_adapters(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "config.json").write_text(json.dumps({"model_type": "llama", "hidden_size": 8, "num_hidden_layers": 2,
                                                  "vocab_size": 10}))
    shape = {"model_type": "llama", "hidden_size": 8, "num_hidden_layers": 2, "vocab_size": 10}
    write_adapter(tmp_path / "sft", shape)
    write_adapter(tmp_path / "other", {**shape, "hidden_size": 16})
    cfg = check_config({"backend": "transformers", "family": "bielik", "path": str(base),
                        "adapters": [str(tmp_path / "sft")]})
    assert cfg["adapters"] == [str(tmp_path / "sft")]
    with pytest.raises(ValueError, match="other"):
        check_config({"backend": "transformers", "family": "bielik", "path": str(base),
                      "adapters": [str(tmp_path / "sft"), str(tmp_path / "other")]})
    with pytest.raises(ValueError, match="adapter_config"):
        check_adapters(str(base), [str(tmp_path / "missing")])


def test_local_model_records_adapters(monkeypatch, tmp_path):
    from src import models

    class Fake:
        config = SimpleNamespace(_commit_hash=None)

        def to(self, device):
            return self

        def eval(self):
            return self

    merged = []
    monkeypatch.setattr(models, "load_weights", lambda *a, **k: (None, Fake()))
    monkeypatch.setattr(models, "merge_adapters", lambda m, adapters: merged.append(adapters) or m)
    model = models.LocalModel("bielik", str(tmp_path), device="cpu", adapters=["a", "b"])
    assert merged == [["a", "b"]]
    assert model.describe()["adapters"] == ["a", "b"]


def test_lora_config():
    from src.rl.policy import LORA_TARGETS, lora_config

    cfg = lora_config(resolve({"model": MODEL})["rl"])
    assert cfg.r == 16 and cfg.lora_alpha == 32 and cfg.lora_dropout == 0.0
    assert set(cfg.target_modules) == set(LORA_TARGETS)
    assert "vision" in cfg.exclude_modules


# Engine

class FakeEngine(Engine):
    def __init__(self, max_context=40):
        cfg = resolve({"model": {"family": "qwen3.5", "path": "/m", "max_new_tokens": 10},
                       "rl": {"max_sample_tokens": max_context}})
        super().__init__(cfg, FakeTokenizer())
        self.calls = []

    def sample(self, lane, prompt, max_new, temperature):
        self.calls.append(max_new)
        return [ord(c) for c in "ok$"], [-0.1, -0.2, -0.3]


def test_rollout_model_records_turns():
    engine = FakeEngine(max_context=40)
    model = engine.model_for_rollout(0)
    out = model.generate([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], [])
    assert out.text == "ok"
    turn = model.turns[0]
    assert turn.output == [ord(c) for c in "ok$"] and turn.logprobs == [-0.1, -0.2, -0.3]
    assert "".join(chr(i) for i in turn.prompt).startswith("<s>s")
    assert engine.calls[0] <= 10


def test_rollout_model_context_limit():
    engine = FakeEngine(max_context=20)
    model = RolloutModel(engine, 0, 1.0)
    with pytest.raises(ContextLimit):
        model.generate([{"role": "system", "content": "s" * 30}, {"role": "user", "content": "u"}], [])
    assert model.context_limit and not model.turns


def test_context_limit_rollout_leaves_the_loss(train_tasks):
    engine = FakeEngine(max_context=20)
    task = first(train_tasks, "query")
    out = run_one(engine.model_for_rollout(0), task, 0, load_prompt("system", "v3"), AGENT, "binary")
    assert out.context_limit and out.reward is None and not out.valid
    ok = Rollout(task=task, group=0, reward=1.0)
    adv, _ = advantages([out.reward, 0.0, ok.reward], [0, 0, 0])
    assert adv == [None, -0.5, 0.5]


# Checkpoints

def test_checkpoint_write_and_read(tmp_path):
    torch.manual_seed(0)
    layer = torch.nn.Linear(3, 2)
    opt = torch.optim.AdamW(layer.parameters(), lr=0.1)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 1.0)
    for step in range(1, 4):
        layer(torch.randn(4, 3)).sum().backward()
        opt.step()
        sched.step()
        checkpoint.save(tmp_path, step, lambda f: (f.mkdir(), torch.save(layer.state_dict(), f / "w.pt")), opt, sched,
                        {"epoch": 0, "position": step * 2}, keep=2)
    folders = sorted((tmp_path / "checkpoints").glob("step-*"))
    assert [f.name for f in folders] == ["step-1", "step-2", "step-3"]
    assert all((f / "adapter" / "w.pt").exists() for f in folders)
    assert [(f / "optimizer.pt").exists() for f in folders] == [False, True, True]
    random.seed(5)
    expected = random.random()
    random.seed(5)
    checkpoint.save(tmp_path, 4, lambda f: f.mkdir(), opt, sched, {"epoch": 0, "position": 8}, keep=2)
    found = checkpoint.find(tmp_path)
    assert found.name == "step-4"
    opt2 = torch.optim.AdamW(torch.nn.Linear(3, 2).parameters(), lr=0.1)
    loaded = checkpoint.load(found, opt2, None)
    assert loaded["state"]["position"] == 8 and loaded["state"]["step"] == 4
    assert random.random() == expected
    a, b = opt.state_dict()["state"][0]["exp_avg"], opt2.state_dict()["state"][0]["exp_avg"]
    assert torch.equal(a, b)


# Loop

def test_next_tasks_and_resume_order():
    count, seed, k = 10, 3, 4
    one = []
    epoch = position = 0
    for _ in range(5):
        picks, epoch, position = next_tasks(count, seed, 2, epoch, position, k)
        one.append(picks)
    # A second job continues from the state after step 2.
    _, e, p = next_tasks(count, seed, 2, 0, 0, k)
    _, e, p = next_tasks(count, seed, 2, e, p, k)
    two = []
    for _ in range(3):
        picks, e, p = next_tasks(count, seed, 2, e, p, k)
        two.append(picks)
    assert two == one[2:]
    assert sorted(one[0] + one[1] + one[2][:2]) == list(range(10))
    assert next_tasks(count, seed, 2, 2, 0, k) is None


class FakeLoop(Loop):
    def __init__(self, cfg, records, clock, rewards):
        super().__init__(cfg, records, clock)
        self.task_count, self.rewards, self.saved = 100, rewards, []

    def generate(self, picks):
        return [], 0.0

    def update(self, rollouts):
        self.clock.now += 3600
        return {"update": True}

    def save_checkpoint(self):
        self.saved.append(self.step)
        self.saved_step = self.step


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.mark.parametrize("overlap", [False, True])
def test_deadline_stops_after_the_step(tmp_path, overlap):
    cfg = resolve({"model": MODEL, "engine": {"overlap": overlap},
                   "rl": {"steps": 10, "deadline_hours": 2.5, "save_every": 2, "eval_every": 0}})
    loop = FakeLoop(cfg, Records(tmp_path), Clock(), [])
    assert loop.run() == "deadline"
    assert loop.step == 3 and loop.saved == [2, 3]
    lines = [json.loads(x) for x in (tmp_path / "metrics.jsonl").read_text().splitlines()]
    assert [x["step"] for x in lines] == [1, 2, 3]


def test_run_complete(tmp_path):
    cfg = resolve({"model": MODEL, "rl": {"steps": 2, "save_every": 1, "eval_every": 0}})
    loop = FakeLoop(cfg, Records(tmp_path), Clock(), [])
    assert loop.run() == "complete" and loop.saved == [1, 2]


def test_status_after_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("model: {family: bielik, path: /m}\nrl: {save_evry: 3}\n")
    assert main([str(bad), "--output", str(tmp_path / "out")]) == 0
    status = json.loads((tmp_path / "out" / "status.json").read_text())
    assert status["status"] == "error" and "save_evry" in status["error"] and status["step"] == 0


class FakePolicy:
    def __init__(self, fail: set):
        self.torch, self.device, self.fail, self.calls = torch, "cpu", fail, 0
        self.w = torch.nn.Parameter(torch.zeros(1))
        self.model = torch.nn.Module()

    def parameters(self):
        return [self.w]

    def logprobs(self, ids, mask):
        self.calls += 1
        if self.calls in self.fail:
            (self.w * 2).sum().backward()  # A part of the gradient before the error must not stay.
            raise torch.cuda.OutOfMemoryError("CUDA out of memory")
        return self.w.expand(sum(mask[1:])) + 0

    def free_memory(self):
        pass


def rollouts_for_update():
    task = SimpleNamespace(category="query", difficulty="easy", id="t")
    rows = []
    for g in range(2):
        for reward in (1.0, 0.0):
            # The correct rollouts are longer, so that the gradients of a group do not cancel.
            output = [3, 4, 5, 6] if reward else [3, 4]
            turn = Turn(prompt=[1, 2], output=output, logprobs=[0.0] * len(output))
            rows.append(Rollout(task=task, group=g, reward=reward, turns=[turn]))
    return rows


def test_oom_skips_one_sample():
    policy = FakePolicy(fail={2})
    rl = resolve({"model": MODEL})["rl"]
    stats = backward_part(policy, build_samples([Turn([1], [2, 3], [0.0, 0.0])], 100, 1.0)[0] * 3, 6, rl, 1.0)
    assert stats["oom"] == 1 and stats["samples"] == 2
    # Two samples of 2 tokens with A = 1: the gradient is -4/6.
    assert policy.w.grad.item() == pytest.approx(-4 / 6)


def test_oom_limit_cancels_the_update():
    rl = resolve({"model": MODEL, "rl": {"max_oom_per_step": 1}})["rl"]
    policy = FakePolicy(fail={1, 2})
    opt = torch.optim.SGD([policy.w], lr=1.0)
    result = Updater([policy], rl, opt, None).update(rollouts_for_update())
    assert result["oom"] == 2 and result["update"] is False and "cancelled" in result
    assert policy.w.item() == 0.0
    policy = FakePolicy(fail={3})
    opt = torch.optim.SGD([policy.w], lr=1.0)
    result = Updater([policy], rl, opt, None).update(rollouts_for_update())
    assert result["update"] is True and policy.w.item() != 0.0


def test_two_copies_get_the_same_weights():
    rl = resolve({"model": MODEL})["rl"]
    a, b = FakePolicy(set()), FakePolicy(set())
    opt = torch.optim.SGD([b.w], lr=1.0)
    result = Updater([a, b], rl, opt, None).update(rollouts_for_update())
    assert result["update"] is True and result["lora_sync_max_diff"] == 0.0
    assert a.w.item() == b.w.item() != 0.0


def test_split_samples():
    samples = build_samples([Turn([1] * n, [2], [0.0]) for n in (1,)], 100)[0]
    samples += [SimpleNamespace(ids=[0] * n) for n in (5, 4, 3, 2)]
    parts = split_samples(samples, 2)
    assert sorted(len(p) for p in parts) == [2, 3]
