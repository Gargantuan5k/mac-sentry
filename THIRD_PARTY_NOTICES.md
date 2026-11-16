# Third-party notices

The reference ASIC layout incorporates SKY130 standard-cell geometry. The installed
`sky130_fd_sc_hd` Verilog model header records:

> Copyright 2020 The SkyWater PDK Authors
>
> Licensed under the Apache License, Version 2.0.
>
> SPDX-License-Identifier: Apache-2.0

The Apache 2.0 text is preserved in [licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).
That standard license text was copied unchanged from the pinned Tiny Tapeout
reference template. The physical input package is identified by the hardening
PDK revision in `requirements/asic-lock.json`; exact experiment identities are in
the published provenance. The reference GDS/PNL/LEF are unmodified historical
outputs, not a claim of a new SKY130 library or new physical sign-off.

The pinned Tiny Tapeout template and support-tools source archives also carry
Apache 2.0 license text. They are fetched separately into the ignored dependency
cache; those full repositories are not vendored into this source distribution.

External HDL tools, Vivado, Python packages, container images and PDK installations
retain their own licenses and notices. This file records upstream notices; it
does not select a license for MAC Sentry's original work.

The submission scaffold under `asic/submission/` adapts the pinned Tiny Tapeout
workflows, test Makefile and testbench, and retains their Apache license text in
`asic/submission/licenses/`. Its unchanged `src/base.sdc` comes from LibreLane
3.0.14, copyright 2022-2025 UmbraLogic Technologies LLC, also Apache-2.0. The
submission's scoped `LICENSE` notice expressly leaves the original project
licensing decision to the team; it is not a blanket license grant.
