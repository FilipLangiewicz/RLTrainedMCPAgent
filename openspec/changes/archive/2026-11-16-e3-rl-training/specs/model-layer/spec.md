# Spec Delta

## ADDED Requirements

### Requirement: LoRA adapters
The `transformers` backend SHALL accept the optional setting `model.adapters`, a list of folders with LoRA adapters. It SHALL merge the adapters into the base weights of `model.path` in the order of the list. The record of a run SHALL contain the list. Without the setting, the backend SHALL load only the base weights.

#### Scenario: Model after SFT and RL
- **WHEN** the config gives the base model and the list of the SFT adapter and the RL adapter
- **THEN** the evaluation runs the model with both adapters merged
- **AND** `metrics.json` records the two folders

#### Scenario: Adapter of another model
- **WHEN** an adapter in the list belongs to another base model
- **THEN** the run stops before the first task with an error that names the adapter
