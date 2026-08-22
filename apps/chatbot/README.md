# AI Chatbot

Voice chatbot using Runtime-owned audio, streaming LLM text, sentence-level
TTS, and the app-facing Raw Frame UI toolkit.

The app reads provider settings from the Runtime process environment. A
provider must be configured explicitly. Missing provider credentials are shown
on the device instead of silently selecting a demo response.

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

Known limit: long replies scroll to the latest text, but Pi Zero 2 W can show
visible streaming redraw stutter. This is a later performance optimization,
not a functional blocker.
