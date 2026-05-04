import json, collections

files = {
    "public": "ecosystems/alpha/public.jsonl",
    "commons": "ecosystems/alpha/commons.jsonl",
    "evaluation": "ecosystems/alpha/evaluation.jsonl",
}
notebooks = {
    "agent-001": "ecosystems/alpha/agents/agent-001/notebook.jsonl",
    "biochem-lead": "ecosystems/alpha/agents/biochem-lead/notebook.jsonl",
    "biochem-lead-r2": "ecosystems/alpha/agents/biochem-lead-r2/notebook.jsonl",
    "psych-lead": "ecosystems/alpha/agents/psych-lead/notebook.jsonl",
    "sweng-lead": "ecosystems/alpha/agents/sweng-lead/notebook.jsonl",
}

def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip("\ufeff")
            if line and line[0] != "{":
                line = line.lstrip("abcdefghijklmnopqrstuvwxyz")
            if line:
                rows.append(json.loads(line))
    return rows

pub = load(files["public"])
event_types = collections.Counter(r["event_type"] for r in pub)
agents_pub = collections.Counter(r["agent_id"] for r in pub)
actions = [r for r in pub if r["event_type"] == "agent.decision.taken"]
top_actions = collections.Counter(r["payload"]["top_action"] for r in actions)
sub_actions = collections.Counter(r["payload"]["sub_action"] for r in actions)

print("=== public.jsonl ===")
print(f"Total events: {len(pub)}")
print(f"Event types: {json.dumps(dict(event_types.most_common()), indent=2)}")
print(f"Events per agent: {json.dumps(dict(agents_pub.most_common()), indent=2)}")
print(f"Top actions: {json.dumps(dict(top_actions.most_common()), indent=2)}")
print(f"Sub actions: {json.dumps(dict(sub_actions.most_common()), indent=2)}")

com = load(files["commons"])
commons_agents = collections.Counter(r["agent_id"] for r in com)
utterances = [r for r in com if r["event_type"] == "commons.utterance"]
print(f"\n=== commons.jsonl ===")
print(f"Total events: {len(com)}, Utterances: {len(utterances)}")
print(f"Agents: {json.dumps(dict(commons_agents.most_common()), indent=2)}")

print(f"\n=== notebooks ===")
for name, path in notebooks.items():
    nb = load(path)
    unique = len(set(r["payload"]["text"] for r in nb))
    print(f"  {name}: {len(nb)} entries, {unique} unique texts ({len(nb)-unique} dupes)")

ev = load(files["evaluation"])
print(f"\n=== evaluation.jsonl ===")
print(f"Total: {len(ev)}")
eval_types = collections.Counter(r["event_type"] for r in ev)
print(f"Types: {dict(eval_types)}")

print("\n=== KEY FINDINGS ===")
# Domain drift in biochem-lead-r2
biochem_r2 = load(notebooks["biochem-lead-r2"])
biochem_r2_unique = set(r["payload"]["text"][:80] for r in biochem_r2)
has_biochem = any("protein" in t.lower() or "biochem" in t.lower() or "enzyme" in t.lower() for t in biochem_r2_unique)
print(f"biochem-lead-r2 mentions biochemistry in notebook: {has_biochem}")
print(f"biochem-lead-r2 notebook topics (first 80 chars of unique entries):")
for t in sorted(biochem_r2_unique):
    print(f"  - {t}")
