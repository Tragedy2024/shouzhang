#!/usr/bin/env node
// Project-owned, read-only supplement for external ID and delegated handlers.
// It does not modify or replace the official Premium audit and is not an E2E test.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const lineAt = (text, position) => text.slice(0, position).split('\n').length;
const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function attrs(raw) {
  const result = {};
  for (const match of raw.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
    result[match[1].toLowerCase()] = match[2] ?? match[3] ?? match[4] ?? '';
  }
  return result;
}

function literalButtons(html) {
  const stack = [], buttons = [];
  const voids = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  for (const token of html.matchAll(/<(\/?)([a-z][\w-]*)\b([^>]*?)>/gi)) {
    const name = token[2].toLowerCase();
    if (token[1]) {
      const index = stack.findLastIndex(entry => entry.name === name);
      if (index >= 0) stack.splice(index);
      continue;
    }
    const attributes = attrs(token[3]);
    if (name === 'button') buttons.push({ attributes, ancestors: stack.map(entry => ({ ...entry })), line: lineAt(html, token.index) });
    if (!voids.has(name) && !token[3].endsWith('/')) stack.push({ name, ...attributes });
  }
  return buttons;
}

function linkedScripts(html) {
  const scripts = [];
  for (const tag of html.matchAll(/<script\b([^>]*)>/gi)) {
    const src = attrs(tag[1]).src;
    if (!src) continue;
    if (!/^\/static\/[\w./-]+\.js$/.test(src) || src.includes('..')) throw new Error(`Unsupported script source: ${src}`);
    const relative = src.slice(1);
    scripts.push({ file: relative, text: fs.readFileSync(path.join(root, relative), 'utf8') });
  }
  return scripts;
}

function directProof(scripts, id, event = 'click') {
  if (!id) return null;
  const matcher = new RegExp(`(?:\\$|document\\.getElementById)\\(\\s*['"]${escape(id)}['"]\\s*\\)\\s*(?:\\?\\.)?\\.?addEventListener\\(\\s*['"]${event}['"]\\s*,`);
  for (const script of scripts) {
    const found = matcher.exec(script.text);
    if (found) return { kind: 'external-id-listener', owner: id, event, file: script.file, line: lineAt(script.text, found.index) };
  }
  return null;
}

function themeProof(scripts, id) {
  if (!id) return null;
  const install = new RegExp(`ZhilvjiUI\\.installTheme\\(\\s*['"](?:creator|hall)['"]\\s*,\\s*(?:\\$|document\\.getElementById)\\(\\s*['"]${escape(id)}['"]\\s*\\)`);
  const foundation = scripts.find(script => /function\s+installTheme\s*\(/.test(script.text) && /button\?\.addEventListener\(\s*['"]click['"]/.test(script.text));
  if (!foundation) return null;
  for (const script of scripts) {
    const match = install.exec(script.text);
    if (match) return { kind: 'shared-theme-listener', owner: 'ZhilvjiUI.installTheme', file: script.file,
      line: lineAt(script.text, match.index), foundation: foundation.file };
  }
  return null;
}

function delegatedProof(scripts, button) {
  const known = [
    ['data-style', 'styleGrid', '[data-style]', 'selectStyle'],
    ['data-tone', 'regenButtons', '[data-tone]', 'regenerate'],
    ['data-topic', 'hallTopics', 'button[data-topic]', 'setFilters'],
    ['data-topic', 'hallDetailTopics', 'button[data-topic]', 'setFilters']
  ];
  for (const [attribute, owner, selector, action] of known) {
    if (!(attribute in button.attributes) || !button.ancestors.some(ancestor => ancestor.id === owner)) continue;
    const direct = directProof(scripts, owner);
    if (!direct) continue;
    const script = scripts.find(item => item.file === direct.file);
    const handlerLine = script.text.split('\n')[direct.line - 1];
    if (!handlerLine.includes(selector) || !new RegExp(`\\b${action}\\s*\\(`).test(handlerLine)) continue;
    return { ...direct, kind: 'delegated-data-listener', selector, attribute, action };
  }
  return null;
}

function prove(scripts, button) {
  const a = button.attributes;
  if (a.onclick && a.onclick.trim()) return { kind: 'inline-handler' };
  if (a.type === 'reset') {
    const form = button.ancestors.findLast(entry => entry.name === 'form');
    if (form) return { kind: 'native-form-reset', owner: form.id || null };
  }
  if (!a.type || a.type === 'submit') {
    const form = a.form ? { id: a.form } : button.ancestors.findLast(entry => entry.name === 'form');
    const proof = form && directProof(scripts, form.id, 'submit');
    if (proof) return { ...proof, kind: 'external-form-submit' };
  }
  return directProof(scripts, a.id) || themeProof(scripts, a.id) || delegatedProof(scripts, button);
}

function check() {
  const records = [], errors = [];
  for (const name of fs.readdirSync(path.join(root, 'templates')).filter(name => name.endsWith('.html')).sort()) {
    const file = `templates/${name}`;
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    const scripts = linkedScripts(html);
    for (const button of literalButtons(html)) {
      const proof = prove(scripts, button);
      const record = { file, line: button.line, id: button.attributes.id || null,
        data: Object.fromEntries(Object.entries(button.attributes).filter(([key]) => key.startsWith('data-'))),
        type: button.attributes.type || 'submit', initiallyDisabled: 'disabled' in button.attributes, proof };
      records.push(record);
      if (!proof) errors.push({ rule: 'literal-button.unresolved-action', file, line: button.line, id: record.id, data: record.data });
    }
  }
  return { schemaVersion: 1, check: 'semanticBindings', passed: !errors.length,
    literalButtons: records.length, verifiedBindings: records.filter(record => record.proof).length,
    scope: 'All literal buttons in templates/*.html; only scripts actually loaded by each template are eligible evidence.',
    limits: 'Static ID/delegation evidence only. Generated buttons, handler semantics, keyboard, focus and actual navigation require the project state tests and browser checks. Official strict findings remain unchanged.',
    errors, buttons: records };
}

let report;
try { report = check(); }
catch (error) { report = { schemaVersion: 1, check: 'semanticBindings', passed: false, errors: [{ rule: 'configuration.unreadable', message: error.message }] }; }
const output = process.argv.indexOf('--output');
if (output >= 0) {
  const target = path.resolve(root, process.argv[output + 1] || '');
  const docsRoot = path.join(root, 'docs/frontend') + path.sep;
  if (!target.startsWith(docsRoot) || !target.endsWith('.json')) throw new Error('Report output must be a JSON file under docs/frontend.');
  fs.writeFileSync(target, JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.passed ? 0 : 1;
