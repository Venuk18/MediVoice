import assert from 'node:assert/strict';
import test from 'node:test';

import {
  shouldAutoPlayVoiceReply,
  shouldAutoSpeakChatTurn,
  shouldResumeVoiceMode,
  TurnAudioCache,
} from '../src/features/chatbot/turnSpeech.ts';

test('normal assistant audio auto-plays while voice interaction is active', () => {
  assert.equal(shouldAutoPlayVoiceReply({ voiceModeActive: true, audioAvailable: true }), true);
  assert.equal(shouldAutoPlayVoiceReply({ voiceModeActive: false, audioAvailable: true }), false);
});

test('pending final confirmation is auto-spoken without treating it as booked', () => {
  assert.equal(shouldAutoSpeakChatTurn({
    isBookingDone: false,
    requiresConfirmation: true,
    voicePanelOpen: false,
  }), true);
});

test('chat does not start another player when the voice panel owns playback', () => {
  assert.equal(shouldAutoSpeakChatTurn({
    isBookingDone: false,
    requiresConfirmation: true,
    voicePanelOpen: true,
  }), false);
});

test('Listen fallback reuses the same audio and duplicate synthesis requests share one promise', async () => {
  const cache = new TurnAudioCache();
  let syntheses = 0;
  let finishSynthesis;
  const request = () => cache.getOrCreate('turn-1', () => {
    syntheses += 1;
    return new Promise((resolve) => { finishSynthesis = resolve; });
  });

  const autoPlayRequest = request();
  const duplicateRequest = request();
  await Promise.resolve();
  assert.equal(syntheses, 1);

  finishSynthesis('blob:confirmation-audio');
  assert.equal(await autoPlayRequest, 'blob:confirmation-audio');
  assert.equal(await duplicateRequest, 'blob:confirmation-audio');
  assert.equal(await cache.getOrCreate('turn-1', async () => {
    syntheses += 1;
    return 'blob:duplicate';
  }), 'blob:confirmation-audio');
  assert.equal(syntheses, 1);
});

test('same assistant turn cannot start playback twice concurrently', () => {
  const cache = new TurnAudioCache();
  assert.equal(cache.beginPlayback('turn-1'), true);
  assert.equal(cache.beginPlayback('turn-1'), false);
  cache.finishPlayback('turn-1');
  assert.equal(cache.beginPlayback('turn-1'), true);
});

test('voice mode resumes listening after the pending confirmation prompt', () => {
  assert.equal(shouldResumeVoiceMode(false), true);
  assert.equal(shouldResumeVoiceMode(true), false);
});

test('cached audio URLs are released when the chat is disposed', () => {
  const cache = new TurnAudioCache();
  cache.remember('turn-1', 'blob:audio');
  const revoked = [];
  cache.dispose((url) => revoked.push(url));
  assert.deepEqual(revoked, ['blob:audio']);
  assert.equal(cache.get('turn-1'), undefined);
});
