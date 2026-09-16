App Development
===============

.. _development:

This section is intended for users who want to modify the built-in applications
or create their own. You can run the project in WSL2 on Windows and open the
Web Simulator in Chrome to preview the interface, simulate button input, and
view application logs without a Raspberry Pi or HAT.

.. note::

   WSL2 and the Web Simulator are suitable for validating application logic,
   interface layouts, button flows, and Runtime/SDK communication. They cannot
   replace GPIO, SPI, WM8960, microphone, or speaker testing on a Raspberry Pi.
   Before release, complete the real-hardware validation described in Part 3.

Follow these stages in order:

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - Stage
     - What you will learn
     - Completion criteria
   * - Understand the architecture
     - Distinguish the Runtime, SDK, UI Toolkit, applications, and device backends
     - You know which layer should contain each type of code
   * - Set up WSL2
     - Install the development dependencies and start the simulator Runtime
     - Chrome can open the simulator Home screen
   * - Develop an application
     - Create a minimal application, test it in the simulator and on a real HAT,
       then install it persistently in the Runtime
     - The application remains on the Home screen and starts normally after the
       Runtime restarts

.. toctree::
   :maxdepth: 2

   1.project_architecture
   2.wsl2_and_simulator
   3.develop_an_app
