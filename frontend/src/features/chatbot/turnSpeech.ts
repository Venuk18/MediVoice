export interface ChatTurnSpeechPolicy {
  isBookingDone: boolean;
  requiresConfirmation: boolean;
  voicePanelOpen: boolean;
}

export function shouldAutoSpeakChatTurn({
  isBookingDone,
  requiresConfirmation,
  voicePanelOpen,
}: ChatTurnSpeechPolicy): boolean {
  return !voicePanelOpen && (isBookingDone || requiresConfirmation);
}

export function shouldAutoPlayVoiceReply({
  voiceModeActive,
  audioAvailable,
}: {
  voiceModeActive: boolean;
  audioAvailable: boolean;
}): boolean {
  return voiceModeActive && audioAvailable;
}

export function shouldResumeVoiceMode(isBookingCompleted: boolean): boolean {
  return !isBookingCompleted;
}

export function base64ToBlob(base64: string, mimeType = 'audio/wav'): Blob {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Blob([bytes], { type: mimeType });
}

export class TurnAudioCache {
  private readonly audioUrls = new Map<string, string>();
  private readonly requests = new Map<string, Promise<string>>();
  private playingTurnId: string | null = null;

  get(turnId: string): string | undefined {
    return this.audioUrls.get(turnId);
  }

  remember(turnId: string, audioUrl: string): void {
    if (audioUrl) this.audioUrls.set(turnId, audioUrl);
  }

  getOrCreate(turnId: string, createAudioUrl: () => Promise<string>): Promise<string> {
    const cached = this.audioUrls.get(turnId);
    if (cached) return Promise.resolve(cached);

    const pending = this.requests.get(turnId);
    if (pending) return pending;

    const request = Promise.resolve()
      .then(createAudioUrl)
      .then((audioUrl) => {
        this.remember(turnId, audioUrl);
        return audioUrl;
      })
      .finally(() => this.requests.delete(turnId));
    this.requests.set(turnId, request);
    return request;
  }

  isPlaying(turnId: string): boolean {
    return this.playingTurnId === turnId;
  }

  beginPlayback(turnId: string): boolean {
    if (this.playingTurnId === turnId) return false;
    this.playingTurnId = turnId;
    return true;
  }

  finishPlayback(turnId: string): void {
    if (this.playingTurnId === turnId) this.playingTurnId = null;
  }

  dispose(revokeAudioUrl: (audioUrl: string) => void): void {
    for (const audioUrl of this.audioUrls.values()) revokeAudioUrl(audioUrl);
    this.audioUrls.clear();
    this.requests.clear();
    this.playingTurnId = null;
  }
}
