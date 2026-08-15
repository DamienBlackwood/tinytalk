"""
Run with:  python -m unittest discover tests

Nothing exhaustive. These are the things I actually broke at least once, so
they're the things worth keeping an eye on.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

_TMP_HOME = tempfile.mkdtemp(prefix="tinytalk-test-")
os.environ["TINYTALK_HOME"] = _TMP_HOME

import numpy as np

from tinytalk import app as app_module
from tinytalk import audio, backend, crypto, render, transcripts


class Wrapping(unittest.TestCase):
    def test_wraps_at_the_boundary(self):
        self.assertEqual(render.wrap("aaa bbb ccc", 7), ["aaa bbb", "ccc"])

    def test_a_word_longer_than_the_line_gets_split(self):
        self.assertEqual(render.wrap("x" * 10, 4), ["xxxx", "xxxx", "xx"])

    def test_no_line_ever_exceeds_the_width(self):
        text = "supercalifragilistic and some shorter ones too, plus another long one"
        for width in range(1, 40):
            for line in render.wrap(text, width):
                self.assertLessEqual(len(line), width, f"width={width}")

    def test_empty_and_silly_widths(self):
        self.assertEqual(render.wrap("", 10), [])
        self.assertEqual(render.wrap("hello", 0), [])


class Layout(unittest.TestCase):
    """compose() and app.py used to disagree about how wide the text was, which
    made the down arrow stop one line early on some terminal sizes."""

    def test_viewport_matches_what_compose_draws(self):
        for w, h in ((60, 18), (80, 24), (120, 40), (200, 60)):
            tx_w, rows = render.text_view(w, h)
            self.assertGreaterEqual(tx_w, 1)
            self.assertGreaterEqual(rows, 1)
            self.assertLessEqual(tx_w, w)

    def test_nothing_gets_drawn_outside_the_screen(self):
        theme = render.Theme()
        long_text = "word " * 400
        for use_ascii in (False, True):
            render.USE_ASCII = use_ascii
            for state in ("idle", "listening", "draining", "processing", "done"):
                for w, h in ((60, 18), (80, 24), (137, 41), (200, 60)):
                    rs = render.RenderState(
                        w=w, h=h, state=state, transcript=long_text, type_pos=97,
                        err="", tick=37, spin_i=5,
                        hist=np.linspace(0, 0.2, 180, dtype=np.float32),
                        show_dev=True, dev_rows=[("model", "TURBO"), ("audio", "4.2s")],
                        version="v0.4",
                        model="TURBO", wave_ceil=0.1, done_tick=3, theme=theme,
                        proc_tick=200, download_pct=0.42, word_count=12,
                        audio_secs=3.5, scroll_offset=2,
                    )
                    for y, x, text, _attr in render.compose(rs):
                        self.assertGreaterEqual(x, 0)
                        self.assertGreaterEqual(y, 0)
                        self.assertLess(y, h, f"{state} {w}x{h}: row {y}")
                        self.assertLessEqual(x + len(text), w,
                                             f"{state} {w}x{h}: {text!r} overruns")
        render.USE_ASCII = False

    def test_the_transcript_actually_fits_at_every_size_we_claim_to_support(self):
        theme = render.Theme()
        text  = "the quick brown fox jumps over the lazy dog and keeps on going"
        DEV   = [("model", "TURBO"), ("audio", "4.2s"), ("decode", "1.1s")]
        for show_dev, w, h in ((d, w, h) for d in (False, True)
                                         for w in (60, 80, 140)
                                         for h in range(18, 50)):
            rs = render.RenderState(
                w=w, h=h, state="done", transcript=text, type_pos=len(text),
                err="", tick=1, spin_i=0, hist=None, show_dev=show_dev, dev_rows=DEV,
                version="v0.4", model="TURBO", wave_ceil=0.1, done_tick=99,
                theme=theme, word_count=12, audio_secs=3.0,
            )
            drawn = {t for _y, _x, t, _a in render.compose(rs)}
            self.assertTrue(any(text.startswith(t[:12]) for t in drawn if len(t) > 12),
                            f"no transcript drawn at {w}x{h} show_dev={show_dev}")

    def test_the_dev_panel_keeps_off_the_keybinds_and_the_rail(self):
        # it used to anchor itself to the bottom rail and write straight over both of them
        theme = render.Theme()
        dev   = [("model", "TURBO · mlx"), ("audio", "4.2s · 18 words"),
                 ("decode", "1.9s · 2.2x realtime")]
        for w, h in ((60, 18), (80, 24), (120, 40), (200, 60)):
            rs = render.RenderState(
                w=w, h=h, state="done", transcript="hello there", type_pos=11,
                err="", tick=1, spin_i=0, hist=None, show_dev=True, dev_rows=dev,
                version="v0.4", model="TURBO", wave_ceil=0.1, done_tick=99,
                theme=theme, word_count=2, audio_secs=1.0,
            )
            _bx, box_y, _bw, box_h, _ix, _iw = render._box(w, h)
            foot_y = box_y + box_h - 2
            rail_y = box_y + box_h - 1
            rows = {}
            for y, x, t, _a in render.compose(rs):
                rows.setdefault(y, []).append(t)
            footer = " ".join(rows.get(foot_y, []))
            rail   = " ".join(rows.get(rail_y, []))
            for label, _v in dev:
                self.assertNotIn(label, footer, f"dev panel on the keybinds at {w}x{h}")
                self.assertNotIn(label, rail, f"dev panel on the rail at {w}x{h}")
            self.assertIn("SPC", footer, f"keybinds missing at {w}x{h}")

    def test_the_waveform_is_more_than_a_centreline_while_you_talk(self):
        # at 60x24 with the dev panel open it booked one row and drew nothing but the glass
        theme = render.Theme()
        loud  = np.full(180, 0.4, dtype=np.float32)
        dev   = [("model", "TURBO"), ("audio", "4.2s"), ("decode", "1.1s")]
        for show_dev in (False, True):
            for w, h in ((60, 18), (60, 24), (80, 24), (120, 40)):
                rs = render.RenderState(
                    w=w, h=h, state="listening", transcript="", type_pos=0, err="",
                    tick=1, spin_i=0, hist=loud, show_dev=show_dev, dev_rows=dev,
                    version="v0.4", model="TURBO", wave_ceil=0.1, done_tick=0,
                    theme=theme,
                )
                bar  = render.glyph("BAR")
                rows = {y for y, _x, t, _a in render.compose(rs) if bar in t}
                self.assertGreaterEqual(len(rows), 2,
                                        f"flat waveform at {w}x{h} show_dev={show_dev}")

    def test_the_viewport_is_as_tall_as_text_view_says(self):
        # app.py scrolls by these numbers, so a disagreement stops the down arrow early
        theme = render.Theme()
        text  = "word " * 500
        for show_dev, w, h in ((d, w, h) for d in (False, True)
                                         for w in (60, 80, 140)
                                         for h in (18, 24, 26, 40, 60)):
            rs = render.RenderState(
                w=w, h=h, state="done", transcript=text, type_pos=len(text), err="",
                tick=1, spin_i=0, hist=None, show_dev=show_dev,
                dev_rows=[("model", "TURBO"), ("audio", "4.2s"), ("decode", "1.1s")],
                version="v0.4", model="TURBO", wave_ceil=0.1, done_tick=99,
                theme=theme, word_count=500, audio_secs=3.0,
            )
            tx_w, rows = render.text_view(w, h, show_dev)
            want  = min(len(render.wrap(text, tx_w)), rows)
            drawn = [t for _y, _x, t, _a in render.compose(rs) if t.startswith("word ")]
            self.assertEqual(len(drawn), want, f"{w}x{h} show_dev={show_dev}")

    def test_ascii_bars_get_denser_not_sparser(self):
        for table in (render._G_ASCII, render._G_UNICODE):
            self.assertEqual(table["STEPS"][0], " ")
            self.assertEqual(table["LOWER"][0], " ")
            self.assertGreaterEqual(len(table["LOWER"]), len(table["STEPS"]))

    def test_a_new_recording_does_not_show_the_previous_dev_stats(self):
        class Screen:
            def getmaxyx(self):
                return 24, 80

            def clear(self):
                pass

        app = app_module.App(Screen(), mock=True)
        app.theme = render.Theme()
        app.show_dev = True
        app.dev_rows = [("model", "OLD"), ("audio", "99s"), ("decode", "88s")]
        app.state = "listening"
        app._listen_start = time.perf_counter() - 2.0

        rows = app._render_state(80, 24).dev_rows
        self.assertEqual(rows[-1], ("status", "recording"))
        self.assertFalse(any("OLD" in value for _key, value in rows))


class Crypto(unittest.TestCase):
    def test_round_trip(self):
        text = "hello, this has a ünicode bit in it"
        self.assertEqual(crypto.decrypt(crypto.encrypt(text)), text)

    def test_junk_envelopes_come_back_as_none(self):
        for junk in (None, "plain string", {}, {"enc": "aes-gcm-v9"},
                     {"enc": crypto.ENVELOPE_VERSION, "n": "!!", "ct": "!!"}):
            self.assertIsNone(crypto.decrypt(junk))


class Log(unittest.TestCase):
    def setUp(self):
        Path(_TMP_HOME, "transcripts.jsonl").unlink(missing_ok=True)

    def test_saves_encrypted_and_reads_back(self):
        transcripts.save("first one", "TINY", 1.0, 2)
        transcripts.save("second one", "TURBO", 2.0, 2)
        self.assertEqual(transcripts.load_recent(5), ["second one", "first one"])
        raw = Path(_TMP_HOME, "transcripts.jsonl").read_text()
        self.assertNotIn("second one", raw)

    def test_blank_transcripts_are_not_logged(self):
        transcripts.save("   ", "TINY", 1.0, 0)
        self.assertEqual(transcripts.load_recent(5), [])

    def test_a_corrupt_line_does_not_take_the_log_down(self):
        transcripts.save("good one", "TINY", 1.0, 2)
        with Path(_TMP_HOME, "transcripts.jsonl").open("a") as f:
            f.write("{not json at all\n\n")
        transcripts.save("also good", "TINY", 1.0, 2)
        self.assertEqual(transcripts.load_recent(5), ["also good", "good one"])


class Clips(unittest.TestCase):
    def test_rejects_the_clips_whisper_would_hallucinate_over(self):
        rate = audio.SAMPLE_RATE
        self.assertIsNotNone(audio.check_clip(None))
        self.assertIsNotNone(audio.check_clip(np.zeros(rate, dtype=np.float32)))
        self.assertIsNotNone(audio.check_clip(np.full(int(rate * 0.1), 0.4, np.float32)))
        self.assertIsNotNone(audio.check_clip(np.full(rate, 0.0001, np.float32)))

    def test_lets_real_speech_through(self):
        speech = (np.random.default_rng(0).normal(0, 0.08, audio.SAMPLE_RATE * 2)
                  .astype(np.float32))
        self.assertIsNone(audio.check_clip(speech))


class Models(unittest.TestCase):
    def test_a_snapshot_without_weights_is_not_cached(self):
        # this was so stupid: an interrupted download left a folder with a README in it and the app cheerfully said the model is ready
        fake = Path(_TMP_HOME) / "hub"
        snap = fake / "models--fake--model" / "snapshots" / "abc123"
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "README.md").write_text("hi")
        os.environ["HF_HUB_CACHE"] = str(fake)
        try:
            self.assertFalse(backend.is_model_cached("fake/model"))
            (snap / "weights.npz").write_bytes(b"\x00")
            self.assertTrue(backend.is_model_cached("fake/model"))
        finally:
            os.environ.pop("HF_HUB_CACHE", None)

    def test_sizes_read_like_sizes(self):
        self.assertEqual(backend.size_label(75), "75 MB")
        self.assertEqual(backend.size_label(1620), "1.6 GB")


if __name__ == "__main__":
    unittest.main()
