# PES 2021 Tactical Game-Plan Rules — Contract v2.2

This document is the single home of tactical semantics: what each decision means and how decisions are chosen and ordered.

Routine set-piece takers are derived downstream. Leave at least one Main Normal defender or midfielder outside the union of Players to Join Attack selections across active presets so LongFK has an eligible taker.

## I. Constraint priority

Apply decisions in this order:

<!-- [IF_MODE:multi] -->

1. exact identity, legal vocabulary, schema validity, and injectability;
2. the shared Starting-XI and Slot invariants (Section II);
3. scenario objective, tactical function, and position assignment (Section III);
4. the preset's Rest Defence Contract (Section VIII);
5. spatial topology, the State Structure Checks, and macro phase-state structural transformation (Section IV);
6. Advanced Instruction live modifiers and Playing-Style activation (Section VI);
7. Players to Join Attack selection for attacking set pieces and maximum attacking mentality (constrained by item 4 and independent of item 6; Section VIII);
8. formation-label aesthetics and bilateral symmetry.

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

1. exact identity, legal vocabulary, schema validity, and injectability;
2. the Main-dedicated Starting-XI and Slot invariants (Section II);
3. scenario objective, tactical function, and position assignment (Section III);
4. the preset's Rest Defence Contract (Section VIII);
5. spatial topology, the State Structure Checks, and macro phase-state structural transformation (Section IV);
6. Advanced Instruction live modifiers and Playing-Style activation (Section VI);
7. Players to Join Attack selection for attacking set pieces and maximum attacking mentality (constrained by item 4 and independent of item 6; Section VIII);
8. formation-label aesthetics and bilateral symmetry.

<!-- [ENDIF_MODE] -->

Items 1–4 are hard constraints. The State Structure Checks in item 5 are mandatory validity checks; the remaining choices in items 5–8 optimize among configurations satisfying those checks and the hard constraints. Item 8 is the lowest priority: bilateral symmetry is an aesthetic tie-breaker among otherwise equal solutions, never a requirement and never a check (Section IV).

### Domain Grounding & Tactical First Principles

Rules provide structural invariants, not exhaustive edge-case enumerations. Any tactical configuration fundamentally violating professional football logic is strictly invalid.

When encountering unhandled edge cases, rule ambiguities, empty candidate pools, or soft-constraint conflicts:

1. **Sanity Floor:** Anchor all decisions in real-world football viability — maintain defensive spatial continuity, logical passing distances, and physical role plausibility.
2. **Graceful Fallback:** Prefer structural integrity, defensive continuity, and natural role plausibility over forced positional assignments.
3. **Intent over Exploitation:** Resolve edge cases to fulfill the scenario's tactical spirit without exploiting literal rule omissions.
4. **Illustrative Non-Prescriptiveness:** All tactical formations, phase-state transformations, grid coordinates, and player archetypes presented in tables, diagrams, or examples — including the Illustrative Baselines of Section IV — are purely pedagogical syntax illustrations, never default templates, quality benchmarks, or preferred solutions. Derive all tactical systems, shapes, and duties organically and exclusively from the active squad's concrete capabilities and scenario demands.

<!-- [IF_MODE:multi] -->

## II. Scenarios and the shared Starting XI

### Presets and scenarios

A game plan contains three presets, each defined by its scenario objective and Risk Budget:

| Preset      | Scenario                                                                                                                                                                                                                                              | Risk Budget |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `Main`      | Opening phase or ordinary competitive play at level score between evenly matched opponents. Build the flagship, opponent-neutral plan without deficit chasing or extreme lead protection.                                                             | `Medium`    |
| `Defensive` | Protect a narrow lead from the middle of the second half to the closing minutes while the opponent commits players forward. Deny comeback routes, minimize defensive exposure, manage possession and territory intelligently, close the match safely. | `Low`       |
| `Custom`    | Chase a deficit in the second half of a match where standard approaches need adaptation. Prioritize attacking momentum, final-third overloads, and direct goal creation under a higher risk budget.                                                   | `High`      |

Risk Budget defines the transition exposure a preset accepts within the boundary of all hard constraints. A preset's `Risk Budget` field must equal its value in this table.

### The shared Starting XI and Slots

All three presets use the exact same eleven player identities in the same permanent Slot order 0–10. Slot 0 is the goalkeeper (Level 1 or Level 2 at `GK`); Slots 1–10 are the ten outfielders.

Slot 0 uses Row 0, `C_Center`, and `GK` in every state of every preset.

The Starting XI must simultaneously satisfy all three scenarios without substitution. Outfielder roles prioritize Level-2 and Level-1 positions for baseline duties, while Level-0 assignments are fully legitimate across any state whenever required by tactical necessity (Section III).

**Slot Immutability & Positional Independence:** Slot order is established once during the Starting-XI lock and remains globally immutable across all artifacts. The lock numbers outfield Slots by a labelling convention (deepest functional line to highest, left to right, remaining ties by ascending numeric Player ID); the baseline allocation behind that convention is not transmitted to later calls and creates no positional obligation. A Slot is purely an abstract identity handle: each preset and fluid state positions every outfield Slot independently on the grid (Rows 1–9, any Lane), with no requirement for Slot numerical order to reflect spatial depth in any preset or state.

**State Array Ordering Invariant:** In all state arrays (`Normal`, `With Ball`, `Without Ball`), objects must strictly be emitted by ascending Slot index ($0 \to 10$, where array index $k$ is always Slot $k$). Never re-order array elements to follow spatial depth or tactical lines.

### Preset independence

Each preset independently defines its three states, Rest Defence Contract, Basic Instructions, Advanced Instructions, Players to Join Attack, and Auto Offside Trap using solely the locked XI, player dossiers, reference documents, and its own scenario objective. Preset decisions are frozen once generated; the Bench call evaluates the squad's non-starters against the objective tactical demands of the frozen Starting XI (Slots 0–10, including Goalkeeper relief), providing direct cover (like-for-like succession) or tactical relief (the same frozen demand served with a materially different execution profile) across all three presets without amending the frozen systems.

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

## II. Core scenario and the Main-dedicated Starting XI

### Core preset and scenario

A game plan contains exactly one authored preset, defined by its core objective and single Risk Budget:

| Preset | Scenario                                                                                                                                                                                                                                       | Risk Budget |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `Main` | The sole flagship system used throughout the match. Maximize the squad's natural strengths, familiar Playing Styles, role synergy, and absolute competitive ceiling without reserving personnel or mechanisms for alternate situational plans. | `Medium`    |

Risk Budget defines the balanced transition exposure accepted by the core system within the boundary of all hard constraints. It is not a compromise between alternate scenarios. The preset's `Risk Budget` field is always `Medium`.

### The Main-dedicated Starting XI and Slots

The `Main` preset uses exactly eleven player identities in permanent Slot order 0–10. Slot 0 is the goalkeeper (Level 1 or Level 2 at `GK`); Slots 1–10 are the ten outfielders.

Slot 0 uses Row 0, `C_Center`, and `GK` in every state.

Select the Starting XI exclusively to optimize the `Main` system. Do not reserve a player, weaken a duty, or introduce a structural trade-off for any alternate situational setup. Outfielder roles prioritize Level-2 and Level-1 positions for baseline duties, while Level-0 assignments are fully legitimate across any state whenever required by tactical necessity (Section III).

**Slot Immutability & Positional Independence:** Slot order is established once during the Starting-XI lock and remains globally immutable across all artifacts. The lock numbers outfield Slots by a labelling convention (deepest functional line to highest, left to right, remaining ties by ascending numeric Player ID); the baseline allocation behind that convention is not transmitted to later calls and creates no positional obligation. A Slot is purely an abstract identity handle: each fluid state positions every outfield Slot independently on the grid (Rows 1–9, any Lane), with no requirement for Slot numerical order to reflect spatial depth in any state.

**State Array Ordering Invariant:** In all state arrays (`Normal`, `With Ball`, `Without Ball`), objects must strictly be emitted by ascending Slot index ($0 \to 10$, where array index $k$ is always Slot $k$). Never re-order array elements to follow spatial depth or tactical lines.

### Core-preset specialization

The `Main` preset defines its three states, Rest Defence Contract, Basic Instructions, Advanced Instructions, Players to Join Attack, and Auto Offside Trap using solely the locked XI, player dossiers, reference documents, and core objective. Its decisions are frozen once generated; the Bench call evaluates the squad's non-starters against the objective tactical demands of the frozen Starting XI (Slots 0–10, including Goalkeeper relief), providing direct cover (like-for-like succession) or tactical relief (the same frozen `Main` demand served with a materially different execution profile) for the sole flagship system without amending the frozen preset. Relief never introduces a demand that does not originate in a frozen `Main` duty.

<!-- [ENDIF_MODE] -->

## III. Fluid states, Positions, familiarity, and Playing Styles

Every preset has three complete eleven-player states:

* `Normal`: the coherent baseline kick-off, settled open-play, and general possession-distribution structure;
* `With Ball`: the in-possession macro-structural attacking shape and optimal advanced baseline coordinates;
* `Without Ball`: the out-of-possession macro-structural defensive block shape and optimal screening coordinates.

Fluid states govern whole-team structural metamorphosis between phases (e.g., base 4-3-3 transforming into in-possession 3-2-4-1 and out-of-possession 4-4-2 mid-block). States may share identical Positions and Grids or transform structurally between phases when supported by each Slot's `Tactical Duty`.

The legal Position codes are `GK`, `CB`, `LB`, `RB`, `DMF`, `CMF`, `LMF`, `RMF`, `AMF`, `LWF`, `RWF`, `SS`, and `CF`. Slot 0 is the sole goalkeeper in every state and always uses `GK` on Row 0, `C_Center`.

### Familiarity and Tactical Role Assignment

* **Level 2 (Natural Core) & Level 1 (Usable Cover):** The primary baseline for Starting-XI personnel selection and overall capability evaluation.
* **Level 0 (Tactical Necessity in Fluid States):** Assigning a Level-0 Position code in any state is completely normal, valid, and encouraged whenever dictated by tactical structure — such as maintaining defensive block continuity (e.g., an `LWF` assigned `LMF` in `Without Ball` to complete a flat midfield bank), asymmetric overloads, or phase-specific duties. State the structural rationale and expected tactical consequence in `Tactical Duty`.

### Tactical layers

Evaluate each Slot in each state through its assigned Position, positional familiarity, Grid anchor, active Playing Style, execution profile, and applicable instructions. Apply the existing configuration rules to determine eligibility. Resolve style activation from Position compatibility and use familiarity to assess suitability. Interpret expected behavior through the combined configuration. Apply documented precedence within the specific behavior and condition it governs.

| Component                                                | Operational responsibility                                                                                                                  |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Assigned Position                                        | Establish the configured role and determine Playing Style activation through the compatibility table.                                       |
| Positional familiarity                                   | Assess suitability at the assigned Position using Level 2, Level 1, or Level 0. Apply existing selection and fluid-state eligibility rules. |
| Grid anchor                                              | Establish the player's nominal placement in the current phase structure.                                                                    |
| Active Playing Style                                     | Supply the documented autonomous movement tendency at the assigned Position.                                                                |
| Abilities, Player Skills, COM Playing Styles, and Traits | Assess execution capability, documented skill effects, AI tendencies, and durability.                                                       |
| Team settings and Advanced Instructions                  | Apply their documented effects to the relevant players, behaviors, and conditions.                                                          |

Resolve an active Playing Style separately in each state. A carried style activates at every compatible Position, including compatible Level-0 assignments. At an incompatible Position, the carried style is dormant. For a dossier marked `Playing Style & Compatibility: None`, assess behavior from the remaining applicable layers. For comparisons, treat both dormant styles and `None` dossiers as an absent active Playing Style; two such absences match.

Assess tactical suitability from the complete dossier and combined configuration. Use glossary ranges to validate values and comparative evidence to explain role fit.

### Position and Grid

Position and Grid are co-determined structural decisions (Section X, Step 1):

* Position establishes the configured tactical role and determines Playing-Style activation through PLAYER_GLOSSARY §1.
* Grid establishes the player's phase-specific structural anchor within the state's configured formation (Section IV).
* Change Grid without changing Position when the configured role remains the same but its nominal phase placement changes.
* Change Position when the configured tactical role changes, while independently assessing the familiarity and Playing-Style consequences of that assignment.
* Always assign the Position code that accurately reflects the player's configured tactical function in that state.

### Playing Styles, Player Skills, COM Playing Styles, Abilities, and Traits as evidence

Playing Styles, Player Skills, COM Playing Styles, Abilities, and Traits constitute immutable dossier evidence:

* **Playing-Style activation:** Resolve activation exclusively from the assigned Position and PLAYER_GLOSSARY §1. Familiarity Levels and Grid coordinates do not determine activation.
* **Dormant style:** A carried Playing Style is dormant at an incompatible Position. Its documented movement tendency is not active there, while the remaining applicable layers still govern expected behavior.
* **Absent style:** A dossier reading `Playing Style & Compatibility: None` carries no Playing Style. Assess its configured behavior through Position, Grid, Abilities, Player Skills, COM Playing Styles, Traits, and applicable team settings and instructions.
* **Behavioral interpretation:** Explain expected movement and execution through the layers that actually apply. Attribute a documented style tendency to the active Playing Style when compatible; apply Player Skills and COM Playing Styles within their documented scopes; use Abilities and Traits as comparative execution and durability evidence; and identify team-setting or Advanced-Instruction effects when they are relevant.
* **Combined configuration:** Do not choose an unnatural Position solely to activate or suppress a Playing Style. Tactical function and structural suitability govern the assignment, with the active or absent style state forming part of the resulting tactical interpretation.

## IV. Semantic grid

Interpret each Grid coordinate as the player's phase-specific structural anchor: the nominal position within that state's formation. Use the anchor to assess spacing, line membership, support relationships, and configured coverage. On a phase change, use the new state's anchor as the positional reference for expected repositioning. Describe the timing and destinations of individual runs, overlaps, recoveries, and support movements in `Tactical Duty`, using the current situation and combined tactical layers.

The grid uses depth bands across the 105m pitch length and lateral channels:

| Row | Pitch Depth Range (X) | Pitch Zone Description                                    |
| :-- | :-------------------- | :-------------------------------------------------------- |
| `0` | 0m – 7m               | Own Goal Area & Goal Line (Goalkeeper only)               |
| `1` | 7m – 17m              | Own Penalty Area Interior                                 |
| `2` | 17m – 27m             | Own Defensive Third, from the Penalty-Area Edge Outward   |
| `3` | 27m – 37m             | Own Defensive-Third Exit & Deep Midfield                  |
| `4` | 37m – 47m             | Own Midfield Sector (Pre-Halfway)                         |
| `5` | 47m – 58m             | Central Halfway Band                                      |
| `6` | 58m – 68m             | Opponent Midfield Sector (Post-Halfway)                   |
| `7` | 68m – 78m             | Opponent Advanced Midfield Sector                         |
| `8` | 78m – 88m             | Opponent Final-Third Entry, Down to the Penalty-Area Edge |
| `9` | 88m – 105m            | Opponent Penalty Area to Goal Line                        |

*Notes: Row 0 is strictly restricted to the Goalkeeper (`GK` at `C_Center`); outfield players must be assigned to Rows 1–9. Rows 2–7 mirror pairwise around the halfway line (Row r ↔ Row 9 − r); the own end is split into Rows 0 and 1 to give the goalkeeper a dedicated row, so Row 9 mirrors Rows 0 and 1 together. Zone descriptions are orientation aids; the depth ranges are normative.*

The legal Lanes, from left to right in the team's attacking direction, are `L_Wing`, `L_Half`, `L_Center`, `C_Center`, `R_Center`, `R_Half`, and `R_Wing`.

Co-occupation is expressed by assigning multiple players to the same semantic cell. When lateral separation is tactically material, assign distinct cells.

Apply structural checks to the configured anchors in each state. Explain expected movement and resulting exposure separately in `Tactical Duty` and `Mechanisms`.

For each duty, identify its structural role, relevant movement tendency, situational trigger, and support or coverage relationship. Distinguish the configured allocation from the behavior expected while play develops.

### 7-Lane Geometry & Modern Spatial Topology

Tactical lines across all fluid states (`Normal`, `With Ball`, `Without Ball`) must balance spatial coverage, passing continuity, and genuine football logic. Bilateral symmetry is only a natural resting reference for flat shapes: it is never verified, and asymmetry is fully valid whenever tactical purpose supports it (Section I, item 8).

* **Illustrative Baselines (reference only — never defaults, benchmarks, or checks):**

  * *Conventional Symmetrical Units:* Flat structures naturally utilize central anchoring (`C_Center` for lone strikers, single pivots, central CBs) or mirrored pairs (`L_Center`+`R_Center` for double pivots, 2-CB lines) to ensure equidistant field coverage.
  * *Interlocking Passing Triangles:* Adjacent vertical lines stagger lane distribution (e.g., double pivots at `L_Center`+`R_Center` occupying the seams of a 3-CB base at `L_Half`–`C_Center`–`R_Half`) to prevent redundant stacking unless constructing a deliberate overload.
* **Modern Functional Topology & Tactical Primacy:**

  * *Tactical Function over Mechanical Line-Counting:* Modern football structures (e.g., 3-2-4-1 box midfields, inverted wingers, asymmetric overloads, or hybrid fullbacks) explicitly supersede rigid odd/even lateral formulas; line counts and odd/even lateral balance are never constraints.
  * *Central-Axis Playmaking Freedom:* Key creators (`AMF`/`SS`) or screening anchors may freely occupy `C_Center` (Zone 14 / central spine) within *any* line configuration — including 4-player attacking fronts or asymmetric units — whenever dictated by their tactical role.
  * *Spatial Continuity Principle:* Deliberate structural asymmetries (such as anchoring width on one flank while overloading the opposite half-space) are fully valid and encouraged, provided the rest-defence and midfield transition structures maintain logical passing distances and prevent unhedged chasms.

### State Structure Checks

These three checks are the only structural checks applied to a state. Apply all three to `Normal`, `With Ball`, and `Without Ball` (Section X, Step 1), evaluating the configured Position-and-Grid anchors:

1. **Lane coverage:** the deepest outfield line and the midfield line of the state leave no unhedged lateral chasm; any Lane deliberately left open is covered by a named Slot's shifting responsibility stated in its `Tactical Duty`.
2. **Passing-triangle continuity:** adjacent vertical lines are staggered or otherwise offer diagonal passing options; identical lane stacking across adjacent lines occurs only as a deliberate overload stated in `Tactical Duty`.
3. **Spatial continuity:** logical passing distances between lines, and a rest-defence and midfield transition structure that honors the preset's Rest Defence Contract (Section VIII).

Symmetry, line-counting, and odd/even lateral balance are not checks.

## V. Basic Instructions

<!-- [IF_MODE:multi] -->

Each preset independently chooses these twelve settings in order, calibrated to dynamic tendencies around the state baseline structure (Section X, Step 3). The backtick-quoted labels (1–12) are the exact, immutable JSON key literals:

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

The `Main` preset chooses these twelve settings in order, calibrated to dynamic tendencies around the state baseline structure (Section X, Step 3). The backtick-quoted labels (1–12) are the exact, immutable JSON key literals:

<!-- [ENDIF_MODE] -->

### Attacking settings

1. `Attacking Style`: `Possession Game` / `Counter Attack`
2. `Build Up`: `Short-pass` / `Long-pass`
3. `Attacking Area`: `Center` / `Wide`
4. `Positioning`: `Maintain Formation` / `Flexible`
5. `Support Range`: Integer 1 through 10 (higher spreads support options farther dynamically).
6. `Numbers in Attack`: `Few` / `Medium` / `Many`

### Defensive settings

7. `Defensive Style`: `Frontline Pressure` / `All-out Defence`
8. `Containment Area`: `Center` / `Wide`
9. `Pressuring`: `Aggressive` / `Conservative`
10. `Defensive Line`: Integer 1 through 10 (higher positions the pressing line farther upfield).
11. `Compactness`: Integer 1 through 10 (higher narrows defensive shape).
12. `Numbers in Defence`: `Few` / `Medium` / `Many`

Slider values (1–10) operate independently of grid Rows and Lanes.

## VI. Advanced Instructions

<!-- [IF_MODE:multi] -->

Each preset has two Attacking slots and two Defending slots. Team-wide instructions cannot be duplicated within the same slot family. Player-specific instructions (`Anchoring`, `Defensive`, `Counter Target`) bind to exactly one starting outfielder per slot, and **may be assigned across multiple slots within the same family to target different outfielders**. No single player may be assigned the same instruction more than once.

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

The `Main` preset has two Attacking slots and two Defending slots. Team-wide instructions cannot be duplicated within the same slot family. Player-specific instructions (`Anchoring`, `Defensive`, `Counter Target`) bind to exactly one starting outfielder per slot, and **may be assigned across multiple slots within the same family to target different outfielders**. No single player may be assigned the same instruction more than once.

<!-- [ENDIF_MODE] -->

### Attacking-slot instructions

* **False Winger:** Wingers or wide midfielders move centrally; the same-side full-back advances into vacated width.
* **Hug the Touchline:** The team expands toward both touchlines to stretch the opposition.
* **Attacking Full Backs:** Both full-backs advance while midfielders cover and wingers move centrally.
* **Wing Rotation:** A teammate supports the ball carrier near the touchline while others attack the created space.
* **Tiki-Taka:** Players prioritize possession support and rarely run behind the defence.
* **False No. 9:** The center forward drops toward midfield while teammates attack the vacated space.
* **Centring Targets:** Strikers position themselves to attack crosses when a winger receives the ball.
* **False Full Backs:** Full-backs move into midfield to create a central numerical advantage.
* **Anchoring:** Designated outfielder holds channel without horizontal drift.
* **Defensive:** Designated outfielder refrains from advancing during possession to preserve rest defence. The designated player must not use `CF` or `SS` in any of the three fluid states.

### Defending-slot instructions

* **Wingback:** Wide midfielders or wingers drop to provide defensive cover.
* **Gegenpressing:** Multiple players press immediately after possession loss; consumes substantial stamina.
* **Deep Defensive Line:** Defensive line drops to protect against through balls.
* **Swarm the Box:** Players crowd the penalty area against flank attacks.
* **Counter Target:** Designated starting outfielder remains advanced during defending phases to conserve stamina. The instruction supplies the documented defensive-tracking exemption. The designated player must not use `CB` in any of the three fluid states. Assess tactical suitability among eligible starting outfielders under the common selection criteria below.

### Instruction budget and contribution assessment

Identify the tactical requirement and its relevant conditions from the scenario, squad evidence, and inherited commitments before evaluating an instruction. Apply the same criteria to every legal instruction and target assignment; instruction names, catalogue order, and illustrative mentions provide no selection evidence.

Compare the configuration with and without each candidate assignment, accounting for the other applicable layers and interactions with other candidate instructions across all three states. Assess the documented additional effect, execution demands, conflicts, and exposure under the intended conditions. During lookahead, also compare alternatives in decisions that remain editable (Section X). Treat another layer as adequate support only when it serves the same tactical requirement under those conditions; neither an anchor nor a movement tendency alone proves sufficiency or insufficiency.

### Selection threshold and unused slots

Select an assignment only when its documented effect is necessary to satisfy a hard requirement or provides material net benefit toward the preset's objective beyond the support supplied by the remaining configuration. A material benefit must identify an expected improvement in an actual tactical requirement under the intended conditions, supported by dossier and configuration evidence; restating an instruction's definition is insufficient.

Legal eligibility, procedural uniqueness, an active or absent Playing Style, a conflicting movement tendency, and nominal placement do not independently establish selection merit. Evaluate assignments in combination so that complementary effects, redundant effects, and conflicts receive the same treatment for every instruction.

Use `"Blank"` with `Designated Slot: null` for each unneeded slot. Do not fill the instruction budget automatically or reject a materially beneficial assignment solely to minimize occupied slots.

### Instruction contention and arbitration priority

The two-slot limit applies separately to Attacking and Defending assignments. Each player-specific instruction paired with a distinct designated Slot is an independent candidate, subject to the duplication rules above. Compare complete instruction combinations, including unfilled slots, while accounting for interactions within and across both families. Apply this priority order:

1. **Tier 1 — Hard-constraint feasibility:** Admit only combinations satisfying every committed hard requirement within both slot limits. An instruction is necessary only when removing it from the evaluated combination would leave a hard requirement unsupported by the remaining configuration. Compare feasible alternatives rather than assuming that a necessary effect has only one implementation; never prune an essential effect and accept a hard-constraint violation.
2. **Tier 2 — Scenario contribution:** Among feasible combinations, compare their documented net contribution to the preset's objective under its Risk Budget, including combined effects, execution demands, and residual exposure. Apply the preset-specific tie-breaker below when these contributions are otherwise comparable.
3. **Tier 3 — Non-redundant selection:** Among combinations otherwise equivalent after Tier 2, prefer fewer occupied slots. Remaining ties confer no preference based on instruction identity or catalogue order; either equivalent combination is valid.

No instruction or category of effect has an intrinsic priority tier. Determine necessity and tactical value from the evaluated configuration, not from a mechanism label. If no feasible combination exists, the current candidate cannot be committed; revise still-editable decisions under Section X rather than relaxing a hard requirement.

<!-- [IF_MODE:multi] -->

**Tie-Breaker:** Within Tier 2, compare otherwise comparable feasible combinations against the preset's Risk Budget: `Low` (`Defensive`) prioritizes risk reduction; `Medium` (`Main`) prioritizes structural balance and the locked XI's natural strengths; `High` (`Custom`) prioritizes chance volume.

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

**Tie-Breaker:** Within Tier 2, compare otherwise comparable feasible combinations against the `Main` preset's `Medium` Risk Budget: prioritize structural balance and the locked XI's natural strengths.

<!-- [ENDIF_MODE] -->

## VII. Preset-local Auto Offside Trap

<!-- [IF_MODE:multi] -->

Each preset independently sets `Auto Offside Trap` to `On` or `Off` (Section X, Step 6).

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

The `Main` preset sets `Auto Offside Trap` to `On` or `Off` (Section X, Step 6).

<!-- [ENDIF_MODE] -->

* Evaluate Defensive Awareness of the intended last defensive line as primary coordination evidence.
* Evaluate Speed/Acceleration of defenders and goalkeeper sweeping style (`Offensive Goalkeeper`) as recovery evidence.
* Choose `On` when high line height, aggressive pressing, and defensive coordination support synchronized stepping. Choose `Off` for deep lines, conservative pressing, or recovery pace deficits.

## VIII. Rest Defence Contract and Players to Join Attack

Establish the Rest Defence Contract together with the three fluid states in Step 1. Derive the required retained protection from the scenario and squad evidence and express it through the contract's existing fields. Assess how anchors, duties, active Playing Styles, execution profiles, and available instructions support that allocation during possession and transition. Explain relevant forward movements, compensating cover, and residual exposure in the existing rationale fields.

Carry the committed contract into Steps 4 and 5. Select compatible settings and assess any instruction contribution under the common criteria of Section VI. Use State Structure Checks to verify the anchor allocation and `Mechanisms` to explain the expected dynamic support for it.

`Players to Join Attack` is populated in Step 5, after Advanced Instructions.

### Rest Defence Contract

* `Retained Protector Slots`: non-empty array of distinct outfield Slots (1–10) designated as the primary rest-defence unit for open-play depth coverage, defensive transition containment, aerial safety, or second-ball screening during attacking phases.
* `Minimum Retained`: integer from 1 to the length of `Retained Protector Slots` — the mandatory minimum number of protectors that must remain allocated to defensive depth and protection during open-play attacks, attacking set pieces, and maximum attacking mentality. The protectors who remain for the set-piece/maximum-mentality calculation are exactly the members of `Retained Protector Slots` not listed in `Players to Join Attack`. Calibrate the floor to the preset's Risk Budget; it can never exceed the array length:

<!-- [IF_MODE:multi] -->

* `Low` (Defensive): Maximum structural stability; almost all or the entire designated protector unit holds (typically the array length or the array length − 1).
* `Medium` (Main): Balanced structural security; preserves a dependable central/depth spine (typically 2 to 3 protectors, capped by the array length) while leaving a structural buffer for auxiliary players or designated aerial threats to join attacks.
* `High` (Custom): Streamlined floor; retains a compact rest-defence base (typically 1 or 2 protectors) while allowing greater forward commitment.

<!-- [ENDIF_MODE] -->

<!-- [IF_MODE:single] -->

* `Medium` (Main): Balanced structural security; preserves a dependable central/depth spine (typically 2 to 3 protectors, capped by the array length) while leaving a structural buffer for designated aerial threats to join attacks.

<!-- [ENDIF_MODE] -->

### What the contract binds

1. **`With Ball` structure (Step 1):** every Retained Protector Slot's `With Ball` Position and Grid must form part of the configured rear structure or screening allocation, and its `Tactical Duty` must state that structural responsibility together with expected conditional movement and coverage.
2. **Combined tactical support (Steps 1–4):** assess each Retained Protector Slot through its anchor, duty, active Playing Style, execution profile, Basic Instructions, and any applicable Advanced Instruction. The combined configuration must support the committed retention requirement. Evaluate collective coverage under the intended conditions: protector membership does not by itself require individual immobility, and conditional movement is permitted only while the required retained protection is maintained. If support is insufficient, compare alternatives in the still-editable layers under Sections VI and X. Determine any instruction requirement through the common assessment and Tier-1 feasibility test of Section VI.
3. **Players to Join Attack (Step 5):** enforce the Rest Defence Retention Invariant below.

### Players to Join Attack

`Players to Join Attack` ($J$) designates up to 3 starting outfielders to push into the opposition penalty area during attacking set pieces (corners, wide free kicks) and maximum attacking mentality (full red attack level). Each entry identifies the outfielder by both `Slot` and `Player ID`; the invariant below is evaluated on Slots.

* **Candidate Pool:** Selected strictly from starting outfielders (Slots 1–10).

* **Advanced-Instruction Independence:** Eligibility is independent of Advanced Instruction assignments. Evaluate attacking-set-piece and maximum-mentality retention through the Retention Invariant, separately from each instruction's documented effects and conditions. Advanced Instructions add no exclusion criteria to this selection (Section I, item 7).

* **Rest Defence Retention Invariant (Hard Constraint):** When selecting outfielders who are also members of `Retained Protector Slots`, the number of protectors remaining back must never fall below `Minimum Retained`:

  \(|J \cap \text{Retained Protector Slots}| \le |\text{Retained Protector Slots}| - \text{Minimum Retained}\)

  *(Example: If `Retained Protector Slots` has 4 members and `Minimum Retained` is 2, at most $4 - 2 = 2$ of those protectors may join the attack, guaranteeing that at least 2 protectors stay back at depth).*

* **Tactical Prioritization:** Prioritize deeper outfielders (`CB`, physical `DMF`, or tall full-backs) who possess top aerial and physical attributes (**Height**, **Physical Contact**, **Jump**, **Header**, and `Heading` skill), strictly subject to the Retention Invariant above. (Note: Forwards and wingers already position inside the box by default on offensive set pieces).

* **Array Cardinality:** 0 to 3 entries. `[]` is always valid; it is the only legal value when every outfielder is a Retained Protector Slot and `Minimum Retained` equals the array length.

## IX. Phase Grids and Advanced Instructions: coexisting tactical layers

### Layer model

The tactical layers coexist. Each supplies a defined part of the configuration or execution model:

| Layer                                                    | Tactical role                                                                                                          | Engine timing                                               | Application lever                                              |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- |
| Phase Grid (`Normal`, `With Ball`, `Without Ball`)       | Phase-specific structural anchor, line spacing, support geometry, and configured coverage                              | Continuous phase reference                                  | Assign Row 0–9 and Lane                                        |
| Position + Playing Style                                 | Configured tactical role plus the documented autonomous movement tendency when the carried style is compatible         | Continuous dynamic play                                     | Assign Position; resolve activation through PLAYER_GLOSSARY §1 |
| Player Skills, COM Playing Styles, Abilities, and Traits | Individual execution capability, documented skill effects, AI-controlled tendencies, and fixed profile characteristics | Continuous dynamic play or the documented applicable action | Player selection and role matching                             |
| Basic Instructions                                       | Team-wide configured tendencies                                                                                        | Continuous dynamic play within their documented scope       | Calibrate 12 settings and sliders                              |
| Advanced Instructions                                    | Specialized team or player behaviors with defined targets and conditions                                               | Runtime modifier within the instruction's documented scope  | Assign up to 2 Attacking + 2 Defending instructions            |

### Instruction interaction

Evaluate each instruction by its documented targets, affected behavior, conditions, duration, and configuration limits. Assess its interaction with the selected Positions, anchors, active Playing Styles, player profiles, and other applicable instructions. Resolve a documented interaction using the rule for that specific effect. Explain the combined tactical expectation in `Mechanisms`.

Do not apply a universal priority ordering to unrelated tactical effects. When an Advanced Instruction directly governs the same behavior as another active tendency under the instruction's documented condition, apply the specific interaction rule for that behavior. Other configured layers remain relevant to spacing, execution, and behaviors outside that effect.

### Rest-defence interaction

The Rest Defence Contract remains canonical in Section VIII. Establish it with the three states during Step 1, verify its anchor allocation through the State Structure Checks, and carry it as a committed requirement into later stages.

Assess how anchors, duties, active Playing Styles, execution profiles, Basic Instructions, and Advanced Instructions jointly support the retained protection. Use `Mechanisms` to explain forward movements, compensating coverage, transition behavior, and residual exposure. Determine any instruction requirement through the common assessment and arbitration of Section VI.

## X. Preset construction pipeline

Follow the existing construction stages in their specified order. Before committing a stage, identify at least one legal completion of the remaining stages within the available settings and instruction capacity. Check the current candidate against all inherited requirements. Commit it after the applicable checks pass.

Use lookahead to compare feasible complete configurations arising from alternatives in decisions that remain editable, applying Section VI's common assessment to their instruction requirements and tactical effects. Derive structural requirements from the scenario and squad evidence, not to justify a prospective instruction. Lookahead choices for later stages remain provisional until their own commitment; their earlier consideration creates no instruction requirement. Carry committed values forward as fixed inputs. At each later stage, choose compatible values for that stage's decisions and retain a feasible continuation for the stages that follow. Treat construction order as an order of commitments; assess gameplay through the coexisting tactical layers in GAME_PLAN_RULES III and IX.

Keep Step 1's co-determination of the three states and Rest Defence Contract; all of these decisions remain editable until their joint commitment. Ascending Slot iteration governs output order, not separate player-level commitments. Complete later settings and instructions compatibly with those commitments. Return a configuration satisfying every applicable hard check. Record the hard limits and committed decisions bounding that valid result in `Binding Constraints`, and explain tactical trade-offs in the existing explanatory fields.

Apply this commitment discipline within each call using its available data. Transmit committed decisions through the existing artifact contract. Use the artifact pipeline table in the system prompt to determine which earlier commitments each call receives.

```text
Step 1 — States + Rest Defence Contract (co-determined)
  For Normal, With Ball, and Without Ball, iterate strictly through fixed Slots 0 to 10 in numerical order, assigning each Slot's Position and Grid together within the editable Step-1 candidate. Never sort array output by pitch lines.
  Position establishes the configured tactical role and Playing-Style activation; Grid establishes the state-specific structural anchor.
  While fixing With Ball, designate the rear structure as Retained Protector Slots and set Minimum Retained from the preset's Risk Budget (Section VIII); the With Ball anchors and Tactical Duties of those Slots must honor the committed contract.
  Apply the State Structure Checks of Section IV to each state's configured anchors.
  Before commitment, compare feasible alternatives under the lookahead rule above and verify a legal completion of Steps 2–6 within the available instruction capacity and all inherited requirements.
      ↓
Step 2 — Autonomous-behavior audit
  Resolve the active Playing Style separately in each state from Position compatibility.
  A compatible carried style is active; an incompatible carried style is dormant; a None dossier has no active Playing Style.
  Assess the resulting behavior together with Grid anchors, execution profile, and the remaining applicable layers.
      ↓
Step 3 — Basic Instructions
  Calibrate the twelve settings (Section V) to the committed Step-1 structure and preset Risk Budget.
  Compare feasible alternatives under the lookahead rule above and retain a legal completion of Steps 4–6 before committing.
      ↓
Step 4 — Advanced Instructions (2 + 2)
  Evaluate each candidate instruction through its documented targets, behavior, conditions, and interaction with the committed configuration (Sections VI and IX).
  Apply the common contribution threshold and combination-level arbitration of Section VI within each family's two-slot limit.
  Select a jointly compatible combination and assign Blank to every unneeded slot.
  The resulting configuration must satisfy all committed hard requirements, including the Rest Defence Contract.
      ↓
Step 5 — Players to Join Attack
  Populate 0–3 starting outfielders (Slots 1–10), each identified by Slot and Player ID and ordered by aerial dominance, strictly enforcing the Rest Defence Retention Invariant:
  |J ∩ Protectors| <= |Protectors| - Minimum Retained (Section VIII).
      ↓
Step 6 — Auto Offside Trap
  Set On or Off based on defensive line awareness, recovery pace, and line height (Section VII).
```

In `Tactical Duty`, describe the assigned structural role and expected conditional behavior through the combined tactical layers, including relevant triggers and support or coverage relationships.

In `Mechanisms`, explain how the selected layers jointly support the plan, including situational triggers, support relationships, and exposure.

In `Binding Constraints`, record the hard requirements and committed decisions that bounded the valid result.
