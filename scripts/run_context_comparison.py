"""Re-run context examples without preceding turns to measure how much context helps.

Loads with-context results from the main validation run, then re-classifies
each multi-turn example as if it were single-turn. Compares both.
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.annotation.prompts import SYSTEM_PROMPT

load_dotenv()

DATA_FILE = Path("data/ground_truth/ground_truth.json")
MAIN_RESULTS = Path("results/tables/ground_truth_validation.json")
OUT_FILE = Path("results/tables/context_comparison.json")
MODEL = "claude-opus-4-6"

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "enum": ["assertive", "aggressive", "passive", "passive-aggressive"],
        },
        "confidence": {"type": "number"},
        "distribution": {
            "type": "object",
            "properties": {
                "assertive": {"type": "number"},
                "aggressive": {"type": "number"},
                "passive": {"type": "number"},
                "passive_aggressive": {"type": "number"},
            },
            "required": ["assertive", "aggressive", "passive", "passive_aggressive"],
            "additionalProperties": False,
        },
        "reasoning": {"type": "string"},
    },
    "required": ["label", "confidence", "distribution", "reasoning"],
    "additionalProperties": False,
}


def classify_no_context(client, example):
    # strip preceding turns, only feed the target message
    convo = example.get("conversation") or []
    if convo:
        speaker, text = convo[-1]["speaker"], convo[-1]["text"]
    else:
        speaker, text = "A", example["text"]

    prompt = (
        f"Conversation:\n"
        f"Speaker {speaker}: {text}\n\n"
        f"Classify only the LAST message in the conversation (Speaker {speaker})."
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
    )

    if resp.stop_reason == "refusal":
        return {"label": None, "confidence": None, "distribution": None, "error": "refusal"}

    data = json.loads(resp.content[0].text)
    return {
        "label": data["label"],
        "confidence": data.get("confidence"),
        "distribution": data.get("distribution"),
        "error": None,
    }


def main():
    if not MAIN_RESULTS.exists():
        print(f"ERROR: Run run_ground_truth_validation.py first ({MAIN_RESULTS} not found)")
        sys.exit(1)

    client = anthropic.Anthropic()
    examples = json.loads(DATA_FILE.read_text())
    main_data = json.loads(MAIN_RESULTS.read_text())
    main_by_id = {r["id"]: r for r in main_data["details"]}

    # only examples that had multi-turn context in the original run
    ctx_examples = [e for e in examples if len(e.get("conversation") or []) > 1]
    print(f"Found {len(ctx_examples)} examples with context | Model: {MODEL}")
    print("Re-classifying without context...")
    print("-" * 70)

    comparisons = []
    with_n, without_n = 0, 0
    both, only_with, only_without, neither = 0, 0, 0, 0
    per_class = defaultdict(lambda: {"total": 0, "with_ctx_correct": 0, "without_ctx_correct": 0})

    for i, ex in enumerate(ctx_examples, start=1):
        expert = ex["label"]
        prior = main_by_id.get(ex["id"])
        if not prior:
            print(f"  WARNING: {ex['id']} not in main results, skipping")
            continue

        with_ok = prior["correct"]
        wo = classify_no_context(client, ex)
        without_ok = wo["label"] == expert

        # track agreement buckets
        if with_ok:
            with_n += 1
        if without_ok:
            without_n += 1
        if with_ok and without_ok:
            both += 1
        elif with_ok:
            only_with += 1
        elif without_ok:
            only_without += 1
        else:
            neither += 1

        per_class[expert]["total"] += 1
        if with_ok:
            per_class[expert]["with_ctx_correct"] += 1
        if without_ok:
            per_class[expert]["without_ctx_correct"] += 1

        comparisons.append({
            "id": ex["id"],
            "text": (ex["text"][:80] + "...") if len(ex["text"]) > 80 else ex["text"],
            "expert_label": expert,
            "with_context": {
                "predicted": prior["predicted_label"],
                "confidence": prior["confidence"],
                "distribution": prior.get("distribution"),
                "correct": with_ok,
            },
            "without_context": {
                "predicted": wo["label"],
                "confidence": wo["confidence"],
                "distribution": wo["distribution"],
                "correct": without_ok,
            },
            "context_helped": with_ok and not without_ok,
            "context_hurt": without_ok and not with_ok,
        })

        # progress line
        delta = ""
        if with_ok and not without_ok:
            delta = " <- HELPED"
        elif without_ok and not with_ok:
            delta = " <- HURT"
        w_cell = f"{'OK' if with_ok else 'MISS':<4} {str(prior['predicted_label']):<20}"
        n_cell = f"{'OK' if without_ok else 'MISS':<4} {str(wo['label']):<20}"
        print(f"[{i}/{len(ctx_examples)}] expert={expert:<20} ctx={w_cell} no_ctx={n_cell}{delta}")
        time.sleep(0.2)

    total = len(comparisons)
    with_acc = with_n / total if total else 0
    without_acc = without_n / total if total else 0
    diff = with_acc - without_acc

    print("\n" + "=" * 60)
    print(f"With context:    {with_n}/{total} ({with_acc:.1%})")
    print(f"Without context: {without_n}/{total} ({without_acc:.1%})")
    print(f"Delta:           {diff:+.1%}")
    print(f"\n  Both correct: {both}  |  Only with ctx: {only_with}  |  Only without: {only_without}  |  Neither: {neither}")

    print(f"\n{'Class':<22} {'With':<12} {'Without':<12} {'Delta':<10}")
    print("-" * 56)
    for label in sorted(per_class):
        s = per_class[label]
        if s["total"]:
            w = s["with_ctx_correct"] / s["total"]
            wo = s["without_ctx_correct"] / s["total"]
            print(f"{label:<22} {w:<12.1%} {wo:<12.1%} {(w - wo):+.1%}")

    # show specific examples that flipped
    for tag, flag in [("HELPED", "context_helped"), ("HURT", "context_hurt")]:
        flipped = [c for c in comparisons if c[flag]]
        if flipped:
            print(f"\nContext {tag} ({len(flipped)}):")
            for c in flipped:
                w = c["with_context"]["predicted"]
                n = c["without_context"]["predicted"]
                print(f"  {c['id']}: expert={c['expert_label']}  ctx={w}  no_ctx={n}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "model": MODEL,
        "total": total,
        "with_context": {"correct": with_n, "accuracy": round(with_acc, 4)},
        "without_context": {"correct": without_n, "accuracy": round(without_acc, 4)},
        "delta": round(diff, 4),
        "breakdown": {
            "both_correct": both,
            "only_with_context_correct": only_with,
            "only_without_context_correct": only_without,
            "neither_correct": neither,
        },
        "per_class": {
            label: {
                "total": s["total"],
                "with_context_correct": s["with_ctx_correct"],
                "without_context_correct": s["without_ctx_correct"],
                "with_context_accuracy": round(s["with_ctx_correct"] / s["total"], 4) if s["total"] else 0,
                "without_context_accuracy": round(s["without_ctx_correct"] / s["total"], 4) if s["total"] else 0,
            }
            for label, s in per_class.items()
        },
        "comparisons": comparisons,
    }
    OUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
