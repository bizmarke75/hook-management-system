"""Command-line entry point for HMS pipeline and recovery operations."""

import argparse


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
    if args.dry_run and (args.rollback or args.restore or args.verify_only):
        raise ValueError(
            "--dry-run cannot be combined with rollback, restore, or verify-only."
        )
    if (args.rollback or args.restore) and (args.audio or args.renders or args.slug):
        raise ValueError("Rollback and restore cannot be combined with pipeline arguments.")
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
