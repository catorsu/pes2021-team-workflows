# PES 2021 Player Glossary

This shared glossary defines the exact vocabulary and mechanics for Playing Styles, Player Skills, COM Playing Styles, the 25 base Abilities, and four Form and Traits ratings used by match planning (Contract v2.2) and player attribute modeling (Contract v4.3). The workflow-specific rules below distinguish modeling a player from evaluating a supplied dossier.

## 0. Reading the tables

- Resolve Playing Style activation from the assigned deployment Position code and the compatibility table in §1. A carried style activates at every compatible Position across familiarity Levels 2, 1, and 0. Registered position, familiarity, and pitch coordinates do not independently control activation.
- Playing Styles describe movement tendencies when active; Player Skills augment or enable specific techniques or effects; COM Playing Styles describe situational AI action preferences; Abilities describe underlying capability. Apply each skill's documented effect and read COM tendencies as preferences, not guaranteed actions or team instructions. Skills and COM styles do not replace Abilities; high Abilities do not automatically grant entries, and entry counts never automatically determine ratings.
- Validate Ability and Trait values against §§4–5, preserving their distinct meanings.

### Match-plan evaluation

- Read `Playing Style & Compatibility: None` as the dossier marker for an absent Playing Style. Assess that player's live behavior from Abilities, Player Skills, COM Playing Styles, Traits, and the applicable team settings and instructions. Treat a carried style at an incompatible Position as dormant. For active-style comparisons, both cases represent an absent active Playing Style, and two such absences match.
- Interpret each active Playing Style as its documented movement tendency within the combined tactical configuration. Apply specific interaction rules within their documented effect scopes (GAME_PLAN_RULES III and IX). Assess Grid anchors and positional familiarity separately under GAME_PLAN_RULES III and IV.
- Assess tactical suitability through comparative dossier evidence and the duty's requirements. The attribute-modeling rules below govern generation of player data; they do not authorize changing supplied dossiers during match planning.

### Player attribute modeling — Core rules

- `Playing Style` is one exact name from §1 or JSON `null`, never the string `"None"`. Contract v4.3 requires activation compatibility with the registered position for an assigned default style; actual deployment still determines activation.
- `Player Skills` and `COM Playing Styles` are exhaustive arrays of unique exact names from §2 and §3. The vocabulary is the only count limit; there is no preferred length, positional quota, or balance budget. `[]` is valid only after the full permissive review finds no plausible entry; unfamiliarity alone does not justify it.
- Apply an inclusion-first threshold: known, reasonably inferred, or potentially applicable entries qualify when there is a plausible connection to the modeled player's technique, role, decisions, or match situations. One reasonable connection is sufficient. Include compatible borderline cases, not just famous, frequent, or defining traits. Role and archetype inference may supply entries for unrecognized players.
- For Player Skills, a plausible executable technique or benefit from the stated effect is enough. For COM styles, infer a plausible preference in a relevant situation, not just physical capacity to perform the action. Include occasional, secondary, complementary, specialist, and conditional applications; none requires a separately remembered highlight or a higher proof threshold.
- Review the full vocabulary, then audit omissions for additional plausible fits. Exclude entries only for mechanical inapplicability, conflict with the modeled player or age interval, or no plausible connection beyond universal possibility. Playing Style activation lists do not restrict skills or COM tendencies. Overlapping and different-context entries may coexist; order them by characteristic fit without trimming.
- Every base Ability is an integer from `40` to `99`, whether directly estimated or inferred. There is no inference-specific ceiling or exclusive proof requirement for higher bands. Use Contract v4.3's generous best-fit calibration while preserving distinct capability meanings.
- Weak-foot traits use `1`–`4`, `Conditioning` uses `1`–`8`, and `Injury Resistance` uses `1`–`3`. Reasonable inference may estimate traits; the contract supplies neutral priors where no distinction is justified.
- When `Registered Position` is not `GK`, all five goalkeeper Abilities remain exactly `40`.

## 1. Playing Styles

| Playing Style | Activation Positions | Movement Pattern |
| --- | --- | --- |
| **Goal Poacher** | CF, SS | Stays on the last defender and makes direct runs behind. |
| **Dummy Runner** | CF, SS, AMF | Makes decoy runs that drag defenders away and open space. |
| **Fox in the Box** | CF | Remains near the penalty area and seeks short scoring movements inside it. |
| **Target Man** | CF | Checks toward the ball, holds position, and offers a central outlet. |
| **Creative Playmaker** | LWF, SS, RWF, LMF, AMF, RMF | Moves into pockets to receive and create. |
| **Prolific Winger** | LWF, RWF | Holds a wide, high position, then attacks inside or behind when space opens. |
| **Roaming Flank** | LWF, RWF, LMF, RMF | Leaves the touchline and moves into central channels to receive. |
| **Cross Specialist** | LWF, RWF, LMF, RMF | Stays wide near the touchline and advances into crossing positions. |
| **Classic No. 10** | SS, AMF, CMF | Stays relatively static between the lines and shows for short passes. |
| **Hole Player** | SS, LMF, AMF, CMF, RMF | Bursts forward into the box or gaps behind the defence during attacks. |
| **Box-to-Box** | LMF, AMF, CMF, DMF, RMF | Continuously moves between both penalty areas to support attack and defence. |
| **The Destroyer** | CMF, DMF, CB | Steps out aggressively to press, challenge, and close the ball carrier. |
| **Orchestrator** | CMF, DMF | Drops into deep passing lanes and shifts laterally to start attacks. |
| **Anchor Man** | DMF | Holds a deep central position and screens the back line. |
| **Offensive Full-back** | LB, RB | Overlaps down the outside and pushes high to support attacks. |
| **Full-back Finisher** | LB, RB | Moves forward into high central or half-space positions. |
| **Defensive Full-back** | LB, RB | Stays deeper and rarely overlaps, preserving the defensive line. |
| **Build Up** | CB | Drops or spreads into space to receive and begin possession from deep. |
| **Extra Frontman** | CB | Leaves the back line and joins advanced attacks when opportunities arise. |
| **Offensive Goalkeeper** | GK | Rushes off the line to sweep through balls behind the defence. |
| **Defensive Goalkeeper** | GK | Favors a position close to the goal line. |

## 2. Player Skills

| Player Skill | Effect |
| --- | --- |
| **Scissors Feint** | Executes Scissors Feint at high speed. |
| **Double Touch** | Quickly executes the Double Touch. |
| **Flip Flap** | Executes the Flip Flap. |
| **Marseille Turn** | Executes the Marseille Turn. |
| **Sombrero** | Executes Boomerang Trap and Crescent Turn. |
| **Cross Over Turn** | Quickly executes the Cross Over Turn. |
| **Cut Behind & Turn** | Executes the Cut Behind. |
| **Scotch Move** | Executes the Scotch Move. |
| **Sole Control** | Uses step-on ball control for feints and turns. |
| **Heading** | Improves downward header frequency and accuracy. |
| **Long Range Curler** | Produces highly accurate curling shots from distance. |
| **Chip Shot Control** | Improves chip-shot accuracy. |
| **Long Range Shooting** | Improves shooting accuracy from long range. |
| **Knuckle Shot** | Makes knuckle shots easier, including from free kicks. |
| **Dipping Shot** | Enables top-spin shots that dip and bounce erratically before the goalkeeper. |
| **Rising Shots** | Enables low-trajectory shots that rise sharply. |
| **Acrobatic Finishing** | Enables finishes from awkward positions or while off-balance. |
| **Heel Trick** | Enables heel passes and shots, including while off-balance. |
| **First-Time Shot** | Improves technique and precision for one-touch shots. |
| **One-touch Pass** | Improves technique and precision for one-touch passes. |
| **Through Passing** | Increases the accuracy of through balls. |
| **Weighted Pass** | Applies back-spin to lofted and through passes for accuracy. |
| **Pinpoint Crossing** | Produces highly accurate curling crosses. |
| **Outside Curler** | Enables passes and shots with the outside of the boot. |
| **Rabona** | Enables Rabona passes and shots. |
| **No Look Pass** | Misdirects opponents with no-look passes. |
| **Low Lofted Pass** | Produces long, accurate lofted passes with a low trajectory. |
| **GK Low Punt** | Produces long, accurate goalkeeper punts with a low trajectory. |
| **GK High Punt** | Produces long, high goalkeeper punts deep into opponent territory. |
| **Long Throw** | Increases throw-in range. |
| **GK Long Throw** | Increases goalkeeper throw range. |
| **Penalty Specialist** | Increases penalty-kick accuracy. |
| **GK Penalty Saver** | Improves goalkeeper reactions against penalty kicks. |
| **Gamesmanship** | Makes winning free kicks easier while on the ball. |
| **Man Marking** | Persistently tracks and stays close to an opponent. |
| **Track Back** | Makes an offensive player actively pressure to regain the ball. |
| **Interception** | Improves ball-interception ability. |
| **Acrobatic Clear** | Enables footed clearances from awkward positions. |
| **Captaincy** | Inspires the team and reduces fatigue effects for teammates. |
| **Super-sub** | Provides a stat boost when the player enters in the second half. |
| **Fighting Spirit** | Improves performance under pressure, fatigue, or adversity. |

## 3. COM Playing Styles

| COM Playing Style | AI Tendency |
| --- | --- |
| **Trickster** | Favors stepovers and skill-based dribbling to beat an opponent. |
| **Mazing Run** | Favors penetrating carries using close turns and dribbling. |
| **Speeding Bullet** | Favors getting forward quickly by using pace. |
| **Incisive Run** | Favors cutting inside from wide areas while dribbling to seek a scoring chance. |
| **Long Ball Expert** | Attempts long passes more readily. |
| **Early Cross** | Looks to cross early when a suitable wide opportunity appears. |
| **Long Ranger** | Attempts shots from outside the penalty area more readily. |

## 4. Abilities

All 25 base Abilities are integers in the range `40`–`99`.

| Ability | Definition |
| --- | --- |
| **Offensive Awareness** | Attacking response and off-ball positioning, including run timing and finding space. Assess passing and creative execution through the relevant passing, possession, skill, and style evidence. |
| **Ball Control** | General control of the ball, including first touch, trapping, and feints. |
| **Dribbling** | Ability to maintain control while carrying the ball at speed. |
| **Tight Possession** | Ability to turn and retain control while dribbling at low speed. |
| **Low Pass** | Accuracy of passes played along the ground. |
| **Lofted Pass** | Accuracy of lofted passes and aerial deliveries. |
| **Finishing** | Shooting accuracy. Assess shot power through Kicking Power and attacking movement through the relevant awareness and tactical layers. |
| **Header** | Accuracy and directional execution of headers. Assess jumping through Jump and strength through Physical Contact. |
| **Set Piece Taking** | Accuracy from set pieces, including free kicks and penalties. |
| **Curl** | Ability to impart spin or curve on the ball. |
| **Speed** | Maximum running speed when off the ball. |
| **Acceleration** | How quickly the player reaches top running speed. |
| **Kicking Power** | Power generated when kicking the ball. Assess accuracy through the relevant shooting or passing Ability. |
| **Jump** | Maximum vertical jumping height. |
| **Physical Contact** | Strength and stability when contesting challenges and collisions. |
| **Balance** | Ability to avoid tackles and remain upright through contact. |
| **Stamina** | Fitness and endurance for sustaining physical output. Assess form reliability through Conditioning. |
| **Defensive Awareness** | Defensive response and positioning, including line discipline and tracking. |
| **Ball Winning** | Proficiency at tackling and dispossessing an opponent. |
| **Aggression** | Intensity and eagerness when attempting to regain the ball. Assess tackling through Ball Winning and strength through Physical Contact. |
| **GK Awareness** | Goalkeeper speed of response to the ball. Assess the tendency to sweep or stay close to goal through the goalkeeper's active Playing Style and applicable tactical layers. |
| **GK Catching** | Ability to catch and secure powerful shots. |
| **GK Parrying** | Ability to deflect shots toward safer areas. |
| **GK Reflexes** | Ability to make quick reaction saves. |
| **GK Reach** | Effective goal coverage and extension when making saves. |

## 5. Form and Traits

| Trait | Range | Definition |
| --- | ---: | --- |
| **Weak Foot Usage** | `1`–`4` | Frequency or willingness to use the weaker foot. Assess execution accuracy through Weak Foot Accuracy. |
| **Weak Foot Accuracy** | `1`–`4` | Execution accuracy with the weaker foot. Assess usage frequency through Weak Foot Usage. |
| **Conditioning** | `1`–`8` | Ability to maintain form reliably over time, distinct from transient current form or match fitness. Assess endurance through Stamina and injury resistance through Injury Resistance; use supplied current-state evidence for current form or fitness. |
| **Injury Resistance** | `1`–`3` | Resistance to injury, distinct from current fitness or recovery speed. Assess endurance through Stamina, form reliability through Conditioning, and current fitness or recovery through supplied current-state evidence. |

## Essential distinctions

- `Offensive Awareness` must not be used as a substitute for passing vision, creativity, or general intelligence.
- `Speed`, `Acceleration`, and `Dribbling` are distinct: off-ball top speed, rate of reaching top speed, and control while carrying at speed.
- `Ball Control`, `Dribbling`, `Tight Possession`, and `Balance` are distinct aspects of technique and stability.
- `Low Pass`, `Lofted Pass`, and `Curl` are independent; specialist passing skills do not replace them.
- `Finishing`, `Kicking Power`, `Offensive Awareness`, and `Set Piece Taking` are independent.
- `Defensive Awareness`, `Ball Winning`, `Aggression`, and `Physical Contact` are independent.
- `Jump`, `Header`, and `Physical Contact` are independent.
- `GK Awareness`, `GK Catching`, `GK Parrying`, `GK Reflexes`, and `GK Reach` are independent; sweeping behavior belongs to goalkeeper Playing Style.
