//#include <MIDI.h>
//MIDI_CREATE_DEFAULT_INSTANCE();
#define LED 13              // LED pin on Arduino Uno

int CS_signal = 2;                      // Chip Select signal onsul pin 2 of Arduino
int CLK_signal = 4;                     // Clock signal on pin 4 of Arduino
int MOSI_signal = 5;                    // MOSI signal on pin 5 of Arduino
byte cmd_byte1 = B00010001 ;            // Wiper 1
byte cmd_byte2 = B00010010 ;            // Wiper 2
int initial_value = 100;                // Setting up the initial value

int DELAY = 250;
int FADE_TIME = 20;

void initialize() {                     // send the command byte of value 100 (initial value)
  spi_out(CS_signal, cmd_byte1, initial_value);
  spi_out(CS_signal, cmd_byte2, initial_value);
}

void spi_out(int CS, byte cmd_byte, byte data_byte){                      // we need this function to send command byte and data byte to the chip
  digitalWrite (CS, LOW);                                                 // to start the transmission, the chip select must be low
  spi_transfer(cmd_byte); // invio il COMMAND BYTE
  delay(2);
  spi_transfer(data_byte); // invio il DATA BYTE
  delay(2);
  digitalWrite(CS, HIGH);                                                 // to stop the transmission, the chip select must be high
}

void spi_transfer(byte working) {
  for(int i = 1; i <= 8; i++) {                                           // Set up a loop of 8 iterations (8 bits in a byte)
    if (working > 127) { 
      digitalWrite (MOSI_signal,HIGH) ;                                   // If the MSB is a 1 then set MOSI high
    } else { 
      digitalWrite (MOSI_signal, LOW) ;                                   // If the MSB is a 0 then set MOSI low                                           
    }
    digitalWrite (CLK_signal,HIGH) ;                                      // Pulse the CLK_signal high
    working = working << 1 ;                                              // Bit-shift the working byte
    digitalWrite(CLK_signal,LOW) ;                                        // Pulse the CLK_signal low
  }
}

void setup() {
  pinMode (CS_signal, OUTPUT);
  pinMode (CLK_signal, OUTPUT);
  pinMode (MOSI_signal, OUTPUT);
  pinMode(LED, OUTPUT);
//  MIDI.begin(1);                                                          // Launch MIDI and listen to channel 4

  initialize();

  Serial.begin(9600);                                                     // setting the serial speed
  Serial.println("ready!");
}

void loop() {
  for (int i = 0; i < FADE_TIME; i++) {
    spi_out(CS_signal, cmd_byte1, i); 
    spi_out(CS_signal, cmd_byte2, i); 
    Serial.println(i); 
    delay(DELAY); 
  }
  for (int i = (255 - FADE_TIME); i < 255; i++) {
    spi_out(CS_signal, cmd_byte1, i); 
    spi_out(CS_signal, cmd_byte2, i); 
    Serial.println(i); 
    delay(DELAY); 
  }
  delay(5000);
  for (int i = 255; i > (255 - FADE_TIME); --i) {
    spi_out(CS_signal, cmd_byte1, i);
    spi_out(CS_signal, cmd_byte2, i);
    Serial.println(i);
    delay(DELAY);
  }
  for (int i = FADE_TIME; i > 0; --i) {
    spi_out(CS_signal, cmd_byte1, i);
    spi_out(CS_signal, cmd_byte2, i);
    Serial.println(i);
    delay(DELAY);
  }
  delay(5000);
//  if (MIDI.read()) {            // If we have received a message
//
//    
//    digitalWrite(LED,HIGH);
////    MIDI.sendNoteOn(42,127,1);  // Send a Note (pitch 42, velo 127 on channel 1)
//    delay(1000);                // Wait for a second
////    MIDI.sendNoteOff(42,0,1);   // Stop the note
//    digitalWrite(LED,LOW);
//    Serial.println(MIDI.getType());
////    switch(MIDI.getType())      // Get the type of the message we caught
////    {
////      case midi::ProgramChange:     // If it is a Program Change,
////        Serial.println(MIDI.getData1());
////
//////        BlinkLed(MIDI.getData1());  // blink the LED a number of times
////                                    // correponding to the program number
////                                    // (0 to 127, it can last a while..)
////        break;
////        // See the online reference for other message types
////        default:
////          break;
////    }
//  }
}

