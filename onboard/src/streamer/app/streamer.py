import threading
from typing import Optional

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import numpy as np
import time
import logging
import simplejpeg

logger = logging.getLogger(__name__)


Gst.init([])


class Streamer:
    def __init__(self):
        self.pipeline: Optional[Gst.Pipeline] = None
        self._lock = threading.Lock()
        self._running = False
        self._appsink = None
        self._valve = None
        # cache pipeline type per device ('mjpeg' or 'raw') determined by _probe_pipeline_type()
        self._device_probe = {}
        # cache the exact working temporary pipeline launch string per device
        self._device_working_launch = {}

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _probe_pipeline_type(self, device: str, cfg) -> str:
        """Run short test pipelines to determine which source format the device supports.

        Returns 'mjpeg' if the device outputs MJPEG and jpegdec is available, 'raw' otherwise.
        The result is cached per device so the probe only runs once.
        """
        with self._lock:
            if device in self._device_probe:
                return self._device_probe[device]

        fps = cfg.camera.fps
        candidates = [
            ('mjpeg', f"v4l2src device={device} num-buffers=1 ! image/jpeg ! jpegdec ! fakesink"),
            ('raw',   f"v4l2src device={device} num-buffers=1 ! videoconvert ! fakesink"),
        ]

        result = 'raw'  # safe fallback
        for name, launch in candidates:
            logger.debug('Probing pipeline type %s: %s', name, launch)
            tmp = None
            try:
                tmp = Gst.parse_launch(launch)
            except Exception:
                logger.debug('parse_launch failed for probe %s', name)
                continue
            if tmp is None:
                continue
            tmp.set_state(Gst.State.PLAYING)
            bus = tmp.get_bus()
            msg = bus.timed_pop_filtered(
                int(3.0 * Gst.SECOND),
                Gst.MessageType.ERROR | Gst.MessageType.EOS,
            )
            tmp.set_state(Gst.State.NULL)
            if msg is not None and msg.type == Gst.MessageType.EOS:
                logger.info('Device %s probe success: pipeline type = %s', device, name)
                result = name
                break
            elif msg is not None and msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                logger.debug('Probe pipeline %s error: %s | %s', name, err, debug)
            else:
                logger.debug('Probe pipeline %s timed out', name)

        with self._lock:
            self._device_probe[device] = result
        logger.info('Device %s probe result cached: %s', device, result)
        return result

    def start(self, address: str, port: int, cfg) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Streamer already running")

        # Probe the device outside the main lock (probe acquires lock only for cache access)
        pipeline_type = self._probe_pipeline_type(cfg.camera.device, cfg)

        with self._lock:
            if self._running:
                raise RuntimeError("Streamer already running")

            width = cfg.camera.width
            height = cfg.camera.height
            fps = cfg.camera.fps
            device = cfg.camera.device

            logger.info('Starting streamer -> %s:%s (device=%s %dx%d@%dfps)', address, port, device, width, height, fps)
            logger.debug('Stream config: use_hardware=%s bitrate=%s mtu=%s pt=%s qstream_max=%s qsnap_max=%s q_leaky=%s',
                         cfg.stream.use_hardware, cfg.stream.bitrate, cfg.stream.mtu, cfg.stream.payload_type,
                         cfg.stream.qstream_max_buffers, cfg.stream.qsnap_max_buffers, cfg.stream.q_leaky)

            pipeline = Gst.Pipeline.new('camera-pipeline')

            src = Gst.ElementFactory.make('v4l2src', 'src')
            src.set_property('device', device)
            try:
                src.set_property('do-timestamp', True)
            except Exception:
                pass

            convert = Gst.ElementFactory.make('videoconvert', 'convert')

            caps = Gst.Caps.from_string(f'video/x-raw,format=BGR,width={width},height={height},framerate={fps}/1')
            capsfilter = Gst.ElementFactory.make('capsfilter', 'caps')
            capsfilter.set_property('caps', caps)

            # enforce framerate to avoid v4l2src 'framerate not fixated' warnings
            videorate = Gst.ElementFactory.make('videorate', 'videorate')

            tee = Gst.ElementFactory.make('tee', 'tee')

            # streaming branch
            qstream = Gst.ElementFactory.make('queue', 'qstream')
            # keep queue small and leaky to avoid blocking camera capture
            try:
                qstream.set_property('max-size-buffers', int(cfg.stream.qstream_max_buffers))
                qstream.set_property('leaky', int(cfg.stream.q_leaky))
            except Exception:
                pass
            enc_convert = Gst.ElementFactory.make('videoconvert', 'enc_convert')

            # choose encoder
            enc = None
            if cfg.stream.use_hardware and Gst.ElementFactory.find('v4l2h264enc'):
                enc = Gst.ElementFactory.make('v4l2h264enc', 'v4l2h264enc')
            else:
                enc = Gst.ElementFactory.make('x264enc', 'x264enc')
                try:
                    # parse bitrate like '1M' or '800k' into kbps for x264enc
                    b = str(cfg.stream.bitrate)
                    if b.lower().endswith('m'):
                        kbps = int(float(b[:-1]) * 1000)
                    elif b.lower().endswith('k'):
                        kbps = int(float(b[:-1]))
                    else:
                        kbps = int(float(b))
                except Exception:
                    kbps = None
                if kbps:
                    enc.set_property('bitrate', kbps)

            pay = Gst.ElementFactory.make('rtph264pay', 'pay')
            # add h264parse between encoder and pay to ensure proper stream format
            h264parse = Gst.ElementFactory.make('h264parse', 'h264parse')
            udpsink = Gst.ElementFactory.make('udpsink', 'udpsink')
            udpsink.set_property('host', address)
            udpsink.set_property('port', int(port))
            udpsink.set_property('sync', False)
            udpsink.set_property('async', False)

            # appsink branch for on-demand snapshots
            qsnap = Gst.ElementFactory.make('queue', 'qsnap')
            try:
                qsnap.set_property('max-size-buffers', int(cfg.stream.qsnap_max_buffers))
                qsnap.set_property('leaky', int(cfg.stream.q_leaky))
            except Exception:
                pass
            valve = Gst.ElementFactory.make('valve', 'valve')
            # initially drop so appsink receives nothing until requested
            valve.set_property('drop', True)
            # add videoscale + capsfilter so snapshot branch can deliver configured size
            snap_scale = Gst.ElementFactory.make('videoscale', 'snap_scale')
            snap_caps = Gst.ElementFactory.make('capsfilter', 'snap_caps')
            # appsink element
            appsink = Gst.ElementFactory.make('appsink', 'appsink')
            appsink.set_property('emit-signals', False)
            appsink.set_property('max-buffers', 1)
            appsink.set_property('drop', True)
            appsink.set_property('sync', False)

            # capsfilter_stream ensures encoder receives I420 (YUV) which x264enc expects
            capsfilter_stream = Gst.ElementFactory.make('capsfilter', 'caps_stream')
            caps_stream_caps = Gst.Caps.from_string(f'video/x-raw,format=I420,width={width},height={height},framerate={fps}/1')
            capsfilter_stream.set_property('caps', caps_stream_caps)

            # snapshot target size (use configured snapshot size or fall back to camera size)
            snap_w = int(cfg.snapshot.width) if getattr(cfg, 'snapshot', None) and cfg.snapshot.width else width
            snap_h = int(cfg.snapshot.height) if getattr(cfg, 'snapshot', None) and cfg.snapshot.height else height
            snap_caps_obj = Gst.Caps.from_string(f'video/x-raw,format=BGR,width={snap_w},height={snap_h},framerate={fps}/1')
            snap_caps.set_property('caps', snap_caps_obj)

            elements = [src, convert, videorate, capsfilter, tee, qstream, enc_convert, capsfilter_stream, enc, h264parse, pay, udpsink, qsnap, valve, snap_scale, snap_caps, appsink]
            for el in elements:
                if el is None:
                    logger.error('GStreamer element missing while building pipeline')
                    raise RuntimeError('GStreamer element not available; ensure gstreamer plugins are installed')
                pipeline.add(el)

            logger.debug('Added elements: %s', [el.get_name() for el in elements])

            # Link source to convert using probed pipeline type.
            if pipeline_type == 'mjpeg':
                jpegdec = Gst.ElementFactory.make('jpegdec', 'jpegdec')
                if jpegdec is None:
                    raise RuntimeError('jpegdec not available; cannot decode MJPEG')
                pipeline.add(jpegdec)
                if not Gst.Element.link(src, jpegdec):
                    raise RuntimeError('Failed to link src->jpegdec')
                if not Gst.Element.link(jpegdec, convert):
                    raise RuntimeError('Failed to link jpegdec->convert')
            else:
                if not Gst.Element.link(src, convert):
                    raise RuntimeError('Failed to link src->convert')

            if not Gst.Element.link(convert, videorate):
                raise RuntimeError('Failed to link convert->videorate')
            if not Gst.Element.link(videorate, capsfilter):
                raise RuntimeError('Failed to link videorate->capsfilter')
            if not Gst.Element.link(capsfilter, tee):
                raise RuntimeError('Failed to link capsfilter->tee')

            # stream branch link via request pad
            tee_stream_pad = tee.get_request_pad('src_%u')
            qstream_sink = qstream.get_static_pad('sink')
            if not tee_stream_pad or not qstream_sink:
                raise RuntimeError('Failed to get pads for stream branch')
            tee_stream_pad.link(qstream_sink)
            if not Gst.Element.link(qstream, enc_convert):
                raise RuntimeError('Failed to link qstream->enc_convert')
            if not Gst.Element.link(enc_convert, capsfilter_stream):
                raise RuntimeError('Failed to link enc_convert->capsfilter_stream')
            if not Gst.Element.link(capsfilter_stream, enc):
                raise RuntimeError('Failed to link capsfilter_stream->enc')
            # link encoder -> h264parse -> pay
            if not Gst.Element.link(enc, h264parse):
                raise RuntimeError('Failed to link enc->h264parse')
            if not Gst.Element.link(h264parse, pay):
                raise RuntimeError('Failed to link h264parse->pay')
            # Ensure RTP payload type is standard for dynamic H264 (96)
            try:
                pay.set_property('pt', int(cfg.stream.payload_type))
                pay.set_property('mtu', int(cfg.stream.mtu))
            except Exception:
                pass
            if not Gst.Element.link(pay, udpsink):
                raise RuntimeError('Failed to link pay->udpsink')

            # snapshot branch link via request pad
            tee_snap_pad = tee.get_request_pad('src_%u')
            qsnap_sink = qsnap.get_static_pad('sink')
            if not tee_snap_pad or not qsnap_sink:
                raise RuntimeError('Failed to get pads for snapshot branch')
            tee_snap_pad.link(qsnap_sink)
            if not Gst.Element.link(qsnap, valve):
                raise RuntimeError('Failed to link qsnap->valve')
            # link valve -> videoscale -> caps -> appsink so snapshots match configured size
            if not Gst.Element.link(valve, snap_scale):
                raise RuntimeError('Failed to link valve->snap_scale')
            if not Gst.Element.link(snap_scale, snap_caps):
                raise RuntimeError('Failed to link snap_scale->snap_caps')
            if not Gst.Element.link(snap_caps, appsink):
                raise RuntimeError('Failed to link snap_caps->appsink')

            # tune encoder for low-latency if using software encoder
            try:
                if enc.get_name() == 'x264enc':
                    enc.set_property('tune', 'zerolatency')
                    enc.set_property('speed-preset', 'superfast')
            except Exception:
                pass

            # configure payloader
            try:
                pay.set_property('config-interval', 1)
            except Exception:
                pass

            # save handles
            self.pipeline = pipeline
            self._appsink = appsink
            self._valve = valve

            # set to playing
            logger.info('Setting pipeline to PLAYING')
            res = self.pipeline.set_state(Gst.State.PLAYING)
            logger.debug('set_state returned: %s', res)
            self._running = True
            # Print human-readable pipeline summary
            try:
                enc_name = enc.get_name() if enc is not None else 'None'
                hw = 'hardware' if cfg.stream.use_hardware else 'software'
                j = pipeline.get_by_name('jpegdec') is not None
                desc_lines = [
                    f"Pipeline: src(device={device}){' -> jpegdec' if j else ''} -> videoconvert -> videorate -> capsfilter -> tee",
                    f"  streaming branch: qstream(max={cfg.stream.qstream_max_buffers},leaky={cfg.stream.q_leaky}) -> enc_convert -> caps_stream(I420) -> {enc_name}({hw},bitrate={cfg.stream.bitrate}) -> h264parse -> rtph264pay(pt={cfg.stream.payload_type},mtu={cfg.stream.mtu}) -> udpsink({address}:{port})",
                    f"  snapshot branch: qsnap(max={cfg.stream.qsnap_max_buffers},leaky={cfg.stream.q_leaky}) -> valve(drop=True) -> appsink(max-buffers={cfg.stream.qsnap_max_buffers})",
                ]
                logger.info('\n%s', '\n'.join(desc_lines))
                try:
                    # try to dump a graph dot file for inspection
                    Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL, 'camera-pipeline')
                    logger.debug('Wrote pipeline dot file camera-pipeline.dot')
                except Exception:
                    logger.debug('Could not write pipeline dot file')
            except Exception:
                pass

    def stop(self) -> None:
        with self._lock:
            if not self._running or self.pipeline is None:
                logger.info('Stop called but pipeline not running')
                return
            logger.info('Stopping pipeline')
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except Exception as e:
                logger.error('Error stopping pipeline: %s', e)
            self.pipeline = None
            self._appsink = None
            self._valve = None
            self._running = False

    def snapshot(self, cfg, timeout_sec: float = 1.0):
        """Capture a single frame. If the streaming pipeline is running, briefly open the valve
        to let one buffer reach the appsink. If not running, create a short-lived pipeline to
        capture one sample from the device.
        Returns a numpy BGR frame or None on timeout/error."""
        logger.debug('Snapshot requested; timeout=%.3fs', timeout_sec)
        # Capture current state under lock, but do not hold the lock while pulling samples
        with self._lock:
            width = cfg.camera.width
            height = cfg.camera.height
            fps = cfg.camera.fps
            device = cfg.camera.device

            running = self._running and self.pipeline is not None and self._appsink is not None and self._valve is not None
            appsink = self._appsink
            valve = self._valve
        logger.debug('Snapshot state: running=%s appsink=%s valve=%s', running, bool(appsink), bool(valve))

        def _pull_sample_from_appsink(asink, timeout_ns=None):
            """Try available appsink pull methods in order and return a Gst.Sample or None.

            Preference order:
            - appsink.try_pull_sample(timeout) if available
            - appsink.pull_sample() if available
            - appsink.emit('pull-sample') as last resort
            """
            if asink is None:
                return None
            # try try_pull_sample if provided by bindings
            if hasattr(asink, 'try_pull_sample'):
                try:
                    return asink.try_pull_sample(timeout_ns)
                except Exception:
                    logger.exception('appsink.try_pull_sample exception while pulling sample')
                    # fall through to other options
            # try blocking pull_sample if available
            if hasattr(asink, 'pull_sample'):
                try:
                    return asink.pull_sample()
                except Exception:
                    logger.exception('appsink.pull_sample exception while pulling sample')
            # final fallback: emit the pull-sample signal
            try:
                return asink.emit('pull-sample')
            except Exception:
                logger.exception('appsink.emit pull-sample exception')
                return None

        if running and appsink is not None and valve is not None:
            logger.debug('Using live pipeline appsink for snapshot')
            # open valve to let one buffer through
            try:
                logger.debug('Opening valve')
                valve.set_property('drop', False)
            except Exception as e:
                logger.exception('Failed to open valve: %s', e)

            try:
                timeout_ns = int(timeout_sec * Gst.SECOND)
                sample = None
                sample = _pull_sample_from_appsink(appsink, timeout_ns)
                logger.debug('appsink pull returned: %s', bool(sample))

                if not sample:
                    logger.debug('No sample pulled from live appsink')
                    return None

                buf = sample.get_buffer()
                caps = sample.get_caps()
                try:
                    structure = caps.get_structure(0)
                    w = structure.get_value('width')
                    h = structure.get_value('height')
                except Exception:
                    logger.exception('Failed to read caps/structure from sample')
                    return None

                result, mapinfo = buf.map(Gst.MapFlags.READ)
                if not result:
                    logger.debug('Failed to map buffer')
                    return None
                try:
                    arr = np.frombuffer(mapinfo.data, dtype=np.uint8)
                    try:
                        frame = arr.reshape((h, w, 3)).copy()
                        logger.debug('Extracted frame from live appsink: shape=%s', getattr(frame, 'shape', None))
                        return frame
                    except Exception:
                        logger.exception('Failed to reshape buffer to frame')
                        return None
                finally:
                    buf.unmap(mapinfo)
            finally:
                # close valve again
                try:
                    logger.debug('Closing valve')
                    valve.set_property('drop', True)
                except Exception as e:
                    logger.exception('Failed to close valve: %s', e)

        # not running: use temporary GStreamer pipelines to capture one frame
        logger.debug('Not streaming: using temporary GStreamer pipelines for one-shot snapshot')
        pipeline_type = self._probe_pipeline_type(device, cfg)
        # determine snapshot target size (use configured snapshot size or fall back to camera size)
        snap_w = int(cfg.snapshot.width) if getattr(cfg, 'snapshot', None) and cfg.snapshot.width else width
        snap_h = int(cfg.snapshot.height) if getattr(cfg, 'snapshot', None) and cfg.snapshot.height else height
        mjpeg_launch = (
            f"v4l2src device={device} num-buffers=1 ! image/jpeg,width={snap_w},height={snap_h},framerate={fps}/1 ! "
            f"jpegdec ! videoconvert ! video/x-raw,format=BGR,width={snap_w},height={snap_h} ! "
            f"appsink name=tmpappsink emit-signals=false sync=false max-buffers=1 drop=true"
        )

        decode_launch = (
            f"v4l2src device={device} num-buffers=1 ! decodebin ! videoconvert ! "
            f"video/x-raw,format=BGR,width={snap_w},height={snap_h},framerate={fps}/1 ! "
            f"appsink name=tmpappsink emit-signals=false sync=false max-buffers=1 drop=true"
        )

        raw_launch = (
            f"v4l2src device={device} num-buffers=1 ! videoconvert ! "
            f"video/x-raw,format=BGR,width={snap_w},height={snap_h},framerate={fps}/1 ! "
            f"appsink name=tmpappsink emit-signals=false sync=false max-buffers=1 drop=true"
        )

        # order pipelines based on probe result
        if pipeline_type == 'mjpeg':
            default_order = [mjpeg_launch, decode_launch, raw_launch]
        else:
            default_order = [raw_launch, decode_launch, mjpeg_launch]

        # if we previously discovered a working launch for this device, try it first
        with self._lock:
            cached_launch = self._device_working_launch.get(device)
        if cached_launch:
            logger.debug('Found cached working pipeline for %s; trying it first', device)
            try_pipelines = [cached_launch]  # try the known-good pipeline first for speed
        else:
            try_pipelines = default_order

        for launch in try_pipelines:
            logger.debug('Trying pipeline: %s', launch)
            tmp = None
            try:
                tmp = Gst.parse_launch(launch)
            except Exception as e:
                logger.exception('parse_launch failed: %s', e)
                tmp = None

            if tmp is None:
                continue

            appsink = tmp.get_by_name('tmpappsink')
            if appsink is None:
                tmp.set_state(Gst.State.NULL)
                continue

            tmp.set_state(Gst.State.PLAYING)
            try:
                timeout_ns = int(timeout_sec * Gst.SECOND)

                # Wait for the bus to report ERROR or EOS before attempting a blocking pull.
                # This avoids hanging indefinitely when the pipeline fails to produce frames
                # (e.g. codec mismatch) but the appsink element stays alive.
                bus = tmp.get_bus()
                msg = bus.timed_pop_filtered(
                    timeout_ns,
                    Gst.MessageType.ERROR | Gst.MessageType.EOS,
                )
                if msg is not None and msg.type == Gst.MessageType.ERROR:
                    err, debug = msg.parse_error()
                    logger.debug('Temporary pipeline error (skipping): %s | %s', err, debug)
                    continue

                sample = None
                sample = _pull_sample_from_appsink(appsink, timeout_ns)
                logger.debug('tmp appsink pull returned: %s', bool(sample))

                if not sample:
                    logger.debug('No sample from temporary pipeline')
                    continue

                buf = sample.get_buffer()
                caps = sample.get_caps()
                try:
                    structure = caps.get_structure(0)
                    w = structure.get_value('width')
                    h = structure.get_value('height')
                except Exception:
                    logger.exception('Failed to read caps from temporary sample')
                    continue

                result, mapinfo = buf.map(Gst.MapFlags.READ)
                if not result:
                    logger.debug('Failed to map temporary buffer')
                    continue
                try:
                    arr = np.frombuffer(mapinfo.data, dtype=np.uint8)
                    try:
                        frame = arr.reshape((h, w, 3)).copy()
                        logger.debug('Temporary pipeline produced frame shape=%s', getattr(frame, 'shape', None))
                        # cache this working launch string for future fast-path
                        try:
                            with self._lock:
                                self._device_working_launch[device] = launch
                        except Exception:
                            logger.exception('Failed to cache working launch for device %s', device)
                        return frame
                    except Exception:
                        logger.exception('Failed to reshape temporary buffer')
                        continue
                finally:
                    buf.unmap(mapinfo)
            finally:
                try:
                    tmp.set_state(Gst.State.NULL)
                except Exception:
                    pass

        logger.debug('All temporary pipeline attempts failed')
        return None

    def frame_to_jpeg_bytes(self, frame: np.ndarray, quality: int = 90, timeout_sec: float = 2.0) -> Optional[bytes]:
        """Encode a BGR numpy frame to JPEG bytes using a short-lived GStreamer pipeline.

        This avoids using OpenCV for JPEG encoding.
        """
        # Use simplejpeg for fast in-memory encoding from BGR numpy array
        if frame is None:
            return None
        try:
            # simplejpeg expects RGB order
            rgb = frame[:, :, ::-1]
            # ensure C-contiguous memory layout (simplejpeg requires contiguous rows)
            rgb = np.ascontiguousarray(rgb)
            jpeg = simplejpeg.encode_jpeg(rgb, quality=int(quality), colorspace='RGB')
            return jpeg
        except Exception:
            logger.exception('simplejpeg.encode_jpeg failed')
            return None


def check_environment():
    """Check availability of required GStreamer elements and hardware encoders.

    Returns a dict with keys:
      - elements: mapping element_name -> bool
      - hw_encoder: bool
    """
    required = ['v4l2src', 'videoconvert', 'valve', 'appsink', 'rtph264pay', 'udpsink']
    available = {}
    for e in required:
        available[e] = Gst.ElementFactory.find(e) is not None

    # check for common hardware encoder plugins on RPi
    hw_candidates = ['v4l2h264enc', 'omxh264enc', 'v4l2_m2m_h264']
    hw = False
    for c in hw_candidates:
        if Gst.ElementFactory.find(c) is not None:
            hw = True
            break

    logger.debug('Hardware encoder present: %s', hw)
    return {'elements': available, 'hw_encoder': hw}



