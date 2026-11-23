import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import vm from 'node:vm';

const compiled = ts.transpileModule(readFileSync(new URL('./src/speech/vad.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {}, Float32Array, Uint8Array, ArrayBuffer, DataView, Math };
vm.runInNewContext(compiled, sandbox);
const { VadSegmenter, rms, downsample, encodeWav, DEFAULT_VAD, nextNoiseFloor, adaptiveThreshold } = sandbox.exports;

const run = (vad, levels, frameMs = 20) => levels.map((l) => vad.feed(l, frameMs)).filter(Boolean);

test('speech start then end after the configured silence', () => {
  const vad = new VadSegmenter(DEFAULT_VAD);
  const loud = Array(20).fill(0.1); // 400 ms
  const quiet = Array(40).fill(0.001); // 800 ms
  assert.deepEqual(run(vad, [...loud, ...quiet]), ['speech_start', 'speech_end']);
});

test('a short click is not speech', () => {
  const vad = new VadSegmenter(DEFAULT_VAD);
  assert.deepEqual(run(vad, [0.2, 0.2, ...Array(60).fill(0)]), []);
});

test('a pause shorter than the end silence does not split a sentence', () => {
  const vad = new VadSegmenter(DEFAULT_VAD);
  const events = run(vad, [...Array(20).fill(0.1), ...Array(20).fill(0), ...Array(20).fill(0.1), ...Array(40).fill(0)]);
  assert.deepEqual(events, ['speech_start', 'speech_end']);
});

test('a higher threshold ignores quiet leakage of the assistant voice', () => {
  const vad = new VadSegmenter({ ...DEFAULT_VAD, threshold: DEFAULT_VAD.threshold * 2.2 });
  assert.deepEqual(run(vad, Array(50).fill(0.03)), []);
});

test('rms of silence is 0 and of a full-scale square wave is 1', () => {
  assert.equal(rms(new Float32Array(10)), 0);
  assert.equal(rms(new Float32Array(10).fill(1)), 1);
  assert.equal(rms(new Float32Array(0)), 0);
});

test('downsample 48k to 16k keeps one third of the samples', () => {
  assert.equal(downsample(new Float32Array(4800), 48000).length, 1600);
  const same = new Float32Array(10);
  assert.equal(downsample(same, 16000), same);
});

test('encodeWav writes a valid 16-bit mono header and clamps samples', () => {
  const wav = encodeWav(new Float32Array([0, 1, -1, 2]), 16000);
  const text = (a, b) => String.fromCharCode(...wav.slice(a, b));
  const view = new DataView(wav.buffer);
  assert.equal(text(0, 4), 'RIFF');
  assert.equal(text(8, 12), 'WAVE');
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint32(40, true), 8);
  assert.equal(wav.length, 44 + 8);
  assert.equal(view.getInt16(46, true), 32767);
  assert.equal(view.getInt16(48, true), -32768);
  assert.equal(view.getInt16(50, true), 32767);
});

test('a natural pause after the name does not split the sentence in two', () => {
  const vad = new VadSegmenter(DEFAULT_VAD);
  const name = Array(20).fill(0.1);            // "Nabiha"            400 ms
  const pause = Array(30).fill(0.0005);        // a breath            600 ms (it was cut at 450 ms before)
  const command = Array(40).fill(0.1);         // "open the fyp folder" 800 ms
  const end = Array(45).fill(0.0005);
  assert.deepEqual(run(vad, [...name, ...pause, ...command, ...end]), ['speech_start', 'speech_end']);
});

test('a sentence trailing off quietly is not cut at its tail', () => {
  const vad = new VadSegmenter(DEFAULT_VAD);
  const tail = Array(60).fill(0.016);          // above 80% of the threshold: still speech
  assert.deepEqual(run(vad, [...Array(20).fill(0.1), ...tail]), ['speech_start']);
  assert.deepEqual(run(vad, Array(40).fill(0.001)), ['speech_end']);
});

test('a soft first syllable starts the recording (120 ms is enough, a click is not)', () => {
  const vad = new VadSegmenter(DEFAULT_VAD);
  assert.deepEqual(run(vad, [0.05, 0.05, 0.05, 0.05, 0.05, 0.05]), ['speech_start']);
  assert.deepEqual(run(new VadSegmenter(DEFAULT_VAD), [0.2, 0.2, ...Array(60).fill(0)]), []);
});

test('quiet speech never pushes the noise floor (and so the threshold) up', () => {
  let floor = 0.002;
  for (let i = 0; i < 2000; i += 1) floor = nextNoiseFloor(floor, 0.03, adaptiveThreshold(floor), false);   // 40 s of soft speech that missed the detector
  assert.ok(floor <= 0.002 + 1e-9, String(floor));
  assert.ok(Math.abs(nextNoiseFloor(0.01, 0.004, 0.03, false) - 0.0094) < 1e-9);                            // follows quiet moments down (gradually)
  assert.equal(nextNoiseFloor(0.01, 0.5, 0.03, true), 0.01);                                                // frozen while speaking
});

test('the threshold follows a noisy room but never gets so high that talking is missed', () => {
  assert.equal(adaptiveThreshold(0), 0.010);
  assert.ok(Math.abs(adaptiveThreshold(0.004) - 0.012) < 1e-9);
  assert.equal(adaptiveThreshold(0.5), 0.04);
});