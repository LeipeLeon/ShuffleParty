#!/usr/bin/env ruby

require 'unimidi'
require 'midi'

FADETIME       = 0.05  # Sleep between values from 0 .. 127 and back
TRAKTOR_INPUT  = 0     # IAC BUS 1
TRAKTOR_OUTPUT = 1     # IAC BUS 2
CC_CUE         = 9
CC_FADE_OUT    = 10
CC_X_FADER     = 11
NOTE_PLAY      = "D1"

# input = UniMIDI::Input.gets
# output = UniMIDI::Output.gets
input  = UniMIDI::Input.use(TRAKTOR_OUTPUT)
output = UniMIDI::Output.use(TRAKTOR_INPUT)

MIDI.using(input, output) do
  channel 0 # Channel 1

  Signal.trap("QUIT") { fade_out } # CTRL-\
  Signal.trap("USR1") { fade_out } # kill -SIGUSR1 <pid>

  def fade_out
    cc CC_CUE, 127        # Goto cue 1 (first cue)
    cc CC_X_FADER, 0      # Xfader
    note NOTE_PLAY        # Play Track

    # Fade live input out
    (0.upto(127)).each do |i|
      sleep FADETIME
      cc CC_X_FADER, i
    end
  end

  # Recieve loop
  receive do |message|
    $stdout.puts message.inspect if ENV['DEBUG']
    # Wait for the fade-out cue
    if message.index == CC_FADE_OUT && message.value == 127
      (127.downto(0)).each do |i|
        sleep FADETIME
        cc CC_X_FADER, i
      end
      note NOTE_PLAY
      off
      # TODO: Load next track
      cc CC_CUE, 127    # Goto cue 1 (first cue)
    end
  end
  
  # start the listener
  join
  
end

