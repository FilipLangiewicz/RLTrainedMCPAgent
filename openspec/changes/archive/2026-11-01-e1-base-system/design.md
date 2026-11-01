# Design

## Context

See `proposal.md` for the motivation. The repository has no code. These facts limit the design:

- The local machines have no GPU and approximately 8 GB of RAM. The full evaluation runs on Kaggle (2x Tesla T4). The local machines run only the unit tests and a smoke test.
- The lock has `mcp` 2.3.0. This version changed the API of version 1 (see "MCP 2.x API" below).
- The lock has `transformers` 5.x and `torch` 2.15 (CPU build locally, the Kaggle GPU build on Kaggle).
- `AGENTS.md` asks for few files, logic only in `src/`, and names that do not depend on the domain.

## Goals / Non-Goals

**Goals:**

- One command makes all boards and both task files. One command runs the evaluation from a codename.
- The tool contract is stable, because the training (E2, E3) and the adapter to real Jira (E3) use it.
- The reference solution of each task is a list of tool calls. Thus E2 can make SFT examples from it.

**Non-Goals:**

- A web interface or a server for more than one client.
- Concurrency in one board.
- Speed optimization of the inference (batches, vLLM).

## Decisions

### Files

All logic is in six modules. `src/` has no `__init__.py`: Python imports `src.<module>` as a namespace package, and `python -m pytest` in the root folder finds it. Remove `src/.gitkeep` and `tests/.gitkeep`.

| File | Content |
|---|---|
| `src/environment.py` | Pydantic models of a board, the board generator, the operations, the search, the difference of two states, save and load. |
| `src/tools.py` | `build_server(board) -> MCPServer` with the seven tools. `python -m src.tools <board.json>` starts the stdio server. |
| `src/tasks.py` | The task model, the templates, the task generator, load and save of task files. `python -m src.tasks --seed 2026` makes all files in `data/`. |
| `src/verifier.py` | `grade(task, initial_board, final_board, final_answer) -> Grade`. A separate file, because RL (E3) uses it as the reward function. |
| `src/agent.py` | The system prompt, the two backends, the parser of tool calls, `run_task(...) -> Trajectory`. |
| `src/evaluate.py` | `load_config(codename)`, `run_evaluation(cfg, output_dir, shard)`, `merge(output_dirs)`, and the command line. |
| `tests/test_environment.py`, `tests/test_tools.py`, `tests/test_tasks.py`, `tests/test_verifier.py`, `tests/test_agent.py`, `tests/test_evaluate.py` | One test file for each module. |
| `data/environments/<board>.json` | The generated boards: `test-01` to `test-05` and `train-01` to `train-20`. |
| `data/tasks/test/tasks.jsonl`, `data/tasks/train/tasks.jsonl` | The generated tasks. |

### Board data

- One project for each board. The project key comes from a fixed list (`WEB`, `APP`, `API`, `SHOP`, `CRM`, ...). Thus a test board and a train board do not have the same keys.
- 6 persons, 4 sprints (1 `closed`, 1 `active`, 2 `future`), 30 to 40 issues.
- Person id: `u1` to `u6`. Display name: an invented full name, for example "Anna Kowalczyk". The first names on one board are unique, so that an instruction "Ani" names exactly one person.
- The name list in `src/environment.py` has, for each first name, the Polish forms that the templates need: nominative, genitive, dative, accusative, instrumental. Example: Ania, Ani, Ani, Anię, Anią.
- Sprint name: "Sprint <n>". The instruction words: "bieżący sprint" is the `active` sprint. "następny sprint" is the `future` sprint with the lowest number.
- Issue titles come from Polish title templates, for example "Błąd walidacji formularza logowania". Labels come from the list `frontend`, `backend`, `api`, `ui`, `database`, `security`, `docs`, `performance`.
- "Otwarte" in an instruction means the status is not `done`. The system prompt tells this to the model.

### Difference of two states

`diff(before, after)` returns a list of entries. Each entry is one of:

- `{"op": "update", "key": "WEB-12", "field": "assignee", "value": "u3"}`. For labels, the value is the full sorted list after the change.
- `{"op": "create", "fields": {...}}` with all fields of the new issue, without the key.
- `{"op": "comment", "key": "WEB-12", "text": "..."}`.

The same format stores the expected changes of a task. The verifier compares two such lists. The entries sort by a fixed order, so that a list has one text form.

### Task generation

- Each template is a Python function. It gets a board and a random generator. It returns the instruction, the category, the difficulty and the reference solution, or `None` when the board has no good target (for example no bug with the label).
- The generator applies the reference solution with the tools to a copy of the board and stores the difference as the expected changes. Thus the expected changes do not depend on the agent.
- The generator removes a task with an empty difference (except refusal tasks) and a task with an instruction that already exists.
- Categories of `easy` tasks: assign one issue, change the status, change the priority, add a label, add a comment, move an issue to a sprint or to the backlog, create an issue.
- Categories of `multi_step` tasks: assign all issues that match two filters; move open bugs with a label to the next sprint and assign them to a person; close all issues of a person in the current sprint; give all open issues of one person to another person; create an issue and put it into a sprint with an assignee; set the unassigned high-priority bugs to `in_progress` and assign them.
- Categories of `refusal` tasks: a request outside the domain (weather, e-mail, calculation), an operation without a tool (delete an issue, delete a sprint, change a password), a person or an issue that does not exist. The test split and the train split use separate lists of refusal texts.
- Sizes: the test set has 200 tasks (70 `easy`, 100 `multi_step`, 30 `refusal`) on the 5 test boards. The train set has 1000 tasks with the same proportions on the 20 train boards. E2 can make the train set again. The test set stays frozen.
- The texts of the instructions follow the rules of the course: the words of a user, not of the documentation, for example "daj to Ani", "wrzuć do następnego sprintu".

### Frozen test set

`tests/test_tasks.py` has a constant with the SHA-256 of `data/tasks/test/tasks.jsonl` and of each test board. The test fails when a file changes. Thus no new file is necessary for the checksum.

### MCP 2.x API

These facts come from a check of `mcp` 2.3.0 in the local environment:

- The server class is `mcp.server.mcpserver.MCPServer`. `mcp.server.fastmcp` does not exist in 2.x.
- The client `mcp.Client(server)` connects in the same process to an `MCPServer` instance. The agent and the tests use this. Thus no subprocess is necessary.
- The fields of the client results use snake case: `tool.input_schema`, `result.is_error`, `result.structured_content`.
- A tool must raise `mcp.server.mcpserver.exceptions.ToolError` for an expected error. Then the model gets "Error executing tool <name>: <message>". Another exception gives only "Error executing tool <name>", without the cause.

### Tool results

A tool returns a dict or a list of dicts. The agent gives the text content of the result (JSON) to the model. The short form of an issue in `search_issues` keeps the tool results small. A search result has at most 50 issues, and it reports the total number.

### Agent backends

- `transformers`: `AutoModelForCausalLM` and `AutoTokenizer` with `apply_chat_template(messages, tools=..., add_generation_prompt=True, enable_thinking=False)`. The tool schemas come from `list_tools()` in the OpenAI function format. Qwen3 writes a tool call as `<tool_call>{"name": ..., "arguments": {...}}</tool_call>`. The parser finds all such blocks with a regular expression. The tool results go back as messages with the role `tool`. Greedy decoding: `do_sample=False`. The dtype comes from the config: `float16` on a T4 (no good bfloat16 support), `float32` on a CPU. `max_new_tokens` is 512 for each step.
- `openai`: the `openai` package with `base_url` and `model` from the config, `temperature=0`, the native `tools` argument. This backend serves a reference API model and also a local server (for example Ollama).
- A third backend `scripted` exists only in the tests. It returns fixed outputs, so that the tests of the loop do not need a model.
- The step limit is 15.

### System prompt

The prompt is in English, because the small model follows English instructions better. It tells the model to answer the user in Polish. It explains "otwarte", "bieżący sprint" and "następny sprint", and the refusal marker `ODMOWA:`. The constant `PROMPT_VERSION` (first value `v1`) names the prompt. A change of the prompt is a new variant with a new version name.

### Evaluation config

A config is a YAML file in a job folder (see `KAGGLE.md`). Example `baseline-v1.yaml`:

```yaml
model:
  backend: transformers
  name: Qwen/Qwen3-1.7B
  dtype: float16
  enable_thinking: false
  max_new_tokens: 512
agent:
  max_steps: 15
tasks:
  split: test
  limit: null
```

The command `python -m src.evaluate <codename> --output <folder> [--shard i/n] [--limit N]` runs the evaluation. `python -m src.evaluate --merge <folder> ...` merges the shards. The model revision comes from the commit hash of the model on the Hugging Face Hub, as `transformers` reports it.

### Alternatives

- A full expected state instead of the expected changes: rejected. The difference shows the error directly, and it makes the check of additional changes simple.
- A board generated from the seed in each task instead of a board file: rejected. A later change of the generator code would change the frozen test set without a note.
- An LLM judge for the grade: rejected. The state of the board gives an exact grade without cost.
- Fewer tools (one generic tool): rejected. Real Jira has separate operations, and the adapter (E3) maps them one to one.

## Risks / Trade-offs

- [The small model does not use the tool-call format correctly] → The loop counts invalid calls and continues. The error analysis shows the frequency. E2 trains the format.
- [The baseline on two T4 GPUs takes many hours with `transformers`] → Shards on both GPUs. A smoke test with `--limit 5` first. If the time is too long, a later change can add vLLM.
- [The template instructions are too regular, and the score is not realistic] → More than one text for each category, and words of a user. The test set has other boards than the train set. Real Jira in E3 gives a separate check.
- [The verifier is too strict, for example with a comment text] → The normalization of text, and the error analysis of the incorrect grades. A change of the verifier is a change of the specs and needs a new run of all variants.
- [The local smoke test with Qwen3-1.7B needs too much RAM] → The local smoke test uses `Qwen/Qwen3-0.6B` with `float32` on 2 tasks. It checks only the code path, not the score.

## Migration Plan

No migration is necessary. The repository has no code. After the archive of this change, the baseline job on Kaggle uses `src/evaluate.py`.

## Open Questions

- The exact number of steps that a multi-step task needs. The step limit of 15 is enough for the planned templates (at most approximately 8 calls). The first run shows if it is correct.
