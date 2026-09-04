# Video Processor Backend - Full Implementation
# This code should be added to complete_platform_final.py after line 4900
# (after the Video Processor UI route)

# ============================================================================
# VIDEO ENCODING WITH PLACEMENT MODES & ERROR RECOVERY
# ============================================================================

def build_video_filter(placement, src_w, src_h, target_w, target_h):
    """Build ffmpeg filtergraph for placement mode."""

    def _scale_crop():
        """Smart crop: scale to fill then center-crop."""
        return (f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={target_w}:{target_h}:trunc((iw-{target_w})/2):trunc((ih-{target_h})/2)[vout]"), True

    def _letterbox(color):
        """Preserve full video with letterbox."""
        return (f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={color}[vout]"), True

    def _blur_bg():
        """Blur background."""
        return (f"[0:v]split[fg][bg];[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={target_w}:{target_h},gblur=sigma=30[blurbg];"
                f"[fg]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
                f"[blurbg][fgs]overlay=(W-w)/2:(H-h)/2[vout]"), True

    def _mirror_bg():
        """Mirror edges for background."""
        return (f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={target_w}:{target_h},split=3[b1][b2][b3];"
                f"[b1]hflip[bh];[b2]vflip[bv0];[bv0]split=2[bv][bv2];[bv]hflip[bhv];"
                f"[b3][bh]hstack=inputs=2[top];[bv2][bhv]hstack=inputs=2[bot];"
                f"[top][bot]vstack=inputs=2[mirror];"
                f"[mirror]scale={target_w}:{target_h}:flags=lanczos[bg];"
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vout]"), True

    try:
        if placement in ("smart_crop", "fill_crop"):
            return _scale_crop()
        elif placement == "yolo_crop":
            return _scale_crop()  # Would need frame analysis
        elif placement == "stretch":
            return (f"[0:v]scale={target_w}:{target_h}:flags=lanczos[vout]"), False
        elif placement == "letterbox_dark":
            return _letterbox("black")
        elif placement == "letterbox_white":
            return _letterbox("white")
        elif placement == "letterbox_blur":
            return _blur_bg()
        elif placement == "mirror_bg":
            return _mirror_bg()
        elif placement == "pad_custom":
            return _letterbox("black")
        elif placement == "ai_bg_extend":
            return _blur_bg()
        else:
            return _scale_crop()
    except Exception as e:
        log.error(f"Filter build error: {e}")
        return _scale_crop()


def run_ffmpeg_encode(cmd, label="ffmpeg"):
    """Run ffmpeg with subprocess, manage stderr to file."""
    log.debug(f"Running: {' '.join(str(c) for c in cmd)}")

    err_fd, err_path = None, None
    try:
        err_fd, err_path = tempfile.mkstemp(prefix="ffmpeg_", suffix=".log")
        os.close(err_fd)

        with open(err_path, "w") as ef:
            proc = subprocess.Popen([str(c) for c in cmd],
                                    stdout=subprocess.DEVNULL, stderr=ef)
            proc.wait(timeout=3600)  # 1 hour max

        if proc.returncode != 0:
            try:
                stderr_data = open(err_path).read()
            except:
                stderr_data = ""
            log.warning(f"{label} failed (rc={proc.returncode})")
            return False, stderr_data[-500:]

        return True, ""

    except Exception as e:
        log.error(f"{label} error: {e}")
        return False, str(e)

    finally:
        if err_path and os.path.exists(err_path):
            try:
                os.remove(err_path)
            except:
                pass


def encode_video_with_recovery(input_path, output_path, placement, width, height,
                               crf, speed, fps, audio_bitrate, include_audio, video_info):
    """Encode video with 4-tier error recovery."""

    filename = os.path.basename(input_path)

    def _try_encode(crf_level, speed_level, attempt_name, include_audio_flag):
        """Attempt encode at specified settings."""
        try:
            vf, is_complex = build_video_filter(placement, video_info['width'],
                                               video_info['height'], width, height)

            cmd = [FFMPEG_EXE, "-y", "-i", str(input_path)]

            if is_complex:
                cmd += ["-filter_complex", vf, "-map", "[vout]"]
            else:
                cmd += ["-vf", vf, "-map", "0:v:0"]

            if include_audio_flag:
                cmd += ["-map", "0:a:0?"]

            if fps and fps != "auto":
                cmd += ["-r", str(fps), "-vsync", "cfr"]

            cmd += ["-c:v", "libx264", "-crf", str(crf_level),
                    "-preset", speed_level, "-pix_fmt", "yuv420p",
                    "-profile:v", "high"]

            if include_audio_flag:
                cmd += ["-c:a", "aac", "-b:a", audio_bitrate]
            else:
                cmd += ["-an"]

            cmd += ["-movflags", "+faststart", str(output_path)]

            ok, err = run_ffmpeg_encode(cmd, attempt_name)
            if ok:
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                audit_log(f"  [{attempt_name}] ✓ {size_mb:.1f}MB @ CRF{crf_level}")
                return True, size_mb
            else:
                audit_log(f"  [{attempt_name}] ✗ {err[:80]}")
                return False, 0

        except Exception as e:
            audit_log(f"  [{attempt_name}] Exception: {str(e)[:80]}")
            return False, 0

    # Tier 1: Primary at requested quality
    audit_log(f"Video encode: {filename} | {width}x{height} | {placement} | CRF{crf}")
    success, size = _try_encode(crf, speed, "Primary", include_audio)

    if not success and include_audio:
        # Tier 2: Reduce CRF
        audit_log(f"  Fallback 1: CRF {crf} → {crf + 5}")
        success, size = _try_encode(crf + 5, speed, "CRF-Fallback", include_audio)

    if not success and include_audio:
        # Tier 3: Reduce preset
        audit_log(f"  Fallback 2: preset {speed} → faster")
        success, size = _try_encode(crf + 10, "faster", "Preset-Fallback", include_audio)

    if not success and include_audio:
        # Tier 4: Remove audio
        audit_log(f"  Fallback 3: removing audio")
        success, size = _try_encode(crf, "faster", "No-Audio", False)

    if success:
        audit_log(f"  [COMPLETE] {filename} → {width}x{height} ({size:.1f}MB)")
        return True, size

    return False, 0


@app.route('/api/video/process', methods=['POST'])
def process_video():
    """Encode video with placement mode + quality."""
    temp_path = None
    output_path = None

    try:
        if not HAS_FFMPEG:
            return jsonify({'error': 'FFmpeg not available'}), 400

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        placement = request.form.get('placement', 'smart_crop')
        width = int(request.form.get('width', 1920))
        height = int(request.form.get('height', 1080))
        crf = int(request.form.get('crf', 22))
        speed = request.form.get('speed', 'medium')
        fps = request.form.get('fps', 'auto')
        audio_bitrate = request.form.get('audio_bitrate', '128k')
        output_format = request.form.get('format', 'mp4').lower()

        # Save input
        os.makedirs('temp', exist_ok=True)
        temp_path = os.path.join('temp', file.filename)
        file.save(temp_path)

        # Probe video
        video_info = _get_video_info(temp_path)
        include_audio = audio_bitrate != "silent" and video_info['has_audio']

        # Encode
        os.makedirs('videos', exist_ok=True)
        output_path = os.path.join('videos', f'processed_{int(time.time())}.{output_format}')

        success, output_size = encode_video_with_recovery(
            temp_path, output_path, placement, width, height,
            crf, speed, fps, audio_bitrate, include_audio, video_info
        )

        if not success:
            raise Exception("Video encoding failed (all tiers)")

        return jsonify({
            'success': True,
            'filename': os.path.basename(output_path),
            'size_mb': round(output_size, 2),
            'download_url': f'/videos/{os.path.basename(output_path)}',
            'original_size': f"{video_info['width']}x{video_info['height']}",
            'output_size': f"{width}x{height}",
            'placement': placement
        }), 200

    except Exception as e:
        log.error(f"Video process error: {e}")
        audit_log(f"[ERROR] {str(e)[:100]}", 'error')
        return jsonify({'success': False, 'error': str(e)[:200]}), 500

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

