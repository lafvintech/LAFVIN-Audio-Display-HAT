.. _preparation-guide:

Prepare the Raspberry Pi
========================

This section prepares the Raspberry Pi and establishes the first login. The
project software is not installed yet. For a first-time setup, complete the
steps in this order:

1. Use Raspberry Pi Imager to write Raspberry Pi OS to the microSD card and
   configure the network and SSH in advance.
2. Install the Audio Display HAT while the Raspberry Pi is completely powered
   off.
3. Start the Raspberry Pi for the first time and log in through SSH or a local
   desktop terminal.

.. warning::
   Power off the Raspberry Pi and disconnect its power supply before working
   with the HAT, the 40-pin GPIO header, or the speaker connector. Never
   install or remove the HAT while the Raspberry Pi is powered on.

After completing this section, you should be able to log in to the Raspberry
Pi from a terminal and access the internet.

.. toctree::
   :maxdepth: 2

   1.flash_raspberry_pi_os
   2.install_hat
   3.first_boot_and_login
