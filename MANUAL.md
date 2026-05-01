# CONTROLS

`space`
:   Start capturing audio input. Double tap `space` to stop capturing audio input and start transcription process.

`esc`
:   CANCEL operation at any time including while recording, transcribing, or after results have been produced.

`m`
:   Cycle through models to the next one.

`M`
:   Cycle through models backwards.

`h`
:   Toggle showing/hiding development statistics panel.

`q`
:   Quit.

# MODELS

There are five models included in tinytalk which you can cycle forward or backwards using `m` / `M`.

| Label | Model Name            | Notes                        |
|-------|-----------------------|------------------------------|
| TINY  | whisper-tiny          | Fastest but least accurate   |
| BASE  | whisper-base          |                              |
| SMALL | whisper-small         |                              |
| MEDIUM| whisper-medium        |                              |
| TURBO | whisper-large-v3-turbo| Default – Best trade-off     |

Model icon represents its status as follows:

- `✗` — Not installed. Run `huggingface-cli download` to get it.
- `↓` — Installed and cached on disk.
- `●` — Loaded and hot. Next transcription with this model will be instant.

Use huggingface-cli to download a model:

```bash
huggingface-cli download mlx-community/whisper-large-v3-turbo
```

# INSTALLATION

Prerequisites: Python 3.11 or greater + Apple silicon machine (MLX).

**Recommended (pipx):**

```bash
git clone https://github.com/DamienBlackwood/tinytalk.git
cd tinytalk
pipx install .
```

Now you can execute `tinytalk` from any directory.

**Manual (venv):**

```bash
python -m venv venv &amp;amp;&amp;amp; source venv/bin/activate
pip install -e .
tinytalk
```

# FILES

`.tinytalk/config.json`
:   Tinytalk configuration file for the current project directory. Stores index of currently selected model and dev overlay state.

Supported keys:

```json
{
  "model_idx": 4,
  "show_dev": false,
  "ascii": false
}
```

Setting `"ascii": true` allows tinytalk to run in environments where block elements are unsupported.

# TERMINAL

In order to run optimally, tinytalk requires terminals supporting Nerd Fonts or any font containing Block Elements Unicode range.

For Ghostty use, tinytalk forces `TERM` to `xterm-256color` because of the character width bug with `xterm-ghostty`.