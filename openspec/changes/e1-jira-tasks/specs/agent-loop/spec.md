## MODIFIED Requirements

### Requirement: System prompt
The system prompt SHALL tell the model to use the tools, to answer the user in Polish, and to start the answer with `ODMOWA:` when the tools cannot do the task or when the request is not clear. The prompt SHALL tell the model that the names of statuses, issue types and priorities are in English, and that numbers in an answer are digits. The prompt SHALL have a version name that the run records. The new version is `v2`.

#### Scenario: Recorded prompt
- **WHEN** a run ends
- **THEN** the result of the run contains the version name of the system prompt

#### Scenario: Version of the new prompt
- **WHEN** a run uses the default prompt
- **THEN** the recorded version is `v2`
