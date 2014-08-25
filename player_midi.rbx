#!/usr/bin/env ruby

require 'unimidi'
require 'midi'
require './vendor/rdmx/rdmx'
include Rdmx

FADETIME       = 0.05  # Sleep between values from 0 .. 127 and back
TRAKTOR_INPUT  = 0     # IAC BUS 1
TRAKTOR_OUTPUT = 1     # IAC BUS 2
NOTE_CUP       = "G-1" # Cue & Play
NOTE_PLAY      = "D1"
CC_PLAY        = 9
CC_FADE_OUT    = 10
CC_X_FADER     = 11
CC_NEXT_TRACK  = 12   # Next track in playlist

input = UniMIDI::Input.gets
output = UniMIDI::Output.gets
# input  = UniMIDI::Input.use(TRAKTOR_OUTPUT)
# output = UniMIDI::Output.use(TRAKTOR_INPUT)

class SwitchPack < Fixture
  self.channels = :one, :two, :three, :four
end


MIDI.using(input, output) do
  channel 0 # Channel 1

  @univers = Universe.new('/dev/tty.usbserial-EN095377', SwitchPack => 1)
  @univers.fixtures[0].all = 0, 255, 255, 255

  Signal.trap("QUIT") { fade_out } # CTRL-\
  Signal.trap("USR1") { fade_out } # kill -SIGUSR1 <pid>

  def fade_out
    @univers.fixtures[0].all = 0, 0, 0, 0
    # note NOTE_CUP         # Play Track
    cc CC_PLAY, 127
    cc CC_X_FADER, 0      # Xfader

    # Fade live input out
    (0.upto(127)).each do |i|
      @univers.fixtures[0].all = i, 255 - i * 2, 255 - i * 2, 255 - i * 2
      sleep FADETIME
      cc CC_X_FADER, i
    end
    # Fade in spotlight is slower
    (128.upto(255)).each do |i|
      @univers.fixtures[0].all = i, 0, 0, 0
      sleep FADETIME
    end
  end

  # Recieve loop
  receive do |message|
    $stdout.puts message.inspect if ENV['DEBUG']
    # Wait for the fade-out cue
    if message.index == CC_FADE_OUT && message.value == 127
      (127.downto(0)).each do |i|
        @univers.fixtures[0].all = i * 2, 255 - i * 2, 255 - i * 2, 255 - i * 2
        sleep FADETIME
        cc CC_X_FADER, i
      end
      @univers.fixtures[0].all = 0, 255, 255, 255
      cc CC_PLAY, 0
      cc CC_NEXT_TRACK, 127  # Load next track
    end
  end
  
  # start the listener
  join
  
end

