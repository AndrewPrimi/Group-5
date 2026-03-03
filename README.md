# Electronics Tool Bench – Group 5

This repository is used to store coursework, scripts, and supporting materials for our electronics and embedded systems projects throughout the semester. It includes work completed using tools such as the Raspberry Pi and GitHub for collaborative development.

## Course Deliverables
 - Documentaton under Technical_Documenation Folder
 - User Manual under User_Manual folder
 - Current Status of these files are relevant to the status of the completion of the project, these files updated with every deliverable and checkpoint

### Deliverable 2 – Raspberry Pi Hello World (RP4)
- File(s): HelloWorldPI.py, HelloWorldScripts
- Description: Python script used to verify Raspberry Pi setup and GitHub integration. The script was run successfully on the Raspberry Pi as part of the assignment. Practice GitHub Commit files. 

### Deiverable 3 - DigiPot and Rotary Encoder
- File(s): gpio_status.py, gpio_status_simple.py, potentiometer.py, LED_ON_OFF.py
- Description: Scripts used to setup GPIO ports and to use the digital potentiometer (change resistance) and rotary encoder (turn off/on an LED), LED turn off and on script.

### Deliverable 4 – Power Supply Simulation, CAD, GPIO Diagram and Power Diagram
- File(s): Deliverable_4.pdf, KiCad_Files, Multisim_Schematics
- Description: GPIO and power diagrams, ±12 V power supply simulation, and initial PCB CAD design using KiCad for future Pi-HAT development.

### Deliverable 5 – Checkpoint C (DigiPot User Interface)  
- File(s): Checkpoint_C_Code (name your Checkpoint “C” code clearly), updated weekly documentation + demo video
- Description: Rotary encoder + LCD user interface to set and display digipot resistance. Slow spin adjusts by 10 Ω and fast spin adjusts by 100 Ω, with a selectable range of 100 Ω to 10 kΩ. Pressing the encoder selects/sets the value and programs the digipot (verified with a multimeter). The UI must allow selecting which side of the dual digipot is being controlled and each side must be independent. Holding the knob for 3 seconds returns to the primary selection screen. No LCD buttons are used and the system should not reboot between resistance changes.

### Deliverable 6 – ±12 V Supply Under Load, 5-bit ADC Simulation, and PCB Schematic Updates
- File(s): Deliverable_6.pdf, KiCad_Files, Multisim_Schematics, updated weekly documentation
- Description: Updated and validated the split-rail ±12 V power supply to ensure stability with no load and with an approximate 50 mA load on both rails. Documented and clarified system ground/reference behavior, including the virtual ground midpoint concept. Developed and simulated a 5-bit-equivalent ADC design using a SAR-based approach with an R-2R DAC, sample-and-hold circuit, and LM339 comparator. Updated the Pi-Hat protector KiCad schematic/PCB to include the ±12 V supply nets (+12 V, GND, −12 V), ADC routing concepts, and initial layout/routing screenshots with key design decisions and debugging considerations (labels, test points, footprints).

### Deliverable 7 – Physical ADC, Ohmmeter, Voltmeter
- File(s): N/A
- Description: 
  
Additional deliverables will be added to this repository as the semester progresses.

## Group Members
- Andrew Primiano  
- Logan Griffy  
- Tillman Clark  
- George Braun
- Kai DeVito
