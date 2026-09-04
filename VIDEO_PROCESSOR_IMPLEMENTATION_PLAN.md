# 🎬 VIDEO PROCESSOR BACKEND IMPLEMENTATION PLAN

**If you want full web-based video processing with all Video Resizer features:**

---

## 🎯 SCOPE: Add Video Resizer to Web Platform

### What Needs to Be Built:

1. **ffmpeg Subprocess Management** (30 minutes)
   - Detect ffmpeg binary
   - Manage encode processes
   - Handle fallback to imageio_ffmpeg

2. **Video Probing** (20 minutes)
   - Get video dimensions, FPS, duration
   - Detect audio presence
   - Extract frame for preview

3. **Quality Profiles** (30 minutes)
   - CRF presets (0-35)
   - Speed presets (ultrafast-veryslow)
   - Audio bitrate options

4. **Placement Modes** (1 hour)
   - Smart Crop (center crop)
   - YOLOv8 Subject Crop (lazy-load YOLO)
   - Letterbox (dark/white/blur)
   - Mirror BG (blurred mirror)
   - Fill & Crop
   - Stretch
   - Pad Custom

5. **Error Recovery Tiers** (45 minutes)
   - Tier 1: Primary at requested quality
   - Tier 2: Reduce CRF (quality)
   - Tier 3: Reduce preset (speed)
   - Tier 4: Disable audio → video only
   - Session logging for each tier

6. **2-Pass Size Guard** (1 hour)
   - Calculate target bitrate
   - Run 2-pass encoding if over limit
   - Log size optimization steps

7. **Batch Folder Processing** (1 hour)
   - Scan folder recursively
   - Preserve folder structure
   - Process queue management
   - Progress tracking per file

8. **Progress Streaming** (1.5 hours)
   - Use Server-Sent Events (SSE)
   - Real-time progress updates
   - ETA calculation
   - Statistics tracking

9. **Session Logging** (30 minutes)
   - Log all encode operations
   - Track fallback decisions
   - Performance metrics
   - Error details

10. **Detection Visualization** (30 minutes)
    - Show YOLOv8 detections during processing
    - Display detected objects
    - Confidence scores

---

## 📋 FILE STRUCTURE

```
complete_platform_final.py
├── Video Processor Routes
│   ├── @app.route('/video-processor', GET)
│   ├── @app.route('/api/video/probe', POST)
│   ├── @app.route('/api/video/process', POST)
│   └── @app.route('/api/video/progress', GET) [SSE]
│
├── Helper Functions
│   ├── _find_ffmpeg_exe()
│   ├── _ffprobe_json()
│   ├── _get_video_info()
│   ├── build_video_filtergraph()
│   ├── _run_ffmpeg()
│   ├── _encode_video()
│   └── _size_guard_2pass()
│
└── Configuration
    ├── PLACEMENT_MODES (10)
    ├── QUALITY_PRESETS (6)
    ├── SPEED_PRESETS (9)
    └── AUDIO_BITRATES (6)
```

---

## ⚙️ TECHNICAL REQUIREMENTS

### Dependencies:
- ✅ ffmpeg (already detected at startup)
- ✅ ffprobe (auto-detected)
- ✅ imageio-ffmpeg (bundled fallback)
- ✅ OpenCV (for frame extraction)
- ✅ YOLOv8 (lazy-loaded)

### Flask Features:
- `request.files` (video upload)
- `request.form` (settings)
- `jsonify` (responses)
- `streaming_with_context` (SSE progress)

### Frontend:
- File upload (single + batch)
- Mode selection (badges)
- Quality/speed/bitrate dropdowns
- Progress bar with ETA
- Before/after preview
- Statistics display
- Detection monitor (YOLOv8 results)

---

## 📊 ESTIMATED EFFORT

| Task | Time | Notes |
|------|------|-------|
| ffmpeg management | 30 min | Already partially done |
| Video probing | 20 min | Reuse ffprobe logic |
| Quality profiles | 30 min | Simple config |
| Placement modes | 1 hour | Filters for crop/letterbox |
| Error recovery | 45 min | Tier logic |
| 2-pass encoding | 1 hour | Complex but proven |
| Batch processing | 1 hour | Queue management |
| Progress streaming | 1.5 hours | SSE implementation |
| Logging | 30 min | Audit trail |
| Detection UI | 30 min | YOLO panel |
| **Total Backend** | **~7 hours** | Full implementation |
| **Total Frontend** | **~2 hours** | UI/UX |
| **Testing** | **~2 hours** | QA across modes |
| **TOTAL** | **~11 hours** | Full web Video Processor |

---

## 🔄 IMPLEMENTATION APPROACH

### Phase 1: Backend API (5 hours)
```python
# Add to complete_platform_final.py:

@app.route('/api/video/probe', methods=['POST'])
def probe_video():
    """Get video info: dimensions, FPS, duration, audio."""
    # Returns: width, height, fps, duration, has_audio

@app.route('/api/video/process', methods=['POST'])
def process_video():
    """Encode video with placement mode + quality."""
    # With 4-tier error recovery + session logging

@app.route('/api/video/progress', methods=['GET'])
def video_progress():
    """Stream progress updates via SSE."""
    # Real-time: current_file, percent, eta, stats
```

### Phase 2: Frontend UI (2 hours)
- Update HTML form with all options
- Add mode badge selection
- Add progress bar with SSE listener
- Add before/after preview
- Add detection panel

### Phase 3: Testing (2 hours)
- Test all 10 modes
- Test quality profiles
- Test error recovery tiers
- Test batch processing
- Test edge cases (corrupt video, no audio, etc.)

---

## 💾 CODE SAMPLE

```python
# Example error recovery tier logic (same as Image Resizer)

def encode_with_recovery(input_path, output_path, placement, width, height, quality, fps):
    """Encode video with 4-tier fallback."""
    
    # Tier 1: Primary
    success = _encode_video(input_path, output_path, placement, width, height, quality, fps)
    if success:
        return True
    
    # Tier 2: Reduce quality (CRF)
    success = _encode_video(input_path, output_path, placement, width, height, quality+5, fps)
    if success:
        return True
    
    # Tier 3: Reduce preset (slower encode)
    success = _encode_video(input_path, output_path, placement, width, height, quality+10, "slow")
    if success:
        return True
    
    # Tier 4: Video only (strip audio)
    success = _encode_video(input_path, output_path, placement, width, height, quality+10, "slow", audio=False)
    return success
```

---

## ✅ FEATURES DELIVERED (if you choose Option 3)

### Video Resizer Features (10 modes):
1. ✅ Smart Crop — scale-to-fill then center-crop
2. ✅ YOLOv8 Subject Crop — detect person, center them
3. ✅ Letterbox (Dark) — preserve all content, black bars
4. ✅ Letterbox (White) — for e-commerce
5. ✅ Letterbox (Blur) — blurred background
6. ✅ Mirror BG — mirror edges for fill
7. ✅ Fill & Crop — center crop, no bars
8. ✅ Stretch — distort to fit
9. ✅ Pad Custom — add black padding
10. ✅ AI Background Extend — reconstruct background

### Video Resizer Features (Quality):
- ✅ CRF profiles (0-35)
- ✅ Speed presets (ultrafast-veryslow)
- ✅ Audio bitrate options (96k-320k or silent)
- ✅ FPS selection (auto, 24, 25, 30, 60)
- ✅ Output formats (MP4, MOV, MKV, WEBM)

### Video Resizer Features (Reliability):
- ✅ 4-tier error recovery
- ✅ 2-pass size guard (if over limit)
- ✅ Folder recursion + structure mirroring
- ✅ Progress streaming + ETA
- ✅ Session audit logging
- ✅ YOLOv8 detection panel
- ✅ Statistics (time, speed, file size)

---

## 🎯 FINAL DECISION NEEDED

**Which option do you want?**

### Option A: Image Resizer Only ✅ DONE
- Web: Image Resizer enhanced
- Desktop: Use Video Resizer v5.4 app directly
- Effort: 0 (already complete)

### Option B: Link to Desktop App (2 hours)
- Web: Video Processor shows features + download link
- Desktop: Point to Video Resizer v5.4
- Effort: 2 hours (add instructions)

### Option C: Full Web Backend (11 hours)
- Web: Complete video encoding pipeline
- Same features as Video Resizer desktop app
- Effort: 11 hours (comprehensive implementation)

**Let me know! I'm ready for any of these.** 🚀
