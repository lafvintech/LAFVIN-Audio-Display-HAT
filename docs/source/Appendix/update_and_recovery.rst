.. _update-and-recovery:

Updates, Logs, and Recovery
===========================

Update a Deployed Project
-------------------------

For a standard Runtime or built-in application source update, run:

.. code-block:: bash

   cd ~/LAFVIN-Audio-Display-HAT
   git pull
   sudo systemctl restart lafvin-hat

If ``pyproject.toml``, the Python dependencies, or deployment resources have
changed, run the installer again:

.. code-block:: bash

   cd ~/LAFVIN-Audio-Display-HAT
   git pull
   sudo bash deploy/install_raspberry_pi.sh
   sudo systemctl restart lafvin-hat

If ``install_driver.sh``, ``deploy/hardware/``, or the WM8960 profile has been
updated, stop the Runtime before updating the hardware configuration and
restarting the Raspberry Pi:

.. code-block:: bash

   sudo systemctl stop lafvin-hat
   sudo bash install_driver.sh --yes
   sudo reboot

After the restart, run ``sudo bash install_driver.sh --check``. The check
should complete without reporting any failures.

Check the Status and Logs
-------------------------

.. code-block:: bash

   sudo systemctl status lafvin-hat --no-pager
   sudo journalctl -u lafvin-hat -n 100 --no-pager
   lafvin-hat app list
   lafvin-hat logs dev.lafvin.chatbot --follow

Modify the Persistent Configuration
-----------------------------------

The deployed Runtime uses the persistent configuration file at
``/etc/lafvin-hat/runtime.env``:

.. code-block:: bash

   sudo nano /etc/lafvin-hat/runtime.env
   sudo systemctl restart lafvin-hat

To intentionally replace the persistent configuration with the project's
``.env`` file, run:

.. code-block:: bash

   sudo bash deploy/install_raspberry_pi.sh --import-project-env

The installer backs up the existing persistent configuration before replacing
it. Do not move the project directory after deployment. If you have moved it,
run ``sudo bash deploy/install_raspberry_pi.sh`` again from the new location.

To remove the Runtime, the WM8960 profile, or the HAT, see
:ref:`Uninstall the Runtime and Drivers <uninstall-runtime-and-drivers>`.
