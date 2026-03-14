int CS_signal = 2;                      // Chip Select signal onsul pin 2 of Arduino
int CLK_signal = 4;                     // Clock signal on pin 4 of Arduino
int MOSI_signal = 5;                    // MOSI signal on pin 5 of Arduino
byte cmd_byte1 = B00010001 ;            // Wiper 1
byte cmd_byte2 = B00010010 ;            // Wiper 2
int initial_value = 127;                // Setting up the initial fader value

String inString = "";    // string to hold serial input

void spi_out(int CS, byte cmd_byte, byte data_byte){                      // we need this function to send command byte and data byte to the chip
  digitalWrite (CS, LOW);                                                 // to start the transmission, the chip select must be low
  spi_transfer(cmd_byte);  // COMMAND BYTE
  delay(2);
  spi_transfer(data_byte); // DATA BYTE
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

  spi_out(CS_signal, cmd_byte1, initial_value);
  spi_out(CS_signal, cmd_byte2, initial_value);

  Serial.begin(9600);                                                     // setting the serial speed
}

void loop() {
  while (Serial.available() > 0) {
    int inChar = Serial.read();
    if (isDigit(inChar)) {
      // convert the incoming byte to a char
      // and add it to the string:
      inString += (char)inChar;
    }
    // if you get a newline, print the string,
    // then the string's value:
    if (inChar == '\n') {
      spi_out(CS_signal, cmd_byte1, inString.toInt()); 
      spi_out(CS_signal, cmd_byte2, inString.toInt()); 
//      Serial.print("Value: ");
//      Serial.println(inString.toInt());
//      Serial.print("String: ");
//      Serial.println(inString);
      // clear the string for new input:
      inString = "";
    }
  }
}

