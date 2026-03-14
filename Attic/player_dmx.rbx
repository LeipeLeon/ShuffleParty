#!/usr/bin/env ruby

require './vendor/rdmx/rdmx'

include Rdmx

class Led < Fixture
  self.channels = :red, :green, :blue
end

class SwitchPack < Fixture
  self.channels = :one, :two, :three, :four
end

@u = Universe.new('/dev/tty.usbserial-EN095377', SwitchPack => 1)
puts @u.inspect
puts @u.fixtures.inspect
@u.fixtures[0].all = 255, 0, 0, 0
puts @u.fixtures[0].inspect
sleep 0.5
@u.fixtures[0].all = 0, 255, 0, 0
sleep 0.5
@u.fixtures[0].all = 0, 0, 255, 0
sleep 0.5
@u.fixtures[0].all = 0, 0, 0, 255


# blink = Animation.new do
#   frame.new do
#     puts "blinking red and green, then green and blue"
#     100.times do
#       @u.first[0..-1] = 255, 255, 0; continue
#       @u.first[0..-1] = 0, 120, 255; continue
#     end
#   end
# end
# 
# fade = Animation.new do
#   frame.new do
#     puts "fading in blue"
#     (0..255).over(10.seconds).each{|v|@u.first[0..-1] = 0, 0, v.to_f.round; continue}
#   end
# end
# 
# xfade = Animation.new do
#   frame.new do
#     puts "cross-fading red and blue"
#     (255..0).over(10.seconds).each do |v|
#       @u.first.fixtures.each{|f|f.red = v.to_f.round}
#       continue
#     end
#   end
# 
#   frame.new do
#     (0..255).over(10.seconds).each do |v|
#       @u.first.fixtures.each{|f|f.blue = v.to_f.round}
#       continue
#     end
#   end
# end

# ll = Layers.new 2, @u.first
# layers = Animation.new do
#   frame.new do
#     puts "foreground/background blending with green fading in"
#     (0..255).over(10.seconds).each do |v|
#       ll.first[0..-1] = 255, 0, 255
#       ll.last[0..-1] = 255, v.to_f.round, 255
#       ll.apply!
#       continue
#     end
#   end
# end
# 
# blink.go!
# fade.go!
# xfade.go!
# layers.go!
