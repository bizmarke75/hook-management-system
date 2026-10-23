"""Command-line entry point for HMS pipeline and recovery operations."""

import argparse
import os
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree as ET


def verify_davinci_xml(xml_path_str: str) -> bool:
    """
    Audits timeline XML schema, gapless video continuity, audio integrity,
    and transient marker frame boundaries for 24fps / 960 frame conformance.
    """
    xml_path = Path(xml_path_str).resolve()
    print(f"[RUN] Auditing timeline XML: {xml_path}")

    if not xml_path.exists():
        print(f"[ERROR] File does not exist on disk: {xml_path}")
        return False

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"[ERROR] XML Parse Error: {str(e)}")
        return False

    # 1. Rate & Sequence Validation
    rate_node = root.find(".//rate/timebase")
    if rate_node is None:
        print("[ERROR] Missing <rate><timebase> node in sequence.")
        return False

    fps = int(rate_node.text.strip())
    if fps != 24:
        print(f"[ERROR] Timebase mismatch: Expected 24 fps, found {fps} fps.")
        return False
    print(f"[INFO] Timebase confirmed: {fps} fps.")

    # 2. Video Track & Gapless Continuity Check
    video_tracks = root.findall("./sequence/media/video/track")
    audio_tracks = root.findall("./sequence/media/audio/track")
    if len(video_tracks) != 1 or len(audio_tracks) not in (1, 2):
        print(
            "[ERROR] Expected one video lane, a master audio lane, and at most one shot-audio lane; "
            f"found {len(video_tracks)} video lane(s) and {len(audio_tracks)} audio lane(s)."
        )
        return False

    video_clips = video_tracks[0].findall("clipitem")
    if not video_clips:
        print("[ERROR] No video <clipitem> elements found in timeline.")
        return False

    print(f"[INFO] Auditing {len(video_clips)} video clip segments...")
    current_timeline_frame = 0

    for idx, clip in enumerate(video_clips, start=1):
        name = clip.findtext("name", f"shot_{idx}")
        start_txt = clip.findtext("start", "-1").strip()
        end_txt = clip.findtext("end", "-1").strip()

        try:
            start_frame = int(start_txt)
            end_frame = int(end_txt)
        except ValueError:
            print(f"[ERROR] Non-integer start/end frame on video clip '{name}': start='{start_txt}', end='{end_txt}'")
            return False

        if start_frame != current_timeline_frame:
            gap = start_frame - current_timeline_frame
            print(f"[ERROR] Track continuity violation at clip {idx} ('{name}'): Expected start {current_timeline_frame}, found {start_frame} (Gap/Overlap: {gap} frames)")
            return False

        clip_duration = end_frame - start_frame
        if clip_duration <= 0:
            print(f"[ERROR] Invalid clip duration for '{name}': {clip_duration} frames.")
            return False

        file_node = clip.find("file")
        video_characteristics = clip.find("./file/media/video/samplecharacteristics")
        try:
            width = int(video_characteristics.findtext("width", "0")) if video_characteristics is not None else 0
            height = int(video_characteristics.findtext("height", "0")) if video_characteristics is not None else 0
        except ValueError:
            width = height = 0
        if width <= 0 or height <= 0:
            print(f"[ERROR] Missing real video dimensions in media metadata for '{name}'.")
            return False
        if clip.find("./file/media/video/samplecharacteristics/rate/timebase") is None:
            print(f"[ERROR] Missing source frame rate metadata for '{name}'.")
            return False

        pathurl = file_node.findtext("pathurl") if file_node is not None else None
        if pathurl:
            parsed = urllib.parse.urlparse(pathurl)
            file_disk_path = urllib.parse.unquote(parsed.path)
            if os.name == "nt" and file_disk_path.startswith("/"):
                file_disk_path = file_disk_path[1:]
            if not Path(file_disk_path).exists():
                print(f"[WARN] Video asset on disk not found: {file_disk_path}")

        current_timeline_frame = end_frame

    if current_timeline_frame != 960:
        print(f"[ERROR] Total video frame count mismatch: Expected exactly 960 frames (40.0s), got {current_timeline_frame}")
        return False
    print(f"[INFO] Video continuity verified: 0 to 960 frames (gapless).")

    # 3. Audio Track Validation
    master_audio_clips = audio_tracks[0].findall("clipitem")
    if len(master_audio_clips) != 1:
        print(f"[ERROR] Expected one master audio clip on A1, found {len(master_audio_clips)}.")
        return False

    audio_clip = master_audio_clips[0]
    if not audio_clip.findtext("name", "").endswith("_master_audio.wav"):
        print("[ERROR] The first audio lane must contain the master audio WAV.")
        return False
    raw_dur = audio_clip.findtext("duration", "-1").strip()

    # Guard against un-interpolated template placeholders
    if raw_dur.startswith("{") and raw_dur.endswith("}"):
        print(f"[ERROR] XML Template Leak Detected: Audio <duration> contains literal placeholder '{raw_dur}' instead of evaluated frame count.")
        return False

    try:
        a_dur = int(raw_dur)
    except ValueError:
        print(f"[ERROR] Invalid integer for audio duration node: '{raw_dur}'")
        return False

    if a_dur != 960:
        print(f"[ERROR] Audio duration mismatch: Expected 960 frames, found {a_dur}")
        return False
    print(f"[INFO] Audio track duration confirmed: {a_dur} frames (40.000s @ 24fps).")

    # Verify media paths and linked source audio on the second audio lane.
    audio_url = audio_clip.findtext(".//file/pathurl")
    if audio_url:
        parsed_audio = urllib.parse.urlparse(audio_url)
        audio_disk_path = urllib.parse.unquote(parsed_audio.path)
        if os.name == "nt" and audio_disk_path.startswith("/"):
            audio_disk_path = audio_disk_path[1:]
        if Path(audio_disk_path).exists():
            file_size_mb = Path(audio_disk_path).stat().st_size / (1024 * 1024)
            print(f"[INFO] Master audio located: {Path(audio_disk_path).name} ({file_size_mb:.2f} MB)")
        else:
            print(f"[WARN] Master audio file referenced but not present at: {audio_disk_path}")

    shot_audio_by_id = {}
    if len(audio_tracks) == 2:
        shot_audio_items = audio_tracks[1].findall("clipitem")
        shot_audio_by_id = {item.get("id"): item for item in shot_audio_items}
        if len(shot_audio_by_id) != len(shot_audio_items):
            print("[ERROR] Duplicate clip IDs found on the shot-audio lane.")
            return False

    for video_clip in video_clips:
        video_id = video_clip.get("id")
        video_links = {
            link.findtext("linkclipref")
            for link in video_clip.findall("link")
        }
        if video_id not in video_links:
            print(f"[ERROR] Video clip '{video_id}' is missing its self-link.")
            return False

        audio_link_ids = {
            link.findtext("linkclipref")
            for link in video_clip.findall("link")
            if link.findtext("mediatype") == "audio"
        }
        source_has_audio = video_clip.find("./file/media/audio") is not None
        if source_has_audio != bool(audio_link_ids):
            print(f"[ERROR] Embedded audio stream/link mismatch for video clip '{video_id}'.")
            return False
        if len(audio_link_ids) > 1:
            print(f"[ERROR] Video clip '{video_id}' has multiple linked source-audio clips.")
            return False
        for audio_id in audio_link_ids:
            shot_audio = shot_audio_by_id.get(audio_id)
            if shot_audio is None:
                print(f"[ERROR] Video clip '{video_id}' links to missing shot-audio clip '{audio_id}'.")
                return False
            reciprocal_links = {
                link.findtext("linkclipref")
                for link in shot_audio.findall("link")
            }
            if video_id not in reciprocal_links or audio_id not in reciprocal_links:
                print(f"[ERROR] Video/audio link pair '{video_id}' and '{audio_id}' is incomplete.")
                return False
            video_file = video_clip.find("file")
            audio_file = shot_audio.find("file")
            if (
                video_file is None
                or audio_file is None
                or video_file.get("id") != audio_file.get("id")
            ):
                print(f"[ERROR] Video/audio pair '{video_id}' and '{audio_id}' does not share its source file.")
                return False
            if shot_audio.findtext("start") != video_clip.findtext("start"):
                print(f"[ERROR] Video/audio pair '{video_id}' and '{audio_id}' are not timeline-synchronized.")
                return False

    for audio_id, shot_audio in shot_audio_by_id.items():
        if not any(
            link.findtext("linkclipref") == audio_id
            for clip in video_clips
            for link in clip.findall("link")
        ):
            print(f"[ERROR] Shot-audio clip '{audio_id}' has no linked video clip.")
            return False
    if shot_audio_by_id:
        print(f"[INFO] Verified {len(shot_audio_by_id)} linked source-audio clip(s) on A2.")

    # 4. Marker Integrity Check
    markers = root.findall(".//marker")
    print(f"[INFO] Auditing {len(markers)} timeline markers...")

    if not markers:
        print("[WARN] No transient beat markers detected in XML.")
    else:
        out_of_bounds = 0
        for marker in markers:
            m_in_txt = marker.findtext("in", "-1").strip()
            try:
                m_in = int(m_in_txt)
            except ValueError:
                print(f"[ERROR] Invalid marker frame value: '{m_in_txt}'")
                return False

            if m_in < 0 or m_in >= 960:
                out_of_bounds += 1

        if out_of_bounds > 0:
            print(f"[ERROR] {out_of_bounds} marker(s) fall outside the 960-frame timeline window.")
            return False

        print(f"[INFO] Marker audit: {len(markers)} transient pins verified within 0 <= frame < 960.")

    print("[SUCCESS] XML timeline verification passed with zero schema or continuity errors.")
    return True


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HMS run history and recovery")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--rollback",
        action="store_true",
        help="restore the latest completed or failed run",
    )
    actions.add_argument(
        "--restore",
        metavar="RUN_ID",
        help="restore a specific run, such as run_003",
    )
    actions.add_argument(
        "--verify-only",
        action="store_true",
        help="verify existing outputs without changing files",
    )
    actions.add_argument(
        "--verify",
        action="store_true",
        help="print a verification-mode notice before opening the GUI",
    )
    actions.add_argument(
        "--list-runs",
        action="store_true",
        help="display available run snapshots",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned operations without writing or renaming",
    )
    parser.add_argument("--audio", help="master audio source path")
    parser.add_argument("--renders", help="directory containing render clips")
    parser.add_argument("--slug", help="track slug used for output names")
    parser.add_argument("--bpm", type=float, default=170.0)
    parser.add_argument("--duration", type=float, default=40.0)
    return parser


def dispatch_cli(args, gui_factory=None):
    """Run a requested CLI operation; return False when the GUI should open."""
    if args.dry_run and (
        args.rollback
        or args.restore
        or args.verify_only
        or args.verify
        or args.list_runs
    ):
        raise ValueError(
            "--dry-run cannot be combined with rollback, restore, or verify modes."
        )
    if (args.rollback or args.restore or args.list_runs) and (
        args.audio or args.renders or args.slug
    ):
        raise ValueError(
            "Rollback, restore, and list-runs cannot be combined with pipeline arguments."
        )
    if args.verify and (args.audio or args.renders or args.slug):
        raise ValueError("--verify cannot be combined with pipeline arguments.")
    if args.list_runs:
        from hms_manifest import ManifestStore

        runs = ManifestStore().list_runs()
        print()
        print("==================================")
        print(" HMS Run History")
        print("==================================")
        if not runs:
            print("No runs found.")
        else:
            for run in runs:
                print(
                    f"{run['run_id']} | {run.get('slug', '')} | "
                    f"{run.get('timestamp', '')} | {run.get('status', '')}"
                )
        print()
        return True
    if args.rollback or args.restore:
        from hms_safety import RollbackStore

        store = RollbackStore()
        manifest = (
            store.rollback_last_run()
            if args.rollback
            else store.restore_run(args.restore)
        )
        print(f"[SUCCESS] Restored run {manifest['run_id']}.")
        return True
    if args.verify_only:
        if args.audio:
            raise ValueError("--verify-only does not accept --audio.")
        if not args.slug:
            raise ValueError("--verify-only requires --slug.")
        from hms_master_gui import verify_pipeline_outputs

        verify_pipeline_outputs(args.slug, args.renders, args.duration)
        return True
    if args.verify:
        print("[INFO] VERIFY mode enabled.")

    cli_run_requested = bool(args.audio or args.renders or args.slug)
    if args.dry_run or cli_run_requested:
        if not args.audio or not args.renders or not args.slug:
            if args.dry_run and not cli_run_requested and gui_factory is not None:
                return False
            raise ValueError(
                "Pipeline execution requires --audio, --renders, and --slug."
            )
        from hms_master_gui import execute_pipeline

        execute_pipeline(
            args.audio,
            args.renders,
            args.slug,
            args.bpm,
            args.duration,
            dry_run=args.dry_run,
        )
        return True
    return False


if __name__ == "__main__":
    argument_parser = build_argument_parser()
    arguments = argument_parser.parse_args()
    try:
        handled = dispatch_cli(arguments)
    except Exception as error:
        argument_parser.error(str(error))
    if not handled:
        argument_parser.print_help()
