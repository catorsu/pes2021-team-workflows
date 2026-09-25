### Call {bench_turn} — `BenchDecision`

Rank every non-starter against the frozen Starting XI duties of {preset_names}
(Slots 0–10, including Goalkeeper relief). Keep StartingXILock and all supplied
PresetPlan artifacts fixed.
Derive tactical demands from those duties before evaluating candidates. Assess
each candidate as one replacement at a time for a preset and slot, jointly across
all three frozen states; treat different preset/slot assignments as alternative deployments,
using positional familiarity, active Playing Style, execution profile, physical
attributes and stamina from the dossiers. Value direct like-for-like cover and
tactical relief serving the same frozen demand with a different execution
profile. Consolidate shared demands across the supplied presets. Rank by
descending overall priority across those demands, highest first.

Return exactly one bare JSON object with these fields in this order:
1. `Schema Version`: `"2.2"`.
2. `Artifact`: `"BenchDecision"`.
3. `Substitutes`: exactly `Total Players − 11` objects in priority order, each
   containing only `Player ID` (the exact string from PLAYER_RECORDS).

Include every unique non-starter exactly once; exclude all starters. Return an
empty array for an eleven-player squad. Do not output Demand Profile, Demands
Served, Coverage Gaps, Rationale, Reason, explanations, Markdown or other fields.
