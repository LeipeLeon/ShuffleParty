# SHUFFLEPARTY

## SYNOPSIS

- Each DJ get's an amount of time
- When the timer expires the dj get's faded out and automagically a shuffle track begins to play.
- When tthe shuffle track finishes (or the playhead[^playhead] passes a cue point[^cuepoint])


## Implementation

Signalling

![](shuffle-timing.png)

```json
// https://wavedrom.com/editor.html
{
  "signal": [
    {},
    [
      "Perception",
      {
        "wave": "==..=..=..=.|",
        "data": "DJ SHUFFLE DJ SHUFFLE DJ SHUFFLE DJ"
      },
      {
        "name": "AUDIO",
        "wave": "54..5..4..5.|",
        "data": "💿 💾 💿 💾 💿 💾 💿"
      },
      {
        "name": "LIGHT",
        "wave": "78..7..8..7.|",
        "data": "🚨 🪩 🚨 🪩 🚨 🪩 🚨"
      },
      {
        "name": "SCREEN",
        "wave": "36..3..6..3.|",
        "data": "10:00 🪩 10:00 🪩 10:00 🪩 10:00"
      }
    ],
    {},
    [
      "PULSES",
      //{ "name": "PULSE", "wave": "lL..L..L..L.|"},
      { "name": "TIMER_STATE", "wave": "hL..h..L..h.|" },
      { "name": "TRACK_STATE", "wave": "Lh..L.h..L.|" },
      { "name": "TIMER_DONE", "wave": "0Pl....Pl...|" },
      { "name": "TRACK_DONE", "wave": "0...Pl....Pl|" },
    ],
    {},
    [
      "AUDIO",
      { "name": "MP3", "wave": "04..0..4..0.|" },
      { "name": "DJ", "wave": "50..5..0..5.|" }
    ],
    {},
    [
      "DMX",
      { "name": "SPOT", "wave": "08..0..8..0.|" },
      { "name": "FX", "wave": "70..7..0..7.|" }
    ]
  ]
}
````

[^cuepoint]: A marker in the audio timeline which indicates a important moment. Like hthe hotques on a Pioneer CDJ
[^playhead]: The position of the player
