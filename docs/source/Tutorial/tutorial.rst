Installation and Deployment
===========================

.. _tutorial:

This section covers the complete first-time installation workflow. You will
install the hardware drivers, verify all onboard peripherals, configure the
Runtime, and finally deploy it as a systemd service. Do not run a manually
started Runtime and ``lafvin-hat.service`` at the same time because they will
compete for access to the display, GPIO, and audio devices.

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Stage
     - Purpose
     - Completion criteria
   * - Install the project and drivers
     - Clone the project and install the WM8960 and interface configuration
     - The Raspberry Pi has restarted with the new hardware configuration
   * - Verify the hardware
     - Test the drivers, display, RGB LED, button, speaker, and microphones
     - The check commands report 0 failures
   * - Configure and test the Runtime
     - Create the project environment and configure a cloud AI service
     - The Home screen and live AI features work correctly
   * - Deploy the Runtime
     - Register the Runtime to start automatically at boot
     - The service reports ``active (running)``

.. toctree::
   :maxdepth: 2

   1.clone_and_install_driver
   2.verify_hardware
   3.configure_runtime
   4.run_and_deploy
