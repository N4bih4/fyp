import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import vm from 'node:vm';

const compiled = ts.transpileModule(readFileSync(new URL('./src/wakeWord.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {} };
vm.runInNewContext(compiled, sandbox);
const { stripWakeWord, isWakeWord, soundKey, wakeWords } = sandbox.exports;

test('a command is accepted only after the name, and the name is removed', () => {
  assert.equal(stripWakeWord('Zara open the FYP folder', 'Zara'), 'open the FYP folder');
  assert.equal(stripWakeWord('Zara, take a screenshot.', 'Zara'), 'take a screenshot.');
  assert.equal(stripWakeWord('hey zara volume kam karo', 'zara'), 'volume kam karo');
  assert.equal(stripWakeWord('ok Zara, notepad kholo', 'zara'), 'notepad kholo');
});

test('noise, music, a fan or a video is never a command', () => {
  for (const heard of ['Screenshot', 'Duit! Downs.', 'Play Doremon!', 'open the FYP folder', 'thank you for watching', 'take a screenshot please']) {
    assert.equal(stripWakeWord(heard, 'Zara'), null, heard);
  }
});

test('the name alone gives an empty command (the app then listens for the next sentence)', () => {
  assert.equal(stripWakeWord('Zara', 'Zara'), '');
  assert.equal(stripWakeWord('Zara.', 'Zara'), '');
});

test('speech-to-text spellings of the name are accepted', () => {
  for (const spelling of ['Sara', 'Zaara', 'Zahra', 'Jara', 'ज़ारा', 'सारा', 'زارا']) {
    assert.equal(stripWakeWord(`${spelling} chrome kholo`, 'Zara'), 'chrome kholo', spelling);
  }
});

test('a different name or a name later in the sentence does not wake it', () => {
  assert.equal(stripWakeWord('Tom open chrome', 'Zara'), null);
  assert.equal(stripWakeWord('please you can open zara chrome', 'Zara'), null);
  assert.equal(isWakeWord('lara', 'zara'), true);          // one letter off is tolerated for a 4-letter name
  assert.equal(isWakeWord('arman', 'zara'), false);
});

test('with no wake word set, everything counts as addressed', () => {
  assert.equal(stripWakeWord('open chrome', ''), 'open chrome');
  assert.equal(stripWakeWord('open chrome', '   '), 'open chrome');
});

test('the name at the end of the sentence also counts', () => {
  assert.equal(stripWakeWord('Roll, Xcreenshot, Zara', 'Zara'), 'Roll, Xcreenshot');
  assert.equal(stripWakeWord('take a screenshot Zara.', 'Zara'), 'take a screenshot');
  assert.equal(stripWakeWord('thank you for watching', 'Zara'), null);
  assert.equal(stripWakeWord('screenshot Zara', 'Zara'), null);        // two words only: too little to trust
});


test('Nabiha is heard in any accent, spelling or script', () => {
  for (const spelling of ['Nabiha', 'nabiha', 'Nabeeha', 'Nabiya', 'Naabiha', 'Nabihah', 'Nabeha', 'Nabia', 'Nabihaa', 'Nabiah', 'नबीहा', 'नबिहा', 'नबीहा', 'نبیحہ', 'نبیہا', 'Nabila']) {
    assert.equal(stripWakeWord(`${spelling} open the fyp folder`, 'Nabiha'), 'open the fyp folder', spelling);
  }
});

test('Zara is heard in any accent, spelling or script', () => {
  for (const spelling of ['Zara', 'Zaara', 'Zahra', 'Zarah', 'Sara', 'Jara', 'Dara', 'Zera', 'ज़ारा', 'जारा', 'सारा', 'زارا', 'سارا', 'زہرا']) {
    assert.equal(stripWakeWord(`${spelling} chrome kholo`, 'Zara'), 'chrome kholo', spelling);
  }
});

test('any other name works the same way, and several names can be set', () => {
  assert.equal(stripWakeWord('Aria close notepad', 'Aria'), 'close notepad');
  assert.equal(stripWakeWord('Arya close notepad', 'Aria'), 'close notepad');
  assert.equal(stripWakeWord('Maria close notepad', 'Maria'), 'close notepad');
  assert.equal(JSON.stringify(wakeWords('Nabiha, Zara')), '["Nabiha","Zara"]');
  assert.equal(JSON.stringify(wakeWords('Nabiha / Zara or Aria')), '["Nabiha","Zara","Aria"]');
  assert.equal(stripWakeWord('Zara open gmail', 'Nabiha, Zara'), 'open gmail');
  assert.equal(stripWakeWord('Nabeeha open gmail', 'Nabiha, Zara'), 'open gmail');
});

test('the name glued to the next word, split in two, repeated, or after hey/ok is still the name', () => {
  assert.equal(stripWakeWord('Nabihaopen chrome', 'Nabiha'), 'open chrome');
  assert.equal(stripWakeWord('Na biha open chrome', 'Nabiha'), 'open chrome');
  assert.equal(stripWakeWord('Hey Nabiha, open chrome', 'Nabiha'), 'open chrome');
  assert.equal(stripWakeWord('oye nabeeha chrome kholo', 'Nabiha'), 'chrome kholo');
  assert.equal(stripWakeWord('Nabiha Nabiha open chrome', 'Nabiha'), 'open chrome');
});

test('the name at the end of the sentence counts, in any spelling', () => {
  assert.equal(stripWakeWord('take a screenshot Nabeeha', 'Nabiha'), 'take a screenshot');
  assert.equal(stripWakeWord('chrome kholo Zaara.', 'Zara'), 'chrome kholo');
});

test('sentences without the name stay ignored, whatever else is said', () => {
  for (const heard of ['open the fyp folder', 'Screenshot', 'Duit! Downs.', 'thank you for watching', 'play doremon', 'Tom open chrome', 'Arman close notepad',
    'Nasir open gmail', 'Hamza open chrome', 'the weather is nice today', 'subscribe to the channel', 'ho gaya bhai chalo']) {
    assert.equal(stripWakeWord(heard, 'Nabiha'), null, heard);
  }
  for (const heard of ['open the fyp folder', 'Screenshot', 'Tom open chrome', 'Arman close notepad', 'Nabiha open chrome']) {
    assert.equal(stripWakeWord(heard, 'Zara'), null, heard);
  }
});

test('the sound key makes spellings of one name equal', () => {
  assert.equal(soundKey('Nabiha'), soundKey('Nabeeha'));
  assert.equal(soundKey('Nabiha'), soundKey('नबीहा'));
  assert.equal(soundKey('Nabiha'), soundKey('نبیحہ'));
  assert.equal(soundKey('Zara'), soundKey('Zahra'));
  assert.equal(soundKey('Zara'), soundKey('ज़ारा'));
  assert.notEqual(soundKey('Nabiha'), soundKey('Zara'));
});
