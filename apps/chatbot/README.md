# AI Chatbot

Voice chatbot using Runtime-owned audio, streaming LLM text, sentence-level
TTS, and the app-facing Raw Frame UI toolkit. The first complete response
sentence is synthesized immediately; later short sentences are combined into
medium speech chunks to reduce request and playback-start overhead on slower
devices.

The 240x280 interface uses a top-left status label and one centered Twemoji
image instead of a fixed title and divider. Six selected PNGs represent Ready,
Listening, Thinking, Speaking, request error, and configuration error states.
The files are loaded once from `assets/emoji/`, resized with LANCZOS filtering,
and reused without installing an emoji font or a complete emoji library.

The app reads provider settings from the Runtime process environment. A
provider must be configured explicitly. Missing provider credentials are shown
on the device instead of silently selecting a demo response.

The Chatbot exposes four allowlisted device tools to LLM Providers that support
native Tool Calling:

- `get_device_status`: read model, hostname, IP address, Runtime uptime, CPU,
  memory, temperature, storage, and installed-App count
- `get_volume`: read speaker volume
- `set_volume`: set speaker volume from 0 to 100 percent
- `set_rgb_led`: set red, green, and blue channels from 0 to 255

No MCP server or plugin is required. OpenAI, DeepSeek, Kimi, compatible Chat
Completions endpoints, and Claude use their native tool-call formats. Custom
OpenAI-compatible endpoints must implement the `tools` and `tool_calls` parts
of the Chat Completions protocol. The Fake Provider does not invoke tools.

Device operations remain Runtime-owned. Volume uses the Audio SDK, and RGB
writes require the Chatbot's authenticated foreground session and `led`
permission. Only the selected status fields above are returned to the LLM;
because they are included in the model request, do not enable these tools when
that device information must not leave the device. Disable them with:

```ini
LAFVIN_CHATBOT_TOOLS_ENABLED=0
```

The tools are enabled by default.

For offline testing, explicitly set `LAFVIN_ASR_PROVIDER`,
`LAFVIN_LLM_PROVIDER`, and `LAFVIN_TTS_PROVIDER` to `fake`.

Run during development:

```bash
lafvin-hat app run apps/chatbot --follow
```

System deployments can use the shorter management CLI:

```bash
lafvin-hat app run apps/chatbot
lafvin-hat logs dev.lafvin.chatbot --follow
```

Controls:

- single click: switch between `Talk` and `Back`
- double click on `Back`: return Home
- hold `Talk`: record audio
- release while recording: submit audio
- press again while an answer is active: interrupt the current LLM stream,
  queued speech, and playback before starting a new recording

Example requests:

- "What are the current CPU and memory usage values?"
- "What is the speaker volume?"
- "Set the volume to 60 percent."
- "Set the RGB light to purple."

Numeric values remain intact across arbitrary LLM stream boundaries. Displayed
text keeps its original form while speech says IPv4 separators as `dot`,
decimal/version separators as `point`, and CJK numeric separators as `点`.

Known limit: Pi Zero 2 W can still show fewer smooth scroll frames than Pi 5
during very long replies. Audio playback no longer waits for the initial
long-text layout calculation, but cached layout and partial-frame display
updates remain possible later UI optimizations.
