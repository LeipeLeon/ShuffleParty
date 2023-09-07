
var fs = require('fs'),
xml2js = require('xml2js');
const util = require('util');

var parser = new xml2js.Parser();
fs.readFile(__dirname + '/Shuffle.nml', function(err, data) {
  parser.parseString(data, function (err, result) {
    // console.dir(util.inspect(result.NML.COLLECTION, false, null));
    // console.dir(result.NML.COLLECTION);
    console.dir(result.NML.COLLECTION[0].ENTRY).forEach(function(element) {
      console.log(util.inspect(element, false, null));
      // console.log(JSON.stringify(element));
    });
    // console.log('Done');
  });
});
