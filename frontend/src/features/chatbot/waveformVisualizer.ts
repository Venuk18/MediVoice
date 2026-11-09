/**
 * High-performance canvas-based waveform visualizer for real-time audio visualization.
 * Renders live frequency equalizer bars directly onto an HTML5 Canvas context,
 * completely bypassing React reconciliation cycles for 60 FPS animation.
 */

export interface WaveformDrawOptions {
  barCount?: number;
  barWidth?: number;
  barGap?: number;
  activeColor?: string;
  idleColor?: string;
  glowBlur?: number;
}

const DEFAULT_OPTIONS: Required<WaveformDrawOptions> = {
  barCount: 8,
  barWidth: 7,
  barGap: 6,
  activeColor: '#25D9C3',
  idleColor: 'rgba(255, 255, 255, 0.8)',
  glowBlur: 8,
};

/**
 * Draws active frequency equalizer bars with acoustic RMS modulation.
 */
export function drawWaveformBars(
  canvas: HTMLCanvasElement | null,
  freqData: Uint8Array | number[],
  rms = 0,
  isSpeaking = false,
  options: WaveformDrawOptions = {}
): void {
  if (!canvas || typeof canvas.getContext !== 'function') return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const opts = { ...DEFAULT_OPTIONS, ...options };
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  const totalWidth = opts.barCount * opts.barWidth + (opts.barCount - 1) * opts.barGap;
  const startX = Math.max(0, (width - totalWidth) / 2);
  const step = Math.floor(freqData.length / opts.barCount) || 1;

  for (let i = 0; i < opts.barCount; i++) {
    const val = (freqData && freqData[i * step]) || 0;
    // Scale bar height based on spectral bin magnitude + acoustic RMS boost
    const scaled = Math.max(8, Math.min(val * 0.7 + rms * 70, height - 4));
    const x = startX + i * (opts.barWidth + opts.barGap);
    const y = (height - scaled) / 2;

    ctx.fillStyle = isSpeaking ? opts.activeColor : opts.idleColor;
    if (isSpeaking) {
      ctx.shadowColor = opts.activeColor;
      ctx.shadowBlur = opts.glowBlur;
    } else {
      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
    }

    ctx.beginPath();
    if (typeof (ctx as any).roundRect === 'function') {
      (ctx as any).roundRect(x, y, opts.barWidth, scaled, opts.barWidth / 2);
    } else {
      ctx.rect(x, y, opts.barWidth, scaled);
    }
    ctx.fill();
  }
}

/**
 * Draws placeholder idle bars matching MediVoice resting equalizer aesthetic.
 */
export function drawIdleWaveform(
  canvas: HTMLCanvasElement | null,
  options: WaveformDrawOptions = {}
): void {
  if (!canvas || typeof canvas.getContext !== 'function') return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const defaultBars = [14, 22, 38, 20, 32, 28, 22, 18];
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  const totalWidth = opts.barCount * opts.barWidth + (opts.barCount - 1) * opts.barGap;
  const startX = Math.max(0, (width - totalWidth) / 2);

  ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;

  for (let i = 0; i < opts.barCount; i++) {
    const defaultVal = defaultBars[i] || 20;
    const scaled = Math.max(8, Math.min(defaultVal * 0.65, height - 4));
    const x = startX + i * (opts.barWidth + opts.barGap);
    const y = (height - scaled) / 2;

    ctx.beginPath();
    if (typeof (ctx as any).roundRect === 'function') {
      (ctx as any).roundRect(x, y, opts.barWidth, scaled, opts.barWidth / 2);
    } else {
      ctx.rect(x, y, opts.barWidth, scaled);
    }
    ctx.fill();
  }
}

