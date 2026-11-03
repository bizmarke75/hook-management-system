import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np

from hms_master_gui import (
    derive_slug_from_audio,
    dry_run_pipeline,
    estimate_audio_bpm,
    execute_pipeline,
    run_step_4_generate_davinci_xml,
    run_step_2_audio_trimmer,
    natural_sort_key,
    run_step_1_shot_renamer,
    select_render_files,
)
from hms_safety import (
    LEGACY_MASTER_AUDIO_SUFFIX,
    MASTER_AUDIO_SUFFIX,
    RollbackStore,
    set_dry_run,
)


class ShotRenameSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.renders = Path(self.temp_dir.name)

    def tearDown(self):
        set_dry_run(False)
        self.temp_dir.cleanup()

    def make_file(self, name):
        path = self.renders / name
        path.write_bytes(b"test clip")
        return path

    def test_dry_run_context_prevents_rename_even_without_argument(self):
        selected = [
            self.make_file("shot_2a.mp4"),
            self.make_file("shot_2b.mov"),
            self.make_file("finished_product.mp4"),
        ]
        set_dry_run(True)

        run_step_1_shot_renamer(
            str(self.renders),
            "test",
            selected_files=selected[:2],
        )

        self.assertTrue((self.renders / "shot_2a.mp4").is_file())
        self.assertTrue((self.renders / "shot_2b.mov").is_file())
        self.assertTrue((self.renders / "finished_product.mp4").is_file())
        self.assertFalse((self.renders / "shot1.mp4").exists())

    def test_complete_dry_run_leaves_inputs_and_existing_outputs_unchanged(self):
        audio = self.make_file("master.wav")
        selected = self.make_file("shot_2a.mp4")
        excluded = self.make_file("shot_2b_final.mp4")
        unrelated = self.make_file("finished_product.mp4")
        output = self.renders / "output"
        output.mkdir()
        existing_output = output / "track_hooktimestamp.txt"
        existing_output.write_text("existing output\n", encoding="utf-8")
        before = {
            path: path.read_bytes()
            for path in (audio, selected, excluded, unrelated, existing_output)
        }

        with patch(
            "hms_master_gui.probe_media",
            side_effect=[
                {"has_audio": True},
                {
                    "has_video": True,
                    "has_audio": False,
                    "width": 1920,
                    "height": 1080,
                    "fps": "24",
                },
            ],
        ):
            dry_run_pipeline(
                str(audio),
                str(self.renders),
                "track",
                output_dir=output,
                include_patterns=["shot_2*"],
                exclude_patterns=["*_final*"],
            )

        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        self.assertFalse((self.renders / "shot1.mp4").exists())
        self.assertFalse((output / "track_thebeats.txt").exists())
        self.assertFalse((self.renders / "rollback").exists())

    def test_patterns_only_rename_included_non_excluded_files(self):
        first = self.make_file("shot_2a.mp4")
        second = self.make_file("shot_2b.mov")
        excluded = self.make_file("shot_2c_final.mp4")
        unrelated = self.make_file("finished_product.mp4")
        selected = select_render_files(
            self.renders,
            ["shot_2*"],
            ["*_final*"],
        )

        result = run_step_1_shot_renamer(
            str(self.renders),
            "test",
            selected_files=selected,
        )

        self.assertEqual([path.name for path in result], ["shot1.mp4", "shot2.mov"])
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertTrue(excluded.exists())
        self.assertTrue(unrelated.exists())

    def test_unmatched_include_is_rejected_without_changes(self):
        clip = self.make_file("clip_a.mp4")

        with self.assertRaises(ValueError):
            select_render_files(self.renders, ["shot_*"])

        self.assertTrue(clip.exists())

    def test_exact_include_patterns_define_custom_uuid_order(self):
        second = self.make_file("render_b_85af2.mp4")
        first = self.make_file("render_a_f0139.mp4")

        selected = select_render_files(
            self.renders,
            ["render_b_85af2.mp4", "render_a_f0139.mp4"],
        )

        self.assertEqual(selected, [second, first])

    def test_target_collision_with_unselected_file_is_blocked(self):
        selected = self.make_file("clip_a.mov")
        collision = self.make_file("shot1.mov")

        with self.assertRaises(FileExistsError):
            run_step_1_shot_renamer(
                str(self.renders),
                "test",
                selected_files=[selected],
            )

        self.assertTrue(selected.exists())
        self.assertTrue(collision.exists())

    def test_natural_sort_handles_numeric_and_text_prefixes(self):
        names = ["10_shot.mp4", "shot_2b.mp4", "shot_2a.mp4", "2_shot.mp4"]
        self.assertEqual(
            sorted(names, key=natural_sort_key),
            ["2_shot.mp4", "10_shot.mp4", "shot_2a.mp4", "shot_2b.mp4"],
        )

    def test_pipeline_sends_only_renamed_selection_to_timeline(self):
        source_a = self.make_file("shot_2a.mp4")
        source_b = self.make_file("shot_2b.mov")
        unrelated = self.make_file("finished_product.mp4")
        output = self.renders / "output"
        output.mkdir()
        (output / "track_thebeats.txt").write_text("0.5\n", encoding="utf-8")
        renamed = [self.renders / "shot1.mp4", self.renders / "shot2.mov"]
        xml_path = output / "track_davinci_timeline.xml"

        with (
            patch("hms_master_gui.RollbackStore") as rollback_store,
            patch("hms_master_gui.run_step_0_audio_analysis"),
            patch(
                "hms_master_gui.run_step_1_shot_renamer",
                return_value=renamed,
            ) as renamer,
            patch("hms_master_gui.run_step_2_audio_trimmer"),
            patch("hms_master_gui.run_step_3_sync_metadata"),
            patch(
                "hms_master_gui.run_step_4_generate_davinci_xml",
                return_value=xml_path,
            ) as xml_generator,
        ):
            rollback_store.return_value.begin_run.return_value = "run_001"
            execute_pipeline(
                "master.wav",
                str(self.renders),
                "track",
                output_dir=output,
                include_patterns=["shot_2a*", "shot_2b*"],
            )

        renamer.assert_called_once()
        self.assertEqual(
            renamer.call_args.kwargs["selected_files"],
            [source_a, source_b],
        )
        self.assertEqual(
            xml_generator.call_args.kwargs["selected_files"],
            renamed,
        )
        self.assertTrue(unrelated.exists())

    def test_full_pipeline_dry_run_exits_before_mutating_pipeline(self):
        audio = self.make_file("master.wav")
        selected = self.make_file("shot_2a.mp4")
        unrelated = self.make_file("finished_product.mp4")
        output = self.renders / "output"
        output.mkdir()

        with (
            patch("hms_master_gui.dry_run_pipeline") as dry_run,
            patch("hms_master_gui.RollbackStore") as rollback_store,
            patch("hms_master_gui.run_step_1_shot_renamer") as renamer,
        ):
            result = execute_pipeline(
                str(audio),
                str(self.renders),
                "track",
                dry_run=True,
                output_dir=output,
                include_patterns=["shot_2a*"],
            )

        self.assertIsNone(result)
        dry_run.assert_called_once()
        rollback_store.assert_not_called()
        renamer.assert_not_called()
        self.assertTrue(audio.exists())
        self.assertTrue(selected.exists())
        self.assertTrue(unrelated.exists())
        self.assertFalse((self.renders / "shot1.mp4").exists())

    def test_gui_pipeline_worker_forwards_checked_dry_run_flag(self):
        from hms_master_gui import HMSMasterGUI

        gui = object.__new__(HMSMasterGUI)
        gui.audio_var = type("Value", (), {"get": lambda self: "master.wav"})()
        gui.renders_var = type("Value", (), {"get": lambda self: "renders"})()
        gui.slug_var = type("Value", (), {"get": lambda self: "track"})()
        gui.bpm_var = type("Value", (), {"get": lambda self: "170.0"})()
        gui.duration_var = type("Value", (), {"get": lambda self: "40.0"})()
        gui.run_all_btn = type(
            "Button",
            (),
            {
                "after": lambda self, delay, callback: callback(),
                "config": lambda self, **kwargs: None,
            },
        )()

        with (
            patch("hms_master_gui.execute_pipeline", return_value=None) as pipeline,
            patch("hms_master_gui.set_dry_run") as set_dry_run_mock,
        ):
            gui._execute_pipeline_worker(
                dry_run=True,
                output_dir="output",
                include_patterns=["shot_2a*"],
            )

        set_dry_run_mock.assert_called_once_with(True)
        self.assertTrue(pipeline.call_args.kwargs["dry_run"])
        self.assertEqual(pipeline.call_args.kwargs["include_patterns"], ["shot_2a*"])

    def test_pending_bpm_estimate_blocks_pipeline_and_step_zero(self):
        from hms_master_gui import HMSMasterGUI

        class Button:
            def __init__(self):
                self.states = []

            def config(self, **kwargs):
                self.states.append(kwargs["state"])

        gui = object.__new__(HMSMasterGUI)
        gui._bpm_estimation_pending = True
        gui.run_all_btn = Button()
        gui.step_0_btn = Button()

        with patch("hms_master_gui.threading.Thread") as thread:
            gui._start_complete_pipeline()
            gui._run_step_async(0)

        thread.assert_not_called()
        self.assertEqual(gui.run_all_btn.states, [])
        self.assertEqual(gui.step_0_btn.states, [])

    def test_pending_bpm_estimate_stops_pipeline_worker_before_execution(self):
        from hms_master_gui import HMSMasterGUI

        class Button:
            def __init__(self):
                self.states = []

            def config(self, **kwargs):
                self.states.append(kwargs["state"])

            def after(self, delay, callback):
                callback()

        gui = object.__new__(HMSMasterGUI)
        gui._bpm_estimation_pending = True
        gui._pipeline_running = True
        gui.run_all_btn = Button()
        gui.step_0_btn = Button()

        with (
            patch("hms_master_gui.execute_pipeline") as pipeline,
            patch("hms_master_gui.set_dry_run"),
        ):
            gui._execute_pipeline_worker()

        pipeline.assert_not_called()
        self.assertFalse(gui._pipeline_running)
        self.assertEqual(gui.run_all_btn.states, ["disabled"])
        self.assertEqual(gui.step_0_btn.states, ["disabled"])

    def test_pending_bpm_estimate_stops_step_zero_worker(self):
        from hms_master_gui import HMSMasterGUI

        gui = object.__new__(HMSMasterGUI)
        gui._bpm_estimation_pending = True

        with (
            patch("hms_master_gui.set_dry_run") as set_dry_run_mock,
            patch("hms_master_gui.run_step_0_audio_analysis") as step_zero,
        ):
            gui._step_worker(0)

        set_dry_run_mock.assert_not_called()
        step_zero.assert_not_called()

    def test_bpm_estimator_uses_new_audio_without_previous_tempo_prior(self):
        audio = self.make_file("new_song.wav")
        with (
            patch("hms_master_gui.librosa.load", return_value=(np.ones(8), 22050)) as load,
            patch(
                "hms_master_gui.librosa.onset.onset_strength",
                return_value=np.array([0.0, 0.4, 0.8]),
            ),
            patch(
                "hms_master_gui.librosa.feature.tempo",
                return_value=np.array([128.75]),
            ) as estimate,
        ):
            result = estimate_audio_bpm(audio)

        self.assertEqual(result, 128.75)
        load.assert_called_once_with(str(audio.resolve()), sr=22050, mono=True)
        self.assertNotIn("start_bpm", estimate.call_args.kwargs)

    def test_browse_audio_resets_and_starts_estimate_for_new_source(self):
        from hms_master_gui import HMSMasterGUI

        class Value:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        audio = self.make_file("New Song.wav")
        gui = object.__new__(HMSMasterGUI)
        gui.audio_var = Value("old.wav")
        gui.slug_var = Value("old")
        gui.bpm_var = Value("123.0")
        gui.bpm_entry = type(
            "Entry",
            (),
            {"configure": lambda self, **kwargs: setattr(self, "state", kwargs["state"])},
        )()
        gui._audio_selection_generation = 0
        gui.run_all_btn = type(
            "Button", (), {"config": lambda self, **kwargs: setattr(self, "state", kwargs["state"])}
        )()
        gui.step_0_btn = type(
            "Button", (), {"config": lambda self, **kwargs: setattr(self, "state", kwargs["state"])}
        )()

        with (
            patch("hms_master_gui.filedialog.askopenfilename", return_value=str(audio)),
            patch("hms_master_gui.threading.Thread") as thread,
        ):
            gui._browse_audio()

        self.assertEqual(gui.audio_var.get(), str(audio))
        self.assertEqual(gui.slug_var.get(), "new_song")
        self.assertEqual(gui.bpm_var.get(), "170.0")
        self.assertEqual(gui.bpm_entry.state, "disabled")
        self.assertTrue(gui._bpm_estimation_pending)
        self.assertEqual(gui.run_all_btn.state, "disabled")
        self.assertEqual(gui.step_0_btn.state, "disabled")
        self.assertEqual(gui._audio_selection_generation, 1)
        self.assertEqual(thread.call_args.kwargs["args"], (str(audio), 1))
        thread.return_value.start.assert_called_once()

    def test_audio_slug_avoids_duplicate_master_suffix(self):
        self.assertEqual(
            derive_slug_from_audio("C:\\audio\\Project_Master.wav"),
            "project",
        )
        self.assertEqual(
            derive_slug_from_audio("C:\\audio\\Project_master_trimmed.wav"),
            "project",
        )

    def test_stale_bpm_estimate_does_not_replace_new_selection(self):
        from hms_master_gui import HMSMasterGUI

        class Value:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        gui = object.__new__(HMSMasterGUI)
        gui.audio_var = Value("new.wav")
        gui.bpm_var = Value("170.0")
        gui._audio_selection_generation = 2
        gui.bpm_entry = type("Entry", (), {"configure": lambda self, **kwargs: None})()

        gui._apply_bpm_estimate("old.wav", 1, 142.0, None)

        self.assertEqual(gui.bpm_var.get(), "170.0")

    def test_completed_bpm_estimate_updates_current_audio_selection(self):
        from hms_master_gui import HMSMasterGUI

        class Value:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        audio = self.make_file("new_song.wav")
        gui = object.__new__(HMSMasterGUI)
        gui.audio_var = Value(str(audio))
        gui.bpm_var = Value("170.0")
        gui._audio_selection_generation = 1
        gui._bpm_estimation_pending = True
        gui._pipeline_running = False
        gui.bpm_entry = type(
            "Entry",
            (),
            {"configure": lambda self, **kwargs: setattr(self, "state", kwargs["state"])},
        )()
        gui.run_all_btn = type(
            "Button", (), {"config": lambda self, **kwargs: setattr(self, "state", kwargs["state"])}
        )()
        gui.step_0_btn = type(
            "Button", (), {"config": lambda self, **kwargs: setattr(self, "state", kwargs["state"])}
        )()
        gui.after = lambda delay, callback, *args: callback(*args)

        with patch("hms_master_gui.estimate_audio_bpm", return_value=126.4):
            gui._estimate_bpm_worker(str(audio), 1)

        self.assertEqual(gui.bpm_var.get(), "126.40")
        self.assertEqual(gui.bpm_entry.state, "normal")
        self.assertFalse(gui._bpm_estimation_pending)
        self.assertEqual(gui.run_all_btn.state, "normal")
        self.assertEqual(gui.step_0_btn.state, "normal")

    def test_trimmed_wav_uses_requested_master_trimmed_name(self):
        output = self.renders / "output"
        output.mkdir()
        (output / "track_hooktimestamp.txt").write_text(
            "0\n40\n40\n",
            encoding="utf-8",
        )

        target = run_step_2_audio_trimmer(
            "master.wav",
            "track",
            dry_run=True,
            output_dir=output,
        )

        self.assertEqual(target.name, f"track{MASTER_AUDIO_SUFFIX}")
        self.assertFalse(target.exists())
        self.assertFalse((output / "track_master_audio.wav").exists())

    def test_recovery_manifest_tracks_renamed_trimmed_audio_output(self):
        output = self.renders / "output"
        output.mkdir()
        store = RollbackStore(root_dir=self.renders)

        run_id = store.begin_run(
            "track",
            "master.wav",
            str(self.renders),
            output,
        )
        manifest = store._read_manifest(run_id)

        self.assertEqual(manifest["wav"], f"track{MASTER_AUDIO_SUFFIX}")
        self.assertIn(
            f"track{MASTER_AUDIO_SUFFIX}",
            {entry["name"] for entry in manifest["backed_up_outputs"]},
        )

    def test_recovery_still_accepts_legacy_master_audio_manifest(self):
        output = self.renders / "output"
        output.mkdir()
        store = RollbackStore(root_dir=self.renders)
        run_id = store.begin_run(
            "track",
            "master.wav",
            str(self.renders),
            output,
        )
        manifest = store._read_manifest(run_id)
        manifest["status"] = "completed"
        manifest["rename_state"] = "restored"
        manifest["wav"] = f"track{LEGACY_MASTER_AUDIO_SUFFIX}"
        for entry in manifest["backed_up_outputs"]:
            if entry["name"] == f"track{MASTER_AUDIO_SUFFIX}":
                entry["name"] = f"track{LEGACY_MASTER_AUDIO_SUFFIX}"
                if entry["existed_before"]:
                    entry["backup"] = f"backups/{entry['name']}"
        store._write_json(store._manifest_path(run_id), manifest)

        renders_dir, output_dir, moves = store._preflight_restore(manifest)

        self.assertEqual(renders_dir, self.renders)
        self.assertEqual(output_dir, output)
        self.assertEqual(moves, [])

    def test_timeline_xml_uses_trimmed_audio_name_and_selected_output_directory(self):
        output = self.renders / "custom-output"
        output.mkdir()
        renders = self.renders / "renders"
        renders.mkdir()
        clip = renders / "shot1.mp4"
        clip.write_bytes(b"video")
        (output / f"track{MASTER_AUDIO_SUFFIX}").write_bytes(b"audio")
        (output / "track_thebeats.txt").write_text("0.5\n", encoding="utf-8")
        audio_metadata = {
            "has_audio": True,
            "duration": 40.0,
            "samplerate": 48000,
            "channels": 2,
            "depth": 24,
        }
        video_metadata = {
            "has_video": True,
            "has_audio": False,
            "duration": 10.0,
            "width": 1920,
            "height": 1080,
            "fps": "24",
            "audio_duration": 0.0,
            "samplerate": 0,
            "channels": 0,
            "depth": 0,
        }

        with patch(
            "hms_master_gui.probe_media",
            side_effect=[audio_metadata, video_metadata],
        ):
            xml_path = run_step_4_generate_davinci_xml(
                "track",
                str(renders),
                output_dir=output,
                selected_files=[clip],
            )

        self.assertEqual(xml_path, output / "track_davinci_timeline.xml")
        root = ET.parse(xml_path).getroot()
        master_clip = root.find("./sequence/media/audio/track/clipitem")
        self.assertIsNotNone(master_clip)
        self.assertEqual(master_clip.findtext("name"), f"track{MASTER_AUDIO_SUFFIX}")
        self.assertTrue(
            master_clip.findtext("file/pathurl").endswith("track_master_trimmed.wav")
        )


if __name__ == "__main__":
    unittest.main()
