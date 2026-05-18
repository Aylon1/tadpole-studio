/**
 * RadioAudioEngine — AudioWorklet-based playback for radio mode.
 *
 * Uses an AudioWorkletNode that holds exclusive ownership of the PCM sample
 * data (transferred via postMessage, zero-copy). The worklet thread has no
 * shared-memory contention with the main thread, and its process() reads from
 * locally-owned Float32Arrays — the most isolated path from memory to audio
 * output possible in a browser.
 *
 * This eliminates audio hiccups when MLX saturates the Metal GPU / unified
 * memory during VAE decode.
 *
 * Library playback continues using the <audio> element unchanged.
 */

class RadioAudioEngine {
  private _ctx: AudioContext | null = null;
  private _gain: GainNode | null = null;
  private _worklet: AudioWorkletNode | null = null;
  private _source: AudioBufferSourceNode | null = null;
  private _useWorklet: boolean = true;
  private _modulePromise: Promise<void> | null = null;
  private _buffers = new Map<string, AudioBuffer>();
  private _currentSongId: string | null = null;

  private _offset = 0;
  private _startCtxTime = 0;
  private _playing = false;
  private _timeupdateInterval: ReturnType<typeof setInterval> | null = null;

  onended: (() => void) | null = null;
  ontimeupdate: ((time: number) => void) | null = null;

  /**
   * Create the AudioContext and GainNode synchronously.
   * MUST be called within a user gesture (click/tap) so the browser allows
   * the context to enter the "running" state.
   */
  private ensureContextSync(): AudioContext {
    if (!this._ctx) {
      this._ctx = new AudioContext({ latencyHint: 1.0, sampleRate: 48000 });
      this._gain = this._ctx.createGain();
      this._gain.connect(this._ctx.destination);
    }
    return this._ctx;
  }

  /**
   * Register the AudioWorklet module (async, but only needs to succeed once).
   * The AudioContext must already exist.
   */
  private ensureWorklet(): Promise<void> {
    const ctx = this.ensureContextSync();
    if (!ctx.audioWorklet) {
      this._useWorklet = false;
      return Promise.resolve();
    }
    if (!this._modulePromise) {
      this._modulePromise = ctx.audioWorklet.addModule(
        "/radio-worklet-processor.js",
      );
    }
    return this._modulePromise;
  }

  /**
   * Call within a user gesture to create + resume the AudioContext before
   * any async work (generation, decoding) begins. This prevents the browser
   * from blocking audio due to expired user gesture.
   */
  warmup(): void {
    const ctx = this.ensureContextSync();
    if (ctx.state === "suspended") {
      ctx.resume();
    }
  }

  // -- Buffer management --

  cacheBuffer(songId: string, buffer: AudioBuffer): void {
    this._buffers.set(songId, buffer);
  }

  hasBuffer(songId: string): boolean {
    return this._buffers.has(songId);
  }

  clearBuffers(): void {
    this._buffers.clear();
  }

  // -- Playback --

  async play(songId: string): Promise<boolean> {
    const buffer = this._buffers.get(songId);
    if (!buffer) return false;

    this.stopNodes();
    // Set immediately so duration getter works before await resolves
    this._currentSongId = songId;
    this._offset = 0;

    await this.ensureWorklet();
    const ctx = this._ctx!;

    // If stop() or another play() was called during await, bail out
    if (this._currentSongId !== songId) return false;

    if (ctx.state === "suspended") {
      await ctx.resume();
    }

    if (this._useWorklet) {
      // Extract channel data — slice() copies from the cached AudioBuffer so the
      // cache stays intact for repeat / re-play. Transfer moves ownership to the
      // worklet thread (zero-copy handoff, no shared memory).
      const channels: Float32Array[] = [];
      const transferables: ArrayBuffer[] = [];
      for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
        const copy = buffer.getChannelData(ch).slice();
        channels.push(copy);
        transferables.push(copy.buffer);
      }

      const worklet = new AudioWorkletNode(ctx, "radio-processor", {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [buffer.numberOfChannels],
      });
      worklet.connect(this._gain!);
      worklet.port.onmessage = (e) => {
        if (e.data.type === "ended") {
          this._playing = false;
          this._offset = 0;
          this.stopTimeupdateTimer();
          this.onended?.();
        }
      };
      worklet.port.postMessage(
        { type: "load", channels, length: buffer.length, startPos: 0 },
        transferables,
      );

      this._worklet = worklet;
    } else {
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(this._gain!);
      source.onended = () => {
        if (this._playing && this._currentSongId === songId) {
          this._playing = false;
          this._offset = 0;
          this.stopTimeupdateTimer();
          this.onended?.();
        }
      };
      source.start(0, this._offset);
      this._source = source;
    }

    this._startCtxTime = ctx.currentTime;
    this._playing = true;
    this.startTimeupdateTimer();
    return true;
  }

  pause(): void {
    if (!this._playing) return;
    this._offset = this.currentTime;
    
    if (this._useWorklet && this._worklet) {
      this._worklet.port.postMessage({ type: "pause" });
    } else if (!this._useWorklet && this._source) {
      this._source.stop();
      this._source.disconnect();
      this._source = null;
    }
    
    this._playing = false;
    this.stopTimeupdateTimer();
  }

  resume(): void {
    if (this._playing || !this._ctx) return;
    
    if (this._useWorklet && this._worklet) {
      this._worklet.port.postMessage({ type: "resume" });
    } else if (!this._useWorklet) {
      const buffer = this._currentSongId
        ? this._buffers.get(this._currentSongId)
        : null;
      if (buffer) {
        const source = this._ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(this._gain!);
        source.onended = () => {
          if (this._playing && this._source === source) {
            this._playing = false;
            this._offset = 0;
            this.stopTimeupdateTimer();
            this.onended?.();
          }
        };
        source.start(0, this._offset);
        this._source = source;
      }
    }
    
    this._startCtxTime = this._ctx.currentTime;
    this._playing = true;
    this.startTimeupdateTimer();
  }

  seek(time: number): void {
    const buffer = this._currentSongId
      ? this._buffers.get(this._currentSongId)
      : null;
    if (!buffer) return;

    this._offset = Math.max(0, Math.min(time, buffer.duration));
    
    if (this._useWorklet && this._worklet) {
      const samplePos = Math.round(this._offset * buffer.sampleRate);
      this._worklet.port.postMessage({ type: "seek", position: samplePos });
      if (this._playing && this._ctx) {
        this._startCtxTime = this._ctx.currentTime;
      }
    } else if (!this._useWorklet) {
      const wasPlaying = this._playing;
      if (wasPlaying && this._source) {
        this._source.stop();
        this._source.disconnect();
        this._source = null;
      }
      if (wasPlaying) {
        const source = this._ctx!.createBufferSource();
        source.buffer = buffer;
        source.connect(this._gain!);
        source.onended = () => {
          if (this._playing && this._source === source) {
            this._playing = false;
            this._offset = 0;
            this.stopTimeupdateTimer();
            this.onended?.();
          }
        };
        source.start(0, this._offset);
        this._source = source;
        this._startCtxTime = this._ctx!.currentTime;
      }
    }
  }

  setVolume(v: number): void {
    if (this._gain) {
      this._gain.gain.value = Math.max(0, Math.min(1, v));
    }
  }

  stop(): void {
    this.stopNodes();
    this._currentSongId = null;
    this._offset = 0;
  }

  get currentTime(): number {
    if (!this._playing || !this._ctx) return this._offset;
    return this._offset + (this._ctx.currentTime - this._startCtxTime);
  }

  get duration(): number {
    const buffer = this._currentSongId
      ? this._buffers.get(this._currentSongId)
      : null;
    return buffer?.duration ?? 0;
  }

  get playing(): boolean {
    return this._playing;
  }

  get currentSongId(): string | null {
    return this._currentSongId;
  }

  get audioContext(): AudioContext | null {
    return this._ctx;
  }

  // -- Internal helpers --

  private stopNodes(): void {
    if (this._worklet) {
      this._worklet.port.postMessage({ type: "stop" });
      this._worklet.disconnect();
      this._worklet = null;
    }
    if (this._source) {
      try {
        this._source.stop();
      } catch (e) {
        // ignore if already stopped
      }
      this._source.disconnect();
      this._source = null;
    }
    this._playing = false;
    this.stopTimeupdateTimer();
  }

  private startTimeupdateTimer(): void {
    this.stopTimeupdateTimer();
    this._timeupdateInterval = setInterval(() => {
      if (this._playing && this.ontimeupdate) {
        this.ontimeupdate(this.currentTime);
      }
    }, 400);
  }

  private stopTimeupdateTimer(): void {
    if (this._timeupdateInterval !== null) {
      clearInterval(this._timeupdateInterval);
      this._timeupdateInterval = null;
    }
  }
}

export const radioEngine = new RadioAudioEngine();
