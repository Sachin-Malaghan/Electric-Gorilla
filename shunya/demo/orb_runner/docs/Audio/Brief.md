# Orb Runner - Audio brief

All sounds are synthesised, mono, in folder `Audio`. The game code looks these names up exactly; a different name means silence.

## Sound effects
| Asset | Plays when | Should feel like | Shape |
|---|---|---|---|
| `S_Pickup` | An orb is collected | A small reward | Two quick rising sine notes (880 Hz then 1320 Hz), about 0.2 s |
| `S_Hit` | The drone damages the hull | A jolt | Short noise burst, then a falling square tone, about 0.25 s |
| `S_Win` | The last orb is collected | Relief | Rising major arpeggio C-E-G-C, triangle wave, under 1 s |
| `S_Lose` | Time or hull runs out | Power failing | Three falling saw notes, the last one sliding down, under 1 s |

## Music
| Asset | Plays | Shape |
|---|---|---|
| `S_MusicLoop` | From the start of the match, looping | 4 second loop, sixteen quarter-second triangle notes in A minor, quiet (volume about 0.2) so effects sit on top |

## Mix rule
Effects are louder than music. Nothing clips: no note above volume 0.8.
