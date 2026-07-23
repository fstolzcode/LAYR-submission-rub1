# LibreLane plugin: Magic density-aware metal filler
#
# Replaces KLayout.Filler with Magic's patternfill(tiled) which generates
# fill patterns per 800x800 um tile.  Uses a modified tech file with
# per-layer tuning: M2 all 3 passes (needs max fill), M1/M3 coarse-only
# with wider spacing (reduce density), M4/M5 coarse-only (default spacing).

import os
import re
import shutil

from librelane.steps.step import Step, ViewsUpdate, MetricsUpdate
from librelane.state import DesignFormat, State
from librelane.common import Path


@Step.factory.register()
class MetalFiller(Step):
    id = "Magic.MetalFiller"
    name = "Filler Generation (Magic)"
    long_name = "Density-Aware Filler Generation using Magic"

    inputs = [DesignFormat.GDS]
    outputs = [DesignFormat.GDS]

    config_vars = []

    # Layers reduced to coarse-only fill to stay below 60% max global density.
    COARSE_ONLY_LAYERS = {"met1fill"}

    # Widen coarse spacing for these layers: {layer: new_spacing}.
    # slots format: "slots border pitch spacing ..."
    # Feature width = pitch - spacing.  Wider spacing = smaller features = less fill.
    # Default spacing is 2000 (feature=3000, ratio=36%).
    COARSE_SPACING_OVERRIDE = {
        "met1fill": 3000,  # feature=2000, ratio=16% → keeps M1 in bounds
        "met2fill": 1000,  # feature=4000, ratio=64% → push sparse M2 tiles above 25%
    }

    def _create_shadow_techfile(self, pdk_root: str, pdk: str) -> str:
        """Copy the PDK tech file with per-layer fill tuning."""
        orig_tech = os.path.join(
            pdk_root, pdk, "libs.tech", "magic", "ihp-sg13g2-GDS.tech"
        )

        shadow_pdk = os.path.join(self.step_dir, "shadow-pdk")
        shadow_magic = os.path.join(shadow_pdk, pdk, "libs.tech", "magic")
        os.makedirs(shadow_magic, exist_ok=True)

        with open(orig_tech, "r") as f:
            tech = f.read()

        # 1) Fix IHP PDK bug: patternfill obstruction templates reference
        #    ALLMET{n} but the aliases section defines ALLM{n}.  Without
        #    this fix, drawn metal is missing from the obstruction zone
        #    and fill is placed on top of wiring.
        tech = re.sub(r"\bALLMET(\d)\b", r"ALLM\1", tech)

        # 1b) Fix undefined diff/poly fill layers in the PDK tech file.
        #     trans = transistor gate area (poly ∩ diff), used in medium/fine
        #     obstruction.  Insert definition before its first user.
        trans_def = " templayer\ttrans ALLPOLY\n\tand\tALLDIFF\n\n"
        tech = re.sub(
            r"(?m)(^ templayer\s+obstruct_diff_medium\b)",
            trans_def + r"\1",
            tech,
        )

        #     obstruct_diff_psd = diff obstruction including PSD implant,
        #     used as starting layer for poly medium/fine obstruction.
        psd_def = " templayer\tobstruct_diff_psd ALLDIFF,DIFFFILL,PSD\n\n"
        tech = re.sub(
            r"(?m)(^ templayer\s+obstruct_poly_medium\b)",
            psd_def + r"\1",
            tech,
        )

        #     DIFFPOLY = gate area, same concept as trans (now defined above).
        tech = re.sub(r"\bDIFFPOLY\b", "trans", tech)

        # 1c) Reduce M2 medium fill fragment filter to fill tighter gaps.
        #     Default shrink/grow 995 removes fragments < ~10µm.
        #     Reduce to 600 (~6µm) to improve coverage in sparse tiles.
        pattern = (
            r"(?m)(templayer\s+met2fill_medium\s+topbox\s*\n"
            r"(?:.*\n)*?"
            r"\s+shrink\s+)995(\s*\n\s+grow\s+)995"
        )
        tech = re.sub(pattern, r"\g<1>600\g<2>600", tech)

        # 1d) Also reduce M2 fine fill fragment filter.
        #     Default shrink/grow 595 removes fragments < ~6µm.
        #     Reduce to 300 (~3µm) to improve coverage in sparse tiles.
        pattern = (
            r"(?m)(templayer\s+met2fill_fine\s+topbox\s*\n"
            r"(?:.*\n)*?"
            r"\s+shrink\s+)595(\s*\n\s+grow\s+)595"
        )
        tech = re.sub(pattern, r"\g<1>300\g<2>300", tech)

        # 1e) Reduce M3 fine fill fragment filter to fill sparse center tiles.
        #     Only fine (not medium) is reduced — medium reduction causes M3Fil.k
        #     violations in edge/padring tiles where filler is already near 75%.
        #     Fine pass adds the least area (smallest features 780nm wide).
        pattern = (
            r"(?m)(templayer\s+met3fill_fine\s+topbox\s*\n"
            r"(?:.*\n)*?"
            r"\s+shrink\s+)595(\s*\n\s+grow\s+)595"
        )
        tech = re.sub(pattern, r"\g<1>300\g<2>300", tech)

        # 1g) Remove M3 coarse fill from the output layer.
        #     Coarse fill dominates filler density in padring edge tiles,
        #     causing M3Fil.k (>75% filler). Medium+fine alone provide
        #     enough fill for center tiles (M3Fil.h) without over-filling edges.
        #     Coarse shrink/grow (2495) can't be increased — feature=3000 leaves
        #     only 10 centimicrons survival margin (3000-2*2495=10).
        tech = re.sub(
            r"(?m)^(\s*layer\s+MET3FILL\s+)met3fill_coarse",
            r"\1met3fill_medium",
            tech,
        )
        tech = re.sub(
            r"(?m)^\s+or\s+met3fill_medium\s*$\n",
            "",
            tech,
            count=1,
        )

        # 2) Coarse-only layers: remove medium and fine from layer output
        for layer in self.COARSE_ONLY_LAYERS:
            for suffix in ("medium", "fine"):
                pattern = r"(?m)^\s+or\s+" + re.escape(f"{layer}_{suffix}") + r"\s*$\n"
                tech = re.sub(pattern, "", tech)

        # 3) Widen coarse spacing for specific layers to reduce fill density
        for layer, new_spacing in self.COARSE_SPACING_OVERRIDE.items():
            # Match the slots line inside the templayer for this layer's coarse pass
            # e.g. "slots   0 5000 2000 0 5000 2000 3500 2500"
            # Replace the spacing (3rd and 6th params) from 2000 to new value
            pattern = (
                r"(?m)(templayer\s+" + re.escape(f"{layer}_coarse") + r"\s+topbox\s*\n"
                r"(?:.*\n)*?"  # skip comment lines
                r"\s*slots\s+0\s+5000\s+)2000(\s+0\s+5000\s+)2000"
            )
            tech = re.sub(pattern, rf"\g<1>{new_spacing}\g<2>{new_spacing}", tech)

        shadow_tech = os.path.join(shadow_magic, "ihp-sg13g2-GDS.tech")
        with open(shadow_tech, "w") as f:
            f.write(tech)

        return shadow_pdk

    def run(self, state_in: State, **kwargs) -> tuple:
        kwargs, env = self.extract_env(kwargs)

        design_name = self.config["DESIGN_NAME"]
        input_gds = str(state_in[DesignFormat.GDS])
        output_gds = os.path.join(self.step_dir, f"{design_name}.gds")

        # Copy input GDS to step dir — generate_fill.py works relative to the
        # GDS location and expects the filename stem to match the top cell name
        local_gds = os.path.join(self.step_dir, f"{design_name}.gds")
        shutil.copy2(input_gds, local_gds)

        # Create gds/ subdir so generate_fill.py writes the final fill pattern there
        gds_dir = os.path.join(self.step_dir, "gds")
        os.makedirs(gds_dir, exist_ok=True)

        # Create shadow PDK with modified tech file (no fine pass on M1/M3/M4/M5)
        pdk_root = self.config["PDK_ROOT"]
        pdk = self.config["PDK"]
        shadow_pdk = self._create_shadow_techfile(pdk_root, pdk)

        fill_script = os.path.join(
            pdk_root, pdk, "libs.tech", "magic", "generate_fill.py"
        )

        # Point generate_fill.py at the shadow PDK so it picks up the modified tech
        env["PDK_ROOT"] = shadow_pdk

        # Run Magic fill generation with multiprocessing (-dist)
        self.run_subprocess(
            ["python3", fill_script, f"{design_name}.gds", "-dist"],
            log_to=os.path.join(self.step_dir, "magic-fill.log"),
            env=env,
            cwd=self.step_dir,
            **kwargs,
        )

        # The fill pattern GDS is written to gds/<design>_fill_pattern.gds.gz
        fill_pattern_gds = os.path.join(
            gds_dir, f"{design_name}_fill_pattern.gds.gz"
        )

        if not os.path.exists(fill_pattern_gds):
            # Fallback: check in step dir directly
            fill_pattern_gds = os.path.join(
                self.step_dir, f"{design_name}_fill_pattern.gds.gz"
            )

        # Write a KLayout script to merge fill pattern into the design GDS
        merge_script_path = os.path.join(self.step_dir, "merge_fill.py")
        with open(merge_script_path, "w") as f:
            f.write(f"""\
import pya

layout = pya.Layout()
layout.read("{local_gds}")

# Read fill pattern into same layout — KLayout adds new cells automatically
layout.read("{fill_pattern_gds}")

design_top = layout.cell("{design_name}")
fill_top = layout.cell("{design_name}_fill_pattern")

if design_top is not None and fill_top is not None:
    design_top.insert(pya.CellInstArray(fill_top.cell_index(), pya.Trans()))
    print(f"Instanced fill pattern into {{design_top.name}}")
else:
    print("WARNING: Could not find fill pattern or design top cell")

layout.write("{output_gds}")
print("Merge complete: {output_gds}")
""")

        # Run KLayout to merge
        self.run_subprocess(
            ["klayout", "-b", "-r", merge_script_path],
            log_to=os.path.join(self.step_dir, "klayout-merge.log"),
            env=env,
            **kwargs,
        )

        views_updates: ViewsUpdate = {
            DesignFormat.GDS: Path(output_gds),
        }
        return views_updates, {}
