# Spec Delta

## Purpose

The RL run trains a LoRA adapter with GRPO on the tasks of the simulator, with the reward from the verifier. It works for each model family of the model layer and for long runs on Kaggle.

## ADDED Requirements

### Requirement: Config of an RL run
An RL run SHALL start from a YAML config with the sections `model`, `agent`, `engine` and `rl`. Each key that the config does not give SHALL get the default of the decisions of idm-pro-047. An unknown key SHALL stop the run before the first step. The run SHALL record the full config with the defaults.

#### Scenario: Defaults
- **WHEN** the config gives only the model and the output folder
- **THEN** the run uses the loss `dapo`, LoRA rank 16, the binary reward and a checkpoint every 25 steps

#### Scenario: Typo in a key
- **WHEN** the config has the key `rl.save_evry`
- **THEN** the run stops before the first step with an error that names the key

### Requirement: Same rollouts as the evaluation
An RL run SHALL use the agent loop and the tools of the evaluation. It SHALL also use the same system prompt and parsers. The settings of the run (step limits, loop limits, context limit) SHALL apply only to the run. The evaluation SHALL keep its own settings.

#### Scenario: Tighter limits in the run
- **WHEN** the RL config gives `agent.error_limit: 3`
- **THEN** the rollouts of the run stop after 3 tool errors in a row
- **AND** an evaluation with its own config keeps its limit

#### Scenario: Context limit
- **WHEN** the prompt of a turn is longer than `rl.max_context_tokens`
- **THEN** the rollout stops and does not go to the loss
- **AND** the advantage of its group uses only the other rollouts

### Requirement: Reward
The reward of a rollout SHALL come from the verifier. In the variant `binary`, a correct task or a correct refusal SHALL give 1, and other results SHALL give 0. A write on the board in a refusal task SHALL give -0.2. The variant `partial` SHALL add 0.2 x F0.5 of the changes for an incorrect change task. A rollout that stops with an error SHALL get 0. A rollout that stops at the context limit SHALL not get a reward, and it SHALL not go to the loss.

#### Scenario: Write in a refusal task
- **WHEN** the task is a refusal task and the rollout changes the board
- **THEN** the reward is -0.2

#### Scenario: Partial reward
- **WHEN** the variant is `partial` and an incorrect change task makes 1 of 2 expected changes and no additional change
- **THEN** the reward is 0.2 x F0.5 of these changes

### Requirement: Loss on the sampled tokens
The loss SHALL use only the tokens that the model sampled, with the log-probabilities of the sampler. Tokens of the prompt, of tool results and of the template SHALL not count in the loss. Consecutive turns SHALL form one sample only when the tokens of the next prompt start with the tokens of the earlier prompt and output.

#### Scenario: Stable prefix
- **WHEN** the prompt of turn 2 starts with the prompt and the output of turn 1
- **THEN** turns 1 and 2 form one sample, and the tool result between them has the mask 0

#### Scenario: Changed prefix
- **WHEN** the prompt of turn 2 does not start with the output of turn 1, because the parser changed the text
- **THEN** turn 2 is a new sample, and the loss uses the exact tokens of turn 1

### Requirement: GRPO update
For each group of rollouts of one task, the advantage SHALL be the reward minus the mean reward of the group. A group with equal rewards SHALL not go to the backward pass. The loss SHALL be the clipped policy loss with `clip_low` and `clip_high`, averaged over all model tokens of the step, without a KL term. A step with a gradient that is not finite SHALL do no update.

#### Scenario: Group with equal rewards
- **WHEN** all 8 rollouts of a task get the reward 0
- **THEN** the step does not use this group, and the records show its share

#### Scenario: Token-level mean
- **WHEN** a step has one sample with 10 model tokens and one sample with 30 model tokens
- **THEN** each of the 40 tokens has the same weight in the loss

#### Scenario: Infinite gradient
- **WHEN** the gradient of a step has a value that is not finite
- **THEN** the LoRA weights do not change, and the records show the event

### Requirement: Memory limits
No sample in the backward pass SHALL be longer than `rl.max_sample_tokens`. Before step 1, the run SHALL do one forward and backward pass with a sequence of this length. If this check gives an out-of-memory error, the run SHALL stop before step 1. An out-of-memory error of one sample in a step SHALL skip this sample. More than `rl.max_oom_per_step` such errors SHALL cancel the update of the step.

#### Scenario: Limit too high for the GPU
- **WHEN** the config gives `rl.max_sample_tokens: 8192` for Gemma 4 E4B
- **THEN** the memory check fails, and `status.json` tells the user to lower `rl.max_sample_tokens`

#### Scenario: One long sample
- **WHEN** one sample of a step gives an out-of-memory error in the backward pass
- **THEN** the step uses the gradients of the other samples, and the records count one error

#### Scenario: Turn longer than the sample limit
- **WHEN** the prompt and the output of one turn have more tokens than `rl.max_sample_tokens`
- **THEN** this turn does not go to the backward pass, and the records count it

### Requirement: Generation engines
The run SHALL support two engines. The engine `vllm` has a vLLM server on one GPU and the trainer on the other GPU. The engine `transformers` has one model copy on each GPU. The config SHALL select the engine. The two engines SHALL give the same interface to the rest of the run.

#### Scenario: Same config with another engine
- **WHEN** two configs differ only in `engine.name`
- **THEN** both runs do the same steps with the same tasks, the same reward and the same loss

#### Scenario: New adapter in vLLM
- **WHEN** the trainer finishes an update and the engine is `vllm`
- **THEN** the server gets the new adapter without a restart

### Requirement: Start weights
The run SHALL load the base weights from `model.path`. It SHALL merge the LoRA adapters of `model.adapters` (for example the SFT adapter) into these weights in the order of the list. The run SHALL train a new LoRA adapter over the merged weights. A folder without an adapter config SHALL load as full weights.

#### Scenario: Run after SFT
- **WHEN** the config gives the base model and the SFT adapter of the same model
- **THEN** the rollouts of step 1 come from the model after SFT

### Requirement: Train data only
A run in train mode SHALL use the split `train` for the steps and the split `validation` for the validation. A config with the split `test` SHALL stop a run in train mode before the first step.

#### Scenario: Test split in train mode
- **WHEN** the config of a run in train mode gives the split `test`
- **THEN** the run stops with an error before the first rollout

### Requirement: Validation during a run
Every `rl.eval_every` steps, the run SHALL do one greedy rollout for each of `rl.eval_tasks` validation tasks and record the score. The run SHALL keep the adapter with the best validation score.

#### Scenario: Better adapter
- **WHEN** the validation score at step 50 is higher than all earlier scores
- **THEN** the folder `best/` has the adapter of step 50

### Requirement: Checkpoints and continuation
The run SHALL write a checkpoint every `rl.save_every` steps. A checkpoint SHALL have the adapter, the optimizer state and the schedule state. It SHALL also have the step, the position in the task order and the random states. A run with `--resume` SHALL continue from a checkpoint. It SHALL stop if its config differs from the config of the checkpoint in a key other than the run length.

The run SHALL keep the adapters of all checkpoints. It SHALL keep the optimizer state only in the last `rl.keep_checkpoints` checkpoints.

#### Scenario: Adapters of a long run
- **WHEN** a run of 200 steps writes a checkpoint every 25 steps
- **THEN** the output has the adapters of all 8 checkpoints, and the optimizer state of the last 2

#### Scenario: Two jobs
- **WHEN** job 1 stops after step 25 and job 2 starts with `--resume` from the checkpoint of step 25
- **THEN** job 2 starts at step 26 with the next tasks of the same order

#### Scenario: Changed config
- **WHEN** job 2 gives another `rl.learning_rate` than the checkpoint
- **THEN** job 2 stops before the first step with an error that names the key

### Requirement: Safe stop on Kaggle
After `rl.deadline_hours`, the run SHALL start no new step, write a checkpoint and stop. An error in the run SHALL not end the process with an error code. The run SHALL write the error and its last step into `status.json` and write a checkpoint when possible.

#### Scenario: Deadline
- **WHEN** the deadline comes during step 140
- **THEN** the run finishes step 140, writes a checkpoint and records the status `deadline`

#### Scenario: Error
- **WHEN** the vLLM server stops during a step
- **THEN** `status.json` has the status `error` and the error text, and the process exits with code 0

### Requirement: Measure mode
In measure mode, the run SHALL sample `rl.group` rollouts for each of `rl.tasks` tasks without an update. It SHALL record the mean reward, the share of groups with mixed rewards, the times and the token counts. Only this mode SHALL accept the split `test`, for a cost measurement.

#### Scenario: Probe after SFT
- **WHEN** the config gives `rl.mode: measure`, the SFT adapter and the split `validation`
- **THEN** the output has the statistics of the groups, and the adapter does not change

### Requirement: Records of a run
The output folder SHALL have these files:

- `run.json`: the config, the git commit, the versions of the packages and the GPU;
- `metrics.jsonl`: one line for each step and each validation;
- `rollouts.jsonl`: one line for each rollout, without the messages;
- `status.json`: the state of the run.

The output SHALL not have the messages of the rollouts.

#### Scenario: Line of a step
- **WHEN** a step finishes
- **THEN** `metrics.jsonl` has a line with the mean reward, the share of groups with mixed rewards, the loss and the gradient norm
- **AND** the line has the share of clipped tokens, the difference of the sampler and trainer log-probabilities, and the times
