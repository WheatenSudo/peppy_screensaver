# PeppyMeter Screensaver for Volumio 4

VU meter and spectrum analyzer screensaver plugin for Volumio 4.x (Bookworm).

Based on [PeppyMeter](https://github.com/project-owner/PeppyMeter) and [PeppySpectrum](https://github.com/project-owner/PeppySpectrum) by project-owner.

Original Volumio plugin by [2aCD](https://github.com/2aCD-creator/volumio-plugins).

## Requirements

- Volumio 4.x (Bookworm-based)
- Minimum: Raspberry Pi 3B or equivalent
- Recommended: Raspberry Pi 4 or Pi 5
- Supported architectures: armv7 (Pi 3/4/5 32-bit), armv8 (Pi 3/4/5 64-bit), x64

### Hardware Compatibility

| Device | Status | Notes |
|--------|--------|-------|
| Pi 5 | Excellent | Best performance |
| Pi 4 | Good | Recommended |
| Pi 3B/3B+ | Minimum | Use 800x480, avoid heavy skins |
| Pi Zero 2 W | Marginal | Thermal throttling, 512MB RAM limit - not recommended |
| Pi 2 | Marginal | Weak cores - not recommended |
| Pi Zero/1 | Unsupported | Single core ARMv6, no NEON - will not run adequately |

Real-time 30fps rendering with ALSA audio capture and metadata updates requires
multi-core ARM with NEON SIMD. Single-core Pi Zero/1 cannot sustain this workload.

## Installation

```bash
git clone --depth=1 https://github.com/foonerd/peppy_screensaver.git
cd peppy_screensaver
volumio plugin install
```

## Manual Installation

If the above method fails:

```bash
git clone --depth=1 https://github.com/foonerd/peppy_screensaver.git
cd peppy_screensaver
zip -r peppy_screensaver.zip .
minidlna -d &
```

Then install via Volumio UI: Settings > Plugins > Install from local file

## Configuration

After installation, enable and configure the plugin:

1. Settings > Plugins > Installed Plugins
2. Enable "PeppyMeter Screensaver"
3. Click Settings to configure meter style, display options, etc.

## Features

- Multiple VU meter skins
- Spectrum analyzer mode
- Album art display with optional LP rotation effect
- Track info overlay with scrolling text
- Random meter rotation
- Touch to exit

## Performance

Expected CPU usage varies by resolution and device:

| Resolution | Pi 5 | Pi 4 | Pi 3B | x64 |
|------------|------|------|-------|-----|
| 800x480 | 10-15% | 15-20% | 25-35% | 1-2% |
| 1024x600 | 15-20% | 20-30% | 35-45% | 1-2% |
| 1280x720 | 25-35% | 35-45% | Not recommended | 1-2% |
| 1920x1080 | 35-45% | 45-60% | Not recommended | 2-3% |

### NEON Optimization (ARM)

The bundled pygame package for ARM (armv7/armv8) is built with NEON SIMD
optimization enabled, providing significantly better performance on Pi 3/4/5.

To verify NEON is enabled:
```bash
PYTHONPATH=/data/plugins/user_interface/peppy_screensaver/lib/arm/python \
  python3 -c "import pygame; pygame.init()"
```

If you see "neon capable but pygame was not built with support" warning,
the package needs to be rebuilt with NEON support. See Build Information below.

## Troubleshooting

### Debug Logging

For diagnosing display issues (white backgrounds, missing graphics, etc.), enable debug logging:

1. Edit `/data/plugins/user_interface/peppy_screensaver/screensaver/volumio_peppymeter.py`
2. Find `DEBUG_LOG = False` near the top (around line 73)
3. Change to `DEBUG_LOG = True`
4. Restart the plugin
5. Check `/tmp/peppy_debug.log` for diagnostic output

**Warning:** Disable after troubleshooting - the log file can fill /tmp (volatile RAM disk) and crash the player on extended use.

### Configuration Diagnostic

To dump the current meter configuration (useful for diagnosing missing backgrounds, wrong paths, etc.):

```bash
cd /data/plugins/user_interface/peppy_screensaver/screensaver
python3 diagnose_config.py
```

This shows:
- Current meter name and settings
- Background image keys (screen.bgr, bgr.filename, fgr.filename)
- Meter folder paths
- Available image files

### Plugin won't start

Check logs:
```bash
journalctl -u volumio -f | grep -i peppy
```

### Manual test

```bash
cd /data/plugins/user_interface/peppy_screensaver
./run_peppymeter.sh
```

### Missing libraries

If you see SDL2 errors:
```bash
sudo apt-get install -y libsdl2-ttf-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libfftw3-double3
```

### Permission errors on uninstall

```bash
sudo chown -R volumio:volumio /data/plugins/user_interface/peppy_screensaver
```

### High CPU usage on Pi

If CPU usage is higher than expected:

1. Verify NEON is enabled (see above)
2. Use a lower resolution meter template (800x480 recommended for Pi 3)
3. Disable spectrum visualization if not needed
4. Disable album art rotation if enabled

## Directory Structure

```
peppy_screensaver/
  bin/{arch}/             - peppyalsa-client binary
  lib/{arch}/             - libpeppyalsa.so library
  lib/{arch}/python/      - Python packages (pygame, socketio, etc.)
  packages/{arch}/        - Python packages archive (extracted on install)
  screensaver/            - PeppyMeter runtime
    peppymeter/           - PeppyMeter module
    volumio_peppymeter.py - Main screensaver script
    volumio_spectrum.py   - Spectrum analyzer module
    diagnose_config.py    - Configuration diagnostic tool
  asound/                 - ALSA configuration
  i18n/                   - Translations
```

## Build Information

Pre-built binaries included for all supported architectures. No compilation required on target system.

- peppyalsa: Native ALSA scope plugin for audio data capture
- Python packages: pygame 2.5.2 (NEON-optimized), python-socketio 5.x, Pillow, etc.

### ARM Python Packages (NEON Build)

The ARM python packages must be built natively on a Raspberry Pi to get
NEON-optimized pygame. Docker/QEMU cross-compilation produces non-NEON builds.

For build instructions and native Pi build scripts, see the separate build repository:

**https://github.com/foonerd/peppy_builds**

### Architecture Package Mapping

| Plugin Path | Target Devices | NEON |
|-------------|----------------|------|
| armv7 | Pi 3/4/5 32-bit (ARMv7+) | Yes |
| armv8 | Pi 3/4/5 64-bit (ARMv8) | Yes |
| x64 | x86_64 PCs | N/A (SSE/AVX) |

Note: ARMv6 (Pi Zero/1) is not supported due to insufficient CPU performance.

## Deprecation Notices

### meters.txt Configuration

The following configuration options are deprecated and will be removed in a future version:

- `playinfo.maxwidth` - Use field-specific settings instead:
  - `playinfo.title.maxwidth`
  - `playinfo.artist.maxwidth`
  - `playinfo.album.maxwidth`
  - `playinfo.samplerate.maxwidth`

## License

MIT

## Credits

- PeppyMeter/PeppySpectrum: [project-owner](https://github.com/project-owner)
- Original Volumio plugin: [2aCD](https://github.com/2aCD-creator)
- Volumio 4 refactoring: [foonerd](https://github.com/foonerd)
- Volumio 4 pythonising: [Wheaten](https://github.com/WheatenSudo)
- Plugin Q&A testing: Wheaten
