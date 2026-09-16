.. _release_checklist:

Documentation Release Checklist
===============================

This page is for documentation maintainers to review before a release. It is
not part of the first-time installation workflow.

Content
-------

* The product name is always written as ``LAFVIN Audio Display HAT``.
* The specifications, package contents, and supported Raspberry Pi models match
  the product being shipped.
* All commands have been verified against the current project version, and the
  repository URL and script paths are correct.
* Third-party API account, key, and billing requirements are clearly explained
  before the configuration steps.
* Troubleshooting entries follow the ``Symptom``, ``Possible causes``, and
  ``Solutions`` structure.

Images and Screenshots
----------------------

* The product overview includes a front view and a labeled interface diagram.
* The HAT installation page includes photos of GPIO alignment, the completed
  installation, and the speaker connector.
* Screenshots of Raspberry Pi Imager, SSH login, and deployment status appear
  immediately after the steps they support.
* Screenshots do not contain Wi-Fi passwords, API keys, IP addresses, or other
  personal information.
* Images are stored in ``docs/source/img/`` and referenced with relative paths.
  Every image directive includes descriptive ``:alt:`` text.

Build
-----

Run the Sphinx build:

.. code-block:: powershell

   cd docs
   .\make.bat html

Before publishing, scan for leftover template text:

.. code-block:: powershell

   rg -n "{{|TODO|FIXME|ESP32|Arduino|ESP-IDF|image file not readable" docs/source -S
