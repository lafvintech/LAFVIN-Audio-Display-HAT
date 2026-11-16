.. _flash-preconfigured-image:

Flash a Preconfigured Image and Get Started
============================================================

This route lets you use the product software with the installation already
complete. The image includes the HAT drivers, Python environment, applications,
and a Runtime service that starts automatically at boot. After flashing the
microSD card and installing the HAT, the device starts in demonstration mode.

.. important::
   Demonstration mode uses preset recognition text, responses, and test audio
   so you can try the interface, button controls, and local interactions.
   Configure your own service API key to enable real speech recognition,
   AI conversations, and translation.

.. Pre-release checklist (not shown in the generated tutorial):
   Verify the image repository JSON URL and its release information.
   Add the tested image version, supported Raspberry Pi models, and minimum
   storage capacity.
   Verify Imager's OS customization against the image's declared init_format.
   Confirm that the preinstalled services work with the pi user.
   Keep compatible OpenAI model and voice defaults in runtime.env even when
   all three Providers use fake; verify the setting names against the image's
   source code.
   Publish tools/configure_openai.py to GitHub and test configuration,
   optional project .env synchronization, permissions, and service restart
   on the final image.
   After an image update, check the screenshots against the supported Imager
   version and final image repository.

What You Need
------------------------------------------------------------

* A Raspberry Pi and Audio Display HAT supported by the image.
* A suitable power supply, microSD card, and card reader. Check the image's
  release notes for supported Raspberry Pi models and minimum storage capacity.
* A Windows, macOS, or Linux computer with internet access.
* Raspberry Pi Imager 2.x, available from the
  `official Raspberry Pi software page <https://www.raspberrypi.com/software/>`_.
* The LAFVIN image repository JSON URL provided below.
* For real AI features, an internet connection on the Raspberry Pi and your
  own service API key.

Step 1: Install Imager and Prepare the Repository URL
------------------------------------------------------------

1. Download and install the latest version of Raspberry Pi Imager on your
   computer.
2. Have the LAFVIN image repository URL below ready to import into Imager.

.. list-table:: Resources
   :header-rows: 1
   :widths: 35 65
   :class: setup-route-table

   * - Resource
     - How to Get It
   * - LAFVIN image repository JSON
     - Copy the repository URL below and paste it into **Use custom URL**
       in Imager.

Image repository URL (copy the complete URL):

.. code-block:: text

   https://www.dropbox.com/scl/fi/62s97u3yvqnnclc6j9k5s/LB011.json?rlkey=3bk9jwadnthiv4dh25c41lbe8&st=718ml3ay&dl=1

The JSON file describes the image repository; it is not the operating system
image itself. Imager reads this URL, lists the available product images, and
downloads the selected image during flashing. You do not need to download
the image separately in advance.

Step 2: Import the LAFVIN Image Repository into Imager
------------------------------------------------------------

1. Open Raspberry Pi Imager and go to **App Options**.

   .. image:: img/2.png
      :align: center
      :alt: App Options in Raspberry Pi Imager

2. Find **Content Repository** and click **Edit**.

   .. image:: img/3.png
      :align: center
      :alt: Content repository source options in Raspberry Pi Imager

3. Select **Use custom URL** and paste the complete repository URL above.

   .. image:: img/4.png
      :align: center
      :alt: Importing the LAFVIN image repository with a custom URL

4. Click **Apply & Restart**. Imager reloads the LAFVIN image list and clears
   the previously selected device model and operating system.

   .. image:: img/5.png
      :align: center
      :alt: Raspberry Pi model selection after loading the LAFVIN image repository

For more information about repository settings, see the
`official Raspberry Pi Imager documentation
<https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#IMAGER_REPO_URL>`_。

.. note::
   If the LAFVIN image list does not appear, check that the JSON URL is
   complete and correct, and that your computer can reach the image download
   server.

Step 3: Flash the Product Image
------------------------------------------------------------

1. Select your Raspberry Pi model on the **Device** page.

2. Select the LAFVIN Audio Display HAT image for that model. Check the image
   version and read its release notes before continuing. The screenshots
   below use a Raspberry Pi 5 as an example.

   .. image:: img/6.png
      :align: center
      :alt: Selecting the LAFVIN Audio Display HAT image for Raspberry Pi 5

3. Select the target microSD card and check its device name and capacity.

   .. image:: img/7.png
      :align: center
      :alt: Selecting the target microSD card in Imager

4. **Configure the first-boot options.**

   Follow the prompts to configure the hostname, localisation, user, Wi-Fi,
   and SSH settings.

   **Hostname**: Give the Raspberry Pi a name you can easily recognize.

   .. image:: img/8.png
      :align: center
      :alt: Setting the Raspberry Pi hostname in Imager

   **Localisation**: Select your region, time zone, and keyboard layout.

   .. image:: img/9.png
      :align: center
      :alt: Setting the region, time zone, and keyboard layout in Imager

   **User**: Enter ``pi`` as the username and set a login password.

   .. important::
      This preconfigured image requires the username ``pi``. Using another
      username may prevent the product software from working correctly.

   .. image:: img/10.png
      :align: center
      :alt: Setting the username to pi and choosing a login password in Imager

   **Wi-Fi**: Enter the network name and password for the Raspberry Pi.

   .. image:: img/11.png
      :align: center
      :alt: Configuring the Raspberry Pi Wi-Fi network in Imager

   **Remote access**: Enable SSH and select **Use password authentication**.

   .. image:: img/12.png
      :align: center
      :alt: Enabling SSH with password authentication in Imager

   .. note::
      Remember the login password you set here. Use the username ``pi`` and
      this password when connecting to the Raspberry Pi through SSH.

5. Review the selected image, target storage device, and OS customization
   settings. Click **WRITE** and confirm that the data can be erased to
   begin flashing.

   .. warning::
      Flashing erases all data on the selected storage device. Before
      confirming, check again that the target is the microSD card you
      prepared.

   .. image:: img/13.png
      :align: center
      :alt: Reviewing the Raspberry Pi model, image, storage, and customization before flashing

6. Wait for the download, writing, and verification to finish. Do not remove
   the card or close Imager during this process.

   .. image:: img/14.png
      :align: center
      :alt: Raspberry Pi Imager writing the product image

7. Safely remove the microSD card when Imager reports that writing is complete.

   .. image:: img/15.png
      :align: center
      :alt: Product image writing complete and the microSD card ready to remove

If the expected user, Wi-Fi, or SSH settings pages do not appear, check the
image's release notes before flashing. These options depend on the image and
its repository configuration. SSH login may be unavailable if you have not
completed the first-boot configuration supported by the image.

If verification fails, try another card reader, microSD card, or USB port,
then flash the image again.

.. _preconfigured-image-first-start:

First Startup and Device Checks
------------------------------------------------------------

1. Power off the Raspberry Pi and disconnect its power supply. Insert the
   flashed card, then install the HAT. See
   :ref:`Install the Audio Display HAT <install-hat>` for the orientation and
   precautions, then return here.
2. Connect a suitable power supply and wait for the first startup to finish.
   Initialization may take a few minutes. Do not disconnect the power.
3. Confirm that the HAT display automatically reaches the Runtime Home screen.
4. Test the button: single-click to move the selection, double-click to open
   an application or confirm an action, and triple-click to return to the
   Home screen. Check that the display and RGB status LED respond as expected.
5. Open Chatbot and try the recording interaction. In demonstration mode,
   the recognition text and replies are preset. Confirm that the speaker
   plays the test audio. Preset results do not verify real speech recognition
   or microphone recording quality.
6. Follow :ref:`First Boot and Login <first-boot-and-login>` to connect through
   SSH, then return here. For this image, use the username ``pi`` and the
   login password you set in Imager.
7. Check the preinstalled services:

   .. code-block:: bash

      systemctl status lafvin-hat --no-pager
      systemctl status wm8960-soundcard --no-pager

The Runtime service should show ``active (running)``, and the WM8960 service
should show ``active (exited)``. If a service fails to start, or the display,
button, or audio does not work correctly, follow
:ref:`Troubleshooting <troubleshooting-guide>` before configuring AI services.

For more detailed microphone and peripheral tests, see
:ref:`Verify the Hardware <verify-hardware>`. Stop the Runtime before running
the interactive hardware test, then restart ``lafvin-hat`` when the test is
complete.

You can continue using demonstration mode without an API key. To enable real
AI interactions, continue to the next section.

.. _preconfigured-image-ai:

Enable Real AI Services
------------------------------------------------------------

The preinstalled service reads its persistent configuration from
``/etc/lafvin-hat/runtime.env``. The OpenAI configuration tool below updates
this file automatically. Changing the project's ``.env`` does not update the
deployed service's configuration.

Prepare your own API key and make sure the API account has available credit.
The OpenAI configuration below uses one ``OPENAI_API_KEY`` for speech
recognition, language model responses, and speech synthesis.

.. warning::
   Cloud API calls may incur charges. OpenAI API usage is billed separately
   from ChatGPT subscriptions. Read the
   `OpenAI API billing information <https://help.openai.com/en/articles/9039756>`_
   before enabling the service. Keep your API key private; do not include it
   in screenshots or messages to technical support.

.. _preconfigured-image-openai-tool:

Use the OpenAI Configuration Tool
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This tool uses only the Python standard library; no additional dependencies
are required.

Run these three commands to retrieve and start the configuration script:

.. code-block:: bash

   cd ~/LAFVIN-Audio-Display-HAT

   git pull

   sudo python3 tools/configure_openai.py

When prompted, type or paste your OpenAI API key. Check the visible first
and last five characters; the middle is masked with asterisks. Use Backspace
to correct the entry, ``Ctrl+U`` to clear it, or ``Ctrl+C`` to cancel.
The script then asks whether to update the project's ``.env`` as well,
as explained below.

The script switches all three Providers to ``openai`` and saves your key,
the official OpenAI API endpoint, and the default models for the three
capabilities. It then restarts and checks ``lafvin-hat.service``:

.. image:: img/config.png
   :align: center
   :alt: OpenAI configuration tool showing a masked API key, project synchronization, and a successful service restart

To choose different models or a voice, use the ``--asr-model``, ``--llm-model``,
``--tts-model``, and ``--voice`` options.

**Should You Also Update the Project's .env?**

After you enter the API key, the script first checks the deployment record
for the project's ``.env``, displays the file path, and asks:

.. code-block:: text

   Also update the project's .env? [y/N]:

Enter ``y`` and press Enter to update both the service configuration and the
project's ``.env``. This lets you run the source code for development and
testing without configuring it again.
Enter ``n`` or press Enter to update only the service's
``/etc/lafvin-hat/runtime.env``.

Synchronization updates only the same OpenAI settings and preserves the
project's other settings. The script does not modify ``.env.example``.

The script does not make an OpenAI API call to validate the key. After setup,
complete a real conversation as described below to verify the network, key,
and available API credit.

Verify Real AI Interactions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Confirm that the service shows ``active (running)`` and that the Home
   screen appears after the restart. A successful service startup alone
   does not prove that the API key or cloud connection works.
2. Open Chatbot and select **Talk**. Hold the button while speaking, then
   release it to submit the recording.
3. Check that the recognition text matches what you said, the response
   answers your question, and the spoken reply plays correctly.
4. If you plan to use Translator, complete a real translation test as well.

If you still receive preset content, check that all three Providers in
``/etc/lafvin-hat/runtime.env`` have been changed and that the service has
restarted. For authentication, credit, model, or network errors, see
:ref:`Troubleshooting <troubleshooting-guide>`. To view recent service logs,
run:

.. code-block:: bash

   sudo journalctl -u lafvin-hat -n 100 --no-pager

After setup, see :ref:`Updates, Logs, and Recovery <update-and-recovery>` for
maintenance and configuration changes, or continue to
:ref:`Application Development <development>` to create your own applications.
