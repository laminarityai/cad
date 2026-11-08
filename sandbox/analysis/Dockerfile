# check=skip=InvalidDefaultArgInFrom
ARG BASE
FROM ${BASE}

# ADR-0005 says why these engines and not the gmsh wheel or OrcaSlicer.
RUN rm /etc/apt/sources.list.d/debian.sources \
    && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20261104T212339Z bookworm main" \
        > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        calculix-ccx=2.20-1 \
        libgmsh4.8=4.8.4+ds2-3 \
        python3-gmsh=4.8.4+ds2-3 \
        prusa-slicer=2.5.0+dfsg-4 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/lib/python3/dist-packages/gmsh.py /usr/local/lib/python3.12/site-packages/gmsh.py
