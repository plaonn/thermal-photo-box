# Research summary

Status as of 2026-11-23. This page collects the conclusions of the dithering research, the decisions taken, and the plan for the next physical print. The details and numbers are on the linked pages.

Terminology: the XP-80T is a direct thermal printer; there is no ink or ribbon. "Ink" or "dark" on these pages means the area of thermal paper that has developed (turned dark).

**Everything below except the [physical print test](experiments-xp80t.md) is simulated.** The print model is uncalibrated; the real dot size is not known.

## Conclusions

1. **Recommended method: JJN + noise 64** (JJN with its threshold varied by ±32 grey levels by a blue-noise mask; `thermal-photo-box render --method jjn-noise`). Its tone error is close to the best at every dot radius from 0.55 up, and it has the fewest directional patterns of the JJN family. It has not been printed yet. ([candidates](candidates.md))
2. **The dot size matters far more than the method.** Each 0.1 of radius shifts the overall lightness by 10–13 L\*; at one radius, the candidates differ by at most 2.5 L\*. Tone is therefore set by the printer density and the preprocessing gamma, not by the choice of method. ([candidates](candidates.md#what-holds-at-every-radius))
3. **Dot gain turns arrangement into tone.** Highlights change through the size of isolated dots; mid and dark tones change mostly through neighbouring dots merging. The same 50% coverage prints very differently depending on how the dots are arranged (heat model, L\*):

   | Radius | checkerboard | vertical lines | horizontal lines | 2×2 clusters |
   | --- | --- | --- | --- | --- |
   | 0.45 | 77.3 | 76.3 | 76.0 | 76.1 |
   | 0.55 | 51.9 | 67.6 | 62.8 | 65.5 |
   | 0.65 | 18.5 | 49.1 | 33.2 | 52.4 |
   | 0.75 | 13.8 | 18.1 | 14.4 | 35.8 |

   (`python experiments/arrangement.py`)

   So a method whose arrangement changes from place to place prints visible bands even where the input is smooth. This is the likely cause of the horizontal stripes Floyd–Steinberg showed on paper and shows in the [simulated prints](dither-comparison.md#artifact-maps). From 0.65 up the effect is large, which is also why clustered dots (as in newspaper printing) are the most stable in tone.
4. **The plain on-screen view of a bitmap is misleading.** Viewers average grey values and happen to match the target tone; perfect square dots would print about 16 L\* lighter at mid-grey, and the printer's dot gain happens to compensate. Non-integer zoom adds moiré that is on neither the bitmap nor the paper. ([square preview](square-preview.md))
5. **Error-diffusion patterns are deterministic, and noise breaks them.** Plain JJN has no randomness: on flat areas the error builds up and is released at a regular rate, near simple fractions (1/2, 1/3, 1/4) the rate locks in, and the rows pull each other into 2-D lattices, lines and worms. Threshold noise keeps the cycles from locking. It lowered the directional score at every radius with almost no cost. ([candidates](candidates.md#what-holds-at-every-radius))
6. **Ideas based on the print model did not beat simple noise.** ([improvements](candidates.md#improvements-experimental))
   - Model-based error diffusion (error measured against the predicted print) has the best tone at every radius, but draws stripes, because a dot next to existing dots adds less darkness and so passes the threshold more easily. This is a systematic push, not a chance pattern, so noise does not remove it.
   - Removing that push (a chain penalty) removes the stripes and the tone gain with them, and makes the print far too light with small dots. Processing rows in alternating directions changes nothing. ([removing the stripes](candidates.md#removing-the-stripes))
   - Paired shadow holes, diffusing 7/8 of the error, and noise that is weaker at edges gave no clear gain.

## Inferred dot size

The XP-80T at density 4 probably behaves like a radius of about **0.6–0.7**. This is an inference, not a measurement:

- The preprocessing (gamma 0.70, contrast 0.90) was tuned by eye on real prints. Against the original, it gives a tone close to neutral at radius 0.65 and about 10 L\* too light at 0.55. ([dithering comparison](dither-comparison.md#reading))
- Floyd–Steinberg showed horizontal stripes on paper; in the model, such stripes from arrangement differences become strong from about 0.55–0.65 up (table above).

## Decisions

- **Choose the method in simulation, robustly across radius 0.45–0.75; calibrate last.** One or two real prints at the end set the printer density and the preprocessing gamma. The method itself should not need to change.
- **Heat history of the print head is not modelled.** The printer is fast (a photo prints in about a second), so heating of the head is spread over the whole print and acts like a global density change, which density and gamma absorb. Local carry-over between neighbouring dots is already approximated by the heat model's summed neighbours.
- **Only public samples are stored.** Private portraits, USB serial numbers and private photos of people are not committed. External implementations (Zhou–Fang, Ostromoukhov) are used from a temporary clone and not vendored.

## Next steps (needs the printer)

1. Print the patch chart and one photo with JJN and JJN + noise 64 at density 4, with the existing preprocessing. Render with `thermal-photo-box render IMAGE --method jjn` and `--method jjn-noise`.
2. Compare the prints with simulations at radius 0.45–0.75, using the 50% arrangement test above (checkerboard against line patterns) as a direct radius probe. Choose the radius that matches.
3. Adjust gamma, then density if needed, to neutral tone. Set the simulation's default radius to the measured value.

The density command `1F 1B 1F 13 14 nn` may change persistent printer settings; send it only with an explicit `--density`.

## Open questions

- The real dot radius and its dependence on density.
- Whether threshold noise reads as grain on paper at a normal viewing distance.
- Whether Zhou–Fang, the least directional error-diffusion method in the model, would beat JJN + noise 64 once the radius is known.
