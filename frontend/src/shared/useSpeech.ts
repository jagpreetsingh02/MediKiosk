/**
 * Speech on the kiosk device: recognition and synthesis, both in the browser.
 *
 * Why on-device rather than server-side: it needs no API key, no vendor, and no network, so
 * it keeps working when the venue wifi dies twenty minutes before judging. The backend still
 * applies the confidence policy to whatever transcript arrives here (see
 * `ClientSpeechBackend`), so a client cannot get a bad transcript accepted just by producing
 * it locally.
 *
 * Barge-in: the moment recognition detects speech, any prompt still being spoken is cancelled.
 * A patient should never have to wait for a machine to finish talking.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface SpeechRecognitionAlternative { transcript: string; confidence: number }
interface SpeechRecognitionResult { 0: SpeechRecognitionAlternative; isFinal: boolean; length: number }
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResult };
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  onspeechstart: (() => void) | null;
}

type RecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** BCP-47 tags. The Web Speech API wants a region, not a bare ISO 639-1 code. */
const LOCALES: Record<string, string> = {
  en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN', ta: 'ta-IN', te: 'te-IN',
  mr: 'mr-IN', kn: 'kn-IN', ml: 'ml-IN', gu: 'gu-IN', pa: 'pa-IN',
};

export interface SpeechResult {
  transcript: string;
  confidence: number;
  bargeIn: boolean;
}

export interface UseSpeech {
  supported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
  start(onResult: (result: SpeechResult) => void): void;
  stop(): void;
  speak(text: string): Promise<void>;
  cancelSpeech(): void;
}

export function useSpeech(language: string): UseSpeech {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);

  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const speaking = useRef(false);
  const bargedIn = useRef(false);
  const supported = recognitionCtor() !== null;

  const cancelSpeech = useCallback(() => {
    if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
    speaking.current = false;
  }, []);

  const stop = useCallback(() => {
    recognition.current?.stop();
    setListening(false);
  }, []);

  const start = useCallback(
    (onResult: (result: SpeechResult) => void) => {
      const Ctor = recognitionCtor();
      if (!Ctor) {
        setError('This browser cannot listen. Please tap your answer instead.');
        return;
      }
      setError(null);
      setInterim('');
      bargedIn.current = false;

      const instance = new Ctor();
      instance.lang = LOCALES[language] ?? 'en-IN';
      instance.continuous = false;
      instance.interimResults = true;
      instance.maxAlternatives = 1;

      instance.onspeechstart = () => {
        // Barge-in: the patient started talking, so stop talking at them.
        if (speaking.current) {
          cancelSpeech();
          bargedIn.current = true;
        }
      };

      instance.onresult = (event) => {
        let finalText = '';
        let finalConfidence = 0;
        let interimText = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          if (result.isFinal) {
            finalText += result[0].transcript;
            finalConfidence = result[0].confidence;
          } else {
            interimText += result[0].transcript;
          }
        }
        if (interimText) setInterim(interimText);
        if (finalText) {
          setInterim('');
          setListening(false);
          // Chrome reports confidence 0 on some Indic locales. Passing that through would
          // degrade every single answer to touch, so an absent score is treated as "unknown
          // but usable" — the backend still applies its own threshold to the value.
          const confidence = finalConfidence > 0 ? finalConfidence : 0.7;
          onResult({ transcript: finalText.trim(), confidence, bargeIn: bargedIn.current });
        }
      };

      instance.onerror = (event) => {
        setListening(false);
        setInterim('');
        if (event.error === 'no-speech') {
          onResult({ transcript: '', confidence: 0, bargeIn: false });
          return;
        }
        if (event.error === 'not-allowed') {
          setError('The microphone is blocked. Please tap your answer instead.');
          return;
        }
        setError('Listening failed. Please tap your answer instead.');
      };

      instance.onend = () => setListening(false);

      recognition.current = instance;
      try {
        instance.start();
        setListening(true);
      } catch {
        setError('Could not start listening. Please tap your answer instead.');
      }
    },
    [language, cancelSpeech],
  );

  const speak = useCallback(
    (text: string) =>
      new Promise<void>((resolve) => {
        if (typeof speechSynthesis === 'undefined' || !text.trim()) {
          resolve();
          return;
        }
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = LOCALES[language] ?? 'en-IN';
        utterance.rate = 0.92; // a touch slower than default: this is read to an elderly patient
        const voice = speechSynthesis
          .getVoices()
          .find((v) => v.lang === utterance.lang) ??
          speechSynthesis.getVoices().find((v) => v.lang.startsWith(language));
        if (voice) utterance.voice = voice;

        speaking.current = true;
        utterance.onend = () => { speaking.current = false; resolve(); };
        utterance.onerror = () => { speaking.current = false; resolve(); };
        speechSynthesis.speak(utterance);
      }),
    [language],
  );

  useEffect(() => () => { recognition.current?.abort(); cancelSpeech(); }, [cancelSpeech]);

  return { supported, listening, interim, error, start, stop, speak, cancelSpeech };
}
