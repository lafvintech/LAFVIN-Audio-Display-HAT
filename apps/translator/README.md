# Translator

Voice translator using Runtime-owned audio, shared ASR/LLM/TTS providers, and
the app-facing Raw Frame UI toolkit.

The provider must be configured explicitly. Missing credentials are displayed
on the device. Use `LAFVIN_AI_PROVIDER=fake` only for an offline deterministic
test.

Set `LAFVIN_TRANSLATOR_TARGET_LANGUAGE` before starting the Runtime to select
the target language. The default is `English`.

Run during development:

```bash
lafvin-hat app run apps/translator --follow
```

Controls:

- single click: switch between `Translate` and `Back`
- double click on `Back`: return Home
- hold `Translate`: record audio
- release while recording: transcribe, translate, stream text, and play TTS

The UI uses the same toolkit path as Chatbot. Long translation output scrolls
to the latest text; smoother Pi Zero 2 W streaming redraw remains a future
performance pass.
