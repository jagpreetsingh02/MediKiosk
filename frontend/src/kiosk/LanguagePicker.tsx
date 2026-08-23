/**
 * The first screen. No text the patient must read to get past it — every option is written in
 * its own script, so someone who reads only Tamil sees தமிழ் and can press it.
 */
import { useEffect, useState } from 'react';
import { api } from '../shared/api';

const NATIVE: Record<string, string> = {
  en: 'English', hi: 'हिन्दी', bn: 'বাংলা', ta: 'தமிழ்', te: 'తెలుగు',
  mr: 'मराठी', kn: 'ಕನ್ನಡ', ml: 'മലയാളം', gu: 'ગુજરાતી', pa: 'ਪੰਜਾਬੀ',
};

/** Which languages have a full translated question set. The rest fall back to English, and
 *  we say so rather than letting the patient discover it three questions in. */
const FULLY_TRANSLATED = new Set(['en', 'hi']);

interface Props {
  onPick: (language: string) => void;
}

export function LanguagePicker({ onPick }: Props): JSX.Element {
  const [languages, setLanguages] = useState<{ code: string; name: string }[]>([]);

  useEffect(() => {
    api
      .languages()
      .then((response) => setLanguages(response.languages))
      .catch(() => setLanguages(Object.keys(NATIVE).map((code) => ({ code, name: NATIVE[code] }))));
  }, []);

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">भाषा चुनिए · Choose your language</h1>
      <p className="kiosk-lead">
        अपनी भाषा दबाइए · Touch your language
      </p>
      <div className="language-grid">
        {languages.map((language) => (
          <button
            key={language.code}
            type="button"
            className="language-option"
            onClick={() => onPick(language.code)}
            lang={language.code}
          >
            {NATIVE[language.code] ?? language.name}
            {!FULLY_TRANSLATED.has(language.code) && (
              <small>questions shown in English</small>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
