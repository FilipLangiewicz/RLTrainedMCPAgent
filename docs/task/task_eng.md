# Semester project: a system based on an LLM

English translation of `task.md`. The original is the Polish text.

## Milestones

| Milestone | Description | Date |
|---|---|---|
| E1 – Base system | The system operates end-to-end on the selected data. For fine-tuning: base model and prompt. A test set (input and expected result) and a baseline score. | 2026-11-16 |
| E2 | For example, advanced RAG or fine-tuning. The score before and after on the same test set. | 2026-12-07 |
| E3 | For example, the model selects tools. A comparison with E2 on the same test set. | 2026-12-21 |
| Demo Day and grading meeting | A demo of the system that operates, and a meeting with the lecturer (date set for each team). | 2027-01-11 |

## What we build

- A system based on an LLM, for example RAG or a fine-tuned model.
- The team proposes the topic and the data.
- Local (Ollama for inference) or remote (API or cloud).
- Example: the RAG starter with the demo "PW study regulations". Teams can use it, but it is not necessary.

## Rules

- Team: 2 persons (maximum 3).
- Data: a data set that is applicable to the task. No personal data.
- Tools: all tools are permitted, also AI coding assistants. The team is responsible for all code and must explain it.

## Grade

- A system that operates.
- A before/after measurement on the same test set. The test set is separate from the fine-tuning data.
- An error analysis.
- A presentation and a discussion.
- A talk on Demo Day: 3 minutes of demo and 3 minutes of questions for each team.

## Evaluation

**Test set (golden set):** input and expected result.

- Prepare the test set before the improvement steps. Compare on the same version. After a change of the set, calculate all variants again.
- Different difficulties: easy, more than one source or step, out of scope (correct answer: refusal).
- RAG: also the sources (locations in the documents, not chunks).
- Fine-tuning: the test examples are separate from the training examples. Keep them aside before the training.
- Minimum at the start: manual grade (correct, incorrect, correct refusal).

**How to measure**

- One change at a time. Use the same set and keep the remaining configuration.
- Repeatability: temperature 0, if the model allows it. Record the configuration, the model version and the results.
- Transparency: a similar context budget, not the same k. Report time and cost next to quality.
- Size of the set: small differences are often noise. Find which examples changed.
- The size of the model (number of parameters) is not a variable in the grade.

> Each change needs a before/after measurement on the same test set. Without it, we do not know if the change helped.

## RAG starter

[github.com/kzbikowski/idm-rag-starter](https://github.com/kzbikowski/idm-rag-starter). It is an example, not a necessary base.
