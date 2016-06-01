SHUFFLEPARTY
============

SYNOPSIS
--------

- Each DJ get's an amount of time
- When the timer expires the output is forced to play a shuffle track and the dj get's faded out

USAGE
-----

- Traktor:
  - Set deck A to live input and set it to the sound from the DJ mixer
  - Set a start and fade-out cue on each track you want to use to automagically crossfade back to live input

- brew install watch

    `watch -n1200 kill -USR1 ``ps waux | grep 'ruby ./player.rbx' | grep -v grep | awk '{print $2}'`

Commands:

    ./player_midi.rbx

    DEBUG=true ./player.rbx

    Select a MIDI input...
    0) Apple Inc. IAC-besturingsbestand
    2) Native Instruments Traktor Audio 10
    > 0

    Select a MIDI output...
    1) Apple Inc. IAC-besturingsbestand
    3) Native Instruments Traktor Audio 10
    > 1

Developed and Tested on OSX, might work on Windows
