.. _uninstall-runtime-and-drivers:

Uninstall the Runtime and Drivers
=================================

First, decide what you want to remove. By default, the uninstall scripts use a
safe preservation policy: they do not automatically delete API keys,
application data, logs, or the project source code. Follow the full cleanup
steps only when you are preparing to transfer, sell, or dispose of the device.

Choose What to Remove
---------------------

.. list-table::
   :header-rows: 1
   :widths: 28 42 30

   * - Goal
     - Action
     - Preserved by Default
   * - Remove one custom application
     - Follow :ref:`Update or Uninstall the Application <update-or-uninstall-app>`
       and run ``app uninstall``
     - Original application source code and separately stored logs
   * - Stop the Runtime from starting at boot
     - Remove the Runtime deployment
     - Project files, configuration, application data, logs, and the hardware
       profile
   * - Stop using the Audio Display HAT
     - Remove the Runtime deployment, then remove the WM8960 profile
     - Project files, Runtime data, packages, fonts, and shared interface
       settings
   * - Transfer, sell, or dispose of the device
     - Run the uninstall scripts, delete the preserved data, and revoke the API
       key
     - Only files that you explicitly choose to keep

Before You Begin
----------------

* Run the uninstall commands from the project directory. Do not use a copy of
  the scripts from an unknown source.
* Back up any configuration, custom applications, or logs that you want to
  keep.
* To remove an individual custom application, do so before removing the Runtime
  and the global ``lafvin-hat`` command.
* Always run each uninstall script with ``--dry-run`` first. Review the proposed
  changes before performing the actual uninstall.

.. note::
   The uninstall scripts rely on deployment and hardware ownership records
   created during installation. If the required record is missing, the script
   stops instead of guessing which files it can safely delete.

Remove the Runtime Deployment
-----------------------------

On the Raspberry Pi, open the project directory and preview the uninstall plan:

.. code-block:: bash

   cd ~/LAFVIN-Audio-Display-HAT
   sudo bash deploy/uninstall_raspberry_pi.sh --dry-run

Check that the listed services, command links, and preserved paths are correct.
Then run:

.. code-block:: bash

   sudo bash deploy/uninstall_raspberry_pi.sh --yes

The script stops and removes ``lafvin-hat.service``, then removes the global
command links and deployment metadata managed by the installer. It preserves:

* The project directory and its ``.venv``;
* The persistent configuration in ``/etc/lafvin-hat/runtime.env``;
* Runtime data and installed applications in ``/var/lib/lafvin-hat``;
* Logs in ``/var/log/lafvin-hat``;
* Packages, interface settings, and the WM8960 hardware profile.

.. warning::
   ``/etc/lafvin-hat/runtime.env`` may contain an API key. Removing the Runtime
   service does not delete this file or revoke the key with the API provider.

After the script finishes, check the result:

.. code-block:: bash

   systemctl status lafvin-hat --no-pager
   ls -l /usr/local/bin/lafvin-hat

Systemd should report that ``lafvin-hat.service`` cannot be found, and the
global command link should no longer exist. If the current shell has the
project's ``.venv`` activated, it may still find ``lafvin-hat`` inside the
virtual environment. This does not mean that the systemd deployment still
exists.

Remove the WM8960 Hardware Profile
----------------------------------

Follow this section only if you no longer plan to use the Audio Display HAT.
Stop or remove the Runtime service first. The hardware uninstall script refuses
to continue while ``lafvin-hat.service`` is still running.

Preview the hardware uninstall plan:

.. code-block:: bash

   cd ~/LAFVIN-Audio-Display-HAT
   sudo bash uninstall_driver.sh --dry-run

After reviewing the plan, run:

.. code-block:: bash

   sudo bash uninstall_driver.sh --yes

The script removes only the WM8960 service, helper program, profile,
WirePlumber rule, modules, and boot configuration recorded as LAFVIN-owned by
the installer. When backups are available, it restores the files that existed
before installation. It preserves the project, Runtime configuration and data,
logs, APT packages, fonts, and shared SPI/I2C settings.

If the HAT remains attached and you want to continue using the Raspberry Pi,
restart it to unload the active modules:

.. code-block:: bash

   sudo reboot

After the restart, check the result:

.. code-block:: bash

   systemctl status wm8960-soundcard --no-pager
   aplay -l

Systemd should report that ``wm8960-soundcard.service`` cannot be found, and
WM8960 should no longer appear in the sound card list.

Safely Remove the HAT
---------------------

If you plan to physically remove the HAT from the Raspberry Pi, do not restart
after uninstalling the driver. Shut down the Raspberry Pi instead:

.. code-block:: bash

   sudo poweroff

Wait for the Raspberry Pi to shut down completely, disconnect the power cable,
and then lift the HAT straight up from the 40-pin GPIO header while keeping it
level. Hold the PCB by its edges; do not pull or press on the display.

.. danger::
   Never install or remove the HAT while the Raspberry Pi is powered. Doing so
   may damage the Raspberry Pi, the HAT, or the GPIO interface.

Optional: Delete Preserved Data
-------------------------------

Follow this section only if you no longer need to restore the configuration,
applications, or logs. First, inspect the contents of each directory:

.. code-block:: bash

   sudo ls -la /etc/lafvin-hat
   sudo ls -la /var/lib/lafvin-hat
   sudo ls -la /var/log/lafvin-hat
   ls -la ~/LAFVIN-Audio-Display-HAT

.. danger::
   The following operations cannot be undone. Confirm that your backup is
   complete and verify each path before continuing. Do not use wildcards, and
   never select ``/home``, your home directory, or another parent directory as
   the deletion target.

Delete the persistent configuration, Runtime data, and logs:

.. code-block:: bash

   sudo rm -rI -- /etc/lafvin-hat
   sudo rm -rI -- /var/lib/lafvin-hat
   sudo rm -rI -- /var/log/lafvin-hat

Each command asks for confirmation before recursively deleting the directory.
Before deleting the project source code, return to your home directory and
verify the target again:

.. code-block:: bash

   cd ~
   pwd
   ls -ld LAFVIN-Audio-Display-HAT
   rm -rI -- LAFVIN-Audio-Display-HAT

The hardware uninstall process may leave pre-installation backups in
``/var/backups/lafvin-hat``. Consider deleting this backup directory separately
only after confirming that the system works correctly and that you will not
need to restore those files. The uninstall scripts do not automatically remove
shared packages or fonts because other programs may still depend on them.

If you are transferring the device to another person, also revoke or rotate the
API key through the corresponding cloud provider. Deleting the local
configuration file does not invalidate a key that may already have been
exposed.

Reinstall
---------

If you removed only the Runtime deployment and preserved the project,
configuration, and data, run the installer again from the project directory:

.. code-block:: bash

   sudo bash deploy/install_raspberry_pi.sh

If you also removed the WM8960 profile, run ``install_driver.sh`` again and
restart the Raspberry Pi before redeploying the Runtime. The preserved
``runtime.env``, application data, and logs can be reused.
