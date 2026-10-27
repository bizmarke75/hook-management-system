import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hms_master_gui import (
    dry_run_pipeline,
    execute_pipeline,
    natural_sort_key,
    run_step_1_shot_renamer,
    select_render_files,
)
from hms_safety import set_dry_run


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


if __name__ == "__main__":
    unittest.main()
