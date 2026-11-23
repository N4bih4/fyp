// Wake word for hands-free listening: room noise, a fan, a video or music must not become commands.
// A sentence is a command only when it starts with the assistant's name ("Nabiha, open the FYP folder"); anything else is ignored.
//
// Speech-to-text writes a name the way it SOUNDED, in any accent and sometimes in another script: Nabiha -> Nabeeha, Nabiya, Naabiha, नबीहा, نبیحہ;
// Zara -> Sara, Zaara, Zahra, Jara, ज़ारा. So names are compared by SOUND, not by letters: both are turned into a sound key (vowels reduced to three
// classes, z/s/j alike, v/w alike, double letters and a silent h dropped, Devanagari and Urdu letters transliterated) and the keys must be close.
// The name may also be glued to the next word ("Nabihaopen chrome") or split ("Na biha open chrome"), may follow "hey/ok/oye", and counts at the end of
// the sentence too ("take a screenshot Nabiha"). Several names can be set, separated by a comma or slash ("Nabiha, Zara").

const clean = (value: string) =>
  value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{M}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim();

const OPENERS = new Set(['hey', 'hi', 'hello', 'ok', 'okay', 'oye', 'oy', 'arey', 'are', 'aye', 'ae', 'ay', 'o', 'sunno', 'suno', 'sun', 'सुनो', 'सुन', 'ऐ', 'अरे', 'ओए',
  'सुनिए', 'اے', 'سنو', 'او']);

// ---- transliteration of Devanagari and Urdu (names only: enough letters to compare a name by sound) ----
const DEVA_VOWELS: Record<string, string> = { 'अ': 'a', 'आ': 'a', 'इ': 'i', 'ई': 'i', 'उ': 'u', 'ऊ': 'u', 'ए': 'e', 'ऐ': 'e', 'ओ': 'o', 'औ': 'o', 'ऑ': 'o' };
const DEVA_MATRAS: Record<string, string> = { 'ा': 'a', 'ि': 'i', 'ी': 'i', 'ु': 'u', 'ू': 'u', 'े': 'e', 'ै': 'e', 'ो': 'o', 'ौ': 'o', 'ॉ': 'o' };
const DEVA_CONSONANTS: Record<string, string> = {
  'क': 'k', 'ख': 'k', 'ग': 'g', 'घ': 'g', 'च': 'c', 'छ': 'c', 'ज': 'z', 'झ': 'z', 'ट': 't', 'ठ': 't', 'ड': 'd', 'ढ': 'd', 'त': 't', 'थ': 't', 'द': 'd', 'ध': 'd',
  'न': 'n', 'प': 'p', 'फ': 'f', 'ब': 'b', 'भ': 'b', 'म': 'm', 'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 's', 'ष': 's', 'स': 's', 'ह': 'h', 'ण': 'n',
  'क़': 'k', 'ख़': 'k', 'ग़': 'g', 'ज़': 'z', 'ड़': 'r', 'ढ़': 'r', 'फ़': 'f',
};
const URDU_VOWELS: Record<string, string> = { 'ا': 'a', 'آ': 'a', 'ی': 'i', 'ے': 'i', 'ئ': 'i', 'ؤ': 'u', 'و': 'u' };
const URDU_CONSONANTS: Record<string, string> = {
  'ب': 'b', 'پ': 'p', 'ت': 't', 'ٹ': 't', 'ث': 's', 'ج': 'z', 'چ': 'c', 'ح': 'h', 'خ': 'k', 'د': 'd', 'ڈ': 'd', 'ذ': 'z', 'ر': 'r', 'ڑ': 'r', 'ز': 'z', 'ژ': 'z',
  'س': 's', 'ش': 's', 'ص': 's', 'ض': 'z', 'ط': 't', 'ظ': 'z', 'غ': 'g', 'ف': 'f', 'ق': 'k', 'ک': 'k', 'گ': 'g', 'ل': 'l', 'م': 'm', 'ن': 'n', 'ں': 'n', 'ہ': 'h',
  'ھ': '', 'ء': '', 'ع': '',
};

function transliterate(word: string): string {
  let out = '';
  let pendingA = false;       // Devanagari: a consonant carries an "a" unless a vowel sign or a virama follows
  const chars = Array.from(word.normalize('NFC').replace(/\u093c/g, ''));        // the nukta dot only refines the sound: dropped
  for (let i = 0; i < chars.length; i += 1) {
    const c = chars[i];
    if (DEVA_CONSONANTS[c] !== undefined) {
      if (pendingA) out += 'a';
      out += DEVA_CONSONANTS[c];
      pendingA = true;
    } else if (DEVA_MATRAS[c] !== undefined) {
      pendingA = false;
      out += DEVA_MATRAS[c];
    } else if (DEVA_VOWELS[c] !== undefined) {
      if (pendingA) out += 'a';
      pendingA = false;
      out += DEVA_VOWELS[c];
    } else if (c === '्') {
      pendingA = false;                                                        // virama: no vowel
    } else if (c === 'ं' || c === 'ँ' || c === '़') {
      // anusvara / chandrabindu / nukta alone: silent here
    } else if (URDU_VOWELS[c] !== undefined || URDU_CONSONANTS[c] !== undefined) {
      if (pendingA) { out += 'a'; pendingA = false; }
      const letter = URDU_VOWELS[c] ?? URDU_CONSONANTS[c];
      const previousIsConsonant = out.length > 0 && !'aeiou'.includes(out[out.length - 1]);
      const isConsonant = URDU_CONSONANTS[c] !== undefined && letter !== '';
      if (isConsonant && previousIsConsonant) out += 'a';                     // Urdu writes no short vowels: put one between two consonants
      out += letter;
    } else {
      if (pendingA) { out += 'a'; pendingA = false; }
      out += c;
    }
  }
  if (pendingA && out.length > 0 && !'aeiou'.includes(out[out.length - 1])) {
    // a Devanagari name ends in its last consonant unless a matra followed; the inherent "a" at the end is not pronounced
  }
  return out;
}

/** What a name sounds like, as a short key; two spellings of one name end up with (nearly) the same key. */
export function soundKey(word: string): string {
  let s = transliterate(clean(word).replace(/\s+/g, ''))
    .replace(/[^a-z]/g, '');
  s = s.replace(/ph/g, 'f').replace(/kh/g, 'k').replace(/gh/g, 'g').replace(/sh/g, 's').replace(/ch/g, 'c').replace(/th/g, 't').replace(/dh/g, 'd').replace(/bh/g, 'b')
    .replace(/ck/g, 'k').replace(/q/g, 'k').replace(/x/g, 'ks');
  s = s.replace(/[wv]/g, 'v').replace(/[zj]/g, 'z').replace(/s/g, 'z').replace(/c/g, 'k');                 // sound-alike consonants
  s = s.replace(/y(?=[aeiou]|$)/g, 'i').replace(/y/g, 'i');                                                 // y is the vowel i
  s = s.replace(/([aeiou])h/g, '$1').replace(/h$/g, '');                                                    // a silent h: zahra, nabiha(h)
  s = s.replace(/[ei]/g, 'i').replace(/[ou]/g, 'u');                                                        // vowels: a / i (e,i) / u (o,u)
  s = s.replace(/(.)\1+/g, '$1');                                                                           // double letters and long vowels
  return s;
}

function editDistance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    let diagonal = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const above = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, diagonal + (a[i - 1] === b[j - 1] ? 0 : 1));
      diagonal = above;
    }
  }
  return row[b.length];
}

const consonants = (key: string) => key.replace(/[aiu]/g, '');

/** True when one spoken word is (a spelling or pronunciation of) the wake word. */
export function isWakeWord(word: string, wake: string): boolean {
  const heard = clean(word);
  const target = clean(wake);
  if (!heard || !target) return false;
  if (heard === target) return true;
  const a = soundKey(heard);
  const b = soundKey(target);
  if (a.length < 2 || b.length < 2) return false;
  if (a === b) return true;
  const longest = Math.max(a.length, b.length);
  const limit = longest >= 7 ? 2 : 1;
  const distance = editDistance(a, b);
  if (distance <= limit && Math.min(a.length, b.length) >= 3) return true;
  // the same consonants in the same order with other vowels ("Nabeeha" / "Nebuha"): still the same name
  return consonants(a).length >= 2 && consonants(a) === consonants(b) && distance <= 2;
}

/** The wake words that were set: "Nabiha, Zara" -> ["Nabiha", "Zara"] (at most five). */
export function wakeWords(wake: string): string[] {
  return wake.split(/[,/|;،]|\s+(?:or|ya|ye|aur)\s+/i).map((w) => w.trim()).filter((w) => clean(w)).slice(0, 5);
}

const stripEdges = (word: string) => word.replace(/^[,.!?;:।۔"'“”()]+|[,.!?;:।۔"'“”()]+$/g, '');
const tidy = (text: string) => text.replace(/^[,.!?;:।۔\s]+/, '').trim();

/** The text after the name if `words[i]` (alone, glued to the next word or split in two) is the name; null otherwise. */
function afterName(words: string[], i: number, wake: string): string | null {
  const word = stripEdges(words[i]);
  if (isWakeWord(word, wake)) return tidy(words.slice(i + 1).join(' '));
  // split in two: "Na biha open chrome"
  if (i + 1 < words.length && isWakeWord(stripEdges(words[i]) + stripEdges(words[i + 1]), wake) && stripEdges(words[i]).length >= 2) return tidy(words.slice(i + 2).join(' '));
  // glued to the next word: "Nabihaopen chrome". The exact name first, then the prefix whose sound is closest to the name.
  const target = clean(wake).replace(/\s+/g, '');
  const lowered = clean(word).replace(/\s+/g, '');
  if (lowered.length > target.length && lowered.startsWith(target)) return tidy([word.slice(target.length), ...words.slice(i + 1)].join(' '));
  if (word.length > target.length + 1) {
    const want = soundKey(wake);
    let best = -1;
    let bestDistance = 99;
    for (let length = Math.max(3, target.length - 1); length <= Math.min(word.length - 1, target.length + 2); length += 1) {
      const head = word.slice(0, length);
      if (!isWakeWord(head, wake)) continue;
      const distance = editDistance(soundKey(head), want);
      if (distance < bestDistance) { best = length; bestDistance = distance; }
    }
    if (best > 0) return tidy([word.slice(best), ...words.slice(i + 1)].join(' '));
  }
  return null;
}

/**
 * The command after the wake word ("nabiha open fyp folder" -> "open fyp folder"), "" when only the name was said, or null when the sentence was
 * not addressed to the assistant. With no wake word configured everything counts as addressed.
 */
export function stripWakeWord(heard: string, wake: string): string | null {
  const first = stripOnce(heard, wake);
  if (first === null || !first) return first;
  return stripOnce(first, wake) ?? first;                  // the name said twice ("Nabiha, Nabiha, open chrome") is still one name
}

function stripOnce(heard: string, wake: string): string | null {
  const text = heard.trim();
  const names = wakeWords(wake);
  if (names.length === 0) return text;
  const words = text.split(/\s+/).filter(Boolean);
  for (const name of names) {
    for (let i = 0; i < Math.min(words.length, 4); i += 1) {
      if (!words.slice(0, i).map(clean).every((w) => OPENERS.has(w))) break;
      const rest = afterName(words, i, name);
      if (rest !== null) return rest;
    }
  }
  // "take a screenshot, Nabiha": the name at the END counts too (speech-to-text often garbles the first words but keeps the name).
  if (words.length >= 3) {
    for (const name of names) {
      if (isWakeWord(stripEdges(words[words.length - 1]), name)) return words.slice(0, -1).join(' ').replace(/[,.!?;:।۔\s]+$/, '').trim();
    }
  }
  return null;
}
