# PES 2021 Match-Plan Builder — Contract v2.2 User Messages

<!-- [IF_MODE:multi] -->

## The application sends these five scoped requests with the companion Contract v2.2 system prompt, which defines every output contract and carries the static rule bases (`PLAYER_GLOSSARY` and `GAME_PLAN_RULES`). Each user message opens with its call-scoped data — the `PLAYER_RECORDS` extract on every call and, from Call 2 onward, `FROZEN_ARTIFACTS` — with content per call as defined in the system prompt's artifact pipeline table, and ends with the task of its call. The application replaces each `[PASTE ... HERE]` placeholder before sending.

## Call 1 — Starting-XI lock

```text
<PLAYER_RECORDS>
[PASTE PLAYER_RECORDS HERE]
</PLAYER_RECORDS>
STEP 1 OF 5 — SQUAD AUDIT, 11-DIMENSIONAL PROFILING, AND STARTING-XI SLOT LOCK
Run the three phases below internally, then return exactly the StartingXILock artifact defined in the system prompt.
PHASE 1 — POSITIONAL MATRIX AND STYLE-SUPPLY AUDIT
Analyze squad capability directly from the PRE-CALCULATED POSITIONAL SQUAD MATRIX in PLAYER_RECORDS above. Audit personnel depth across positional core and cover (GAME_PLAN_RULES III), identifying key strengths, scarcity, and Playing-Style availability. Treat Playing Style & Compatibility: None as an absent style and include the player in positional depth by familiarity (PLAYER_GLOSSARY §0).
PHASE 2 — 11-DIMENSIONAL TEAM CAPABILITY PROFILE
Evaluate the squad's tactical ceiling, physical limits, and structural constraints across exactly these eleven complementary dimensions, using relevant Abilities, Player Skills, Playing Styles, COM Playing Styles, and Traits as comparative evidence. These dimensions organize assessment; they do not prescribe mechanisms, player archetypes, or Advanced Instructions:
 1. Build-up Security — low-pressure and high-pressure circulation from the back.
 2. Direct Progression — vertical bypass, aerial outlet targets, and direct forward distribution.
 3. Central Creation — playmaking between the lines and half-space penetration into Zone 14.
 4. Width and Crossing — flank stretching, touchline speed, and delivery accuracy.
 5. Penalty-area Threat — box arrival, penalty-box instincts, aerial duels, and conversion.
 6. Attacking-transition Pace — breakout acceleration, counter-carrying threat, and transition speed.
 7. Pressing and Defensive Transition — counter-pressing intensity, immediate ball recovery, and duel engagement.
 8. Rest Defence — positional screening and defensive stability during sustained attacking phases.
 9. Goalkeeping and Distribution — shot-stopping, area coverage, and distribution range.
10. Set Pieces — aerial dominance, dead-ball threat, and physical box presence.
11. Durability and Role Flexibility — stamina maintenance, form stability, and multi-position versatility.
PHASE 3 — XI SELECTION AND SLOT ORDER
Select the Starting XI satisfying the invariants of GAME_PLAN_RULES II. Compare feasible preset constructions for the mode's required scope under GAME_PLAN_RULES VI and X before committing the lock.
Assign outfield Slots 1–10 as a labelling convention derived from your internal Main-scenario baseline allocation, using this deterministic sequence:
1. Deepest functional line to highest (e.g., CB / full-backs → DMF → CMF / wide midfielders / wingers → CF / SS).
2. Within the same functional line, order from left to right (e.g., LB → left CB → right CB → RB).
3. Break any remaining tie by ascending numeric Player ID.
Carry the locked Slot-to-player mapping forward. Determine later Position and Grid assignments from each call's scenario under GAME_PLAN_RULES II; the baseline allocation serves this call's labelling step.
```

---

## Call 2 — Main PresetPlan

```text
<PLAYER_RECORDS>
[PASTE PLAYER_RECORDS HERE]
</PLAYER_RECORDS>
<FROZEN_ARTIFACTS>
[PASTE FROZEN_ARTIFACTS HERE]
</FROZEN_ARTIFACTS>
STEP 2 OF 5 — MAIN PRESETPLAN
Design the Main preset for its scenario in GAME_PLAN_RULES II under Preset independence, using the locked Starting XI in FROZEN_ARTIFACTS above. Build it in the construction order of GAME_PLAN_RULES X: co-determine the three fluid states and the Rest Defence Contract in Step 1, apply the State Structure Checks of GAME_PLAN_RULES IV to each state's configured anchors, and enforce the contract through Steps 4 and 5. Evaluate gameplay through the coexisting tactical layers of GAME_PLAN_RULES III and IX; explain conditional movement and protection in Tactical Duty and Mechanisms. Apply the feasibility and commitment rules of GAME_PLAN_RULES X at each stage. Return exactly the PresetPlan artifact defined in the system prompt with Preset set to Main and Risk Budget set to Medium.
```

---

## Call 3 — Defensive PresetPlan

```text
<PLAYER_RECORDS>
[PASTE PLAYER_RECORDS HERE]
</PLAYER_RECORDS>
<FROZEN_ARTIFACTS>
[PASTE FROZEN_ARTIFACTS HERE]
</FROZEN_ARTIFACTS>
STEP 3 OF 5 — DEFENSIVE PRESETPLAN
Design the Defensive preset for its scenario in GAME_PLAN_RULES II under Preset independence, using the locked Starting XI in FROZEN_ARTIFACTS above. Build it in the construction order of GAME_PLAN_RULES X: co-determine the three fluid states and the Rest Defence Contract in Step 1, apply the State Structure Checks of GAME_PLAN_RULES IV to each state's configured anchors, and enforce the contract through Steps 4 and 5. Evaluate gameplay through the coexisting tactical layers of GAME_PLAN_RULES III and IX; explain conditional movement and protection in Tactical Duty and Mechanisms. Apply the feasibility and commitment rules of GAME_PLAN_RULES X at each stage. Return exactly the PresetPlan artifact defined in the system prompt with Preset set to Defensive and Risk Budget set to Low.
```

---

## Call 4 — Custom PresetPlan

```text
<PLAYER_RECORDS>
[PASTE PLAYER_RECORDS HERE]
</PLAYER_RECORDS>
<FROZEN_ARTIFACTS>
[PASTE FROZEN_ARTIFACTS HERE]
</FROZEN_ARTIFACTS>
STEP 4 OF 5 — CUSTOM PRESETPLAN
Design the Custom preset for its scenario in GAME_PLAN_RULES II under Preset independence, using the locked Starting XI in FROZEN_ARTIFACTS above. Build it in the construction order of GAME_PLAN_RULES X: co-determine the three fluid states and the Rest Defence Contract in Step 1, apply the State Structure Checks of GAME_PLAN_RULES IV to each state's configured anchors, and enforce the contract through Steps 4 and 5. Evaluate gameplay through the coexisting tactical layers of GAME_PLAN_RULES III and IX; explain conditional movement and protection in Tactical Duty and Mechanisms. Apply the feasibility and commitment rules of GAME_PLAN_RULES X at each stage. Return exactly the PresetPlan artifact defined in the system prompt with Preset set to Custom and Risk Budget set to High.
```

---

## Call 5 — BenchDecision

```text
[PASTE BENCH_USER HERE]
```

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

## The application sends these three scoped requests with the companion Contract v2.2 system prompt, which defines every output contract and carries the static rule bases (`PLAYER_GLOSSARY` and `GAME_PLAN_RULES`). Each user message opens with its call-scoped data — the `PLAYER_RECORDS` extract on every call and, from Call 2 onward, `FROZEN_ARTIFACTS` — with content per call as defined in the system prompt's artifact pipeline table, and ends with the task of its call. The application replaces each `[PASTE ... HERE]` placeholder before sending.

## Call 1 — Starting-XI lock

```text
<PLAYER_RECORDS>
[PASTE PLAYER_RECORDS HERE]
</PLAYER_RECORDS>
STEP 1 OF 3 — SQUAD AUDIT, 11-DIMENSIONAL PROFILING, AND MAIN-DEDICATED STARTING-XI SLOT LOCK
Run the three phases below internally, then return exactly the StartingXILock artifact defined in the system prompt.
PHASE 1 — POSITIONAL MATRIX AND STYLE-SUPPLY AUDIT
Analyze squad capability directly from the PRE-CALCULATED POSITIONAL SQUAD MATRIX in PLAYER_RECORDS above. Audit personnel depth across positional core and cover (GAME_PLAN_RULES III), identifying key strengths, scarcity, and Playing-Style availability. Treat Playing Style & Compatibility: None as an absent style and include the player in positional depth by familiarity (PLAYER_GLOSSARY §0).
PHASE 2 — 11-DIMENSIONAL TEAM CAPABILITY PROFILE
Evaluate the squad's tactical ceiling, physical limits, and structural constraints across exactly these eleven complementary dimensions, using relevant Abilities, Player Skills, Playing Styles, COM Playing Styles, and Traits as comparative evidence. These dimensions organize assessment; they do not prescribe mechanisms, player archetypes, or Advanced Instructions:
 1. Build-up Security — low-pressure and high-pressure circulation from the back.
 2. Direct Progression — vertical bypass, aerial outlet targets, and direct forward distribution.
 3. Central Creation — playmaking between the lines and half-space penetration into Zone 14.
 4. Width and Crossing — flank stretching, touchline speed, and delivery accuracy.
 5. Penalty-area Threat — box arrival, penalty-box instincts, aerial duels, and conversion.
 6. Attacking-transition Pace — breakout acceleration, counter-carrying threat, and transition speed.
 7. Pressing and Defensive Transition — counter-pressing intensity, immediate ball recovery, and duel engagement.
 8. Rest Defence — positional screening and defensive stability during sustained attacking phases.
 9. Goalkeeping and Distribution — shot-stopping, area coverage, and distribution range.
10. Set Pieces — aerial dominance, dead-ball threat, and physical box presence.
11. Durability and Role Flexibility — stamina maintenance, form stability, and multi-position versatility.
PHASE 3 — MAIN-DEDICATED XI SELECTION AND SLOT ORDER
Select the Starting XI exclusively to maximize the squad's natural strengths, positional familiarity, active Playing Styles, role synergy, and competitive ceiling in the sole Main system. Allocate personnel and duties to this Main objective. Satisfy the single-mode invariants of GAME_PLAN_RULES II. Compare feasible preset constructions for the mode's required scope under GAME_PLAN_RULES VI and X before committing the lock.
Assign outfield Slots 1–10 as a labelling convention derived from your internal Main core allocation, using this deterministic sequence:
1. Deepest functional line to highest (e.g., CB / full-backs → DMF → CMF / wide midfielders / wingers → CF / SS).
2. Within the same functional line, order from left to right (e.g., LB → left CB → right CB → RB).
3. Break any remaining tie by ascending numeric Player ID.
Carry the locked Slot-to-player mapping forward. Determine later Position and Grid assignments from the Main scenario under GAME_PLAN_RULES II; the core allocation serves this call's labelling step.
```

---

## Call 2 — Main PresetPlan

```text
<PLAYER_RECORDS>
[PASTE PLAYER_RECORDS HERE]
</PLAYER_RECORDS>
<FROZEN_ARTIFACTS>
[PASTE FROZEN_ARTIFACTS HERE]
</FROZEN_ARTIFACTS>
STEP 2 OF 3 — CORE MAIN PRESETPLAN
Design the sole Main preset for the core scenario in GAME_PLAN_RULES II, using the locked Starting XI in FROZEN_ARTIFACTS above. Maximize the locked XI's natural strengths, positional familiarity, active Playing Styles, role synergy, and tactical ceiling for this Main objective. Build it in the construction order of GAME_PLAN_RULES X: co-determine the three fluid states and the Rest Defence Contract in Step 1, apply the State Structure Checks of GAME_PLAN_RULES IV to each state's configured anchors, and enforce the contract through Steps 4 and 5. Evaluate gameplay through the coexisting tactical layers of GAME_PLAN_RULES III and IX; explain conditional movement and protection in Tactical Duty and Mechanisms. Apply the feasibility and commitment rules of GAME_PLAN_RULES X at each stage. Return exactly the PresetPlan artifact defined in the system prompt with Preset set to Main and Risk Budget set to Medium.
```

---

## Call 3 — BenchDecision

```text
[PASTE BENCH_USER HERE]
```

<!-- [ENDIF_MODE] -->
