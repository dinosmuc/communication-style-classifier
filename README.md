# Communication Style Classifier

NLP system for classifying text into four communication styles — **assertive**, **aggressive**, **passive**, and **passive-aggressive** — grounded in clinical psychology taxonomy.

## Communication Styles

| Style              | Description                                                        |
| ------------------ | ------------------------------------------------------------------ |
| Assertive          | Clear, respectful, direct expression of needs and boundaries       |
| Aggressive         | Hostile, dominating, disregards others' rights                     |
| Passive            | Avoids conflict, suppresses own needs, overly accommodating        |
| Passive-Aggressive | Indirectly expresses hostility through subtle, covert behaviours   |

## Project Structure

```
communication-style-classifier/
├── config/
│   ├── paths.py                       # Central path definitions
│   ├── training_config.py             # Hyperparameters for all models
│   └── annotation_config.py           # LLM annotation settings
├── data/
│   ├── raw/                           # Unprocessed downloads (gitignored)
│   ├── ground_truth/                  # Expert-labeled test set (tracked)
│   ├── annotated/                     # LLM-labeled training data (gitignored)
│   └── cleaned/                       # Final training data (gitignored)
├── src/
│   ├── collection/                    # Data loaders (HuggingFace, Arctic Shift, clinical)
│   ├── preprocessing/                 # Text cleaning, filtering, dedup, anonymization
│   ├── annotation/                    # LLM batch annotation & validation
│   ├── cleaning/                      # Cleanlab label cleaning
│   ├── training/                      # SVM, DeBERTa, RoBERTa training
│   └── evaluation/                    # Metrics, statistical tests, error analysis
├── scripts/                           # Pipeline entry points
├── notebooks/                         # EDA & visualization notebooks
├── models/                            # Saved checkpoints (gitignored)
├── results/                           # Tables, figures, logs
├── report/                            # References and report materials
├── requirements.txt
├── pyproject.toml
└── .pre-commit-config.yaml
```

## Setup

### Prerequisites

- Python 3.10+
- CUDA-capable GPU (recommended) with CUDA 11.8+ / 12.x
- ~8 GB VRAM for fine-tuning transformer models

### Installation

```bash
git clone https://github.com/dinosmuc/communication-style-classifier.git
cd communication-style-classifier

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pre-commit install
```

### Verify CUDA

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```
