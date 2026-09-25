# PES 2021 Player Database — Illustrative Fragment

> **Documentation-only fragment — abridged, and not itself a runnable document.**
>
> Illustrative team: Example FC
> Illustrative Team ID: 001
> Intended full-squad size: 25
> Dossiers shown in this fragment: 4

This illustrative fragment defines the normative human-readable `PLAYER_RECORDS` format. `players/generator.py` renders each runnable document in memory from the editor CSVs when a run needs it. Preserve the format below. Use the system prompt's artifact pipeline table to select each call's extract, and inject it inside `<PLAYER_RECORDS>` tags ahead of the task. Resolve source disagreements through the system prompt's Source precedence section. Use `PLAYER_GLOSSARY` for the meaning of every Playing Style, Player Skill, COM Playing Style, Ability, and Trait.

## Runtime document format

### Full document

A full runnable PLAYER_RECORDS document consists of, in this order:

1. A header line, exactly `Team: <Team Name> (ID: <numeric ID>) | Total Players: <N>`. The Team ID is written in digits only; leading zeros, as in `001`, are permitted and preserved. `N` is the size of the full squad (at least 11) and is identical in every extract.
2. One complete 13-Position pre-calculated matrix, under `## PRE-CALCULATED POSITIONAL SQUAD MATRIX`.
3. Exactly `N` complete `### Player:` dossiers, under `## DETAILED PLAYER DOSSIERS`, in the structure shown below.

Place the matrix before the dossiers. The parser reads the matrix between `## PRE-CALCULATED POSITIONAL SQUAD MATRIX` and `## DETAILED PLAYER DOSSIERS`.

### Call-scoped extracts

The renderer produces one extract per call from the same in-memory full document. The header line is copied unchanged (`Total Players` stays `N`); the matrix section, when omitted, is omitted entirely including its `##` heading; the `## DETAILED PLAYER DOSSIERS` heading is always present and is followed only by complete dossiers:

| Extract | Used by | Header | Matrix | Dossiers |
| :--- | :--- | :--- | :--- | :--- |
| Full | Starting-XI lock call | Yes | Yes | All `N` |
| Starters | Every PresetPlan call | Yes | Omitted | The eleven locked starters, in Slot order |
| Squad | Bench call | Yes | Omitted | All `N`: the eleven starters in Slot order, then the non-starters |

Render complete values and dossiers in every runnable document or extract. This documentation fragment uses ellipses and a subset of dossiers to illustrate the format.

### Dossier conventions

* Partition each carried style's Level-2 and Level-1 Positions between `Compatible Familiar Positions` and `Not-listed Familiar Positions` using PLAYER_GLOSSARY §1. Use these lines as a familiarity-filtered view. Resolve activation at every assigned Position through the compatibility table, including compatible Level-0 Positions.
* For a player with an absent Playing Style, render `Playing Style & Compatibility: None` and proceed directly to `Player Skills`. Read familiar Positions from `Familiarity`. Preserve this as the dossier format's sole structural variation.
* `Detailed Abilities` lists all 25 Abilities in the four groups shown, and `Durability & Traits` lists the four Traits; every value lies within the ranges of PLAYER_GLOSSARY §§4–5.

## PRE-CALCULATED POSITIONAL SQUAD MATRIX

The matrix indexes Level-2 positional core and Level-1 cover under GAME_PLAN_RULES III, together with squad-available compatible Playing Styles. Assess Level-0 fluid-state assignments under the same section's existing rules.

**Column legend — `Squad-Available Playing Styles (derived)`:** For each Position row, derive `Squad-Available Playing Styles (derived)` from the carried styles of that row's Level-2 and Level-1 players whose styles are compatible with the Position in PLAYER_GLOSSARY §1. Include each player in positional depth according to familiarity. A `None` dossier contributes positional depth and an empty style contribution. Read `None` in the derived style column as an empty union for that squad cross-section. Determine style activation for individual assignments through PLAYER_GLOSSARY §1.

| Position | Level-2 Players (ID)                     | Level-1 Players (ID)     | Squad-Available Playing Styles (derived)           |
| :------- | :--------------------------------------- | :----------------------- | :------------------------------------------------- |
| **GK**   | Player ALPHA (1001), Player DELTA (1004) | None                     | Defensive Goalkeeper, Offensive Goalkeeper         |
| **CB**   | Player EPSILON (1005)                    | Player ZETA (1006)       | Build Up, The Destroyer                            |
| **LB**   | ...                                      | ...                      | ...                                                |
| **RB**   | ...                                      | ...                      | ...                                                |
| **DMF**  | Player ETA (1007)                        | None                     | None                                               |
| **CMF**  | Player BETA (1002), ...                  | ...                      | Box-to-Box, Classic No. 10, Hole Player            |
| **LMF**  | ...                                      | ...                      | ...                                                |
| **RMF**  | ...                                      | ...                      | ...                                                |
| **AMF**  | Player BETA (1002), ...                  | ...                      | Classic No. 10, Creative Playmaker, Hole Player    |
| **LWF**  | ...                                      | Player BETA (1002), ...  | Creative Playmaker, Prolific Winger, Roaming Flank |
| **RWF**  | ...                                      | Player BETA (1002), ...  | Creative Playmaker, Prolific Winger, Roaming Flank |
| **SS**   | ...                                      | Player GAMMA (1003), ... | Goal Poacher, Hole Player                          |
| **CF**   | Player GAMMA (1003), ...                 | ...                      | Fox in the Box, Goal Poacher                       |

## DETAILED PLAYER DOSSIERS

### Player: Player ALPHA (ID: 1001)

* **Basic Profile**: Registered Position: GK | Preferred Foot: Right | Height: 192 cm | Weight: 90 kg
* **Familiarity**:
  - Fully Familiar (Level 2): GK
  - Partially Familiar (Level 1): None
* **Playing Style & Compatibility**: Offensive Goalkeeper
  * Compatible Familiar Positions: GK
  * Not-listed Familiar Positions: None
* **Player Skills**: GK High Punt, GK Long Throw, Penalty Specialist, GK Penalty Saver, Captaincy, Fighting Spirit
* **COM Playing Styles**: Long Ball Expert
* **Detailed Abilities**:
  * *Attacking & Possession*: Offensive Awareness: 45, Ball Control: 65, Dribbling: 50, Tight Possession: 55, Low Pass: 70, Lofted Pass: 80, Finishing: 45, Header: 75, Set Piece Taking: 55, Curl: 50
  * *Athleticism*: Speed: 65, Acceleration: 68, Kicking Power: 90, Jump: 88, Physical Contact: 92, Balance: 80, Stamina: 75
  * *Defending*: Defensive Awareness: 65, Ball Winning: 60, Aggression: 80
  * *Goalkeeping*: GK Awareness: 95, GK Catching: 90, GK Parrying: 92, GK Reflexes: 96, GK Reach: 95
  * *Durability & Traits*: Weak Foot Usage: 2, Weak Foot Accuracy: 2, Conditioning: 7, Injury Resistance: 3

### Player: Player BETA (ID: 1002)

* **Basic Profile**: Registered Position: AMF | Preferred Foot: Right | Height: 180 cm | Weight: 74 kg
* **Familiarity**:
  - Fully Familiar (Level 2): CMF, AMF
  - Partially Familiar (Level 1): LWF, RWF
* **Playing Style & Compatibility**: Creative Playmaker
  * Compatible Familiar Positions: LWF, RWF, AMF
  * Not-listed Familiar Positions: CMF
* **Player Skills**: Double Touch, One-touch Pass, Through Passing, Weighted Pass, Pinpoint Crossing, Long Range Shooting
* **COM Playing Styles**: Trickster, Mazing Run, Long Ball Expert
* **Detailed Abilities**:
  * *Attacking & Possession*: Offensive Awareness: 88, Ball Control: 95, Dribbling: 92, Tight Possession: 94, Low Pass: 95, Lofted Pass: 92, Finishing: 82, Header: 68, Set Piece Taking: 88, Curl: 86
  * *Athleticism*: Speed: 80, Acceleration: 84, Kicking Power: 82, Jump: 70, Physical Contact: 74, Balance: 90, Stamina: 84
  * *Defending*: Defensive Awareness: 58, Ball Winning: 55, Aggression: 62
  * *Goalkeeping*: GK Awareness: 40, GK Catching: 40, GK Parrying: 40, GK Reflexes: 40, GK Reach: 40
  * *Durability & Traits*: Weak Foot Usage: 3, Weak Foot Accuracy: 3, Conditioning: 7, Injury Resistance: 2

### Player: Player GAMMA (ID: 1003)

* **Basic Profile**: Registered Position: CF | Preferred Foot: Right | Height: 185 cm | Weight: 78 kg
* **Familiarity**:
  - Fully Familiar (Level 2): CF
  - Partially Familiar (Level 1): SS
* **Playing Style & Compatibility**: Goal Poacher
  * Compatible Familiar Positions: CF, SS
  * Not-listed Familiar Positions: None
* **Player Skills**: Heading, First-Time Shot, Acrobatic Finishing, Rising Shots, Outside Curler, Fighting Spirit
* **COM Playing Styles**: Incisive Run, Speeding Bullet
* **Detailed Abilities**:
  * *Attacking & Possession*: Offensive Awareness: 94, Ball Control: 86, Dribbling: 84, Tight Possession: 82, Low Pass: 76, Lofted Pass: 72, Finishing: 95, Header: 90, Set Piece Taking: 74, Curl: 78
  * *Athleticism*: Speed: 88, Acceleration: 90, Kicking Power: 90, Jump: 88, Physical Contact: 88, Balance: 84, Stamina: 85
  * *Defending*: Defensive Awareness: 48, Ball Winning: 52, Aggression: 75
  * *Goalkeeping*: GK Awareness: 40, GK Catching: 40, GK Parrying: 40, GK Reflexes: 40, GK Reach: 40
  * *Durability & Traits*: Weak Foot Usage: 3, Weak Foot Accuracy: 3, Conditioning: 8, Injury Resistance: 2

### Player: Player ETA (ID: 1007)

* **Basic Profile**: Registered Position: DMF | Preferred Foot: Right | Height: 184 cm | Weight: 79 kg
* **Familiarity**:
  - Fully Familiar (Level 2): DMF
  - Partially Familiar (Level 1): CMF
* **Playing Style & Compatibility**: None
* **Player Skills**: Interception, Man Marking, Acrobatic Clear, Fighting Spirit
* **COM Playing Styles**: Long Ball Expert
* **Detailed Abilities**:
  * *Attacking & Possession*: Offensive Awareness: 60, Ball Control: 72, Dribbling: 64, Tight Possession: 68, Low Pass: 78, Lofted Pass: 74, Finishing: 52, Header: 76, Set Piece Taking: 50, Curl: 55
  * *Athleticism*: Speed: 68, Acceleration: 66, Kicking Power: 80, Jump: 82, Physical Contact: 86, Balance: 78, Stamina: 88
  * *Defending*: Defensive Awareness: 84, Ball Winning: 86, Aggression: 78
  * *Goalkeeping*: GK Awareness: 40, GK Catching: 40, GK Parrying: 40, GK Reflexes: 40, GK Reach: 40
  * *Durability & Traits*: Weak Foot Usage: 2, Weak Foot Accuracy: 2, Conditioning: 6, Injury Resistance: 3
