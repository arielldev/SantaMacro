import argparse
import os
from macro import SantaMacro


def main():
    parser = argparse.ArgumentParser(description="Santa event helper macro")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"), help="Path to config.json")
    parser.add_argument("--check", action="store_true", help="Load config and exit (sanity check)")
    parser.add_argument("--autostart", action="store_true", help="Start detecting immediately (no need to press F8)")
    parser.add_argument("--mode", choices=["template", "motion", "hybrid"], help="Override detection mode")
    parser.add_argument("--no-overlay", action="store_true", help="Disable overlay window")
    parser.add_argument("--clicks", action="store_true", help="Enable clicking (use with caution)")
    args = parser.parse_args()

    macro = SantaMacro(args.config)

    if args.mode:
        macro.det_mode = args.mode
        macro.logger.info("CLI override: detection mode -> %s", args.mode)
    if args.no_overlay:
        macro.overlay_enabled = False
        macro.logger.info("CLI override: overlay disabled")
    if args.clicks:
        macro.clicks_enabled = True
        macro.logger.info("CLI override: clicks enabled")

    if args.check:
        print("Config loaded. Templates:", len(macro.templates))
        return

    if args.autostart:
        macro._running = True
        macro.state = "detecting"

    macro.run()


if __name__ == "__main__":
    main()
