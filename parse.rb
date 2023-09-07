require 'nokogiri'


doc = File.open("Shuffle.nml") { |f| Nokogiri::XML(f) }
# puts doc
doc.xpath('//COLLECTION//ENTRY').each do |thing|
  puts thing.attr('TITLE')
  # puts "TITLE= " + thing.at_xpath('TITLE').content
  # puts "Name = " + thing.at_xpath('Name').content
end
