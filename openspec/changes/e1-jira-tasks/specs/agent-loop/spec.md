## MODIFIED Requirements

### Requirement: System prompt
The system prompt SHALL come from a file `prompts/system-<version>.md`. The config of a run SHALL give the version, and the run SHALL record it. A changed prompt SHALL get a new file and a new version. The prompt `v2` SHALL tell the model to use the tools, to answer in Polish, that the names of statuses, issue types and priorities are in English, that numbers are digits, and to start the answer with `ODMOWA:` when the task is not possible or not clear.

#### Scenario: Recorded prompt
- **WHEN** a run ends
- **THEN** the result of the run contains the version name of the system prompt

#### Scenario: Version of the new prompt
- **WHEN** the config of a run does not give a prompt version
- **THEN** the agent uses `prompts/system-v2.md` and records the version `v2`

#### Scenario: Unknown version
- **WHEN** the config gives the prompt version `v9` and the file `prompts/system-v9.md` does not exist
- **THEN** the run stops before the first task with an error that names the file

## REMOVED Requirements

### Requirement: Model backends
**Reason**: The model layer now has the backends, the model families and their tool-call formats.
**Migration**: See the capability `model-layer`, requirements "Backends" and "Model families".

### Requirement: Repeatable generation
**Reason**: The model layer now has the generation settings and the thinking switch.
**Migration**: See the capability `model-layer`, requirements "Repeatable generation" and "Thinking switch".
