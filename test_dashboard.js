'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const engine = require('./browser-engine.js');
const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');

for (const name of ['dashboard.template.html', 'nzoth-lab.html', 'docs/index.html']) {
  const html = read(name);
  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  assert.equal(scripts.length, 2, `${name}: expected two inline scripts`);
  scripts.forEach((source, i) => new vm.Script(source, {filename: `${name}:script${i}`}));

  if (name === 'dashboard.template.html') {
    let destination;
    const context = vm.createContext({window: {location: {replace(url) {destination = url;}}}});
    scripts.forEach(source => vm.runInContext(source, context));
    assert.equal(destination, 'nzoth-lab.html');
  } else {
    assert(!html.includes('/*__'), `${name}: unresolved build marker`);
    const stats = JSON.parse(html.match(/const STATS=(.*);/)[1]);
    assert.equal(Object.keys(stats).length, 10);
    Object.values(stats).forEach(result => assert.equal(result.n, 200000));
    for (const side of ['first', 'second']) {
      const combo = stats[`combo_${side}_empty`];
      assert.equal(combo.mulligan, 'combo');
      assert.equal(combo.second, side === 'second');
      assert.equal(combo.enemy_target, false);
    }
  }
}

assert.equal(read('docs/index.html'), read('nzoth-lab.html'));
assert(fs.existsSync(path.join(__dirname, 'docs', '.nojekyll')));

const baseline = JSON.parse(read('browser-parity-cases.json'));
const comboCases = JSON.parse(read('browser-combo-parity-cases.json'));
assert.equal(baseline.length, 1232);
assert.equal(comboCases.length, 308);
const cases = [...baseline, ...comboCases];
for (const test of cases) {
  const replay = engine.simulate(test.seed, {
    second: test.second,
    enemy: test.mode === 'target',
    policy: ['cheap', 'combo'].includes(test.mode) ? test.mode : 'guide',
    naturalOnly: test.mode === 'natural'
  });
  const label = `${test.seed}/${test.mode}/${test.second ? 'second' : 'first'}`;
  assert.equal(replay.turn, test.turn, `${label}: launch turn`);
  assert.equal(replay.burned, test.burned, `${label}: burned cards`);
  if (test.mode === 'combo') {
    const first = replay.events[0];
    const names = cards => cards.map(card => engine.names[card.kind]);
    assert.deepEqual(names(first.opening), test.opening, `${label}: original opening`);
    assert.deepEqual(names(first.rejected), test.rejected, `${label}: rejected opening`);
    assert.deepEqual(names(first.state.hand), test.hand_after_mulligan, `${label}: mulligan hand`);
    const paired = first.opening.some(card => card.kind === 6 || card.kind === 7);
    for (const prep of first.opening.filter(card => card.kind === 4)) {
      assert.equal(!first.rejected.some(card => card.uid === prep.uid), paired, `${label}: Prep pair rule`);
    }
  }
  const ends = replay.events.filter(event => event.type === 'end').map(event => ({
    turn: event.state.turn,
    mana: event.state.mana,
    // Python stores the bonus Coin under the same kind as Counterfeit Coin.
    hand: event.state.hand.map(card => engine.names[card.kind]),
    ice: event.state.ice_discount
  }));
  assert.deepEqual(ends, test.ends, `${label}: end-of-turn states`);
}
console.log('PASS: template redirect, script syntax, 10 x 200000 datasets, Pages output and 1540 replay parity cases.');
