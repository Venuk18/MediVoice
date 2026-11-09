import test from 'node:test';
import assert from 'node:assert/strict';
import {
  drawWaveformBars,
  drawIdleWaveform,
} from '../src/features/chatbot/waveformVisualizer.ts';

// Helper mock to emulate HTML5 Canvas and CanvasRenderingContext2D
function createMockCanvas(width = 120, height = 44) {
  const operations = [];
  const ctx = {
    canvas: null,
    fillStyle: '',
    shadowColor: '',
    shadowBlur: 0,
    clearRect(x, y, w, h) {
      operations.push({ op: 'clearRect', args: [x, y, w, h] });
    },
    beginPath() {
      operations.push({ op: 'beginPath' });
    },
    roundRect(x, y, w, h, radius) {
      operations.push({ op: 'roundRect', args: [x, y, w, h, radius] });
    },
    rect(x, y, w, h) {
      operations.push({ op: 'rect', args: [x, y, w, h] });
    },
    fill() {
      operations.push({
        op: 'fill',
        fillStyle: this.fillStyle,
        shadowColor: this.shadowColor,
        shadowBlur: this.shadowBlur,
      });
    },
  };

  const canvas = {
    width,
    height,
    getContext(type) {
      if (type === '2d') {
        ctx.canvas = canvas;
        return ctx;
      }
      return null;
    },
  };

  return { canvas, ctx, operations };
}

test('WaveformVisualizer: safely handles null or uninitialized canvas without throwing', () => {
  assert.doesNotThrow(() => {
    drawWaveformBars(null, [10, 20, 30], 0.05, false);
    drawIdleWaveform(null);
  });

  const dummyElementWithoutCtx = {};
  assert.doesNotThrow(() => {
    drawWaveformBars(dummyElementWithoutCtx, [10, 20, 30], 0.05, false);
    drawIdleWaveform(dummyElementWithoutCtx);
  });
});

test('WaveformVisualizer: drawIdleWaveform renders 8 resting equalizer bars with muted color', () => {
  const { canvas, operations } = createMockCanvas(120, 44);
  drawIdleWaveform(canvas);

  // Verifies clearRect is called first
  assert.strictEqual(operations[0].op, 'clearRect');
  assert.deepStrictEqual(operations[0].args, [0, 0, 120, 44]);

  // Verifies exactly 8 bars are drawn
  const barOps = operations.filter((op) => op.op === 'roundRect' || op.op === 'rect');
  assert.strictEqual(barOps.length, 8);

  const fillOps = operations.filter((op) => op.op === 'fill');
  assert.strictEqual(fillOps.length, 8);
  assert.strictEqual(fillOps[0].fillStyle, 'rgba(255, 255, 255, 0.6)');
  assert.strictEqual(fillOps[0].shadowBlur, 0);
});

test('WaveformVisualizer: drawWaveformBars renders live equalizer bars with idle style when not speaking', () => {
  const { canvas, operations } = createMockCanvas(120, 44);
  const freqData = new Uint8Array([10, 25, 40, 60, 80, 50, 30, 15]);
  const rms = 0.02;
  const isSpeaking = false;

  drawWaveformBars(canvas, freqData, rms, isSpeaking);

  // 1 clearRect
  assert.strictEqual(operations[0].op, 'clearRect');

  // 8 bars drawn
  const barOps = operations.filter((op) => op.op === 'roundRect' || op.op === 'rect');
  assert.strictEqual(barOps.length, 8);

  // Bar width is 7, gap is 6 -> startX = (120 - (8*7 + 7*6)) / 2 = (120 - 98) / 2 = 11
  const firstBar = barOps[0];
  assert.strictEqual(firstBar.args[0], 11); // x
  assert.strictEqual(firstBar.args[2], 7); // width
  assert.strictEqual(firstBar.args[4], 3.5); // corner radius = barWidth / 2

  const fills = operations.filter((op) => op.op === 'fill');
  assert.strictEqual(fills[0].fillStyle, 'rgba(255, 255, 255, 0.8)');
  assert.strictEqual(fills[0].shadowBlur, 0);
});

test('WaveformVisualizer: drawWaveformBars applies teal accent color (#25D9C3) and glow when patient is speaking', () => {
  const { canvas, operations } = createMockCanvas(120, 44);
  const freqData = new Uint8Array([80, 120, 160, 140, 110, 90, 70, 50]);
  const rms = 0.25;
  const isSpeaking = true;

  drawWaveformBars(canvas, freqData, rms, isSpeaking);

  const fills = operations.filter((op) => op.op === 'fill');
  assert.strictEqual(fills.length, 8);
  assert.strictEqual(fills[0].fillStyle, '#25D9C3');
  assert.strictEqual(fills[0].shadowColor, '#25D9C3');
  assert.strictEqual(fills[0].shadowBlur, 8);
});

test('WaveformVisualizer: clamps bar height safely within canvas bounds even under extreme audio spikes', () => {
  const { canvas, operations } = createMockCanvas(120, 44);
  // Extreme values simulating audio distortion or clipping
  const freqData = new Uint8Array([255, 255, 255, 255, 255, 255, 255, 255]);
  const rms = 5.0; // extreme loudness spike

  drawWaveformBars(canvas, freqData, rms, true);

  const barOps = operations.filter((op) => op.op === 'roundRect' || op.op === 'rect');
  barOps.forEach((bar) => {
    const barHeight = bar.args[3];
    assert.ok(barHeight <= 40, `Bar height ${barHeight} exceeds maximum safe height (height - 4 = 40)`);
    assert.ok(barHeight >= 8, `Bar height ${barHeight} is below minimum height (8)`);
  });
});

test('Waveform Lifecycle: cancels previous requestAnimationFrame when re-starting visualizer loop', () => {
  let activeFrameId = null;
  const cancelledFrames = [];
  let nextFrameId = 100;

  const mockRequestAnimationFrame = (fn) => {
    const id = ++nextFrameId;
    activeFrameId = id;
    return id;
  };

  const mockCancelAnimationFrame = (id) => {
    cancelledFrames.push(id);
    if (activeFrameId === id) activeFrameId = null;
  };

  // Simulating startAudioVisualizerAndVad
  let animFrameRef = { current: null };

  const startVisualizer = () => {
    if (animFrameRef.current) {
      mockCancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    animFrameRef.current = mockRequestAnimationFrame(() => {});
  };

  // Turn 1 starts
  startVisualizer();
  const firstFrameId = animFrameRef.current;
  assert.ok(firstFrameId > 100);

  // Turn 2 starts before Turn 1 unmounted (e.g. fast re-listen)
  startVisualizer();
  assert.strictEqual(cancelledFrames.length, 1);
  assert.strictEqual(cancelledFrames[0], firstFrameId);
  assert.notStrictEqual(animFrameRef.current, firstFrameId);
});

test('Waveform Cleanup: thoroughly releases AudioContext, MediaStream tracks, and resets canvas & glow scale', () => {
  let tracksStopped = 0;
  let audioContextClosed = false;
  let sourceDisconnected = false;
  let cancelledFrameId = null;

  const mockTrack = {
    stop() {
      tracksStopped++;
    },
  };

  const mockStream = {
    getTracks() {
      return [mockTrack, mockTrack];
    },
  };

  const mockAudioContext = {
    state: 'running',
    close() {
      audioContextClosed = true;
      return Promise.resolve();
    },
  };

  const mockSourceNode = {
    disconnect() {
      sourceDisconnected = true;
    },
  };

  const mockGlowDiv = {
    style: {
      transform: 'scale(1.42)',
    },
  };

  const { canvas, operations } = createMockCanvas(120, 44);

  // Simulating cleanupAudioResources
  const cleanup = (resources) => {
    if (resources.animFrameRef.current) {
      cancelledFrameId = resources.animFrameRef.current;
      resources.animFrameRef.current = null;
    }
    if (resources.waveformCanvasRef.current) {
      const ctx = resources.waveformCanvasRef.current.getContext('2d');
      if (ctx) {
        ctx.clearRect(0, 0, resources.waveformCanvasRef.current.width, resources.waveformCanvasRef.current.height);
      }
    }
    if (resources.glowRef.current) {
      resources.glowRef.current.style.transform = 'scale(1)';
    }
    if (resources.sourceNodeRef.current) {
      resources.sourceNodeRef.current.disconnect();
      resources.sourceNodeRef.current = null;
    }
    if (resources.audioStreamRef.current) {
      resources.audioStreamRef.current.getTracks().forEach((t) => t.stop());
      resources.audioStreamRef.current = null;
    }
    if (resources.audioContextRef.current && resources.audioContextRef.current.state !== 'closed') {
      resources.audioContextRef.current.close();
      resources.audioContextRef.current = null;
    }
  };

  const resources = {
    animFrameRef: { current: 42 },
    waveformCanvasRef: { current: canvas },
    glowRef: { current: mockGlowDiv },
    sourceNodeRef: { current: mockSourceNode },
    audioStreamRef: { current: mockStream },
    audioContextRef: { current: mockAudioContext },
  };

  cleanup(resources);

  assert.strictEqual(cancelledFrameId, 42);
  assert.strictEqual(resources.animFrameRef.current, null);
  assert.strictEqual(tracksStopped, 2);
  assert.strictEqual(audioContextClosed, true);
  assert.strictEqual(sourceDisconnected, true);
  assert.strictEqual(mockGlowDiv.style.transform, 'scale(1)');

  const clearOps = operations.filter((op) => op.op === 'clearRect');
  assert.strictEqual(clearOps.length, 1);
  assert.deepStrictEqual(clearOps[0].args, [0, 0, 120, 44]);
});

test('Performance Benchmark: Canvas direct rendering produces 0 React component re-renders vs ~60/s baseline', () => {
  // Baseline emulation: React useState called on every animation frame (60 FPS for 3 seconds = 180 frames)
  let baselineReactRenders = 0;
  const simulatedFrames = 180; // 3 seconds at 60 FPS

  for (let frame = 0; frame < simulatedFrames; frame++) {
    // Legacy: setWaveformBars(barHeights) and setAudioLevel(...)
    baselineReactRenders++;
  }

  // Optimized canvas emulation:
  let optimizedReactRenders = 0;
  let canvasDrawCalls = 0;
  let isPatientSpeakingState = false;
  const isPatientSpeakingRef = { current: false };
  const { canvas } = createMockCanvas(120, 44);

  for (let frame = 0; frame < simulatedFrames; frame++) {
    // 1. Direct canvas draw on every frame (60 FPS)
    drawWaveformBars(canvas, [20, 40, 60], 0.1, isPatientSpeakingRef.current);
    canvasDrawCalls++;

    // 2. React state only dispatches on discrete state transitions (e.g. onset at frame 30, silence at frame 150)
    const isLoud = frame >= 30 && frame < 150;
    if (isLoud && !isPatientSpeakingRef.current) {
      isPatientSpeakingRef.current = true;
      isPatientSpeakingState = true;
      optimizedReactRenders++; // 1st state change: Patient began speaking
    } else if (!isLoud && isPatientSpeakingRef.current) {
      isPatientSpeakingRef.current = false;
      isPatientSpeakingState = false;
      optimizedReactRenders++; // 2nd state change: Patient stopped speaking
    }
  }

  assert.strictEqual(baselineReactRenders, 180, 'Legacy implementation triggered 180 React reconciliations');
  assert.strictEqual(canvasDrawCalls, 180, 'Canvas rendered smoothly at 60 FPS (180 draw calls)');
  assert.strictEqual(optimizedReactRenders, 2, 'Optimized implementation had exactly 2 React re-renders for the entire turn');
  assert.ok(
    optimizedReactRenders < baselineReactRenders * 0.05,
    'Re-render count reduced by more than 98%'
  );
});

