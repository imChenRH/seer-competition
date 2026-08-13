#!/usr/bin/env python3
"""Render one warehouse frame before committing to a full Isaac recording."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scenario", choices=("normal", "recovery", "intervention"), default="normal")
    parser.add_argument("--phase", default="insert_forks")
    parser.add_argument("--warehouse-asset-root", type=Path)
    parser.add_argument("--resolution", default="1280x720")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    width, height = (int(value) for value in args.resolution.split("x", 1))
    os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True, "width": width, "height": height})
    try:
        import omni.replicator.core as rep
        from omni.replicator.core.functional import write_image

        from seer_demo.isaac.scene import apply_frame, build_scene, camera_pose_for_phase
        from seer_demo.isaac.timeline import build_timeline

        args.output.parent.mkdir(parents=True, exist_ok=True)
        scene_path = args.output.with_suffix(".usda")
        handles = build_scene(scene_path, args.scenario, args.warehouse_asset_root)
        frame = next(
            (item for item in build_timeline(args.scenario, fps=8).frames if item.phase == args.phase),
            None,
        )
        if frame is None:
            raise ValueError(f"phase not found: {args.phase}")
        apply_frame(handles, frame)
        pose = camera_pose_for_phase(frame.phase)
        camera = rep.functional.create.camera(
            position=pose.position,
            look_at=pose.look_at,
            parent="/World",
            name="PreviewCamera",
            focal_length=30.0,
            clipping_range=(0.1, 1000.0),
        )
        render_product = rep.create.render_product(camera, resolution=(width, height))
        rgb = rep.annotators.get("rgb")
        rgb.attach(render_product)
        for _ in range(20):
            rep.orchestrator.step(rt_subframes=2)
        write_image(path=str(args.output), data=rgb.get_data())
        handles.stage.GetRootLayer().Export(str(scene_path))
        print(f"PREVIEW_COMPLETE:{args.output}:assets={len(handles.referenced_assets)}", flush=True)
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
