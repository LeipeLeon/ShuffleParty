#!/usr/bin/env ruby

require 'unimidi'
require 'midi'


# input = UniMIDI::Input.gets
# output = UniMIDI::Output.gets
input = UniMIDI::Input.use(1)
output = UniMIDI::Output.use(0)

MIDI.using(input, output) do
  channel 0
  cc 9, 127  # Goto cue 1
  cc 11, 127 # Xfader
  note "D1"  # Play

  receive do |message|
    $stdout.puts message.inspect if ENV['DEBUG']
    if message.index == 10 && message.value == 127
      (127.downto(0)).each do |i|
        # puts i
        sleep 0.025
        cc 11, i
      end
      note "D1"
      off
    end
  end
  
  join
  
end
