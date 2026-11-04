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
    write_srt_sidecar,
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
        self.renders = Path(self.temp_dir.name).resolve()

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
                    "duration": 12.0,
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

    def test_selecting_render_directory_prompts_for_included_clips(self):
        from hms_master_gui import HMSMasterGUI

        class Value:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        renders = self.renders / "renders"
        renders.mkdir()
        clip = renders / "shot_2a.mp4"
        clip.write_bytes(b"video")
        gui = object.__new__(HMSMasterGUI)
        gui.renders_var = Value("old-renders")
        gui.include_var = Value("old-clip.mp4")

        with (
            patch("hms_master_gui.filedialog.askdirectory", return_value=str(renders)),
            patch(
                "hms_master_gui.filedialog.askopenfilenames",
                return_value=(str(clip),),
            ) as choose_files,
        ):
            gui._browse_renders()

        self.assertEqual(gui.renders_var.get(), str(renders.resolve()))
        self.assertEqual(gui.include_var.get(), "shot_2a.mp4")
        self.assertEqual(
            choose_files.call_args.kwargs["initialdir"],
            str(renders.resolve()),
        )

    def test_choose_render_clips_rejects_files_outside_render_directory(self):
        from hms_master_gui import HMSMasterGUI

        class Value:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        renders = self.renders / "renders"
        renders.mkdir()
        other_dir = self.renders / "other"
        other_dir.mkdir()
        outside_clip = other_dir / "shot.mp4"
        outside_clip.write_bytes(b"video")
        gui = object.__new__(HMSMasterGUI)
        gui.renders_var = Value(str(renders))
        gui.include_var = Value("")

        with patch(
            "hms_master_gui.filedialog.askopenfilenames",
            return_value=(str(outside_clip),),
        ):
            gui._choose_render_clips()

        self.assertEqual(gui.include_var.get(), "")

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
            "has_audio": True,
            "duration": 10.0,
            "width": 1920,
            "height": 1080,
            "fps": "24",
            "audio_duration": 10.0,
            "samplerate": 48000,
            "channels": 2,
            "depth": 16,
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
        audio_tracks = root.findall("./sequence/media/audio/track")
        self.assertEqual(len(audio_tracks), 1)
        video_clip = root.find("./sequence/media/video/track/clipitem")
        self.assertIsNotNone(video_clip)
        self.assertIsNotNone(video_clip.find("./file/media/audio"))
        self.assertFalse(
            any(
                link.findtext("mediatype") == "audio"
                for link in video_clip.findall("link")
            )
        )
        from hms_v31_patcher import verify_davinci_xml

        self.assertTrue(verify_davinci_xml(str(xml_path)))


class LyricImageVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        set_dry_run(False)
        self.temp_dir.cleanup()

    def test_image_selection_accepts_jpeg_and_png_only_when_requested(self):
        renders = self.root / "renders"
        renders.mkdir()
        image_jpg = renders / "page-1.jpg"
        image_png = renders / "page-2.png"
        video = renders / "clip.mp4"
        for path in (image_jpg, image_png, video):
            path.write_bytes(b"media")

        selected = select_render_files(
            renders,
            ["*.jpg", "*.png"],
            extensions={".jpg", ".jpeg", ".png"},
        )

        self.assertEqual(selected, [image_jpg, image_png])
        self.assertNotIn(video, selected)

    def test_gui_image_picker_accepts_only_stills_in_the_selected_folder(self):
        from hms_master_gui import HMSMasterGUI

        class Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        renders = self.root / "images"
        renders.mkdir()
        image = renders / "page.jpeg"
        image.write_bytes(b"image")
        gui = object.__new__(HMSMasterGUI)
        gui.renders_var = Value(str(renders))
        gui.include_var = Value("")
        gui.media_mode_var = Value("Image-only Lyric Video")

        with patch(
            "hms_master_gui.filedialog.askopenfilenames",
            return_value=[str(image)],
        ):
            gui._choose_render_clips()

        self.assertEqual(gui.include_var.get(), "page.jpeg")

    def test_image_timeline_generates_and_verifies_custom_duration(self):
        from hms_v31_patcher import verify_davinci_xml

        output = self.root / "output"
        renders = self.root / "images"
        output.mkdir()
        renders.mkdir()
        image = renders / "page.png"
        image.write_bytes(b"image")
        (output / f"track{MASTER_AUDIO_SUFFIX}").write_bytes(b"audio")
        (output / "track_thebeats.txt").write_text("1.0\n", encoding="utf-8")
        audio_metadata = {
            "has_audio": True,
            "duration": 10.0,
            "samplerate": 48000,
            "channels": 2,
            "depth": 24,
        }
        image_metadata = {
            "has_video": True,
            "has_audio": False,
            "duration": 0.0,
            "width": 1280,
            "height": 720,
            "fps": None,
            "samplerate": 44100,
            "channels": 2,
            "depth": 24,
        }

        with patch(
            "hms_master_gui.probe_media",
            side_effect=[audio_metadata, image_metadata],
        ):
            xml_path = run_step_4_generate_davinci_xml(
                "track",
                str(renders),
                total_duration=10.0,
                output_dir=output,
                selected_files=[image],
            )

        root = ET.parse(xml_path).getroot()
        image_clip = root.find("./sequence/media/video/track/clipitem")
        self.assertEqual(image_clip.findtext("name"), "page.png")
        self.assertEqual(image_clip.findtext("start"), "0")
        self.assertEqual(image_clip.findtext("end"), "240")
        self.assertTrue(verify_davinci_xml(str(xml_path)))

    def test_srt_sidecar_is_clipped_and_retimed_for_hook(self):
        source = self.root / "lyrics.srt"
        source.write_text(
            "1\n00:00:10,000 --> 00:00:12,000\nFirst line\n\n"
            "2\n00:00:39,000 --> 00:00:42,000\nSecond line\n",
            encoding="utf-8",
        )
        output = self.root / "output.srt"

        write_srt_sidecar(source, output, start_seconds=11.0, duration_seconds=30.0)

        self.assertEqual(
            output.read_text(encoding="utf-8"),
            "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n"
            "2\n00:00:28,000 --> 00:00:30,000\nSecond line\n",
        )

    def test_image_full_song_mode_uses_all_audio_without_renaming_stills(self):
        renders = self.root / "images"
        output = self.root / "output"
        renders.mkdir()
        output.mkdir()
        image = renders / "comic-page.png"
        image.write_bytes(b"image")
        audio = self.root / "master.wav"
        audio.write_bytes(b"audio")
        beats = output / "track_thebeats.txt"

        def write_analysis_files(*args, output_dir=None, **kwargs):
            output_path = Path(output_dir)
            (output_path / "track_hooktimestamp.txt").write_text(
                "0.000\n120.000\n120.000\n", encoding="utf-8"
            )
            (output_path / "track_thebeats.txt").write_text("", encoding="utf-8")

        with (
            patch(
                "hms_master_gui.probe_media",
                return_value={"has_audio": True, "duration": 120.0},
            ),
            patch("hms_master_gui.RollbackStore") as rollback_store,
            patch(
                "hms_master_gui.run_step_0_audio_analysis",
                side_effect=write_analysis_files,
            ) as analysis,
            patch("hms_master_gui.run_step_1_shot_renamer") as renamer,
            patch("hms_master_gui.run_step_2_audio_trimmer"),
            patch("hms_master_gui.run_step_3_sync_metadata"),
            patch(
                "hms_master_gui.run_step_4_generate_davinci_xml",
                return_value=output / "track_davinci_timeline.xml",
            ) as xml_generator,
        ):
            rollback_store.return_value.begin_run.return_value = "run_001"
            execute_pipeline(
                str(audio),
                str(renders),
                "track",
                output_dir=output,
                include_patterns=["*.png"],
                image_only=True,
                full_song=True,
            )

        analysis.assert_called_once()
        self.assertEqual(analysis.call_args.kwargs["window_duration"], 120.0)
        self.assertTrue(analysis.call_args.kwargs["full_song"])
        renamer.assert_not_called()
        self.assertEqual(xml_generator.call_args.kwargs["total_duration"], 120.0)
        self.assertEqual(xml_generator.call_args.kwargs["selected_files"], [image])
        self.assertTrue(image.is_file())
        self.assertTrue(beats.is_file())

    def test_full_song_video_uses_clips_once_and_trims_the_final_clip(self):
        output = self.root / "output"
        renders = self.root / "renders"
        output.mkdir()
        renders.mkdir()
        clips = [renders / name for name in ("shot1.mp4", "shot2.mp4", "shot3.mp4")]
        for clip in clips:
            clip.write_bytes(b"video")
        (output / f"track{MASTER_AUDIO_SUFFIX}").write_bytes(b"audio")
        (output / "track_thebeats.txt").write_text("", encoding="utf-8")
        audio_metadata = {
            "has_audio": True,
            "duration": 40.0,
            "samplerate": 48000,
            "channels": 2,
            "depth": 24,
        }
        video_metadata = [
            {
                "has_video": True,
                "has_audio": False,
                "duration": duration,
                "width": 1920,
                "height": 1080,
                "fps": "24",
                "samplerate": 48000,
                "channels": 2,
                "depth": 16,
            }
            for duration in (10.0, 15.0, 20.0)
        ]

        with patch(
            "hms_master_gui.probe_media",
            side_effect=[audio_metadata, *video_metadata],
        ):
            xml_path = run_step_4_generate_davinci_xml(
                "track",
                str(renders),
                total_duration=40.0,
                output_dir=output,
                selected_files=clips,
                full_song_video=True,
            )

        from hms_v31_patcher import verify_davinci_xml

        root = ET.parse(xml_path).getroot()
        timeline_clips = root.findall("./sequence/media/video/track/clipitem")
        self.assertEqual(root.findtext("./sequence/duration"), "960")
        self.assertEqual(
            [clip.findtext("name") for clip in timeline_clips],
            [clip.name for clip in clips],
        )
        self.assertEqual(
            [
                (clip.findtext("start"), clip.findtext("end"), clip.findtext("out"))
                for clip in timeline_clips
            ],
            [("0", "240", "240"), ("240", "600", "360"), ("600", "960", "360")],
        )
        self.assertTrue(verify_davinci_xml(str(xml_path)))

    def test_full_song_video_requires_more_footage_before_renaming(self):
        renders = self.root / "renders"
        output = self.root / "output"
        renders.mkdir()
        output.mkdir()
        audio = self.root / "master.wav"
        audio.write_bytes(b"audio")
        clip = renders / "short.mp4"
        clip.write_bytes(b"video")

        with (
            patch(
                "hms_master_gui.probe_media",
                side_effect=[
                    {"has_audio": True, "duration": 20.0},
                    {"has_video": True, "duration": 5.0},
                ],
            ),
            patch("hms_master_gui.RollbackStore") as rollback_store,
            patch("hms_master_gui.run_step_1_shot_renamer") as renamer,
        ):
            with self.assertRaisesRegex(ValueError, "Add more video shots/files"):
                execute_pipeline(
                    str(audio),
                    str(renders),
                    "track",
                    output_dir=output,
                    include_patterns=["*.mp4"],
                    full_song=True,
                )

        rollback_store.return_value.begin_run.assert_not_called()
        renamer.assert_not_called()
        self.assertEqual(clip.read_bytes(), b"video")

    def test_full_song_video_pipeline_passes_full_song_timeline_mode(self):
        renders = self.root / "renders"
        output = self.root / "output"
        renders.mkdir()
        output.mkdir()
        audio = self.root / "master.wav"
        audio.write_bytes(b"audio")
        clip = renders / "shot.mp4"
        clip.write_bytes(b"video")

        def write_analysis_files(*args, output_dir=None, **kwargs):
            output_path = Path(output_dir)
            (output_path / "track_hooktimestamp.txt").write_text(
                "0.000\n120.000\n120.000\n", encoding="utf-8"
            )
            (output_path / "track_thebeats.txt").write_text("", encoding="utf-8")
            return {"duration": 120.0}

        with (
            patch(
                "hms_master_gui.probe_media",
                side_effect=[
                    {"has_audio": True, "duration": 120.0},
                    {"has_video": True, "duration": 120.0},
                ],
            ),
            patch("hms_master_gui.RollbackStore") as rollback_store,
            patch(
                "hms_master_gui.run_step_0_audio_analysis",
                side_effect=write_analysis_files,
            ) as analysis,
            patch(
                "hms_master_gui.run_step_1_shot_renamer",
                return_value=[clip],
            ),
            patch("hms_master_gui.run_step_2_audio_trimmer"),
            patch("hms_master_gui.run_step_3_sync_metadata"),
            patch(
                "hms_master_gui.run_step_4_generate_davinci_xml",
                return_value=output / "track_davinci_timeline.xml",
            ) as xml_generator,
        ):
            rollback_store.return_value.begin_run.return_value = "run_001"
            execute_pipeline(
                str(audio),
                str(renders),
                "track",
                output_dir=output,
                include_patterns=["*.mp4"],
                full_song=True,
            )

        self.assertTrue(analysis.call_args.kwargs["full_song"])
        self.assertEqual(xml_generator.call_args.kwargs["total_duration"], 120.0)
        self.assertTrue(xml_generator.call_args.kwargs["full_song_video"])

    def test_cli_full_song_flag_enables_video_full_song_mode(self):
        from hms_v31_patcher import build_argument_parser, dispatch_cli

        args = build_argument_parser().parse_args(
            [
                "--audio", "master.wav",
                "--renders", "renders",
                "--slug", "track",
                "--include", "*.mp4",
                "--full-song",
            ]
        )
        with patch("hms_master_gui.execute_pipeline") as pipeline:
            self.assertTrue(dispatch_cli(args))

        self.assertTrue(pipeline.call_args.kwargs["full_song"])

    def test_rollback_restores_preexisting_subtitle_sidecar(self):
        output = self.root / "output"
        output.mkdir()
        subtitle_file = output / "track_subtitles.srt"
        subtitle_file.write_text("original\n", encoding="utf-8")
        store = RollbackStore(root_dir=self.root)
        run_id = store.begin_run(
            "track",
            "master.wav",
            str(self.root),
            output,
        )
        subtitle_file.write_text("generated\n", encoding="utf-8")
        manifest = store._read_manifest(run_id)
        manifest["status"] = "completed"
        manifest["rename_state"] = "restored"
        store._write_json(store._manifest_path(run_id), manifest)

        store.restore_run(run_id)

        self.assertEqual(subtitle_file.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()
