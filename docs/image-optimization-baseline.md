# Image optimization — pre-fix baseline

Captured 2026-09-01 from git commit of record, before any compression.
Originals remain recoverable from git history.

## Per-page photo payload

| Page | Photos | Transfer (photos only) |
|---|---|---|
| Home (`/`) | 8 | **39.2 MB** |
| About (`/about.html`) | 5 | **22.2 MB** |
| Services (`/services.html`) | 0 | 0 MB |

Total photo assets in repo: **44.2 MB** across 11 files.

## Every source file

| File | Dimensions | Size | GPS in EXIF |
|---|---|---|---|
| `batteries-enphase-garage.jpg` | 5712×4284 | 3.56 MB | yes |
| `batteries-enphase-outdoor.jpg` | 4032×3024 | 4.62 MB | yes |
| `install-cloudy-day.jpg` | 3024×4032 | 4.11 MB | yes |
| `install-craftsman.jpg` | 5712×4284 | 4.04 MB | yes |
| `install-rockridge.jpg` | 1179×996 | 1.20 MB | no |
| `install-rooftop-vertical.jpg` | 3024×4032 | 4.83 MB | yes |
| `install-shingle-hills.jpg` | 4284×5712 | 8.85 MB | yes |
| `install-tudor-maple.jpg` | 5712×4284 | 6.05 MB | yes |
| `isaac-lake-merritt.jpg` | 4032×3024 | 3.19 MB | yes |
| `isaac-portrait.jpg` | 2316×3088 | 3.04 MB | yes |
| `isaac-roof-solar.jpg` | 1179×1537 | 0.67 MB | no |

All shot on iPhone 15; EXIF carries capture date, device, and in most cases
GPS coordinates of the property photographed.


## Result after optimization

| Page | Before | After | Reduction |
|---|---|---|---|
| Home | 39.2 MB | **1.49 MB** | −96.2% |
| About | 22.2 MB | **0.64 MB** | −97.1% |

Every output is under 300,000 bytes. All EXIF stripped — this also removes the
GPS coordinates of client properties that were embedded in 9 of the 11 originals.

Crops are baked to the aspect ratio the CSS renders (`object-fit: cover`, centered),
so the visible framing is identical to the previous build.

Originals recoverable at any time:
`git show 6745c50:assets/photos/<name>.jpg > <name>.jpg`

