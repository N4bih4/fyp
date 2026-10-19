import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import vm from 'node:vm';

// Execute production helpers without a browser or microphone. Native speech
// recognition/TTS interruption still needs an actual Chrome microphone check.
const compiled = ts.transpileModule(readFileSync(new URL('./src/voice.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {} };
vm.runInNewContext(compiled, sandbox);
const { spokenReply, afterInterruption, isSpeechEcho, finishOnce } = sandbox.exports;

test('speech never reads long plans, paths, provider errors or action details', () => {
  for (const language of ['ur-PK', 'hi-IN', 'en-US']) {
    for (const status of ['completed', 'failed', 'awaiting_input', 'awaiting_approval', 'waiting_retry']) {
      const text = spokenReply({ status, error: 'PRIVATE_KEY', plan_note: 'private path '.repeat(300) }, language);
      assert.ok(text.length < 100);
      assert.ok(!text.includes('PRIVATE_KEY') && !text.includes('private path'));
    }
  }
});

test('interruption acknowledgements are not approval commands', () => {
  for (const heard of ['achha theek hai', 'اچھا ٹھیک ہے', 'अच्छा ठीक है', 'okay', 'stop speaking', 'ruko']) {
    assert.equal(afterInterruption(heard), '');
  }
  assert.equal(afterInterruption('achha theek hai volume down'), 'volume down');
  assert.equal(afterInterruption('اچھا ٹھیک ہے میوٹ پی سی'), 'میوٹ پی سی');
  assert.equal(afterInterruption('open settings'), 'open settings');
  assert.equal(afterInterruption('stopping application'), 'stopping application');
});

test('own spoken reply is ignored, a different user command is preserved', () => {
  assert.equal(isSpeechEcho('ہو گیا', 'ہو گیا۔'), true);
  assert.equal(isSpeechEcho('میوٹ پی سی', 'ہو گیا۔'), false);
  assert.equal(isSpeechEcho('', 'Done.'), false);
});

test('cancel, end and error release the speech queue exactly once', () => {
  let released = 0;
  const finish = finishOnce(() => released++);
  finish(); // interruption
  finish(); // delayed synthesis end
  finish(); // synthesis cancelled error
  assert.equal(released, 1);
});
