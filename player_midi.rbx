#!/usr/bin/env ruby

require 'unimidi'
require 'midi'
require './vendor/rdmx/rdmx'
include Rdmx

FADETIME       = 0.025  # Sleep between values from 0 .. 127 and back
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
  def on(controller)
    $stdout.puts "[%s] On: %s" % [Time.now.to_f, controller] if ENV['DEBUG']
    cc controller, 127
    sleep FADETIME * 3
  end
  def off(controller)
    $stdout.puts "[%s] Off: %s" % [Time.now.to_f, controller] if ENV['DEBUG']
    cc controller, 0
    sleep FADETIME * 3
  end
  def pulse(controller)
    on(controller)
    off(controller)
  end
  channel 0 # Channel 1
  off CC_STOP_TIMER    # Stop Timer
  off CC_RESET_TIMER   # Toggle Reset Timer down
  on  CC_START_TIMER

  begin
    @univers = Universe.new('/dev/tty.usbserial-EN095377', SwitchPack => 1)
  rescue Errno::ENOENT => e
    @univers = nil
  end
  @univers.fixtures[0].all = 0, 255, 255, 255 if @univers

  Signal.trap("QUIT") { fade_shuffle_in } # CTRL-\
  Signal.trap("USR1") { fade_shuffle_in } # kill -SIGUSR1 <pid>

  off CC_START_TIMER   # Toggle Start Timer down

  def fade_shuffle_in
    $stdout.puts "[%s] Fade Shuffle In" % Time.now.to_f
    pulse  CC_STOP_TIMER  # Stop Timer
    on  CC_PLAY        # Play Track

    @univers.fixtures[0].all = 0, 0, 0, 255 if @univers

    # Fade live input out
    (0.upto(127)).each do |i|
      @univers.fixtures[0].all = i, 255 - i * 2, 255 - i * 2, 255 if @univers
      cc CC_X_FADER, i
      sleep FADETIME
    end
    # Fade in spotlight is slower
    (128.upto(255)).each do |i|
      @univers.fixtures[0].all = i, 0, 0, 255 if @univers
      sleep FADETIME
    end

    pulse  CC_RESET_TIMER # Reset Timer

  end

  def fade_shuffle_out
    $stdout.puts "[%s] Fade Shuffle Out" % Time.now.to_f

    (127.downto(0)).each do |i|
      @univers.fixtures[0].all = i * 2, 255 - i * 2, 255 - i * 2, 255 if @univers
      cc CC_X_FADER, i # XFader
      sleep FADETIME
    end
    @univers.fixtures[0].all = 0, 255, 255, 255 if @univers
    off CC_PLAY        # Stop track
    pulse CC_NEXT_TRACK  # Load next track
    pulse CC_START_TIMER # Start Timer
  end

  # Recieve loop
  receive do |message|
    $stdout.puts "[%s] %s"  % [Time.now.to_f, message.inspect] if ENV['DEBUG']

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
