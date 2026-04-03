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
├── src/                        # Source code
│   ├── data/                   #   Data loading & preprocessing
│   ├── models/                 #   Model definitions
│   ├── training/               #   Training loops & scripts
│   └── evaluation/             #   Metrics & evaluation
├── data/                       # Raw & processed datasets (gitignored)
│   ├── raw/
│   └── processed/
├── models/                     # Saved checkpoints (gitignored)
├── notebooks/                  # Exploratory Jupyter notebooks
├── configs/                    # Training & model configs
├── requirements.txt            # Pinned dependencies
├── pyproject.toml              # Ruff configuration
└── .pre-commit-config.yaml     # Pre-commit hooks
```

## Setup

### Prerequisites

- Python 3.10+
- CUDA-capable GPU (recommended) with CUDA 11.8+ / 12.x
- ~8 GB VRAM for fine-tuning transformer models

### Installation

```bash
# Clone the repository
git clone https://github.com/dinosmuc/communication-style-classifier.git
cd communication-style-classifier

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install
```

### Verify CUDA

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

