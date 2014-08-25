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
CC_NEXT_DJ     = 116
CC_START_TIMER = 117
CC_STOP_TIMER  = 118
CC_RESET_TIMER = 119

input = UniMIDI::Input.gets
output = UniMIDI::Output.gets
# input  = UniMIDI::Input.use(TRAKTOR_OUTPUT)
# output = UniMIDI::Output.use(TRAKTOR_INPUT)
# puts input.inspect
# puts output.inspect

class SwitchPack < Fixture
  self.channels = :one, :two, :three, :four
end

MIDI.using(input, output) do
  channel 0 # Channel 1
  cc CC_STOP_TIMER,  0    # Stop Timer
  sleep FADETIME
  cc CC_RESET_TIMER, 0    # Toggle Reset Timer down
  sleep FADETIME
  cc CC_START_TIMER, 127
  sleep FADETIME

  @univers = Universe.new('/dev/tty.usbserial-EN095377', SwitchPack => 1)
  @univers.fixtures[0].all = 0, 255, 255, 255

  Signal.trap("QUIT") { fade_shuffle_in } # CTRL-\
  Signal.trap("USR1") { fade_shuffle_in } # kill -SIGUSR1 <pid>

  cc CC_START_TIMER, 0
  sleep FADETIME

  def fade_shuffle_in
    $stdout.puts "Fade Shuffle In"
    cc CC_STOP_TIMER,  127 # Stop Timer
    sleep FADETIME
    cc CC_PLAY,        127 # Play Track
    sleep FADETIME
    cc CC_X_FADER,     0   # XFader
    sleep FADETIME
    @univers.fixtures[0].all = 0, 0, 0, 0

    # Fade live input out
    (0.upto(127)).each do |i|
      @univers.fixtures[0].all = i, 255 - i * 2, 255 - i * 2, 255 - i * 2
      cc CC_X_FADER, i
      sleep FADETIME
    end
    # Fade in spotlight is slower
    (128.upto(255)).each do |i|
      @univers.fixtures[0].all = i, 0, 0, 0
      sleep FADETIME
    end

    cc CC_RESET_TIMER, 0    # Toggle Reset Timer down
    sleep FADETIME
  end

  def fade_shuffle_out
    $stdout.puts "Fade Shuffle Out"
    cc CC_RESET_TIMER, 127 # Reset Timer
    sleep FADETIME
    cc CC_START_TIMER, 127  # Start Timer
    sleep FADETIME

    (127.downto(0)).each do |i|
      @univers.fixtures[0].all = i * 2, 255 - i * 2, 255 - i * 2, 255 - i * 2
      cc CC_X_FADER, i     # XFader
      sleep FADETIME
    end
    @univers.fixtures[0].all = 0, 255, 255, 255
    cc CC_PLAY,        0   # Stop track
    sleep FADETIME
    cc CC_NEXT_TRACK,  127 # Load next track
    sleep FADETIME

    cc CC_START_TIMER, 0   # Toggle Start Timer down
    sleep FADETIME
  end

  # Recieve loop
  receive do |message|
    $stdout.puts message.inspect if ENV['DEBUG']

    if message.index == CC_NEXT_DJ && message.value == 127
      fade_shuffle_in
    end

    # Wait for the fade-out cue
    if message.index == CC_FADE_OUT && message.value == 127
      fade_shuffle_out
    end

  end
  
  # start the listener
  join
  
end
