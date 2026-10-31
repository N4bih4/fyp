import { useState } from 'react';
import type { Persona } from '../api';
import { useFocusTrap } from './useFocusTrap';

interface OnboardingProps {
  persona: Persona;
  micSupported: boolean;
  onFinish: (language: Persona['language'], startVoice: boolean) => void;
}

const EXAMPLE: Record<Persona['language'], string> = {
  'ur-PK': 'Documents mein Demo naam ka folder banao',
  'hi-IN': 'Documents mein Demo naam ka folder banao',
  'en-US': 'Create a folder called Demo in Documents',
  'en-GB': 'Create a folder called Demo in Documents',
};

/** First run: language, microphone, and one guided command, in three short steps. */
export function Onboarding({ persona, micSupported, onFinish }: OnboardingProps) {
  const [step, setStep] = useState(0);
  const [language, setLanguage] = useState<Persona['language']>(persona.language);
  const ref = useFocusTrap<HTMLElement>(true, () => onFinish(language, false));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
      <section ref={ref} role="dialog" aria-modal="true" aria-labelledby="onboarding-title" data-testid="onboarding"
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <p className="text-xs font-semibold text-slate-500">Step {step + 1} of 3</p>
        {step === 0 && (
          <>
            <h2 id="onboarding-title" className="mt-1 text-xl font-semibold">Welcome to {persona.name}</h2>
            <p className="mt-2 text-sm text-slate-600">
              Speak or type what you want done on this PC. Anything that changes files or settings is shown to you first
              and runs only after you approve it.
            </p>
            <label htmlFor="onboarding-language" className="mt-4 block text-sm font-medium">Language you will speak</label>
            <select id="onboarding-language" value={language} onChange={(e) => setLanguage(e.target.value as Persona['language'])}
              className="mt-1 w-full rounded border p-2">
              <option value="ur-PK">Urdu / Roman Urdu</option>
              <option value="hi-IN">Hindi</option>
              <option value="en-US">English</option>
            </select>
          </>
        )}
        {step === 1 && (
          <>
            <h2 id="onboarding-title" className="mt-1 text-xl font-semibold">Microphone</h2>
            <p className="mt-2 text-sm text-slate-600">
              {micSupported
                ? 'When you press the orb (or Ctrl+Space) your browser will ask for microphone permission once. Choose Allow.'
                : 'Voice input is not available in this browser. You can still type every command.'}
            </p>
          </>
        )}
        {step === 2 && (
          <>
            <h2 id="onboarding-title" className="mt-1 text-xl font-semibold">Try one command</h2>
            <p className="mt-2 text-sm text-slate-600">Press <strong>Start</strong>, then say:</p>
            <p className="mt-2 rounded-lg bg-indigo-50 p-3 font-medium text-indigo-900" data-testid="onboarding-example">“{EXAMPLE[language]}”</p>
            <p className="mt-2 text-sm text-slate-600">A card shows what will happen. Press <strong>Approve</strong> and watch it get checked.</p>
          </>
        )}
        <div className="mt-6 flex justify-between gap-2">
          <button type="button" onClick={() => onFinish(language, false)} className="rounded px-3 py-2 text-sm text-slate-600 underline">
            Skip
          </button>
          {step < 2 ? (
            <button type="button" data-autofocus onClick={() => setStep(step + 1)} className="rounded-lg bg-blue-700 px-4 py-2 font-semibold text-white">
              Next
            </button>
          ) : (
            <button type="button" data-autofocus onClick={() => onFinish(language, micSupported)} className="rounded-lg bg-emerald-700 px-4 py-2 font-semibold text-white">
              {micSupported ? 'Start' : 'Done'}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
