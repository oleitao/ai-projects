# Fine-Tuning Datasets

Este diretório guarda datasets JSONL para treino e avaliação de agentes com output estruturado.

## Formato recomendado

Cada linha JSON representa uma tarefa:

```json
{
  "task": "requirements_spec_v1",
  "prompt_contains": "AWS prod eu-west-1",
  "input": {
    "prompt": "texto original",
    "rag_sources": ["providers.md", "modules.md"]
  },
  "output": {
    "cloud": "aws",
    "region": "eu-west-1"
  }
}
```

Tarefas atuais:
- `requirements_spec_v1`
- `planner_design_v1`
- `generator_overrides_v1`

## Scripts

Gerar dataset a partir de jobs existentes:

```bash
python scripts/export_finetune_dataset.py --jobs-dir jobs --output datasets/finetune_train.jsonl
```

Avaliar o agente de requisitos:

```bash
python scripts/evaluate_requirements_agent.py --dataset datasets/finetune_train.jsonl
```

## Replay mode (simulação de modelo fine-tuned)

Podes usar o dataset como "modelo replay" com variáveis de ambiente:

```bash
export INFRA_AGENTS_LLM_MODE=replay
export INFRA_AGENTS_LLM_REPLAY_FILE=datasets/finetune_train.jsonl
python -m infra_agents.cli --prompt-file examples/prompt.txt --engine classic
```
