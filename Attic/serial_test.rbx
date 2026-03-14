#!/usr/bin/env ruby

require 'serialport'

# SerialPort.new "/dev/tty.usbmodem1451", 9600 do
#   write 0
#   write "\n"
# end

#params for serial port
baud_rate = 9600
data_bits = 8
stop_bits = 1
parity    = SerialPort::NONE

tries_cnt = 0
begin
  port_str = [
    "/dev/ttyACM0", # Raspbian
    "/dev/tty.usbmodemfd121",  # OS X
    "/dev/tty.usbmodem1451",
  ][tries_cnt]

  @sp = SerialPort.new(port_str, baud_rate, data_bits, stop_bits, parity)
  p [:info, "Connected on #{port_str}"]
rescue Errno::ENOENT => e
  p [:warning, "No Serial Port for: #{port_str}, trying next."]
  tries_cnt += 1
  retry
rescue TypeError => e
  p [:error, "Couldn't find any suitable Serial Port. Exiting."]
  exit
end

sleep(5) #Give the port some time to connect. 1s too fast, 2s works, 3s just in case
@sp.write "0\n"
# @read_ser_thread = Thread.new do
#
#   @sp.flush # Clean it out before we go
#
#   while line = @sp.readline
#     line = line.strip
#
#     p line
#   end
# end
