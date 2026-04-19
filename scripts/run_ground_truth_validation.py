"""Validate Claude's annotation accuracy against the expert-labeled ground truth set.

Collects both hard labels and soft distributions (for future KL training)
so we don't need a separate annotation pass later.
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
OUT_FILE = Path("results/tables/ground_truth_validation.json")
MODEL = "claude-opus-4-6"

# hard label + full 4-class soft distribution in one call
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


def classify(client, example):
    convo = example.get("conversation") or [{"speaker": "A", "text": example["text"]}]
    last_speaker = convo[-1]["speaker"]
    formatted = "\n".join(f"Speaker {t['speaker']}: {t['text']}" for t in convo)
    prompt = (
        f"Conversation:\n{formatted}\n\n"
        f"Classify only the LAST message in the conversation (Speaker {last_speaker})."
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
    )

    if resp.stop_reason == "refusal":
        return {"label": None, "confidence": None, "distribution": None, "reasoning": None, "error": "refusal"}

    data = json.loads(resp.content[0].text)
    return {
        "label": data["label"],
        "confidence": data.get("confidence"),
        "distribution": data.get("distribution"),
        "reasoning": data.get("reasoning"),
        "error": None,
    }


def main():
    client = anthropic.Anthropic()
    examples = json.loads(DATA_FILE.read_text())

    print(f"Loaded {len(examples)} ground truth examples | Model: {MODEL}")
    print("-" * 60)

    results = []
    errors = []
    per_class = defaultdict(lambda: {"correct": 0, "total": 0, "predictions": defaultdict(int)})

    for i, ex in enumerate(examples, start=1):
        expert = ex["label"]
        pred = classify(client, ex)
        ok = pred["label"] == expert

        per_class[expert]["total"] += 1
        if pred["label"]:
            per_class[expert]["predictions"][pred["label"]] += 1
        if ok:
            per_class[expert]["correct"] += 1
        if pred["error"]:
            errors.append({"id": ex["id"], "error": pred["error"]})

        has_ctx = len(ex.get("conversation") or []) > 1
        tc = ex.get("text_classifiable", True)

        results.append({
            "id": ex["id"],
            "previous_id": ex.get("previous_id"),
            "original_id": ex.get("original_id"),
            "text": (ex["text"][:100] + "...") if len(ex["text"]) > 100 else ex["text"],
            "expert_label": expert,
            "predicted_label": pred["label"],
            "confidence": pred["confidence"],
            "distribution": pred["distribution"],
            "reasoning": pred["reasoning"],
            "has_context": has_ctx,
            "context_source": ex.get("context_source", "none"),
            "text_classifiable": tc,
            "exclusion_category": ex.get("exclusion_category"),
            "correct": ok,
        })

        tag = " [CTX]" if has_ctx else ""
        if not tc:
            tag += " [EXCL]"
        print(f"[{i}/{len(examples)}] {'OK' if ok else 'MISS'}{tag}  expert={expert:<20} pred={str(pred['label']):<20}")
        time.sleep(0.2)

    # split into text-classifiable (primary) and excluded
    tc_results = [r for r in results if r["text_classifiable"]]
    ex_results = [r for r in results if not r["text_classifiable"]]
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    tc_correct = sum(1 for r in tc_results if r["correct"])

    print("\n" + "=" * 60)
    print(f"Overall:              {correct}/{total} ({correct/total:.1%})")
    print(f"Text-classifiable:    {tc_correct}/{len(tc_results)} ({tc_correct/len(tc_results):.1%})  <- primary metric")

    # per-class on text-classifiable subset
    tc_pc = defaultdict(lambda: {"correct": 0, "total": 0, "predictions": defaultdict(int)})
    for r in tc_results:
        tc_pc[r["expert_label"]]["total"] += 1
        if r["predicted_label"]:
            tc_pc[r["expert_label"]]["predictions"][r["predicted_label"]] += 1
        if r["correct"]:
            tc_pc[r["expert_label"]]["correct"] += 1

    print(f"\n{'Class':<22} {'Accuracy':<12} {'Correct':<10} {'Total':<8}")
    print("-" * 52)
    for label in sorted(tc_pc):
        s = tc_pc[label]
        print(f"{label:<22} {s['correct']/s['total']:<12.1%} {s['correct']:<10} {s['total']:<8}")

    # confusion — only show misclassifications
    print("\nConfusion (text-classifiable):")
    for label in sorted(tc_pc):
        misses = {k: v for k, v in tc_pc[label]["predictions"].items() if k != label}
        for p, n in sorted(misses.items(), key=lambda x: -x[1]):
            print(f"  {label} -> {p}: {n}")

    # context split
    ctx_ok = sum(1 for r in results if r["has_context"] and r["correct"])
    ctx_n = sum(1 for r in results if r["has_context"])
    no_ctx_ok = sum(1 for r in results if not r["has_context"] and r["correct"])
    no_ctx_n = sum(1 for r in results if not r["has_context"])
    print(f"\nContext:  with={ctx_ok}/{ctx_n} ({ctx_ok/ctx_n:.1%})  without={no_ctx_ok}/{no_ctx_n} ({no_ctx_ok/no_ctx_n:.1%})")

    if ex_results:
        ex_ok = sum(1 for r in ex_results if r["correct"])
        print(f"Excluded: {ex_ok}/{len(ex_results)} ({ex_ok/len(ex_results):.1%})")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for e in errors:
            print(f"  {e['id']}: {e['error']}")

    # confidence thresholds (computed for json, not printed)
    threshold_stats = {}
    for t in [0.75, 0.80, 0.85, 0.90, 0.95]:
        bucket = [r for r in tc_results if r["confidence"] is not None and r["confidence"] >= t]
        n_ok = sum(1 for r in bucket if r["correct"]) if bucket else 0
        threshold_stats[str(t)] = {
            "total": len(bucket), "correct": n_ok,
            "accuracy": round(n_ok / len(bucket), 4) if bucket else 0,
        }

    # excluded breakdown by category (for json)
    ex_by_cat = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in ex_results:
        cat = r["exclusion_category"] or "unknown"
        ex_by_cat[cat]["total"] += 1
        if r["correct"]:
            ex_by_cat[cat]["correct"] += 1

    # save everything — detailed enough for any downstream analysis
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "model": MODEL,
        "full_dataset": {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else 0,
            "per_class": {
                label: {
                    "accuracy": round(s["correct"] / s["total"], 4) if s["total"] else 0,
                    "correct": s["correct"],
                    "total": s["total"],
                    "predictions": dict(s["predictions"]),
                }
                for label, s in per_class.items()
            },
        },
        "text_classifiable": {
            "total": len(tc_results),
            "correct": tc_correct,
            "accuracy": round(tc_correct / len(tc_results), 4) if tc_results else 0,
            "per_class": {
                label: {
                    "accuracy": round(s["correct"] / s["total"], 4) if s["total"] else 0,
                    "correct": s["correct"],
                    "total": s["total"],
                    "predictions": dict(s["predictions"]),
                }
                for label, s in tc_pc.items()
            },
            "confidence_thresholds": threshold_stats,
        },
        "excluded": {
            "total": len(ex_results),
            "by_category": {
                cat: {
                    "total": s["total"],
                    "correct": s["correct"],
                    "accuracy": round(s["correct"] / s["total"], 4) if s["total"] else 0,
                }
                for cat, s in ex_by_cat.items()
            },
        },
        "context_comparison": {
            "with_context": {"correct": ctx_ok, "total": ctx_n, "accuracy": round(ctx_ok / ctx_n, 4) if ctx_n else 0},
            "without_context": {"correct": no_ctx_ok, "total": no_ctx_n, "accuracy": round(no_ctx_ok / no_ctx_n, 4) if no_ctx_n else 0},
        },
        "details": results,
        "errors": errors,
    }
    OUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
