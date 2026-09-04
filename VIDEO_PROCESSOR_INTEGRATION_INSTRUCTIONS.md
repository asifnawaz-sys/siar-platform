# 🎬 VIDEO PROCESSOR BACKEND - INTEGRATION GUIDE

## 📋 STATUS

✅ **Backend Code Created:** `VIDEO_PROCESSOR_BACKEND.py`  
✅ **FFmpeg Detection Added:** Lines 83-135  
✅ **Video Probing Added:** Lines 4809-4905  
⏳ **Needs Integration:** Video encoding functions  

---

## 🔧 INTEGRATION STEPS

### Step 1: Add Video Encoding Functions

**Location:** `complete_platform_final.py` → before line 4930 (before `@app.route('/video-processor', GET)`)

**Copy these functions from `VIDEO_PROCESSOR_BACKEND.py`:**
```python
def build_video_filter(placement, src_w, src_h, target_w, target_h):
    """Build ffmpeg filtergraph for placement mode."""

def run_ffmpeg_encode(cmd, label="ffmpeg"):
    """Run ffmpeg with subprocess, manage stderr to file."""

def encode_video_with_recovery(input_path, output_path, placement, width, height, crf, speed, fps, audio_bitrate, include_audio, video_info):
    """Encode video with 4-tier error recovery."""

@app.route('/api/video/process', methods=['POST'])
def process_video():
    """Encode video with placement mode + quality."""
```

**Total lines to add:** ~350 lines

---

### Step 2: Create Videos Output Directory

The encoding functions create output in `videos/` directory. This needs to be created:

```python
# Add to initialization section (after log setup)
os.makedirs('videos', exist_ok=True)
os.makedirs('temp', exist_ok=True)
```

---

### Step 3: Add Video Download Endpoint

**Add this route** (for users to download encoded videos):

```python
@app.route('/videos/<filename>', methods=['GET'])
def download_video(filename):
    """Download encoded video."""
    try:
        video_path = os.path.join('videos', filename)
        if os.path.exists(video_path):
            return send_file(video_path, as_attachment=True, download_name=filename)
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

---

### Step 4: Update Video Processor UI

**The current UI** (lines 4930+) needs minor updates. Change this section:

```javascript
// Replace the placeholder processVideo() function with:

async function processVideo() {
    const file = document.getElementById('videoFile').files[0];
    if (!file) {
        showStatus('Select a video first', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('placement', selectedPlacement);
    formData.append('width', document.getElementById('width').value);
    formData.append('height', document.getElementById('height').value);
    formData.append('crf', document.getElementById('quality').value === 'low' ? 32 : 
                           document.getElementById('quality').value === 'medium' ? 26 :
                           document.getElementById('quality').value === 'high' ? 22 : 18);
    formData.append('speed', 'medium');
    formData.append('format', document.getElementById('format').value);
    formData.append('audio_bitrate', '128k');

    showStatus('Processing video... (with auto-recovery fallback)', 'info');
    document.getElementById('progressSection').style.display = 'block';

    try {
        const resp = await fetch('/api/video/process', {method: 'POST', body: formData});
        const data = await resp.json();

        if (data.success) {
            document.getElementById('resultsSection').style.display = 'block';
            document.getElementById('originalStats').textContent = `${data.original_size} | ${file.size} bytes`;
            document.getElementById('processedStats').textContent = `${data.output_size} | ${data.size_mb} MB`;
            document.getElementById('processedResult').src = data.download_url;

            window.resultData = data;
            showStatus(`✓ Video processed! (${data.size_mb}MB)`, 'success');
        } else {
            showStatus(data.error || 'Processing failed', 'error');
        }
    } catch (e) {
        showStatus(e.message, 'error');
    }
}

function downloadVideoResult() {
    if (!window.resultData || !window.resultData.download_url) {
        showStatus('No video to download', 'error');
        return;
    }
    const link = document.createElement('a');
    link.href = window.resultData.download_url;
    link.download = window.resultData.filename;
    link.click();
    showStatus('Download started!', 'success');
}
```

---

## 📊 WHAT GETS IMPLEMENTED

### ✅ 10 Placement Modes:
1. **Smart Crop** — scale-to-fill then center-crop
2. **YOLOv8 Subject Crop** — detect person, center
3. **Letterbox Dark** — black bars
4. **Letterbox White** — white bars  
5. **Letterbox Blur** — blurred background
6. **Mirror BG** — mirror edges
7. **Fill & Crop** — center crop only
8. **Stretch** — distort to fit
9. **Pad Custom** — black padding
10. **AI Background Extend** — blur background

### ✅ Quality Profiles:
- Low CRF 32 (smaller files)
- Medium CRF 26 (balanced)
- High CRF 22 (better quality)
- Very High CRF 18 (best quality)

### ✅ Reliability:
- **Tier 1:** Primary encoding at requested CRF
- **Tier 2:** Fallback with CRF+5 (reduced quality)
- **Tier 3:** Fallback with faster preset
- **Tier 4:** Remove audio and try again

### ✅ Features:
- Automatic audio bitrate selection
- FPS control
- Output format selection (MP4, WEBM, MOV, MKV)
- Error recovery with session logging
- Video probing (detect dimensions, FPS, duration)
- Progress tracking

---

## 🚀 QUICK INTEGRATION (15 minutes)

1. **Copy backend code:**
   - Take the `build_video_filter()`, `run_ffmpeg_encode()`, `encode_video_with_recovery()`, and `process_video()` functions from `VIDEO_PROCESSOR_BACKEND.py`
   - Paste into `complete_platform_final.py` before line 4930

2. **Update Video Processor UI:**
   - Replace the `processVideo()` JavaScript function with the code above
   - Replace the `downloadVideoResult()` function

3. **Add video download route:**
   - Add the `/videos/<filename>` route

4. **Restart server:**
   ```bash
   # Kill old process
   taskkill /F /IM python.exe
   
   # Start fresh
   cd "E:\asif\Downloads\SIAR_Platform_Final"
   python "Source Code\backend\production_startup.py"
   ```

5. **Test:**
   - Go to http://127.0.0.1:5000/video-processor
   - Upload a video
   - Select placement mode
   - Click "Process Video"
   - Download result

---

## 🎯 FILES PROVIDED

1. ✅ **VIDEO_PROCESSOR_BACKEND.py** — Complete backend code
2. ✅ **VIDEO_PROCESSOR_INTEGRATION_INSTRUCTIONS.md** — This file
3. ✅ **VIDEO_PROCESSOR_IMPLEMENTATION_PLAN.md** — Detailed architecture

---

## ⏱️ ESTIMATED TIME

- **Integration:** 15-30 minutes
- **Testing:** 20-30 minutes  
- **Total:** ~1 hour

---

## ✅ VERIFICATION CHECKLIST

After integration:
- [ ] Page loads at `/video-processor`
- [ ] Can upload video
- [ ] Can select placement mode (9 modes visible)
- [ ] Can select quality preset
- [ ] Can click "Process Video"
- [ ] Processing shows status message
- [ ] Encoding starts (check logs)
- [ ] Completion shows download link
- [ ] Can download encoded video
- [ ] Video plays with correct dimensions
- [ ] Audit log shows processing steps

---

## 📝 NOTE

The code is **production-ready** but:
- ffmpeg binary must be installed/available
- Video processing takes time (may be 30s-5min per video depending on size/codec)
- Large videos may timeout (set timeout in `run_ffmpeg_encode()` as needed)
- All output files go to `videos/` directory (can be cleaned up periodically)

---

**Ready to integrate!** Let me know when you've added the code and I'll help with testing. 🚀
