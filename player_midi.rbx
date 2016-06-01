#!/usr/bin/env ruby

require 'unimidi'
require 'midi'
require 'serialport'

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
A_FADE_TRESHOLD = 20.0
#params for serial port
port_str = "/dev/tty.usbmodem1451"  #may be different for you
baud_rate = 9600
data_bits = 8
stop_bits = 1
parity = SerialPort::NONE

input = UniMIDI::Input.gets
output = UniMIDI::Output.gets
# input  = UniMIDI::Input.use(TRAKTOR_OUTPUT)
# output = UniMIDI::Output.use(TRAKTOR_INPUT)
# puts input.inspect
# puts output.inspect

MIDI.using(input, output) do

  @serial_port = SerialPort.new(port_str, baud_rate, data_bits, stop_bits, parity)
  puts "Connecting serial"
  sleep 1 # wait a little bit to establish it
  @serial_port.write("254")
  @serial_port.write("\n")
  @prev_pos = 0

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
  def write_serial(i)
    a_pos = 0
    if i < 64
      a_pos = ((A_FADE_TRESHOLD / 64) * i ).to_i.to_s
    else
      a_pos = (255 - A_FADE_TRESHOLD - A_FADE_TRESHOLD + ((A_FADE_TRESHOLD / 64) * i )).to_i.to_s
    end
    if @prev_pos != a_pos
      $stdout.puts [i, a_pos, ((A_FADE_TRESHOLD / 64) * i )].inspect if ENV['DEBUG']
      @serial_port.write(a_pos)
      @serial_port.write("\n")
      @prev_pos = a_pos
    end
  end

  channel 0 # Channel 1
  off CC_STOP_TIMER    # Stop Timer
  off CC_RESET_TIMER   # Toggle Reset Timer down
  on  CC_START_TIMER

  Signal.trap("QUIT") { fade_shuffle_in } # CTRL-\
  Signal.trap("USR1") { fade_shuffle_in } # kill -SIGUSR1 <pid>

  off CC_START_TIMER   # Toggle Start Timer down

  def fade_shuffle_in
    $stdout.puts "[%s] Fade Shuffle In" % Time.now.to_f
    pulse  CC_STOP_TIMER  # Stop Timer
    on  CC_PLAY        # Play Track

    # Fade live input out
    (0.upto(127)).each do |i|
      cc CC_X_FADER, i
      write_serial(i)
      sleep FADETIME
    end

    pulse  CC_RESET_TIMER # Reset Timer

  end

  def fade_shuffle_out
    $stdout.puts "[%s] Fade Shuffle Out" % Time.now.to_f

    (127.downto(0)).each do |i|
      cc CC_X_FADER, i # XFader
      write_serial(i)
      sleep FADETIME
    end
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
