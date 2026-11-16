# Build context: build/asic-tools/vendor/tt-support-tools
# Separate environment: upstream support/precheck requirements intentionally differ.
ARG BASE_IMAGE=ghcr.io/librelane/librelane:3.0.14
FROM ${BASE_IMAGE}
COPY precheck /opt/tt-precheck
RUN nix-build /opt/tt-precheck/default.nix -o /opt/precheck-shell
RUN nix-build --expr '(import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/cee01fe2c16da2d972b56c595d96b53fdd8ecc3f.tar.gz") {}).python311' -o /opt/precheck-python
RUN /opt/precheck-python/bin/python3.11 -m venv /opt/precheck-venv && /opt/precheck-venv/bin/pip install --no-cache-dir -r /opt/tt-precheck/requirements.txt
RUN nix-build --expr 'let pkgs = import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/cee01fe2c16da2d972b56c595d96b53fdd8ecc3f.tar.gz") {}; in pkgs.symlinkJoin { name = "precheck-native-libs"; paths = [ pkgs.stdenv.cc.cc.lib pkgs.zlib ]; }' -o /opt/precheck-native
ENV LD_LIBRARY_PATH="/opt/precheck-native/lib"
ENV QT_QPA_PLATFORM=offscreen
ENV PATH="/opt/precheck-venv/bin:${PATH}"
# Both fetchTarball URLs name immutable commits, already cached by nix-build.
ENTRYPOINT ["nix-shell", "--option", "tarball-ttl", "315360000", "/opt/tt-precheck/default.nix", "--run"]
CMD ["/opt/precheck-venv/bin/python --version; klayout -v; magic --version"]
