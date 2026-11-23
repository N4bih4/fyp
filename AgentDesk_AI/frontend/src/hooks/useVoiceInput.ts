import { useRef, type MutableRefObject } from 'react';
import { authMessage, hasApiToken, voiceApi, type Preferences } from '../api';
import { afterInterruption, isSpeechEcho } from '../voice';
import { stripWakeWord, wakeWords } from '../wakeWord';
import { WhisperRecognition } from '../speech/whisperRecognition';
import type { SpeechRecognitionConstructor, SpeechRecognitionLike } from '../speech/recognitionTypes';
import { errMsg } from '../taskFormat';
import type { VoiceCore } from './useVoiceCore';

interface Params {
  voice: VoiceCore;
  prefs: Preferences | null;
  voiceLanguage: string;
  setCommand: (text: string) => void;
  setBanner: (message: string | null) => void;
  submittingRef: MutableRefObject<boolean>;
  runCommandRef: MutableRefObject<(text: string) => Promise<void>>;
}

/** Microphone side of the voice loop: start/stop listening, queue spoken commands, handle recogniser events. */
export function useVoiceInput({ voice: v, prefs, voiceLanguage, setCommand, setBanner, submittingRef, runCommandRef }: Params) {
  const idleTimerRef = useRef<number | null>(null);
  /** True when the assistant was waiting for an answer (follow-up window) while this sentence was heard: no wake word is needed then. */
  const followUpHeardRef = useRef(false);
  /** After the name was said alone ("Nabiha") the next sentence, within 8 s, is the command: no second name needed. */
  const armedUntilRef = useRef(0);
  const stopHandsFree = (message: string) => {
    const queuedCount = v.voiceQueueRef.current.length;
    v.handsFreeRef.current = false;
    v.setHandsFree(false);
    v.setListening(false);
    v.voiceWaitingForTaskRef.current = false;
    v.voiceTaskActiveRef.current = false;
    v.voiceSpeakingRef.current = false;
    v.speechEpochRef.current += 1;
    v.speechFinishRef.current = () => {};
    v.interruptedSpeechRef.current = false;
    v.spokenTextRef.current = '';
    v.voiceQueueRef.current = [];
    v.voiceCommandRef.current = '';
    if (v.voiceDebounceRef.current !== null) window.clearTimeout(v.voiceDebounceRef.current);
    if (v.voiceRestartRef.current !== null) window.clearTimeout(v.voiceRestartRef.current);
    v.voiceDebounceRef.current = null;
    v.voiceRestartRef.current = null;
    v.recognitionRef.current?.abort();
    v.recognitionRef.current = null;
    v.playerRef.current?.stop();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    v.setVoiceMessage(
      queuedCount > 0 ? `${message} Cleared ${queuedCount} queued command(s).` : message,
    );
  };

  /** After silence the server (its own clock) says whether to wait, to ask "Shall I end this task?" (then listen 15 s), or that the task ended. */
  const scheduleIdle = (afterMs: number) => {
    if (idleTimerRef.current !== null) window.clearTimeout(idleTimerRef.current);
    idleTimerRef.current = window.setTimeout(async () => {
      idleTimerRef.current = null;
      try {
        const r = await voiceApi.sessionIdle(voiceLanguage);
        if (r.action === 'wait') scheduleIdle(Math.max(1000, (r.retry_in ?? 10) * 1000 + 500));
        else if (r.action === 'ask') { await v.playerRef.current?.speak(r.text); beginFollowUp(15000); }
        else if (r.action === 'ended') { await v.playerRef.current?.speak(r.text); }
      } catch { /* the page keeps working without it */ }
    }, afterMs);
  };

  const beginFollowUp = (ms?: number) => {
    if (idleTimerRef.current !== null) { window.clearTimeout(idleTimerRef.current); idleTimerRef.current = null; }
    v.voiceTaskActiveRef.current = false;
    v.voiceWaitingForTaskRef.current = false;
    if (v.recognitionRef.current) return;
    v.handsFreeRef.current = true;
    v.setHandsFree(true);
    v.startListeningRef.current();
    v.followUpTimerRef.current = window.setTimeout(() => {
      v.followUpTimerRef.current = null;
      if (v.voiceCommandRef.current || v.voiceDebounceRef.current !== null || v.voiceQueueRef.current.length) return;
      v.handsFreeRef.current = false;
      v.setHandsFree(false);
      v.recognitionRef.current?.abort();
      v.recognitionRef.current = null;
      v.setListening(false);
      scheduleIdle(1000);   // the microphone closes, the TASK stays open: only two minutes of silence (asked first) or "end task" ends it
    }, ms ?? v.followUpMs);
  };

  /** Stops the assistant mid-sentence and goes back to listening ("Stop speaking" button). */
  const stopSpeaking = () => {
    v.interruptedSpeechRef.current = true;
    v.speechFinishRef.current();
    v.playerRef.current?.stop();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    v.startListeningRef.current();
    v.setVoiceMessage('Bolna rok diya. Agli command batayein.');
  };

  const toggleVoiceInput = () => {
    if (v.handsFreeRef.current) {
      stopHandsFree('Hands-free voice mode stopped.');
      return;
    }
    if (!hasApiToken()) {
      setBanner(authMessage());
      v.setVoiceMessage(authMessage());
      return;
    }
    const speechWindow = window as typeof window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    const useWhisper = v.speechReadyRef.current && WhisperRecognition.supported;
    if (!Recognition && !useWhisper) {
      v.setVoiceMessage('Voice input is not supported in this browser. Please use Chrome or type your command.');
      return;
    }

    if (v.listenModeRef.current === 'off') {
      v.setVoiceMessage('Listen mode is Off (Settings). Type your command instead.');
      return;
    }
    v.handsFreeRef.current = true;
    v.setHandsFree(true);
    v.voiceNetworkErrorsRef.current = 0;
    v.setVoiceMessage(v.listenModeRef.current === 'push_to_talk'
      ? 'Listening for one command…'
      : 'Hands-free is on. Speak commands at any time; they will run one by one.');

    v.drainVoiceQueueRef.current = () => {
      if (
        !v.handsFreeRef.current ||
        v.voiceTaskActiveRef.current ||
        v.voiceQueueRef.current.length === 0 ||
        submittingRef.current
      )
        return;
      const nextCommand = v.voiceQueueRef.current.shift();
      if (!nextCommand) return;
      v.voiceTaskActiveRef.current = true;
      v.voiceWaitingForTaskRef.current = true;
      setCommand(nextCommand);
      v.setVoiceMessage(
        v.voiceQueueRef.current.length
          ? `Working on: ${nextCommand}. ${v.voiceQueueRef.current.length} command(s) queued.`
          : `Working on: ${nextCommand}. Keep speaking to queue more commands.`,
      );
      void runCommandRef.current(nextCommand);
    };

    v.startListeningRef.current = () => {
      if (!v.handsFreeRef.current || v.recognitionRef.current) return;
      if (v.followUpTimerRef.current !== null) {
        window.clearTimeout(v.followUpTimerRef.current);
        v.followUpTimerRef.current = null;
      }
      const recognition = (useWhisper ? new WhisperRecognition() : new Recognition!()) as unknown as SpeechRecognitionLike;
      if (recognition instanceof WhisperRecognition) {
        // Whisper spells what it expects: the WAKE WORD (twice, it is the word that matters most) and the assistant's name come first.
        const names = wakeWords(prefs?.persona.wake_word ?? '');
        recognition.prompt = [...names, ...names, prefs?.persona.name, 'Chrome kholo, Notepad band karo, VS Code open karo, Antigravity chalao, folder banao Documents mein, volume kam karo, YouTube, WhatsApp, Excel, Word, Desktop, Downloads, FYP folder, FYP report, DevOps, Gmail, screenshot'].filter(Boolean).join(', ');
        recognition.onspeechstart = () => {
          // Barge-in: the user began talking while the assistant was speaking.
          if (!v.voiceSpeakingRef.current && !v.playerRef.current?.speaking) return;
          v.interruptedSpeechRef.current = true;
          v.voiceSpeakingRef.current = false;
          v.playerRef.current?.stop();
          v.speechFinishRef.current();
          v.setVoiceMessage('Ji, sun raha hoon. Agli command batayein.');
        };
      }
      recognition.lang = voiceLanguage === 'auto' ? 'en-US' : voiceLanguage;
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onresult = (event) => {
        if (!v.handsFreeRef.current) return;
        const heard = Array.from({ length: event.results.length - event.resultIndex }, (_, offset) => event.results[event.resultIndex + offset][0].transcript.trim()).filter(Boolean).join(' ');
        // Ignore the assistant's own short reply if the microphone hears it.
        if (v.voiceSpeakingRef.current && isSpeechEcho(heard, v.spokenTextRef.current)) return;
        if (heard && v.followUpTimerRef.current !== null) {
          followUpHeardRef.current = true;
          window.clearTimeout(v.followUpTimerRef.current);
          v.followUpTimerRef.current = null;
        }
        if (heard) v.setHeard([v.voiceCommandRef.current, heard].filter(Boolean).join(' '));
        if (heard && v.voiceSpeakingRef.current) {
          v.interruptedSpeechRef.current = true;
          v.voiceSpeakingRef.current = false;
          v.speechFinishRef.current();
          v.playerRef.current?.stop();
          v.playerRef.current?.stop();
          if ('speechSynthesis' in window) window.speechSynthesis.cancel();
          v.setVoiceMessage('Ji, sun raha hoon. Agli command batayein.');
        }
        const finalText = Array.from({ length: event.results.length - event.resultIndex }, (_, offset) => {
          const result = event.results[event.resultIndex + offset];
          return result.isFinal ? result[0].transcript.trim() : '';
        }).filter(Boolean).join(' ');
        if (!finalText) return;
        v.voiceNetworkErrorsRef.current = 0;
        const nextText = v.interruptedSpeechRef.current ? afterInterruption(finalText) : finalText;
        v.interruptedSpeechRef.current = false;
        if (!nextText) return;
        v.voiceCommandRef.current = [v.voiceCommandRef.current, nextText].filter(Boolean).join(' ').trim();
        v.setHeard(v.voiceCommandRef.current);
        v.setVoiceMessage(`Heard: ${v.voiceCommandRef.current}. Finish speaking or pause briefly to send.`);
        if (v.voiceDebounceRef.current !== null) window.clearTimeout(v.voiceDebounceRef.current);
        v.voiceDebounceRef.current = window.setTimeout(() => {
          v.voiceDebounceRef.current = null;
          const transcript = v.voiceCommandRef.current.trim();
          v.voiceCommandRef.current = '';
          if (!transcript || !v.handsFreeRef.current) return;
          // Hands-free hears the whole room (a fan, music, a video): with a wake word set, only a sentence that starts with the name is a command.
          // Pressing the microphone for ONE command (push to talk) and answering a question the assistant just asked need no name.
          let command = transcript;
          const wake = (prefs?.persona.wake_word ?? '').trim();
          const armed = Date.now() < armedUntilRef.current;
          const answering = followUpHeardRef.current || armed;
          followUpHeardRef.current = false;
          armedUntilRef.current = 0;
          if (wake && v.listenModeRef.current === 'hands_free' && !answering) {
            const addressed = stripWakeWord(transcript, wake);
            if (addressed === null) {
              v.setHeard('');
              v.setVoiceMessage(`Ignored: I heard "${transcript}". Start with "${wake}" (any accent is fine).`);
              return;
            }
            if (!addressed) {
              v.setHeard('');
              v.setVoiceMessage(`Ji, boliye. (${wake} sun rahi hai)`);
              armedUntilRef.current = Date.now() + 8000;
              return;
            }
            command = addressed;
          }
          v.voiceQueueRef.current.push(command);
          // Noise must not pile up: a command that waited behind three newer ones is stale, so only the newest three are kept.
          while (v.voiceQueueRef.current.length > 3) v.voiceQueueRef.current.shift();
          v.setHeard('');
          v.setVoiceMessage(
            v.voiceTaskActiveRef.current
              ? `Queued: ${command}. ${v.voiceQueueRef.current.length} command(s) waiting.`
              : `Starting: ${command}`,
          );
          v.drainVoiceQueueRef.current();
          if (v.listenModeRef.current === 'push_to_talk') {
            // One command per press: the microphone turns off once the command is sent.
            v.handsFreeRef.current = false;
            v.setHandsFree(false);
            v.recognitionRef.current?.abort();
            v.recognitionRef.current = null;
            v.setListening(false);
          }
        }, recognition instanceof WhisperRecognition ? 120 : 2200); // Whisper input is already a finished sentence (a command was held 500 ms before)
        if (recognition instanceof WhisperRecognition) {
          v.speechEndedAtRef.current = recognition.lastSpeechEndAt;
          if (recognition.lastSpeechEndAt > 0) void voiceApi.latency('local', { transcribed: performance.now() - recognition.lastSpeechEndAt });
        }
      };
      recognition.onerror = (event) => {
        if (!v.handsFreeRef.current) return;
        if (event.error === 'network') {
          v.voiceNetworkErrorsRef.current += 1;
          v.setVoiceMessage(`Voice service error${event.message ? ` (${event.message})` : ''}. Hands-free will keep retrying; check that the backend is running and the speech service is reachable.`);
          return;
        }
        if (event.error === 'no-speech' || event.error === 'aborted') return;
        if (event.error === 'not-authorized') {
          stopHandsFree(event.message ?? authMessage());
          return;
        }
        stopHandsFree(
          event.error === 'not-allowed' || event.error === 'service-not-allowed'
            ? 'Microphone access was blocked. Allow microphone access for this site and try again.'
            : `Voice input stopped (${event.error}). Check microphone permission and try again.`,
        );
      };
      recognition.onend = () => {
        v.setListening(false);
        if (v.recognitionRef.current === recognition) v.recognitionRef.current = null;
        if (!v.handsFreeRef.current) return;
        const delay = v.voiceNetworkErrorsRef.current
          ? Math.min(1000 * 2 ** (v.voiceNetworkErrorsRef.current - 1), 15000)
          : 350;
        v.voiceRestartRef.current = window.setTimeout(() => {
          v.voiceRestartRef.current = null;
          v.startListeningRef.current();
        }, delay);
      };
      v.recognitionRef.current = recognition;
      try {
        recognition.start();
        v.setListening(true);
        v.setVoiceMessage(v.listenModeRef.current === 'push_to_talk' ? 'Listening… say one command.' : 'Hands-free is on. Listening… Speak a command.');
      } catch (error) {
        v.recognitionRef.current = null;
        v.setListening(false);
        stopHandsFree(`Could not start voice input: ${errMsg(error)}`);
      }
    };
    v.startListeningRef.current();
  };

  return { toggleVoiceInput, stopHandsFree, beginFollowUp, stopSpeaking };
}
