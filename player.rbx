#!/usr/bin/env ruby

require 'unimidi'
require 'midi'

FADETIME = 0.025
TRAKTOR_INPUT  = 0 # IAC BUS 1
TRAKTOR_OUTPUT = 1 # IAC BUS 2

# input = UniMIDI::Input.gets
# output = UniMIDI::Output.gets
input  = UniMIDI::Input.use(TRAKTOR_OUTPUT)
output = UniMIDI::Output.use(TRAKTOR_INPUT)

MIDI.using(input, output) do
  channel 0  # Channel 1
  cc 9, 127  # Goto cue 1 (first cue)
  cc 11, 0   # Xfader
  note "D1"  # Play Track

  # Fade live input out
  (0.upto(127)).each do |i|
    sleep FADETIME
    cc 11, i
  end

  # Recieve loop
  receive do |message|
    $stdout.puts message.inspect if ENV['DEBUG']
    # Wait for the fade-out cue
    if message.index == 10 && message.value == 127
      (127.downto(0)).each do |i|
        # puts i
        sleep FADETIME
        cc 11, i
      end
      note "D1"
      off
    end
  end
  
  # start the listener
  join
  
end
