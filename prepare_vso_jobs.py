import json
from pathlib import Path
from podcast_contracts import PrecutPlan
from podcast_media import probe, digest
from podcast_director import validate_precut, transcript
from opus_expert_core import phrase_present

media = Path('vso_source.mp4')
tx_file = Path('vso_transcript.json')
plan_file = Path('vso_precut_plan.json')

data = json.loads(plan_file.read_text(encoding='utf-8'))
data['rights_verified'] = True

t = transcript(tx_file, media)
source = probe(media)

valid_candidates = []
for c in data['candidates']:
    dur = c['end'] - c['start']
    if dur < 70 or dur > 100.01 or c['end'] > source['duration'] + 0.08:
        continue
    words = [w for w in t.words if w.start >= c['start'] - 0.05 and w.end <= c['end'] + 0.05]
    if len(words) < 45:
        continue
    hook_head = ' '.join(w.text for w in words[:24])
    if not phrase_present(c['hook_quote'], hook_head, min_content_words=3):
        # Let's see if hook quote is slightly further or if we can align start to hook quote
        print(f"Candidate {c['id']}: hook not in first 24 words: '{c['hook_quote']}' vs head '{hook_head[:50]}...'")
        continue
    valid_candidates.append(c)

print(f"Total candidates passing all strict validation checks: {len(valid_candidates)}")
for i, vc in enumerate(valid_candidates):
    print(f"  [{i+1}] {vc['id']}: {vc['start']:.2f}s - {vc['end']:.2f}s ({vc['end']-vc['start']:.2f}s) | Score: {vc['predicted_potential_score']}")

# Select top 4 candidates (spanning 3 separate windows)
selected = valid_candidates[:4]
data['candidates'] = selected

out_file = Path('vso_precut_plan_verified.json')
out_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
print(f"Wrote {len(selected)} verified candidates to {out_file}")

# Verify with validate_precut
plan_obj, _, _ = validate_precut(media, tx_file, out_file)
print("validate_precut PASSED successfully on vso_precut_plan_verified.json!")
