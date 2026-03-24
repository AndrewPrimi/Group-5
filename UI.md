
1) Function Generator:
    a. Produce an X-axis centered square wave with adjustability:
    i. Use the UI to produce a variable amplitude within the range of +/- 10V.
    1. The square wave should be centered at 0V.
    2. The resolution for x-axis and peak values should be within 0.3125V and
    all values should shift in the same relative direction.
    ii. Use the UI to change the frequency to any value from 100Hz-10KHz.
    1. The duty cycle should be 50%.
    b. Use UI to display the live values being outputted.
    c. The function generator should not drive current and should be considered High Z.
2) Ohmmeter:
    a. Measures from 500-10KΩ range from external resistance input and display to the user
    how close to the true value they are (i.e. 50Ω +/- YΩ). Y should be representative of the
    value that is true to your design. This should be derived in your documentation. The
    Ohmeter should be autoranging.
    b. Use UI to report back values to user.
3) Voltmeter:
    a. Must be able to measure a DC voltage from +/- 5V and display to the user how close to
    the true value they are (i.e. 2.5V +/- 0.3125V).
    b. Use UI to report back values to user.
    c. Must be able to measure voltage from an external supply OR from your DC voltage
    reference (see next).
4) DC Voltage Reference
    a. Measure with High Z.
    b. This is a reference which does not supply high current.
    c. Output is +/- 5V in 0.625V steps.
    d. Use UI to control the output.
    e. Use UI to report back values to user.





a. UI must use the rotating feature to scroll through selections and the push button feature
to select/input. Each selectable area must have a return to Main and a Back select. The
back select takes the UI back one in the tree.
b. The Main level UI is:
i. OFF: Everything is off.
ii. Mode Select
1. Function Generator
    a. Type
        i. Square
        ii. Back
        iii. Main
    b. Frequency
        i. Input Frequency
        ii. Back
        iii. Main
    c. Amplitude
        i. Input Amplitude
        ii. Back
        iii. Main
    d. Output
        i. On (Note: if you back out of this or go to main, must
        turn off by default). UI must show value of generated
        output.
        ii. Off
        iii. Back
        iv. Main
2. Ohmmeter (UI shows value of reading and threshold)
    a. Back
    b. Main
3. Voltmeter (UI show value of reading and show threshold)
    a. Source
        i. External
        ii. Internal Reference (If selected go to DC Reference)
        iii. Back
        iv. Main
4. DC Reference
    a. Voltage Value Input
    b. Output
        i. On (note if you back out of this or go to main, must turn
        off by default). UI must show value of generated
        output. UI must show value of generated output using
        your Voltmeter!)
        ii. Off
        iii. Back
        iv. Main
    c. Back
    d. Main
5. Back
6. Main

(Indenting should help with organization when you read this file)